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

## The Code

The recipe shows the pattern in a single file. In production, split along module boundaries:

```python
import asyncio

from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec


class SummarizeInput(BaseModel):
    text: str
    max_length: int = 200


class SummarizeOutput(BaseModel):
    summary: str


async def main(mesh: AgentMesh) -> None:
    @mesh.agent(AgentSpec(
        name="nlp.summarizer",
        description="Summarizes text to a target length. Input: raw text and optional max_length.",
    ))
    async def summarize(req: SummarizeInput) -> SummarizeOutput:
        truncated = req.text[:req.max_length]
        return SummarizeOutput(summary=truncated)

    # Discover agents on the mesh
    catalog = await mesh.catalog()
    for entry in catalog:
        print(f"{entry.name} - {entry.description}")

    # Call by name
    result = await mesh.call(
        "nlp.summarizer",
        SummarizeInput(
            text="AgentMesh connects agents over NATS. Agents register, discover, and invoke each other at runtime.",
            max_length=40,
        ),
    )
    print(f"\nResult: {result['summary']}")
```

## Run It

```python
import asyncio
from openagentmesh import AgentMesh

async def run():
    async with AgentMesh.local() as mesh:
        await main(mesh)

asyncio.run(run())
```

## How It Works

`@mesh.agent` stores handler metadata at decoration time. No NATS connection is needed yet. When `mesh.run()` (or `async with mesh:`) executes, the mesh connects, creates KV buckets, and subscribes all registered agents. Handlers that reference `mesh.kv` or `mesh.call()` inside their function body work because the mesh is connected by the time the handler runs.

## Splitting Into Modules

**mesh.py** creates the instance. No agent imports here.

```python
from openagentmesh import AgentMesh

mesh = AgentMesh()
```

**agents/researcher.py** imports `mesh` and registers its handler.

```python
from openagentmesh import AgentSpec
from mesh import mesh

@mesh.agent(AgentSpec(name="analysts.researcher", description="Researches a topic."))
async def research(req: Query) -> ResearchResult:
    return ResearchResult(findings=f"Research on {req.topic}: ...")
```

**main.py** imports the agent modules (which registers handlers as a side effect) and starts the mesh.

```python
from mesh import mesh
import agents.researcher
import agents.summarizer

mesh.run()
```

## Testing

Use `AgentMesh.local()` as an async context manager. It starts an embedded NATS server and connects the existing instance (with all its registered agents) to it:

```python
from mesh import mesh
import agents.researcher

async def test_researcher():
    async with mesh.local():
        result = await mesh.call("analysts.researcher", {"topic": "NATS"})
        assert "NATS" in result["findings"]
```

No need to re-register agents. The handlers registered by importing `agents.researcher` are already on the `mesh` instance.
