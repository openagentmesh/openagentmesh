# AgentContract

Represents a registered agent's full contract. Retrieved via `mesh.contract()` or `mesh.discover()`.

The contract schema is a superset of the A2A Agent Card format. A2A fields at the top level; OAM-specific fields under `x-agentmesh` when serialized.

## Using Contracts for LLM Tool Injection

Contracts carry the schemas needed to build LLM tool definitions.

```python
contract = await mesh.contract("summarizer")

# Build a tool definition for your LLM provider
tool = {
    "name": contract.name,
    "description": contract.description,
    "input_schema": contract.input_schema,
}

# For streaming agents, chunk_schema describes each yielded chunk
if contract.streaming:
    print(contract.chunk_schema)
```

### Two-step discovery for LLM tool selection

Use `catalog()` for lightweight browsing (20-30 tokens per agent), then `contract()` for the full schema of the selected agent:

```python
# Step 1: lightweight listing for LLM to pick from
catalog = await mesh.catalog(channel="nlp")
options = [{"name": e.name, "description": e.description} for e in catalog]

# Step 2: full schema for the selected agent
contract = await mesh.contract(selected_name)
tool_def = {
    "name": contract.name,
    "description": contract.description,
    "input_schema": contract.input_schema,
}
```

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Agent name |
| `description` | `str` | LLM-consumable description |
| `version` | `str` | Semantic version |
| `channel` | `str \| None` | Channel namespace |
| `tags` | `list[str]` | Searchable tags |
| `invocable` | `bool` | Whether the agent accepts requests |
| `streaming` | `bool` | Whether the agent streams responses |
| `input_schema` | `dict \| None` | JSON Schema for input model |
| `output_schema` | `dict \| None` | JSON Schema for output model (buffered agents) |
| `chunk_schema` | `dict \| None` | JSON Schema for chunk model (streaming agents) |
| `capabilities` | `dict` | Capability flags (`streaming`, `invocable`) |
| `subject` | `str` | NATS invocation subject |

## Methods

### `.to_catalog_entry()`

Project to a lightweight `CatalogEntry`.

```python
entry = contract.to_catalog_entry()
# CatalogEntry(name="summarizer", description="...", invocable=True, streaming=False)
```

### `.to_registry_json()`

Serialize to the registry JSON format (A2A-compatible with `x-agentmesh` namespace).

```python
json_str = contract.to_registry_json()
```
