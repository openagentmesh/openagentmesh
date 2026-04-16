# ADR-0001: Reject JSON-RPC 2.0 as internal message standard

- **Type:** protocol
- **Date:** 2026-04-11
- **Status:** accepted
- **Source:** km/notes/20260411_On JSON-RPC and MCP bridges.md

## Context

MCP uses JSON-RPC 2.0; A2A uses it over HTTP at federation boundaries. The question was whether AgentMesh should adopt JSON-RPC 2.0 as its internal wire format for consistency with the broader ecosystem.

## Decision

Do not adopt JSON-RPC 2.0 internally. Every structural concern JSON-RPC addresses is already handled at the NATS layer: subjects replace `method`, `X-Mesh-Request-Id` replaces `id`, raw JSON bodies replace `params`/`result`. Adding JSON-RPC on top of NATS creates redundancy with zero information density gain.

Additional reasoning:
- JSON-RPC is fundamentally request/response; AgentMesh's pub/sub pattern (fan-out events) is architecturally incompatible with JSON-RPC's mental model.
- AgentMesh's error envelope (`code`, `message`, `agent`, `request_id`, `details`) is semantically richer than JSON-RPC's integer error codes.
- `X-Mesh-Status: error` in NATS headers enables zero-copy error routing before body parsing.

## Alternatives Considered

- **Adopt JSON-RPC 2.0 everywhere.** Rejected due to redundancy with NATS primitives and incompatibility with pub/sub patterns.
- **Adopt JSON-RPC 2.0 for MCP familiarity.** Rejected; MCP runs over stdio/HTTP (point-to-point), not an event-driven mesh. Familiarity is a thin reason for significant architectural overhead.

## Risks and Implications

- JSON-RPC 2.0 is the right format at the **A2A gateway boundary** (Phase 4) where HTTP is the transport. The gateway translates between NATS and JSON-RPC; this is a perimeter concern, not internal.
- MCP adapters (`mesh.run_mcp()`, `mesh.add_mcp()`) will similarly translate at the bridge layer.
- Developers familiar only with JSON-RPC may find NATS headers unfamiliar; documentation must explain the mapping clearly.
