# Cookbook

Practical recipes demonstrating common patterns with OpenAgentMesh. Each recipe is a self-contained demo you can run with a single command:

```bash
oam demo run <name>
```

This starts a temporary local mesh, runs the recipe, and tears down. No setup required.

To run any recipe manually against your own mesh:

```python
import asyncio
from openagentmesh import AgentMesh

async def run():
    async with AgentMesh() as mesh:     # connects to oam mesh up
        await demo_main(mesh)           # paste the recipe's main() body here

asyncio.run(run())
```

Or self-contained with an embedded mesh:

```python
import asyncio
from openagentmesh import AgentMesh

async def run():
    async with AgentMesh.local() as mesh:
        await demo_main(mesh)

asyncio.run(run())
```

## Available Recipes

| Recipe | Demo name | Pattern |
|--------|-----------|---------|
| [Multi-Process Agents](multi-process.md) | `multi_agent` | Provider/consumer on a shared bus |
| [Multi-Module Projects](multi-module.md) | `multi_agent` | Scaling beyond a single file |
| [Shared Plan Coordination](shared-plan.md) | `shared_plan` | CAS-based concurrent state |
| [LLM-Driven Tool Selection](llm-tool-selection.md) | `llm_tool_selection` | Runtime discovery for LLM tools |
| [Error Handling](error-handling.md) | `error_handling` | Retry, fallback, monitoring |
| [Automatic Load Balancing](load-balancing.md) | `load_balancing` | Queue group scaling |
| [Reactive Pipeline](reactive-pipeline.md) | `reactive_pipeline` | KV watch coordination |
| [Parallel RAG Indexing](parallel-rag-indexing.md) | -- | ObjectStore + queue groups |

Browse the source code of any demo:

```bash
oam demo show <name>
```
