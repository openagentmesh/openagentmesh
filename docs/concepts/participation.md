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

## Watcher

Register agents that react to shared state changes. No incoming requests, no outgoing calls to other agents. Coordination happens through data in the KV store.

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

@mesh.agent(AgentSpec(
    name="extract",
    channel="pipeline",
    description="Watches for raw documents and extracts entities.",
))
async def extract():
    async for value in mesh.kv.watch("pipeline.*.raw"):
        doc = Document.model_validate_json(value)
        extracted = do_extraction(doc)
        await mesh.kv.put(f"pipeline.{doc.id}.extracted", extracted.model_dump_json())

mesh.run()
```

The watcher registers on the mesh (visible in the catalog, tracked for liveness) but is not invocable. Its handler runs as a background task that reacts to KV changes. This is the natural pattern for reactive pipeline stages and state-driven coordination.

!!! note "Scaling"
    Watcher agents do not benefit from queue-group scaling; every instance receives every KV update. For expensive processing, have the watcher delegate to an invocable agent via `mesh.call()`. The invocable agent scales via queue groups; the watcher stays as a single thin routing instance.

## Summary

| Pattern | Registers agents | Calls agents | Lifecycle |
|---------|-----------------|-------------|-----------|
| Provider | Yes | No | `mesh.run()` |
| Consumer | No | Yes | `async with mesh:` |
| Hybrid | Yes | Yes | `mesh.run()` or `async with mesh:` |
| Watcher | Yes | No (reacts to KV) | `mesh.run()` |

All four connect to the same NATS server. All four can run in the same process or in separate processes. The mesh doesn't distinguish between them; they're just different usage patterns of the same `AgentMesh` class.
