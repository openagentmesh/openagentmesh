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

The agent must be a streaming handler (async generator). Calling `mesh.stream()` against a buffered agent raises a `MeshError`.

## Async Callback

Fire-and-forget with a reply subject. The caller continues working while the agent processes the request.

```python
import uuid

request_id = uuid.uuid4().hex
await mesh.send(
    "summarizer",
    {"text": long_doc, "max_length": 500},
    reply_to=f"mesh.results.{request_id}",
)
# Result arrives on mesh.results.{request_id}
```

The caller subscribes to the reply subject independently. This pattern is useful for long-running operations or pipeline workflows.

## Pub/Sub Events

Event emitter agents yield events on their event subject for fan-out consumption:

```
mesh.agent.{channel}.{name}.events
```

No invocation; any subscriber receives the event. Useful for notifications, audit trails, and reactive pipelines.

## Error Handling

When an invocation fails, `mesh.call()` and `mesh.stream()` raise `MeshError` with a structured error:

```python
from openagentmesh import MeshError

try:
    result = await mesh.call("summarizer", payload)
except MeshError as e:
    print(e.code, e.message)
```

Error codes: `validation_error`, `handler_error`, `timeout`, `not_found`, `streaming_not_supported`.
