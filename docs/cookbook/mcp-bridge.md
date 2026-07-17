# Serving Mesh Agents to MCP Clients

Any MCP client — Claude Code, Claude Desktop, Cursor — can list and call your mesh agents as tools. The bridge is a gateway to the whole mesh: it walks the catalog, exports every agent that opts in, and proxies `tools/call` to `mesh.call()`. Agents registered by other processes are exported too, as long as their contract opts in.

Requires the `mcp` extra:

```bash
pip install 'openagentmesh[mcp]'
```

## The Code

Mark agents for export with the `mcp` flag and serve:

```python
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()


class SummarizeInput(BaseModel):
    text: str


class SummarizeOutput(BaseModel):
    summary: str


@mesh.agent(AgentSpec(name="nlp.summarizer", description="Summarizes text"), mcp=True)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    return SummarizeOutput(summary=req.text[:100])


@mesh.agent(AgentSpec(name="internal.audit", description="Plumbing"), mcp=False)
async def audit(req: SummarizeInput) -> SummarizeOutput:
    return SummarizeOutput(summary="internal")


# Blocking, like mesh.run(). Serves MCP over stdio while hosting the agents.
mesh.run_mcp(default_mcp=False)  # opt-in: only nlp.summarizer is exported
```

The MCP client sees `nlp_summarizer` (dots become underscores — MCP tool names are flat), with the description and JSON Schema straight from the contract.

## Export policy

Per ADR-0003, export selection is a per-agent boolean plus a mesh-level default:

| `default_mcp` | Agent flag | Exported? |
|---------------|-----------|-----------|
| `True` (opt-out) | unset | yes |
| `True` (opt-out) | `mcp=False` | no |
| `False` (opt-in) | unset | no |
| `False` (opt-in) | `mcp=True` | yes |

Use opt-out (`default_mcp=True`, the default) for local development, opt-in for anything shared. Only invocable agents (Responder shape) are exported; streamers and publishers are skipped.

## Bridging an already-running mesh

You don't need to host agents in the same process. `oam mcp serve` connects to a mesh and gateways whatever is registered there:

```bash
claude mcp add mesh -- oam mcp serve --url nats://localhost:4222
```

Then, in Claude Code: the mesh's exported agents appear as tools named after the agents.

## Errors

The MCP SDK validates arguments against the tool's input schema client-side, so malformed calls fail before touching the mesh. Faults inside an agent surface as MCP tool errors carrying the OAM error taxonomy code (`handler_error: ...`), so the calling model can tell caller faults from provider faults.
