# Error Handling

Every error on the mesh is structured. No raw tracebacks, no mystery strings. Each categorical error has a dedicated `MeshError` subclass — callers can branch on type instead of inspecting strings.

```python
from openagentmesh import AgentMesh, InvalidInput, HandlerError, MeshError

mesh = AgentMesh("nats://localhost:4222")

async with mesh:
    try:
        result = await mesh.call("summarizer", {"text": 42})  # wrong type
    except InvalidInput as e:
        # Caller fault: payload didn't match the agent's input schema.
        # Fix the request, don't retry as-is.
        print(e.code)              # "invalid_input"
        print(e.details["errors"]) # pydantic-style error list
    except HandlerError as e:
        # Provider fault: the agent's handler raised. Retry, fall back, or alert.
        print(e.code)              # "handler_error"
    except MeshError as e:
        # Anything else categorically.
        print(e.code, e.message)
```

## Error Envelope

When an agent returns `X-Mesh-Status: error`, the response body is always this shape (ADR-0001):

```json
{
  "code": "invalid_input",
  "message": "Input failed validation for agent 'summarizer'",
  "agent": "summarizer",
  "request_id": "a1b2c3d4",
  "details": {
    "errors": [
      {"loc": ["text"], "msg": "Input should be a valid string", "type": "string_type"}
    ]
  }
}
```

The `details` field carries category-specific context (pydantic errors for `invalid_input`, sequence numbers for `chunk_sequence_error`, etc.).

## The Taxonomy

Every error code maps to a dedicated `MeshError` subclass (ADR-0057). The class is the local Python convenience; the code is the cross-language wire identifier.

| Code | Class | Raised when | What the caller should do |
|------|-------|-------------|---------------------------|
| `invalid_input` | `InvalidInput` | Caller's payload failed schema validation | Fix the payload; do not retry as-is |
| `handler_error` | `HandlerError` | Handler body raised a non-`MeshError` exception | Treat as opaque agent failure; retry/fallback |
| `invocation_mismatch` | `InvocationMismatch` | Wrong verb (`call`/`stream`/`send`) for the agent's shape | Use the correct verb |
| `not_found` | `NotFound` | Agent missing from registry/catalog, or nobody serving the subject | Check the name; verify the agent is running |
| `not_available` | `NotAvailable` | Agent in the catalog but offline — a [lifecycle gate](lifecycle.md) closed it (or it is draining) | Retry when its condition changes |
| `connection_failed` | `ConnectionFailed` | Initial NATS connect or reconnect failed | Check transport / URL |
| `connection_denied` | `ConnectionDenied` | Connection or operation rejected by mesh permissions ([security](security.md)) | Check credentials and role grants |
| `timeout` | `MeshTimeout` | No reply within the deadline | Retry with backoff or raise SLA |
| `agent_died` | `AgentDied` | The agent left the mesh during your in-flight request | Retry against a replacement; see [Liveness](liveness.md) |
| `chunk_sequence_error` | `ChunkSequenceError` | Stream chunks arrived out of order | Treat as transport bug |
| `kv_key_exists` | `KVKeyExists` | `mesh.kv.create()` (put-if-absent) collided with an existing key | Normal outcome when losing a claim race; catch and move on |

All subclasses inherit from `MeshError`. `except MeshError:` still catches everything when you don't want to discriminate.

### `InvalidInput` vs `HandlerError`

The most important distinction. They sound similar but tell you different things:

- **`InvalidInput`** is raised *before* the handler runs. The caller sent a payload that doesn't conform to the agent's declared input schema. The agent code is fine; the caller's request is broken. Re-sending the same payload will fail the same way.
- **`HandlerError`** is raised *during* handler execution. The payload was valid; the handler ran and threw. The caller did nothing wrong. Retrying might help (transient bug), or it might not (deterministic crash).

Treating both as the same thing is the trap this taxonomy avoids.

