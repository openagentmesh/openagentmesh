# Invocation

Three patterns for calling agents on the mesh.

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

Agents can emit events on their event subject for fan-out consumption:

```
mesh.agent.{channel}.{name}.events
```

No invocation; any subscriber receives the event. Useful for notifications, audit trails, and reactive pipelines.

## Error Handling

When `X-Mesh-Status: error`, the response body contains:

```json
{
  "code": "validation_error",
  "message": "Field 'text' is required",
  "agent": "summarizer",
  "request_id": "abc123",
  "details": {}
}
```

Error codes: `validation_error`, `handler_error`, `timeout`, `not_found`, `rate_limited`.
