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

The demo shows the pattern in a single file. In production, split along module boundaries:

```python
--8<-- "src/openagentmesh/demos/multi_agent.py"
```

## Run It

```bash
oam demo run multi_agent
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

@mesh.agent(AgentSpec(name="researcher", channel="analysts", description="Researches a topic."))
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
        result = await mesh.call("researcher", {"topic": "NATS"})
        assert "NATS" in result["findings"]
```

No need to re-register agents. The handlers registered by importing `agents.researcher` are already on the `mesh` instance.
