# ADR-0034: Subscribe primitive, publisher emission, and managed async callback

- **Type:** api-design
- **Date:** 2026-04-17
- **Status:** documented
- **Supersedes:** ADR-0029 (async callback consumption API)
- **Related:** ADR-0005 (streaming wire protocol), ADR-0031 (capabilities over type taxonomy)
- **Source:** conversation (shaping session on mesh.subscribe and mesh.send DX)

## Context

The SDK has three gaps in its invocation surface:

1. **No general subscription primitive.** Publisher agents (no input, async generator, `invocable=false`) are detected by the decorator but have no mechanism to emit events, and consumers have no SDK method to subscribe.

2. **No receive side for async callbacks.** `mesh.send(reply_to=...)` fires a request, but the caller must drop to raw NATS to receive the response (ADR-0029 documents this gap). The spec acknowledges this needs a correlation/timeout manager.

3. **Two use cases, one primitive.** Pub/sub event streams and async callback replies are both "subscribe to a subject and yield messages." A single `mesh.subscribe()` method serves both, with `mesh.send()` hiding the plumbing for the callback case.

## Decision

### 1. `mesh.subscribe()`: general subscription primitive

```python
async def subscribe(
    self,
    *,
    agent: str | None = None,
    channel: str | None = None,
    subject: str | None = None,
    timeout: float | None = None,
) -> AsyncGenerator[dict, None]:
```

**Subject resolution (keyword-only, mutually exclusive):**

- `agent="price-feed"` resolves to `mesh.agent.{channel}.{name}.events`. If `channel=` is provided, it scopes the lookup; otherwise the channel is resolved from the catalog. If the agent is not found in the catalog, raises `MeshError` with code `not_found`.
- `channel="finance"` without `agent=` subscribes to `mesh.agent.finance.>` (wildcard, all events in channel).
- `subject="mesh.results.abc123"` passes through as-is. No resolution. Used for async callback replies and ad-hoc subscriptions.
- Passing both `agent=` and `subject=` raises `ValueError`. Passing neither raises `ValueError`.

**Envelope handling:** Each incoming NATS message is deserialized from the OAM envelope into a `dict`.

**Terminal detection:** When `X-Mesh-Stream-End: true` is present, the generator closes cleanly.

**Error propagation:** When `X-Mesh-Status: error` is present, raises `MeshError` with code and message from the envelope.

**Inactivity timeout:** If `timeout=` is set and no message arrives within the window, raises `MeshTimeout`. `None` means no timeout (subscription lives until the generator is closed or terminal is received).

**Cleanup:** Breaking out of the `async for` loop triggers generator `aclose()`, which unsubscribes from NATS.

```python
# Pub/sub: follow a publisher's event stream
async for event in mesh.subscribe(agent="price-feed"):
    print(event["symbol"], event["price"])

# Channel-wide: all events in a channel
async for event in mesh.subscribe(channel="finance"):
    print(event)

# Raw subject: catch an async callback reply
async for msg in mesh.subscribe(subject=f"mesh.results.{request_id}"):
    print(msg)
    break
```

### 2. `mesh.send()` with managed async callback

Enhanced signature:

```python
async def send(
    self,
    name: str,
    payload: dict,
    *,
    on_reply: Callable[[dict], Awaitable[None]] | None = None,
    on_error: Callable[[MeshError], Awaitable[None]] | None = None,
    reply_to: str | None = None,
    timeout: float = 60.0,
) -> None:
```

**Three modes:**

```python
# Fire-and-forget (no reply handling)
await mesh.send("summarizer", payload)

# Managed callback (SDK handles plumbing)
await mesh.send("summarizer", payload, on_reply=handle_summary, on_error=handle_failure)

# Manual reply subject (power user, backwards compatible)
await mesh.send("summarizer", payload, reply_to="mesh.results.abc123")
```

**Managed callback behavior:**

1. SDK generates `request_id = uuid4().hex`.
2. Subscribes to `mesh.results.{request_id}` before sending.
3. Sends the request with `reply_to` set to that subject.
4. On each incoming message: deserializes envelope, calls `on_reply(result)`.
5. On `X-Mesh-Stream-End: true`: calls `on_reply` with the final payload (if non-empty), then unsubscribes.
6. On `X-Mesh-Status: error`: calls `on_error(MeshError(...))`, unsubscribes.
7. On timeout with no message: calls `on_error(MeshTimeout(...))`, unsubscribes.
8. If `on_error` is not provided: logs a warning via `logging.getLogger("openagentmesh")`.

**Constraints:**