```python
try:
    summary = await mesh.call("summarizer", payload)
except InvalidInput as e:
    return JSONResponse({"error": "bad request", "issues": e.details["errors"]}, status_code=400)
except HandlerError as e:
    metrics.incr("summarizer.handler_error")
    return JSONResponse({"error": "service degraded"}, status_code=502)
except MeshTimeout:
    return JSONResponse({"error": "service unreachable"}, status_code=504)
```

### Pydantic naming

`openagentmesh.InvalidInput` deliberately does not collide with `pydantic.ValidationError`. You can import both in the same file without aliasing. Internally, the SDK catches `pydantic.ValidationError` raised during input deserialization and re-raises it as `InvalidInput`, copying the pydantic error list into `details["errors"]`.

## Pre-flight Capability Checks

Invocation mismatches are caught before the request leaves the SDK (ADR-0047). On connect, the catalog cache is seeded from the current KV snapshot, so the check works from the first invocation even for pure-caller processes with no local agents.

```python
from openagentmesh import InvocationMismatch

try:
    result = await mesh.call("price-feed", {"symbol": "AAPL"})
except InvocationMismatch as e:
    print(e.message)
    # "Agent 'price-feed' is a publisher and cannot be called. Subscribe to its events instead"
```

| Verb | Target shape | Message |
|------|-------------|---------|
| `call()` on Publisher | invocable=false, streaming=true | "is a publisher and cannot be called. Subscribe to its events instead" |
| `call()` on Source-only | invocable=false, streaming=false | "is a background task and cannot be called" |
| `call()` on Streamer | invocable=true, streaming=true | "is streaming-only. Use stream() instead" |
| `stream()` on Responder | invocable=true, streaming=false | "does not support streaming. Use call() instead" |
| `stream()` on Publisher | invocable=false, streaming=true | "is a publisher and cannot be streamed. Subscribe to its events instead" |
| `send()` on Publisher | invocable=false, streaming=true | "is a publisher and cannot be sent to. Subscribe to its events instead" |

## How Errors Propagate

The mesh catches exceptions so callers don't have to guess what went wrong.

### Non-streaming invocation

1. The caller sends a request via `mesh.call()`.
2. Capabilities are checked before the request is sent. If the agent is non-invocable or streaming-only, `InvocationMismatch` is raised locally (no round trip).
3. On the agent side, the runtime validates the payload against the input schema. If validation fails, the request never reaches the handler — `InvalidInput` is sent back.
4. If the handler runs and raises a `MeshError` subclass (e.g. a domain-specific `InvalidInput` from inside the handler), that subclass is forwarded as-is.
5. If the handler raises any other exception, the mesh wraps it as `HandlerError` and returns it to the caller.
6. The caller receives a structured subclass, not a raw Python exception. Wire-side reconstruction preserves the subclass identity (a remote `InvalidInput` is caught locally as `except InvalidInput`).

### Streaming invocation

1. The caller sends a request via `mesh.stream()`.
2. Capabilities are checked before the request is sent. If the target agent is non-streaming or non-invocable, `InvocationMismatch` is raised locally (no round trip).
3. Input validation runs the same way as for `call()`. A bad payload terminates the stream with `InvalidInput` before any chunks are sent.
4. If the handler's async generator raises mid-stream (after yielding some chunks), the error is published to the stream subject with `X-Mesh-Stream-End: true`. The caller receives all chunks up to the failure, then gets the matching `MeshError` subclass.

Handler authors don't need to catch their own errors for the caller's sake. The mesh does it. You can still raise specific `MeshError` subclasses inside a handler to control the surfaced error type — they propagate without being wrapped.

## Dead-Letter Subject

Every error is also published to the agent's dead-letter subject:

```
mesh.errors.{name}
```

(`name` is the full dotted identifier — ADR-0049.)

Subscribe to this subject for monitoring, alerting, or debugging. The payload is the same error envelope.

```python
async def on_error(msg):
    error = json.loads(msg.data)
    logger.warning(f"{error['agent']}: {error['code']} - {error['message']}")

await nc.subscribe("mesh.errors.nlp.summarizer", cb=on_error)
```

