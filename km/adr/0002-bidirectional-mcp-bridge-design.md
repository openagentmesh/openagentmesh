# ADR-0002: Bidirectional MCP bridge design (run_mcp + add_mcp)

- **Type:** architecture
- **Date:** 2026-04-11
- **Status:** spec
- **Source:** km/notes/20260411_On JSON-RPC and MCP bridges.md

## Context

AgentMesh needs to interoperate with the MCP ecosystem in both directions: exposing mesh agents to MCP clients (Claude Desktop, Cursor) and consuming external MCP servers (GitHub, filesystem) from within the mesh.

## Decision

Two distinct APIs serving opposite directions:

- **`mesh.run_mcp()`.** Starts an MCP server (stdio or HTTP/SSE) that proxies `tools/list` and `tools/call` to the mesh. MCP clients see mesh agents as tools. Contract-to-MCP-tool conversion is trivial since `AgentContract` already holds JSON Schema. Phase 2 deliverable.

- **`mesh.add_mcp()`.** Connects to an external MCP server, enumerates its tools, registers them as **virtual agents** (type: `mcp_bridge`) in the mesh catalog. Mesh agents call them via `mesh.call()` transparently. The bridge manages the MCP session lifecycle (reconnect, deregister on crash). Phase 3 deliverable.

From any mesh agent's perspective, MCP-bridged tools are indistinguishable from native agents: they appear in `mesh.catalog()`, have contracts, and are callable via `mesh.call()`.

## Alternatives Considered

- **Single unified adapter.** Rejected because the two directions have fundamentally different lifecycle concerns (run_mcp is a server, add_mcp manages a client session) and trust models.

## Risks and Implications

- `add_mcp()` introduces session-oriented lifecycle management (MCP servers are stateful) into a stateless mesh model. Bridge process must handle reconnection, deregistration on crash, and cleanup.
- MCP doesn't define output schemas, so mesh agents calling MCP bridge tools get untyped results. Bridge should optionally accept `output_model` overrides for developer-supplied validation.
- MCP resources and prompts are out of scope initially but map naturally to future mesh primitives (Object Store, prompts namespace).
- Phase placement locks in: `run_mcp()` in Phase 2, `add_mcp()` in Phase 3 alongside spawner work.

## Amendment (2026-07-17): run_mcp v1 ships stdio-only; SSE superseded upstream

The MCP spec deprecated HTTP+SSE in favor of Streamable HTTP (spec rev 2025-03-26).
v1 of the export direction therefore ships **stdio only** — it covers the dominant
clients (Claude Code, Claude Desktop, Cursor) and avoids binding an HTTP stack.
Streamable HTTP becomes a follow-up once someone needs a networked MCP endpoint.

Scope decisions for v1:

- `mesh.serve_mcp(default_mcp=...)` is the async primitive; `mesh.run_mcp(...)` is the
  blocking convenience wrapper (mirrors `mesh.run()`). Both host the mesh's registered
  agents and serve MCP on stdio at the same time.
- The gateway exports the **whole mesh**, not just locally registered agents: `tools/list`
  walks the catalog and fetches contracts; `tools/call` proxies `mesh.call()`. The
  per-agent `mcp` flag (ADR-0003) is stored in the contract under `x-agentmesh.mcp`
  so remote agents' export intent survives the registry round-trip.
- Only invocable agents (Responder shape) export in v1. Streamers need MCP progress
  notifications; publishers/watchers have no request/reply semantics. Both are skipped.
- Tool names pass through the existing dot→underscore sanitizer (ADR-0039); the server
  keeps a reverse map for call routing.
- `oam mcp serve --url nats://...` wraps `run_mcp` for clients that register commands
  (e.g. `claude mcp add mesh -- oam mcp serve`).
- The `mcp` Python SDK is an optional extra: `pip install openagentmesh[mcp]`.

### Code sample (DX contract)

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

@mesh.agent(AgentSpec(name="nlp.summarizer", description="Summarizes text"), mcp=True)
async def summarize(req: SummarizeInput) -> SummarizeOutput: ...

@mesh.agent(AgentSpec(name="internal.audit", description="Plumbing"), mcp=False)
async def audit(req: AuditInput) -> AuditOutput: ...

# Blocking, like mesh.run(). Serves MCP over stdio while hosting agents.
mesh.run_mcp(default_mcp=False)   # opt-in: only nlp.summarizer is exported
```

An MCP client then sees `nlp_summarizer` via `tools/list` and invokes it via
`tools/call`; the bridge validates nothing itself — input validation stays with the
agent (ADR-0057 taxonomy maps to MCP errors).
