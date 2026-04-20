# AgentContract

Represents a registered agent's full contract. Retrieved via `mesh.contract()` or `mesh.discover()`.

The contract schema is a superset of the A2A Agent Card format. A2A fields at the top level; OAM-specific fields under `x-agentmesh` when serialized.

## Using Contracts for LLM Tool Injection

Contracts carry the schemas needed to build LLM tool definitions. Three conversion methods produce ready-to-use tool dicts.

### Provider-neutral (recommended)

`to_tool_schema()` returns a `{name, description, input_schema}` triple that works with Anthropic, LangChain, LiteLLM, and any framework that accepts a JSON Schema dict:

```python
contract = await mesh.contract("summarizer")
tool = contract.to_tool_schema()
# {"name": "summarizer", "description": "...", "input_schema": {...}}
```

### OpenAI

`to_openai_tool()` wraps the schema in the OpenAI envelope. Supports both Chat Completions and the Responses API:

```python
# Chat Completions (default)
tool = contract.to_openai_tool()
# {"type": "function", "function": {"name": ..., "parameters": ...}}

# Responses API
tool = contract.to_openai_tool(api="responses")
# {"type": "function", "name": ..., "parameters": ...}

# Strict mode (opt-in, constrains schema for structured outputs)
tool = contract.to_openai_tool(strict=True)
```

### Anthropic

`to_anthropic_tool()` returns the Anthropic Messages API format (identical to `to_tool_schema()`):

```python
tool = contract.to_anthropic_tool()
# {"name": ..., "description": ..., "input_schema": {...}}
```

### Bulk conversion from discovery

```python
contracts = await mesh.discover(channel="finance")
invocable = [c for c in contracts if c.invocable]

# Pick the format you need
tools = [c.to_tool_schema() for c in invocable]
openai_tools = [c.to_openai_tool() for c in invocable]
anthropic_tools = [c.to_anthropic_tool() for c in invocable]
```

### Two-step discovery for LLM tool selection

Use `catalog()` for lightweight browsing (20-30 tokens per agent), then `contract()` for the full schema of the selected agent:

```python
# Step 1: lightweight listing for LLM to pick from
catalog = await mesh.catalog(channel="nlp")
options = [{"name": e.name, "description": e.description} for e in catalog]

# Step 2: full schema for the selected agent
contract = await mesh.contract(selected_name)
tool = contract.to_tool_schema()
```

### Name sanitization

Agent names with dots (e.g. `billing.invoice.create`) are automatically converted to underscores (`billing_invoice_create`) since LLM providers restrict tool names to `[a-zA-Z0-9_-]`. Names that cannot be sanitized raise `ValueError`.

### Output schema hints

When `output_schema` is present, the description is appended with a `Returns: <field names>` line, giving the LLM a lightweight hint about the response shape. The full schema remains accessible via `contract.output_schema`.

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
| `output_schema` | `dict \| None` | JSON Schema for output model (non-streaming agents) |
| `chunk_schema` | `dict \| None` | JSON Schema for chunk model (streaming agents) |
| `capabilities` | `dict` | Capability flags (`streaming`, `invocable`) |
| `subject` | `str` | NATS invocation subject |

## Methods

### `.to_tool_schema()`

Returns a provider-neutral dict with `name`, `description`, and `input_schema`. Raises `ValueError` if the agent is not invocable.

### `.to_openai_tool(*, api="chat", strict=False)`

Returns an OpenAI-format tool dict. `api="responses"` uses the flat Responses API shape. `strict=True` applies OpenAI's structured output constraints to the schema.

### `.to_anthropic_tool()`

Returns an Anthropic Messages API tool dict. Equivalent to `to_tool_schema()`.

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
