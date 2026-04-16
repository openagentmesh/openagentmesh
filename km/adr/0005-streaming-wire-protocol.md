# ADR-0005: Streaming wire protocol with per-request stream subjects

- **Type:** protocol
- **Date:** 2026-04-11
- **Status:** accepted
- **Source:** km/notes/20260411_On JSON-RPC and MCP bridges.md

## Context

NATS has no built-in chunked response for request/reply. The contract schema already has `capabilities.streaming: true` but the wire protocol for delivering streamed responses was undefined. Additionally, MCP bridge needs to translate SSE progress notifications to/from NATS.

## Decision

Introduce a per-request streaming subject:

```
Request:  mesh.agent.{channel}.{name}     (with X-Mesh-Stream: true header)
Chunks:   mesh.stream.{request_id}        (N messages, each a partial response)
Terminal: mesh.stream.{request_id}        (final message, X-Mesh-Stream-End: true)
```

New headers:
- `X-Mesh-Stream: true`: request-side, caller wants streaming
- `X-Mesh-Stream-Seq: N`: response-side, chunk sequence number (0-indexed)
- `X-Mesh-Stream-End: true`: response-side, final chunk

New SDK method:
```python
async for chunk in mesh.stream("agent-name", payload, timeout=30.0):
    # chunk.delta, chunk.seq, chunk.done
```

Capability enforcement: if a caller sends `X-Mesh-Stream: true` to an agent with `streaming: false`, the agent returns a `MeshError` with `code: "streaming_not_supported"`. No silent fallback to buffered mode.

## Risks and Implications

- New subject namespace `mesh.stream.*` must be documented and reserved.
- Chunk ordering relies on sequence numbers, not NATS delivery order (NATS subjects are unordered by default). Consumers must buffer and reorder if needed.
- MCP bridge translation adds latency per chunk (SSE → NATS pub or vice versa). Acceptable for the bridging use case.
- `mesh.call()` (buffered) remains the default; streaming is opt-in on both sides.
