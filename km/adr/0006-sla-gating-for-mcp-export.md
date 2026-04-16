# ADR-0006: SLA gating for MCP tool export

- **Type:** architecture
- **Date:** 2026-04-11
- **Status:** accepted
- **Source:** km/notes/20260411_On JSON-RPC and MCP bridges.md

## Context

MCP clients (Claude Desktop, Cursor) are synchronous: they block on `tools/call`. Mesh agents can have arbitrarily long timeouts (e.g., 5-minute human-in-the-loop agents). Exposing slow agents to MCP clients would stall or timeout the client.

## Decision

The `mesh.run_mcp()` bridge enforces a maximum SLA threshold at startup:

```python
mesh.run_mcp(
    max_timeout_ms=30_000,
    on_sla_violation="skip",  # "skip" | "warn" | "raise"
)
```

Agents exceeding the threshold are silently excluded from `tools/list` (with a startup log warning). Both the export flag (`mcp=True`) and the SLA check must pass for an agent to appear:

```
Export policy check → SLA fitness check → appears in tools/list
```

For `add_mcp()` (inbound direction), the bridge stamps an SLA on virtual agent contracts from observed behavior or developer-supplied hints.

## Risks and Implications

- Silent exclusion could confuse developers who set `mcp=True` but don't see their agent in `tools/list`. Startup warnings and `agentmesh status` must surface the reason.
- The 30s default is conservative; some legitimate MCP use cases (long document processing) may need higher limits. The threshold is configurable per bridge instance.