- `on_reply` and `reply_to` are mutually exclusive. Passing both raises `ValueError`.
- `timeout` only applies when `on_reply` is set. Ignored otherwise.
- The callback runs in a background task; `send()` returns immediately after publishing.

### 3. Publisher agent emission

The SDK owns event emission for publisher handlers. When `mesh` starts serving, publisher handlers (no input param, async generator, `invocable=false`) are launched as background tasks.

```python
@mesh.agent(spec)
async def price_feed() -> PriceEvent:
    while True:
        yield PriceEvent(symbol="AAPL", price=await fetch_price())
        await asyncio.sleep(1)
```

Each yielded value is serialized and published to `mesh.agent.{channel}.{name}.events` with the standard envelope and `X-Mesh-Stream-End: false`.

**Lifecycle:**

- Generator runs as long as it yields. Infinite loop = long-lived publisher.
- Generator returns naturally: terminal message (`X-Mesh-Stream-End: true`) sent, publisher marked offline.
- Generator raises: error logged, terminal message with `X-Mesh-Status: error` sent.
- `mesh.close()`: cancels the background task, sends terminal message.

**Contract storage:** The output model's JSON Schema is stored as `output_schema` in the contract (same field streaming handlers use for chunk schema). Subscribers can inspect it via `mesh.contract("price-feed")`.

### 4. `MeshTimeout` exception

New exception, subclass of `MeshError`:

```python
class MeshTimeout(MeshError):
    def __init__(self, subject: str, timeout: float):
        super().__init__(code="timeout", message=f"No message on {subject} within {timeout}s")
```

Raised by `mesh.subscribe()` on inactivity timeout. Passed to `on_error` by `mesh.send(on_reply=...)` on timeout.

### 5. Default timeout strategy

`mesh.send(on_reply=...)` defaults to `timeout=60.0` (matching the agent-type SLA default from the spec). Callers can override explicitly. When `x-agentmesh.sla.timeout_ms` is implemented in the contract models, the SDK will read the agent's timeout from the contract automatically. No API change needed.

## What stays unchanged

- `mesh.call()` and `mesh.stream()` are untouched.
- `mesh.send(reply_to=...)` still works for manual plumbing.
- `@mesh.agent` decorator: publisher shape detection is already implemented.
- Envelope format and `X-Mesh-Stream-*` headers: reused as-is (ADR-0005).
- Contract schema: `output_schema` field already exists.

## Out of scope (Phase 2+)

- Backpressure / bounded queues for high-throughput subscriptions.
- Subscription lifecycle tracking on the mesh instance.
- Reading `timeout_ms` from contract SLA at runtime.
- Mesh-level default `on_error` handler.

## Risks and implications

- Publisher background tasks add one long-lived task per publisher agent per mesh instance. Must be properly cancelled on shutdown.
- `mesh.subscribe()` with `channel=` uses NATS wildcards (`mesh.agent.{channel}.>`), which may match unexpected subjects if naming conventions are violated.
- The `on_reply`/`on_error` callback pattern means errors surface asynchronously. Developers unfamiliar with callback-based error handling may miss failures. The fallback warning log mitigates silent failures.

## Code samples

### Pub/sub: publisher and subscriber

**publisher.py:**

```python
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

class PriceEvent(BaseModel):
    symbol: str
    price: float

spec = AgentSpec(name="price-feed", channel="finance", description="Real-time price events.")

@mesh.agent(spec)
async def price_feed() -> PriceEvent:
    while True:
        yield PriceEvent(symbol="AAPL", price=await fetch_price())
        await asyncio.sleep(1)

mesh.run()
```

**subscriber.py:**

```python
import asyncio
from openagentmesh import AgentMesh

async def main():
    mesh = AgentMesh()
    async with mesh:
        async for event in mesh.subscribe(agent="price-feed"):
            print(event["symbol"], event["price"])

asyncio.run(main())
```

### Async callback with managed reply

```python
import asyncio
from openagentmesh import AgentMesh, MeshError

async def main():
    mesh = AgentMesh()
    async with mesh:
        async def on_summary(result: dict):
            print("Got summary:", result["summary"])

        async def on_failure(err: MeshError):
            print("Failed:", err.message)

        await mesh.send(
            "summarizer",
            {"text": "A long document...", "max_length": 100},
            on_reply=on_summary,
            on_error=on_failure,
            timeout=30.0,
        )

        # Continue other work while waiting for callback
        other = await mesh.call("other-agent", {"key": "value"})
        print(other)

        # Keep running to receive the callback
        await asyncio.sleep(35)

asyncio.run(main())
```
