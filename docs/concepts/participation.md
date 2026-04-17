# Participation Patterns

There are three ways to participate in the mesh. They differ in whether you register agents, call agents, or both.

## Provider

Register agents and serve requests. No outgoing calls.

```python
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

class SummarizeInput(BaseModel):
    text: str

class SummarizeOutput(BaseModel):
    summary: str

@mesh.agent(AgentSpec(name="summarizer", channel="nlp", description="Summarizes text."))
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    return SummarizeOutput(summary=req.text[:100])

mesh.run()
```

The provider registers agents, subscribes to NATS subjects, and blocks. It never calls other agents. This is the simplest deployment: one process, one responsibility.

## Consumer

No registered agents. Discover and call agents on the mesh.

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

The consumer connects, browses the catalog, calls agents, and disconnects. No `@mesh.agent` decorator, no registration. This is how scripts, notebooks, CLI tools, and orchestrators interact with the mesh.

## Hybrid

Register agents that also call other agents. Provider and consumer in one process.

```python
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

class ReviewInput(BaseModel):
    text: str

class ReviewOutput(BaseModel):
    summary: str
    sentiment: str

@mesh.agent(AgentSpec(name="reviewer", channel="nlp", description="Summarizes and classifies text."))
async def review(req: ReviewInput) -> ReviewOutput:
    summary = await mesh.call("summarizer", {"text": req.text})
    sentiment = await mesh.call("classifier", {"text": req.text})
    return ReviewOutput(summary=summary["summary"], sentiment=sentiment["label"])

mesh.run()
```

The `reviewer` agent is itself registered on the mesh, but its handler calls two other agents (`summarizer` and `classifier`) to compose the result. It accesses the mesh via closure over the `mesh` variable.

This is the natural pattern for orchestrator agents, pipelines, and any agent that coordinates work across other agents.

## Summary

| Pattern | Registers agents | Calls agents | Lifecycle |
|---------|-----------------|-------------|-----------|
| Provider | Yes | No | `mesh.run()` |
| Consumer | No | Yes | `async with mesh:` |
| Hybrid | Yes | Yes | `mesh.run()` or `async with mesh:` |

All three connect to the same NATS server. All three can run in the same process or in separate processes. The mesh doesn't distinguish between them; they're just different usage patterns of the same `AgentMesh` class.
