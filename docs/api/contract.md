# AgentContract

Represents a registered agent's full contract. Retrieved via `mesh.contract()` or `mesh.discover()`.

## LLM Tool Conversion

### `.to_openai_tool()`

Returns the contract in OpenAI function calling format.

```python
contract = await mesh.contract("summarizer")
tool = contract.to_openai_tool()
# Pass to OpenAI's tools parameter
```

### `.to_anthropic_tool()`

Returns the contract in Anthropic tool use format.

```python
tool = contract.to_anthropic_tool()
# Pass to Anthropic's tools parameter
```

### `.to_generic_tool()`

Returns a generic JSON Schema tool definition.

```python
tool = contract.to_generic_tool()
```

### `.to_agent_card(url=None)`

Projects the contract to A2A Agent Card format. A thin projection — injects `url` if provided.

```python
card = contract.to_agent_card()

# At a federation boundary, provide the external URL
card = contract.to_agent_card(url="https://api.company.com/agents/summarizer")
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str \| None` | `None` | External URL for federation |

## Properties

| Property | Type | Description |
|----------|------|-------------|
| `name` | `str` | Agent name |
| `description` | `str` | LLM-consumable description |
| `version` | `str` | Semantic version |
| `channel` | `str \| None` | Channel namespace |
| `tags` | `list[str]` | Searchable tags |
| `input_schema` | `dict` | JSON Schema for input |
| `output_schema` | `dict` | JSON Schema for output |
| `capabilities` | `dict` | Capability flags |
| `sla` | `dict` | SLA metadata |
