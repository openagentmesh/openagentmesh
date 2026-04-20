# ADR-0005: Streaming wire protocol with per-request stream subjects

- **Type:** protocol
- **Date:** 2026-04-11
- **Status:** documented
- **Source:** km/notes/20260411_On JSON-RPC and MCP bridges.md

## Context

NATS has no built-in chunked response for request/reply. The contract schema already has `capabilities.streaming: true` but the wire protocol for delivering streamed responses was undefined. Additionally, MCP bridge needs to translate SSE progress notifications to/from NATS.

## Decision

### Wire Protocol

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
- `X-Mesh-Status: error`: response-side on stream subject, signals handler error during streaming

### Capability Enforcement

The SDK maintains a local catalog cache, updated via a catalog change subscription (started on connect, stopped on disconnect). This cache enables pre-flight capability checks without a round trip.

**Client-side (primary):** `mesh.stream()` checks the catalog cache before publishing. If the target agent does not support streaming, raises `StreamingNotSupported` locally. `mesh.call()` checks the inverse: if the target agent is streaming-only, raises `StreamingRequired` locally.

**Handler-side (defense-in-depth):** If a request with `X-Mesh-Stream: true` reaches a non-streaming handler (e.g., stale cache, direct NATS publish), the handler responds with a `MeshError` using code `streaming_not_supported`. The reverse case (`streaming_required`) is enforced the same way.

### Error Subclasses

Three new `MeshError` subclasses for typed exception handling:

```python
from openagentmesh import MeshError

class StreamingNotSupported(MeshError):
    """Raised when mesh.stream() targets a responder agent."""
    # code: "streaming_not_supported"

class StreamingRequired(MeshError):
    """Raised when mesh.call() targets a streaming-only agent."""
    # code: "streaming_required"

class ChunkSequenceError(MeshError):
    """Raised when stream chunks arrive out of order."""
    # code: "chunk_sequence_error"
    # details: {"expected_seq": int, "got_seq": int}
```

Callers can catch specific errors:

```python
try:
    async for chunk in mesh.stream("summarizer", payload):
        print(chunk["delta"], end="")
except StreamingNotSupported:
    # agent doesn't support streaming, fall back to mesh.call()
    result = await mesh.call("summarizer", payload)
```

### Chunk Ordering

NATS core pub/sub guarantees per-publisher message ordering on a single subject. Since the handler publishes chunks sequentially from a single coroutine to `mesh.stream.{request_id}`, chunks arrive in order. The client validates `X-Mesh-Stream-Seq` against an expected counter and raises `ChunkSequenceError` on mismatch rather than implementing reordering.

### Error Propagation During Streaming

If the handler's async generator raises during iteration (after some chunks have already been published), the error is published to the stream subject with `X-Mesh-Stream-End: true` and `X-Mesh-Status: error`. The body contains the standard error envelope. The client detects this and raises the appropriate `MeshError`.

### SDK Method

```python
async for chunk in mesh.stream("agent-name", payload, timeout=30.0):
    # chunk is a dict (deserialized JSON)
```

`mesh.call()` (responder) remains the default; streaming is opt-in on both sides.

## Risks and Implications

- New subject namespace `mesh.stream.*` must be documented and reserved.
- Catalog change subscription adds one subscription per mesh instance. Catalog may be momentarily stale (milliseconds); handler-side enforcement covers the gap.
- MCP bridge translation adds latency per chunk (SSE to NATS pub or vice versa). Acceptable for the bridging use case.
- The `ChunkSequenceError` path should be unreachable under normal operation (NATS ordering guarantee). It exists as a defensive check.
