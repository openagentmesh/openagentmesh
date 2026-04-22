# Participation Patterns

There are two ways to participate in the mesh: registered and unregistered. The difference is whether you use `@mesh.agent` to put agents on the mesh.

## Registered

A registered process uses `@mesh.agent` to declare one or more agents. Those agents appear in the catalog, get contracts in the registry, and participate in liveness tracking. Any [handler shape](agents.md#handler-shapes) works.

```python
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

class SummarizeInput(BaseModel):
    text: str

class SummarizeOutput(BaseModel):
    summary: str

@mesh.agent(AgentSpec(name="nlp.summarizer", description="Summarizes text."))
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    return SummarizeOutput(summary=req.text[:100])

mesh.run()
```

A registered process can also call other agents from inside its handlers:

```python
@mesh.agent(AgentSpec(name="nlp.reviewer", description="Summarizes and classifies text."))
async def review(req: ReviewInput) -> ReviewOutput:
    summary = await mesh.call("nlp.summarizer", {"text": req.text})
    sentiment = await mesh.call("nlp.classifier", {"text": req.text})
    return ReviewOutput(summary=summary["summary"], sentiment=sentiment["label"])
```

## Unregistered

An unregistered process connects to the mesh, discovers and calls agents, and disconnects. No `@mesh.agent` decorator, no registration, no catalog entry. This is how scripts, notebooks, CLI tools, and orchestrators interact with the mesh.

```python
import asyncio
from openagentmesh import AgentMesh

async def main():
    mesh = AgentMesh()
    async with mesh:
        catalog = await mesh.catalog()
        for entry in catalog:
            print(entry.name, "-", entry.description)

        result = await mesh.call("summarizer", {"text": "A long document..."})
        print(result["summary"])

asyncio.run(main())
```

## Summary

| Pattern | Registers agents | Lifecycle |
|---------|-----------------|-----------|
| Registered | Yes | `mesh.run()` or `async with mesh:` |
| Unregistered | No | `async with mesh:` |

Both connect to the same NATS server. Both can run in the same process or in separate processes. The mesh doesn't distinguish between them; they're just different usage patterns of the same `AgentMesh` class.
