# Invocation

Four patterns for interacting with agents on the mesh.

## Synchronous Request/Reply

The default pattern. Caller blocks until the agent responds.

```python
result = await mesh.call("summarizer", {"text": doc, "max_length": 200})
print(result["summary"])
```

Options:

```python
result = await mesh.call("summarizer", payload, timeout=30.0)
```

Under the hood, this uses NATS native request/reply with automatic inbox management.

## Streaming

For agents that yield incremental output (LLM token streams, progressive results).

```python
async for chunk in mesh.stream("summarizer", {"text": doc}):
    print(chunk["delta"], end="")
```

The agent must be a streaming handler (async generator). Calling `mesh.stream()` against a non-streaming agent raises `StreamingNotSupported`. Calling `mesh.call()` against a streaming-only agent raises `StreamingRequired`. Both checks happen locally before the request is sent.

## Async Callback

Non-blocking invocation with a managed callback. The SDK generates the reply subject, subscribes, and dispatches to your callback.

```python
from openagentmesh import MeshError

async def handle_summary(result: dict):
    print(result["summary"])

async def handle_error(err: MeshError):
    print(f"Failed: {err.message}")

await mesh.send(
    "summarizer",
    {"text": long_doc, "max_length": 500},
    on_reply=handle_summary,
    on_error=handle_error,
    timeout=30.0,
)
# Continues immediately. Callback fires when the agent responds.
```

For manual control over the reply subject:

```python
import uuid

request_id = uuid.uuid4().hex
reply_subject = f"mesh.results.{request_id}"
await mesh.send("summarizer", payload, reply_to=reply_subject)

async for msg in mesh.subscribe(subject=reply_subject, timeout=30.0):
    print(msg["summary"])
    break
```

This pattern is useful for long-running operations or pipeline workflows where you need explicit subject control.

## Pub/Sub Events

Subscribe to an agent's event stream:

```python
async for event in mesh.subscribe(agent="price-feed"):
    print(event["symbol"], event["price"])
```

Subscribe to all events in a channel:

```python
async for event in mesh.subscribe(channel="finance"):
    print(event)
```

Publisher agents yield events with no request parameter. The SDK publishes each yielded value to the agent's event subject automatically:

```
mesh.agent.{channel}.{name}.events
```

No invocation; any subscriber receives the event. Useful for notifications, audit trails, and reactive pipelines.

## Error Handling

When an invocation fails, `mesh.call()` and `mesh.stream()` raise `MeshError`. See [Error Handling](errors.md) for the full envelope, error codes, and propagation semantics.
