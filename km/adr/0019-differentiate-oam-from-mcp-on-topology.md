# ADR-0019: Differentiate OAM from MCP on topology, not sync/async

- **Type:** strategy
- **Date:** 2026-04-13
- **Status:** documented
- **Source:** .specstory/history/2026-04-13_21-50-40Z.md

## Context

The OAM documentation and comparison tables described MCP as "synchronous request/reply only" and listed "Async patterns: Not supported" for MCP. This is an oversimplification: MCP uses JSON-RPC 2.0 over SSE/stdio with streaming responses and server-initiated notifications. The framing risked appearing uninformed to developers familiar with MCP internals.

## Decision

Reframe the OAM-vs-MCP differentiator as topology and initiative, not sync vs. async:

- MCP is **client-initiated, single-tool, streamed response**. A client connects to one server at a time, calls tools individually, and receives streamed results.
- OAM is **agent-to-agent on a shared bus**. Any participant can discover and invoke any other participant. Fan-out, pub/sub, and async callback patterns are native.

The real differentiators are: runtime discovery across a shared namespace, multi-agent topology (not 1:1 client-server), and typed contracts with catalog-based selection.

The term "synchronous" remains valid in the narrow SLA-gating context (MCP clients block on `tools/call`), but should not be used as the primary positioning distinction.

## Risks and Implications

- As MCP evolves (e.g., agent-to-agent MCP use cases, multi-server orchestration), the comparison will need periodic revisiting.
- Spec files (`km/agentmesh-spec.md`) still use "synchronous" when discussing SLA gating for the MCP bridge. This is correct in context but should not be generalized to MCP's overall interaction model.