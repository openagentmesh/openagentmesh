# ADR-0003: MCP export flag as boolean, not list

- **Type:** api-design
- **Date:** 2026-04-11
- **Status:** accepted
- **Source:** km/notes/20260411_On JSON-RPC and MCP bridges.md

## Context

When exposing mesh agents via `mesh.run_mcp()`, some agents should be visible to MCP clients and others should not (internal plumbing agents). The question was whether the per-agent flag should be `export=["mcp"]` (list of protocols) or `mcp=True` (boolean).

## Decision

Use a simple boolean `mcp=True/False` on the `@mesh.agent` decorator. The list pattern (`export=["mcp", "a2a"]`) was premature generalization; A2A exposure happens at the gateway level (boundary config, not per-agent), and no other export target is foreseeable.

Mesh-level default policy is preserved:
```python
mesh.run_mcp(default_mcp=True)   # opt-out: everything unless mcp=False
mesh.run_mcp(default_mcp=False)  # opt-in: nothing unless mcp=True
```

Local dev default: opt-out (expose everything). Production default: opt-in.

## Alternatives Considered

- **`export=["mcp"]` list.** Rejected as premature generalization. A2A is gateway-level, not per-agent. The list would never grow beyond one entry.

## Risks and Implications

- If a future protocol requires per-agent export control (unlikely), the flag would need to evolve. Considered acceptable. YAGNI.
- The `mcp` field lives in the contract under `x-agentmesh.mcp`. Must be documented for manual `mesh.register()` users, not just decorator users.
