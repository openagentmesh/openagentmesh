# Discovery

OpenAgentMesh uses a two-tier discovery system designed for efficient agent selection, including by LLMs.

## Tier 1: Catalog

The catalog is a lightweight index: a single KV key (`mesh-catalog`) containing a JSON array of summary entries. `mesh.catalog()` returns typed `CatalogEntry` objects.

```python
catalog = await mesh.catalog()
for entry in catalog:
    print(entry.name, "-", entry.description)
    print(f"  invocable={entry.invocable}, streaming={entry.streaming}")
```

Each entry is compact (~20-30 tokens per agent), making the full catalog suitable for direct inclusion in LLM context up to ~500 agents without RAG or vector search.

### Filtering

```python
# By channel
catalog = await mesh.catalog(channel="nlp")

# By tags
catalog = await mesh.catalog(tags=["summarization"])

# By capability
streaming_agents = await mesh.catalog(streaming=True)
buffered_agents = await mesh.catalog(streaming=False)
event_emitters = await mesh.catalog(invocable=False)
```

## Tier 2: Full Contract

Once the catalog narrows the candidates, fetch the full contract for a specific agent:

```python
contract = await mesh.contract("summarizer")

contract.name             # "summarizer"
contract.description      # "Summarizes text..."
contract.input_schema     # JSON Schema dict
contract.invocable        # True
contract.streaming        # False
```

This returns the complete `AgentContract` with JSON Schemas and all capabilities. This is the authoritative source; the catalog may be momentarily stale (milliseconds) due to CAS update windows.

## Full Discovery

For programmatic use cases that need all contracts at once:

```python
agents = await mesh.discover()
agents = await mesh.discover(channel="nlp")
```

## Catalog Cache

The SDK maintains a local cache of the catalog, updated automatically via a background subscription to catalog changes. This enables:

- **Pre-flight capability checks.** `mesh.call()` and `mesh.stream()` verify the target agent's capabilities before sending a request, avoiding a wasted round trip on capability mismatch.
- **Fast `mesh.catalog()` reads.** No KV fetch on every call; the cache is always current within milliseconds.

Local agents (registered on the same mesh instance) are seeded into the cache immediately on registration. Remote agents appear in the cache as soon as the catalog change subscription delivers the update.

## Design Rationale

The two-tier approach avoids the common pitfalls:

- **No RAG needed.** The catalog is small enough for direct LLM consumption.
- **No over-fetching.** You only pull full schemas for agents you intend to call.
- **CAS consistency.** Concurrent registrations retry read-modify-write until the KV revision matches.
- **Eventually consistent catalog.** The cache may be momentarily stale (milliseconds). Handler-side enforcement covers the gap for capability checks.
