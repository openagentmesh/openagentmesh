# Protocol

OpenAgentMesh is protocol-first. The core asset is a contract schema and subject naming convention that any compliant transport can implement. The Python SDK is a convenience layer; the reference implementation uses NATS, but the protocol itself is transport-agnostic.

## Required Transport Primitives

Any transport that provides the following primitives can host an OpenAgentMesh deployment:

| Primitive | Description |
|-----------|-------------|
| **Pub/Sub with queue groups** | Publish messages to named subjects; subscribers in the same queue group receive load-balanced delivery |
| **Request/Reply** | Synchronous request to a subject with a single response |
| **Key-Value store** | Per-key read/write with compare-and-swap (CAS) support |
| **Object store** | Binary blob storage for large payloads |
| **Message headers** | Arbitrary key-value metadata attached to each message |

## Participation Without the SDK

Any client speaking the underlying transport can participate in the mesh by following the protocol:

| Protocol concept | What to implement |
|-----------------|-------------------|
| Subject `mesh.agent.{channel}.{name}` | Subscribe with a queue group |
| KV key `mesh-registry.{channel}.{name}` | Write contract JSON on startup |
| KV key `mesh-catalog` | CAS-update the catalog array |
| `X-Mesh-Request-Id` header | Generate per request, echo in response |
| `X-Mesh-Status` header | Set to `ok` or `error` |

## Registry

Two tiers of state in the KV store:

### Catalog (`mesh-catalog`)

Single KV key containing a JSON array of lightweight entries:

```json
[
  {
    "name": "summarizer",
    "channel": "nlp",
    "description": "Summarizes text to a target length.",
    "version": "1.0.0",
    "tags": ["text", "summarization"],
    "invocable": true,
    "streaming": false
  }
]
```

Updated via CAS (compare-and-swap) on every registration/deregistration. May be momentarily stale during concurrent updates.

### Per-Agent Registry (`mesh-registry.{channel}.{name}`)

Full contract with JSON Schemas, SLA metadata, and error schema. This is the authoritative source for an agent's capabilities.

## Storage Buckets

The protocol requires four storage buckets, pre-created on startup by `oam mesh up` (or `AgentMesh.local()` in test contexts).

### KV Stores

| Bucket | Purpose | Key pattern | History | Notes |
|--------|---------|-------------|---------|-------|
| `mesh-catalog` | Lightweight agent index | Single key: `catalog` | 1 | CAS updates on every register/deregister |
| `mesh-registry` | Full agent contracts | `{channel}.{name}` or `{name}` | 1 | One key per agent, authoritative source |
| `mesh-context` | Shared context between agents | Agent-defined | 1 | For structured data (JSON). Explicit delete; no TTL by default |

### Object Store

| Bucket | Purpose | Notes |
|--------|---------|-------|
| `mesh-artifacts` | Binary artifacts shared between agents | For files, images, large payloads |

Bucket names use hyphens, not dots.

## Consistency Model

- **Catalog.** Eventually consistent within milliseconds. CAS retries handle concurrent writes.
- **Registry.** Strongly consistent per key. Each agent owns its own key.
- **Discovery.** `mesh.contract()` reads from registry (authoritative). `mesh.catalog()` reads from catalog (fast, possibly stale).
