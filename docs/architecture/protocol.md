# Protocol

OpenAgentMesh is protocol-first. The core asset is a contract schema and subject naming convention that any NATS client in any language can implement. The Python SDK is a convenience layer.

## Participation Without the SDK

Any NATS client can participate in the mesh by following the protocol:

| Protocol concept | What to implement |
|-----------------|-------------------|
| Subject `mesh.agent.{channel}.{name}` | Subscribe with a queue group |
| KV key `mesh-registry.{channel}.{name}` | Write contract JSON on startup |
| KV key `mesh-catalog` | CAS-update the catalog array |
| `X-Mesh-Request-Id` header | Generate per request, echo in response |
| `X-Mesh-Status` header | Set to `ok` or `error` |

## Registry

Two tiers of state in NATS JetStream KV:

### Catalog (`mesh-catalog`)

Single KV key containing a JSON array of lightweight entries:

```json
[
  {
    "name": "summarizer",
    "channel": "nlp",
    "description": "Summarizes text to a target length.",
    "version": "1.0.0",
    "tags": ["text", "summarization"]
  }
]
```

Updated via CAS (compare-and-swap) on every registration/deregistration. May be momentarily stale during concurrent updates.

### Per-Agent Registry (`mesh-registry.{channel}.{name}`)

Full contract with JSON Schemas, SLA metadata, and error schema. This is the authoritative source for an agent's capabilities.

## Consistency Model

- **Catalog.** Eventually consistent within milliseconds. CAS retries handle concurrent writes.
- **Registry.** Strongly consistent per key. Each agent owns its own key.
- **Discovery.** `mesh.contract()` reads from registry (authoritative). `mesh.catalog()` reads from catalog (fast, possibly stale).
