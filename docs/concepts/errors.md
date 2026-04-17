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

| Code | When |
|------|------|
| `validation_error` | Input doesn't match the agent's Pydantic schema |
| `handler_error` | The agent's handler function raised an exception |
| `timeout` | The agent didn't respond within the timeout window |
| `not_found` | No agent registered with that name |
| `rate_limited` | Agent or mesh rate limit exceeded |

## How Errors Propagate

The mesh catches exceptions so callers don't have to guess what went wrong.

1. The caller sends a request via `mesh.call()`.
2. The mesh validates the payload against the agent's input schema. If it fails, a `validation_error` is returned immediately; the handler never runs.
3. If the handler raises an exception, the mesh wraps it in the error envelope with code `handler_error` and returns it to the caller.
4. The caller receives a structured `MeshError`, not a raw Python exception.

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
