# Error Handling

Handle agent failures gracefully. Catch structured errors, retry transient failures, and fall back to alternative agents.

## The Code

```python
--8<-- "src/openagentmesh/demos/error_handling.py"
```

## Run It

```bash
oam demo run error_handling
```

## How It Works

Key properties:

- **Structured errors everywhere.** Every failure produces a `MeshError` with `code`, `agent`, and `request_id`. No raw exceptions leak through the mesh.
- **Retry selectively.** `not_found` means the agent doesn't exist; retrying won't help. `handler_error` and `timeout` are potentially transient.
- **Fallback across agents.** When multiple agents can handle the same task, try them in preference order. The catalog and contracts enable this pattern at runtime via `mesh.discover()`.
- **Dead-letter stream.** Every error is published to `mesh.errors.{channel}.{name}` regardless of whether the caller handles it. Subscribe for monitoring, alerting, or audit logging.

## Error Monitor

Subscribe to the dead-letter subject for real-time error observability:

```python
import asyncio
import json
import nats

async def monitor():
    nc = await nats.connect("nats://localhost:4222")

    async def on_error(msg):
        error = json.loads(msg.data)
        print(f"[{error['agent']}] {error['code']}: {error['message']}")

    await nc.subscribe("mesh.errors.>", cb=on_error)

    print("Monitoring errors... (Ctrl+C to stop)")
    while True:
        await asyncio.sleep(1)

asyncio.run(monitor())
```
