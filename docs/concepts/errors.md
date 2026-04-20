# Error Handling

Every error on the mesh is structured. No raw tracebacks, no mystery strings.

```python
from openagentmesh import AgentMesh, MeshError

mesh = AgentMesh("nats://localhost:4222")

async with mesh:
    try:
        result = await mesh.call("summarizer", {"text": 42})  # wrong type
    except MeshError as e:
        print(e.code)        # "validation_error"
        print(e.message)     # "Field 'text' expected str, got int"
        print(e.agent)       # "summarizer"
        print(e.request_id)  # "a1b2c3..."
```

## Error Envelope

When an agent returns `X-Mesh-Status: error`, the response body is always this shape:

```json
{
  "code": "validation_error",
  "message": "Field 'text' expected str, got int",
  "agent": "summarizer",
  "request_id": "a1b2c3d4",
  "details": {}
}
```

The `details` field carries extra context when available. Validation errors include the field-level issues; handler errors may include a truncated traceback.

## Error Codes

| Code | When | Exception class |
|------|------|-----------------|
| `validation_error` | Input doesn't match the agent's Pydantic schema | `MeshError` |
| `handler_error` | The agent's handler function raised an exception | `MeshError` |
| `timeout` | The agent didn't respond within the timeout window | `MeshError` |
| `not_found` | No agent registered with that name | `MeshError` |
| `streaming_not_supported` | `mesh.stream()` called on a non-streaming agent | `StreamingNotSupported` |
| `buffered_not_supported` | `mesh.call()` called on a streaming-only agent | `BufferedNotSupported` |
| `chunk_sequence_error` | Stream chunks arrived out of order | `ChunkSequenceError` |
| `rate_limited` | Agent or mesh rate limit exceeded | `MeshError` |

## Error Subclasses

Streaming-related errors have dedicated `MeshError` subclasses for typed exception handling:

```python
from openagentmesh import StreamingNotSupported, BufferedNotSupported

try:
    async for chunk in mesh.stream("summarizer", payload):
        print(chunk["delta"], end="")
except StreamingNotSupported:
    # agent doesn't support streaming, fall back to a single-response call
    result = await mesh.call("summarizer", payload)
except BufferedNotSupported:
    # shouldn't happen here, but shows the pattern
    pass
```

All subclasses inherit from `MeshError`, so `except MeshError:` still catches everything.

## How Errors Propagate

The mesh catches exceptions so callers don't have to guess what went wrong.

### Non-streaming invocation

1. The caller sends a request via `mesh.call()`.
2. The mesh validates the payload against the agent's input schema. If it fails, a `validation_error` is returned immediately; the handler never runs.
3. If the handler raises an exception, the mesh wraps it in the error envelope with code `handler_error` and returns it to the caller.
4. The caller receives a structured `MeshError`, not a raw Python exception.

### Streaming invocation

1. The caller sends a request via `mesh.stream()`.
2. Capability is checked before the request is sent. If the target agent is non-streaming, `StreamingNotSupported` is raised locally (no round trip).
3. If the handler's async generator raises mid-stream (after yielding some chunks), the error is published to the stream subject. The caller receives all chunks up to the failure, then gets the `MeshError`.

Handler authors don't need to catch their own errors for the caller's sake. The mesh does it. But you can still raise specific exceptions if you want to control the error message.

## Dead-Letter Subject

Every error is also published to the agent's dead-letter subject:

```
mesh.errors.{channel}.{name}
```

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

### The four failure modes

| Mode | Cause | What the caller sees | Detection speed |
|------|-------|---------------------|-----------------|
| Graceful shutdown | `mesh.stop()` or process exit | `MeshError(code="not_found")` on next call (agent already deregistered) | Instant |
| Handler exception | Bug in handler code | `MeshError(code="handler_error")` with the exception message | Instant |
| Process crash | OOM kill, SIGKILL, unhandled panic | `MeshError(code="timeout")` after the timeout window expires | Timeout (default varies by agent type) |
| Network partition | Network failure between agent and NATS | `MeshError(code="timeout")` after the timeout window expires | Timeout |

### Handler exceptions (the common case)

When a handler raises an exception, the mesh catches it and:

1. Wraps it in the error envelope with code `handler_error`
2. Sends it back to the caller on the reply subject (for `mesh.call()`) or stream subject (for `mesh.stream()`)
3. Publishes it to the dead-letter subject `mesh.errors.{channel}.{name}` for observability

The caller always gets a structured `MeshError`, never a raw traceback.

### Mid-stream failures

If a streaming handler yields some chunks then crashes:

```python
chunks = []
try:
    async for chunk in mesh.stream("summarizer", payload):
        chunks.append(chunk)  # partial data is still delivered
except MeshError as e:
    print(f"Stream failed after {len(chunks)} chunks: {e.code}")
    # chunks contains everything received before the failure
```

Partial data has value (especially for LLM streaming). The error signals "no more is coming", not "discard what you have".

### Process crashes and timeouts

When an agent process dies after accepting a request (crash, OOM, kill), no error reply is sent because the process is gone. The caller's `mesh.call()` or `mesh.stream()` waits until the timeout expires, then raises `MeshError(code="timeout")`.

The timeout is set per call:

```python
result = await mesh.call("summarizer", payload, timeout=10.0)
```

Or inferred from the agent's SLA in its contract (`sla.timeout_ms`). Tool-type agents default to shorter timeouts than LLM-powered agents.

There is no way to distinguish "agent is slow" from "agent is dead" at the caller level today. Future versions will use death notices to detect agent death mid-request and fail fast.

### Choosing timeout values

- **Tool agents** (deterministic, fast): 1-5 seconds. A tool that hasn't responded in 5s is almost certainly dead.
- **LLM agents** (variable latency): 30-120 seconds. LLM calls can genuinely take this long.
- **Human-in-the-loop**: Use `mesh.send()` with async callbacks instead of `mesh.call()`. Don't block on humans.
