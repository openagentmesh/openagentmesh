# Cookbook

Practical recipes demonstrating common patterns with OpenAgentMesh. Each recipe is a self-contained code sample you can copy and run.

To run any recipe against a local embedded mesh:

```python
import asyncio
from openagentmesh import AgentMesh

async def run():
    async with AgentMesh.local() as mesh:
        # paste the recipe's main() body here
        ...

asyncio.run(run())
```

Or against your own mesh started with `oam mesh up`:

```python
async with AgentMesh() as mesh:     # connects to nats://localhost:4222
    ...
```

## Available Recipes

| Recipe | Pattern |
|--------|---------|
| [Multi-Process Agents](multi-process.md) | Provider/consumer on a shared bus |
| [Multi-Module Projects](multi-module.md) | Scaling beyond a single file |
| [Shared Plan Coordination](shared-plan.md) | CAS-based concurrent state |
| [LLM-Driven Tool Selection](llm-tool-selection.md) | Runtime discovery for LLM tools |
| [Error Handling](error-handling.md) | Retry, fallback, monitoring |
| [Automatic Load Balancing](load-balancing.md) | Queue group scaling |
| [Reactive Pipeline](reactive-pipeline.md) | KV watch coordination |
| [Parallel RAG Indexing](parallel-rag-indexing.md) | ObjectStore + queue groups |

!!! tip "Interactive demos"
    For an interactive experience, try `oam demo`. It starts a local mesh with sample agents you can explore from another terminal.
