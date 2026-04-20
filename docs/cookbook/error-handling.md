# Error Handling

Handle agent failures gracefully. Catch structured errors, retry transient failures, and fall back to alternative agents.

## The Code

```python
import asyncio
import random

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, MeshError


class SummarizeInput(BaseModel):
    text: str


class SummarizeOutput(BaseModel):
    summary: str


async def call_with_retry(mesh: AgentMesh, agent: str, payload, retries: int = 3, base_delay: float = 0.1):
    for attempt in range(retries):
        try:
            return await mesh.call(agent, payload)
        except MeshError as e:
            if e.code == "not_found":
                raise
            if attempt == retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(f"  Attempt {attempt + 1} failed ({e.code}), retrying in {delay}s")
            await asyncio.sleep(delay)


async def call_with_fallback(mesh: AgentMesh, agents: list[str], payload):
    last_error = None
    for agent in agents:
        try:
            return await mesh.call(agent, payload, timeout=5.0)
        except MeshError as e:
            last_error = e
            print(f"  {agent} failed ({e.code}), trying next...")
            if e.code in ("not_found", "handler_error"):
                continue
            raise
    raise last_error


async def main(mesh: AgentMesh) -> None:
    @mesh.agent(AgentSpec(name="summarizer", channel="nlp", description="Summarizes text. May fail under load."))
    async def summarize(req: SummarizeInput) -> SummarizeOutput:
        if random.random() < 0.3:
            raise RuntimeError("LLM provider timeout")
        return SummarizeOutput(summary=f"Summary of: {req.text[:50]}")

    @mesh.agent(AgentSpec(name="basic-summarizer", channel="nlp", description="Simple fallback summarizer."))
    async def basic_summarize(req: SummarizeInput) -> SummarizeOutput:
        return SummarizeOutput(summary=req.text[:80] + "...")

    # Pattern 1: Basic error handling
    try:
        result = await mesh.call("summarizer", SummarizeInput(text="Long document about AI agents"))
        print(f"  Success: {result['summary']}")
    except MeshError as e:
        print(f"  Error: [{e.code}] {e}")

    # Pattern 2: Retry with backoff
    result = await call_with_retry(mesh, "summarizer", SummarizeInput(text="Important document"))
    print(f"  Success: {result['summary']}")

    # Pattern 3: Fallback agent
    result = await call_with_fallback(
        mesh,
        agents=["summarizer", "basic-summarizer"],
        payload=SummarizeInput(text="Critical document that must be processed"),
    )
    print(f"  Success: {result['summary']}")
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
