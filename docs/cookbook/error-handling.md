# Error Handling

Handle agent failures gracefully. Catch structured errors, retry transient failures, fall back to alternative agents, and monitor the error stream for observability.

## The Agent

A summarizer agent that sometimes fails, simulating real-world flakiness:

```python
import asyncio
import random
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

class SummarizeInput(BaseModel):
    text: str

class SummarizeOutput(BaseModel):
    summary: str

spec = AgentSpec(
    name="summarizer",
    channel="nlp",
    description="Summarizes text. May fail under load.",
)

@mesh.agent(spec)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    if random.random() < 0.3:
        raise RuntimeError("LLM provider timeout")
    await asyncio.sleep(0.2)
    return SummarizeOutput(summary=f"Summary of: {req.text[:50]}")

mesh.run()
```

## The Client

Demonstrates three patterns: basic error handling, retry with backoff, and fallback to an alternative agent.

```python
import asyncio
from openagentmesh import AgentMesh, MeshError

async def main():
    mesh = AgentMesh()
    async with mesh:
        # Pattern 1: Basic error handling
        try:
            result = await mesh.call("summarizer", {"text": "Long document..."})
            print(result["summary"])
        except MeshError as e:
            print(f"[{e.code}] {e.message} (agent={e.agent})")

        # Pattern 2: Retry with backoff
        result = await call_with_retry(
            mesh, "summarizer", {"text": "Important document"}, retries=3
        )
        print(result["summary"])

        # Pattern 3: Fallback agent
        result = await call_with_fallback(
            mesh,
            agents=["summarizer", "summarizer-v2", "basic-summarizer"],
            payload={"text": "Critical document"},
        )
        print(result["summary"])


async def call_with_retry(mesh, agent, payload, retries=3, base_delay=0.5):
    for attempt in range(retries):
        try:
            return await mesh.call(agent, payload)
        except MeshError as e:
            if e.code == "not_found":
                raise  # agent doesn't exist, don't retry
            if attempt == retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"Attempt {attempt + 1} failed ({e.code}), retrying in {delay}s")
            await asyncio.sleep(delay)


async def call_with_fallback(mesh, agents, payload):
    last_error = None
    for agent in agents:
        try:
            return await mesh.call(agent, payload, timeout=5.0)
        except MeshError as e:
            last_error = e
            if e.code == "not_found":
                continue  # try next agent
            if e.code == "handler_error":
                continue  # this agent is broken, try next
            raise  # unexpected error, don't mask it
    raise last_error


asyncio.run(main())
```

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
        if error.get("request_id"):
            print(f"  request_id: {error['request_id']}")

    # Monitor all agents in the nlp channel
    await nc.subscribe("mesh.errors.nlp.*", cb=on_error)
    # Or monitor everything: "mesh.errors.>"

    print("Monitoring errors... (Ctrl+C to stop)")
    while True:
        await asyncio.sleep(1)

asyncio.run(monitor())
```

## Run It

```bash
# Terminal 1
oam mesh up

# Terminal 2
python summarizer.py

# Terminal 3: monitor errors
python monitor.py

# Terminal 4: run client
python client.py
```

## How It Works

Key properties:

- **Structured errors everywhere.** Every failure produces a `MeshError` with `code`, `message`, `agent`, and `request_id`. No raw exceptions leak through the mesh.
- **Retry selectively.** `not_found` means the agent doesn't exist -- retrying won't help. `handler_error` and `timeout` are potentially transient.
- **Fallback across agents.** When multiple agents can handle the same task, try them in preference order. The catalog and contracts enable this pattern at runtime via `mesh.discover()`.
- **Dead-letter stream.** Every error is published to `mesh.errors.{channel}.{name}` regardless of whether the caller handles it. Subscribe for monitoring, alerting, or audit logging.
