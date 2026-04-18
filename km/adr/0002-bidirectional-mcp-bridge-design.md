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
