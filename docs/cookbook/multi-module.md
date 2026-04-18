# Multi-Module Projects

As your project grows beyond a single file, agents move into separate modules. The pattern: create the `AgentMesh` instance in one module, import it everywhere else.

## Project Structure

```
myproject/
    mesh.py            # shared AgentMesh instance
    agents/
        researcher.py  # agent handler
        summarizer.py  # agent handler
    main.py            # entry point
```

## Shared Instance

**mesh.py** creates the instance. No agent imports here.

```python
from openagentmesh import AgentMesh

mesh = AgentMesh()
```

## Agent Modules

Each agent module imports `mesh` and registers its handler.

**agents/researcher.py**

```python
from pydantic import BaseModel
from openagentmesh import AgentSpec
from mesh import mesh

class Query(BaseModel):
    topic: str

class ResearchResult(BaseModel):
    findings: str

spec = AgentSpec(
    name="researcher",
    channel="analysts",
    description="Researches a topic and returns findings.",
)

@mesh.agent(spec)
async def research(req: Query) -> ResearchResult:
    return ResearchResult(findings=f"Research on {req.topic}: ...")
```

**agents/summarizer.py**

```python
from pydantic import BaseModel
from openagentmesh import AgentSpec
from mesh import mesh

class TextInput(BaseModel):
    text: str

class Summary(BaseModel):
    text: str

spec = AgentSpec(
    name="summarizer",
    channel="nlp",
    description="Summarizes text.",
)

@mesh.agent(spec)
async def summarize(req: TextInput) -> Summary:
    return Summary(text=req.text[:100] + "...")
```

## Entry Point

**main.py** imports the agent modules (which registers handlers as a side effect) and starts the mesh.

```python
from mesh import mesh

import agents.researcher   # registers researcher
import agents.summarizer   # registers summarizer

mesh.run()
```

## How It Works

`@mesh.agent` stores handler metadata at decoration time. No NATS connection is needed yet. When `mesh.run()` (or `async with mesh:`) executes, the mesh connects, creates KV buckets, and subscribes all registered agents. Handlers that reference `mesh.kv` or `mesh.call()` inside their function body work because the mesh is connected by the time the handler runs.

## Testing

Use `mesh.local()` as an instance method. It starts an embedded NATS server and connects the existing instance (with all its registered agents) to it:

```python
import asyncio
from mesh import mesh
import agents.researcher

async def test_researcher():
    async with mesh.local():
        result = await mesh.call("researcher", {"topic": "NATS"})
        assert "NATS" in result["findings"]

asyncio.run(test_researcher())
```

No need to re-register agents. The handlers registered by importing `agents.researcher` are already on the `mesh` instance.

## Consumer Scripts

A consumer that only calls agents (no handlers to register) creates its own instance or imports the shared one:

```python
import asyncio
from openagentmesh import AgentMesh

async def main():
    mesh = AgentMesh()
    async with mesh:
        catalog = await mesh.catalog()
        for entry in catalog:
            print(f"{entry.name}: {entry.description}")

        result = await mesh.call("researcher", {"topic": "multi-agent systems"})
        print(result["findings"])

asyncio.run(main())
```

Consumers don't need to import agent modules. They discover agents at runtime through the catalog.
