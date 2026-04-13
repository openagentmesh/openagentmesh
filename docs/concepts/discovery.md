# Discovery

OpenAgentMesh uses a two-tier discovery system designed for efficient agent selection, including by LLMs.

## Tier 1: Catalog

The catalog is a lightweight index: a single KV key (`mesh.catalog`) containing a JSON array of summary entries.

```python
catalog = await mesh.catalog()
for entry in catalog:
    print(entry["name"], "-", entry["description"])

# [
#   {"name": "summarizer", "channel": "nlp", "description": "Summarizes text to a target length.",
#    "version": "1.0.0", "tags": ["text", "summarization"]},
#   {"name": "sentiment", "channel": "nlp", "description": "Classifies sentiment of input text.",
#    "version": "1.2.0", "tags": ["text", "classification"]},
#   ...
# ]
```

Each entry is compact (~20-30 tokens per agent), making the full catalog suitable for direct inclusion in LLM context up to ~500 agents without RAG or vector search.

### Filtering

```python
# By channel
catalog = await mesh.catalog(channel="nlp")

# By tags
catalog = await mesh.catalog(tags=["summarization"])
```

## Tier 2: Full Contract

Once the catalog narrows the candidates, fetch the full contract for a specific agent:

```python
contract = await mesh.contract("summarizer")

# AgentContract(
#   name="summarizer",
#   description="Summarizes text to a target length.",
#   version="1.0.0",
#   capabilities={"streaming": False, "pushNotifications": True},
#   skills=[Skill(id="summarizer", tags=["text", "summarization"], input_schema={...}, output_schema={...})],
#   x_agentmesh={"type": "agent", "channel": "nlp", "subject": "mesh.agent.nlp.summarizer", "sla": {...}},
# )
```

This returns the complete `AgentContract` with JSON Schemas, SLA metadata, error schema, and all capabilities. This is the authoritative source; the catalog may be momentarily stale (milliseconds) due to CAS update windows.

## Full Discovery

For programmatic use cases that need all contracts at once:

```python
agents = await mesh.discover()
agents = await mesh.discover(channel="nlp")

# [
#   AgentContract(name="summarizer", channel="nlp", version="1.0.0", ...),
#   AgentContract(name="sentiment", channel="nlp", version="1.2.0", ...),
# ]
```

## Design Rationale

The two-tier approach avoids the common pitfalls:

- **No RAG needed.** The catalog is small enough for direct LLM consumption.
- **No over-fetching.** You only pull full schemas for agents you intend to call.
- **CAS consistency.** Concurrent registrations retry read-modify-write until the KV revision matches.