This is a passive stream. It doesn't affect the caller's response.

## Failure Modes

There are four ways an agent can leave the mesh. Each produces a different caller experience.

| Mode | Cause | What the caller sees | Detection speed |
|------|-------|---------------------|-----------------|
| Graceful shutdown | Context manager exit or process interrupt | `NotFound` on next call (agent already deregistered); `AgentDied` if a request was in flight | Instant |
| Bad input | Caller sent a payload that fails the schema | `InvalidInput` with pydantic error list in `details` | Instant (no handler call) |
| Handler exception | Bug in handler code | `HandlerError` with the exception message | Instant |
| Process crash | OOM kill, SIGKILL, unhandled panic | `AgentDied` on in-flight requests, `NotFound` afterwards (health monitor running); `MeshTimeout` otherwise | Sub-second with the health monitor; timeout without |
| Network partition | Network failure between agent and NATS | Same as process crash | 10–20s (server ping settings) |
| Zombie | Process alive but stuck (deadlock, hung LLM call) | `MeshTimeout` after the timeout window expires | Timeout |

Fast failure for crashes and partitions comes from the mesh health monitor
(disconnect advisories + death notices) — see [Liveness](liveness.md) for how
it works and what runs it.

### Handler exceptions

When a handler raises a non-`MeshError` exception, the mesh:

1. Wraps it as `HandlerError` (code `handler_error`)
2. Sends it back to the caller on the reply subject (for `mesh.call()`) or stream subject (for `mesh.stream()`)
3. Publishes it to the dead-letter subject `mesh.errors.{name}` for observability

The caller always gets a structured `MeshError` subclass, never a raw traceback.

### Mid-stream failures

If a streaming handler yields some chunks then crashes:

```python
chunks = []
try:
    async for chunk in mesh.stream("summarizer", payload):
        chunks.append(chunk)  # partial data is still delivered
except HandlerError as e:
    print(f"Stream failed after {len(chunks)} chunks: {e.message}")
    # chunks contains everything received before the failure
```

Partial data has value (especially for LLM streaming). The error signals "no more is coming", not "discard what you have".

### Process crashes and timeouts

When an agent process dies after accepting a request (crash, OOM, kill), no error reply is sent because the process is gone. The caller's `mesh.call()` or `mesh.stream()` waits until the timeout expires, then raises `MeshTimeout`.

The timeout is set per call:

```python
result = await mesh.call("summarizer", payload, timeout=10.0)
```

There is no way to distinguish "agent is slow" from "agent is dead" at the caller level today. Future versions may use disconnect advisories (ADR-0016) to detect agent death mid-request and fail fast.

### Choosing timeout values

- **Tool agents** (deterministic, fast): 1-5 seconds. A tool that hasn't responded in 5s is almost certainly dead.
- **LLM agents** (variable latency): 30-120 seconds. LLM calls can genuinely take this long.
- **Human-in-the-loop**: Use `mesh.send()` with async callbacks instead of `mesh.call()`. Don't block on humans.

## Catching errors at scale

The base `MeshError` catches all of them. Use it as a fallback after specific cases:

```python
from openagentmesh import (
    InvalidInput,    # caller fault
    HandlerError,    # provider fault
    MeshTimeout,     # transport/liveness
    NotFound,        # agent missing
    InvocationMismatch,  # wrong verb
    MeshError,       # base
)

try:
    result = await mesh.call(name, payload)
except InvalidInput:
    ...   # fix the payload
except HandlerError:
    ...   # retry or fall back
except MeshTimeout:
    ...   # transport problem
except NotFound:
    ...   # the agent is gone
except MeshError:
    ...   # anything else (forward-compatible with future codes)
```

If a future SDK version adds a code your version doesn't recognize, it deserializes to a plain `MeshError` with the unknown `code` preserved — the catch-all branch handles it cleanly.
