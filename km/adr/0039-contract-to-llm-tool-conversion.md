# ADR-0039: Contract-to-LLM-Tool Conversion

- **Type:** api-design
- **Date:** 2026-04-20
- **Status:** spec
- **Source:** conversation

## Context

`AgentContract` already holds everything needed to produce a provider-native tool definition: `name`, `description`, `input_schema` (Pydantic v2 JSON Schema), `invocable`, `streaming`. The SDK promises LLM interop, and prior docs (km/agentmesh-spec.md, ADR-0023, ADR-0028) assume conversion methods exist. They do not exist yet. This ADR specifies them.

### The landscape

Every major LLM framework (OpenAI, Anthropic, LangChain, LiteLLM, Haystack, AutoGen, PydanticAI, CrewAI) uses JSON Schema as the parameter specification for tools. They differ only in the envelope wrapping it. The common denominator is a triple: **name + description + JSON Schema of the input**.

| Provider / Framework | Format |
|---|---|
| OpenAI Chat Completions | `{"type":"function","function":{"name","description","parameters": <schema>}}` |
| OpenAI Responses API | `{"type":"function","name","description","parameters": <schema>}` (flat) |
| Anthropic Messages | `{"name","description","input_schema": <schema>}` (flat) |
| LangChain, LiteLLM, AutoGen | Accept OpenAI-format dicts directly |
| MCP | `{"name","description","inputSchema": <schema>}` |

Frameworks like PydanticAI and CrewAI require a callable, not a dict. That is a bridge concern (future ADR), not a schema concern.

### Provider-specific constraints

OAM names can contain dots (`billing.invoice.create`) which providers reject. The name regex across providers is `^[a-zA-Z0-9_-]{1,64}$`.

OpenAI offers an opt-in strict mode that imposes heavy schema constraints: `additionalProperties: false` on every object, all properties in `required` (optionals become `{"type": ["T", "null"]}`), and strips keywords like `format`, `pattern`, min/max constraints, `default`, `title`. Anthropic has no equivalent strict mode.

Pydantic v2 schemas include `title` and allow optional fields absent from `required`, both of which break OpenAI strict mode.

Streaming, `chunk_schema`, and `output_schema` have no home in any exported tool shape.

## Decision

Add three methods on `AgentContract`:

```python
def to_tool_schema(self) -> dict[str, Any]: ...
def to_openai_tool(self, *, api: Literal["chat", "responses"] = "chat", strict: bool = False) -> dict[str, Any]: ...
def to_anthropic_tool(self) -> dict[str, Any]: ...
```

All three raise `ValueError` when `invocable` is False (publishers cannot be tools).

### `to_tool_schema()`: the core

Returns the provider-neutral canonical triple:

```python
{
    "name": "summarizer",
    "description": "Summarizes text. Returns: summary.",
    "input_schema": {"type": "object", "properties": {...}, "required": [...]}
}
```

This is the method most callers should use. It is directly consumable by Anthropic's API, LangChain, LiteLLM, and any framework that accepts a JSON Schema dict.

Normalization applied:

1. **Name**: dots in `name` replaced with `_`. Result is asserted to match `^[a-zA-Z0-9_-]{1,64}$`; if it does not, raise `ValueError` so the user fixes the agent name at registration time rather than mangling tool names silently.
2. **Description**: used verbatim. If `output_schema` is present, append one line: `Returns: {top-level field names}.` (see "Output schema handling" below).
3. **Input schema**: `input_schema` passed through as-is.
4. **Streaming / `chunk_schema`**: silently dropped. Not representable in any tool format.

### `to_openai_tool()`: OpenAI envelope

Wraps `to_tool_schema()` in the OpenAI envelope. Two variants:

```python
# Chat Completions (default)
{"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

# Responses API
{"type": "function", "name": ..., "description": ..., "parameters": ...}
```

When `strict=True`, the schema is run through `_strict_clean_schema()` before wrapping:
- Sets `additionalProperties: false` on every object
- Moves every property into `required`; optional fields become `{"type": ["T", "null"]}`
- Strips unsupported keywords (`format`, `pattern`, `minLength`, `maxLength`, `minimum`, `maximum`, `minItems`, `maxItems`, `default`, `title`)
- Sets `"strict": true` on the function definition

Note: `strict` is an OpenAI-specific concept. Anthropic has no equivalent, so `to_anthropic_tool()` does not accept this parameter.

### `to_anthropic_tool()`: Anthropic envelope

Trivial rename from `to_tool_schema()`: the canonical triple already matches Anthropic's format (`input_schema` key). This method exists for discoverability and symmetry.

```python
{"name": ..., "description": ..., "input_schema": ...}
```

### Code sample (DX contract)

```python
from openagentmesh import AgentMesh

mesh = AgentMesh()
async with mesh:
    # Discover and convert
    contracts = await mesh.discover(channel="finance")
    invocable = [c for c in contracts if c.invocable]

    # Provider-neutral (works with LangChain, LiteLLM, Anthropic, etc.)
    tools = [c.to_tool_schema() for c in invocable]

    # OpenAI Chat Completions
    openai_tools = [c.to_openai_tool() for c in invocable]

    # OpenAI with strict mode
    openai_strict = [c.to_openai_tool(strict=True) for c in invocable]

    # OpenAI Responses API
    openai_resp = [c.to_openai_tool(api="responses") for c in invocable]

    # Anthropic Messages API
    anthropic_tools = [c.to_anthropic_tool() for c in invocable]

    # Single conversion
    contract = await mesh.contract("summarizer")
    tool = contract.to_tool_schema()
    # {"name": "summarizer",
    #  "description": "Summarizes text. Returns: summary.",
    #  "input_schema": {"type": "object", "properties": {...}, "required": [...]}}
```

### Output schema handling

No provider format carries output schema. The decision: append a one-line `Returns: <top-level field names>` to the description when `output_schema` is present. This gives the LLM a lightweight hint without inventing a non-standard field. The full schema stays accessible via `contract.output_schema` for callers who need it.

### Non-invocable contracts

All three methods raise `ValueError("Agent '<name>' is not invocable (publisher)")` when `invocable=False`. Callers filter with `if c.invocable` (as shown in the code sample) before converting in bulk.

### Shared internals

A private `_strict_clean_schema(schema: dict) -> dict` helper encodes the OpenAI strict-mode transform. It is reused by both `api="chat"` and `api="responses"` branches. It is not exposed to `to_anthropic_tool()` or `to_tool_schema()`, since strict mode is an OpenAI-specific concept.

A private `_build_description(description: str, output_schema: dict | None) -> str` helper appends the `Returns:` line when output_schema is present. Shared by all three public methods.

A private `_sanitize_name(name: str) -> str` helper replaces dots with underscores and validates the result. Shared by all three public methods.

## Alternatives Considered

- **Only `to_openai_tool()` and `to_anthropic_tool()`, no `to_tool_schema()`.** Rejected. The provider-neutral triple is the common denominator; provider methods are thin envelopes on top. Forcing users to pick a provider when they just want the schema is unnecessary friction. Most framework integrations (LangChain, LiteLLM) can consume the triple directly.
- **Single `to_tool(provider=...)`.** Rejected. Separate methods are more discoverable, give better type hints per provider, and match prior art (LangChain's `convert_to_openai_tool` / `convert_to_anthropic_tool`).
- **`strict` parameter on `to_anthropic_tool()`.** Rejected. Anthropic has no native strict mode for tool schemas. Applying OpenAI's constraints (all-required, strip format/pattern/min-max) would degrade the schema for no provider-side reason. Users who want a simplified schema for any provider can call `_strict_clean_schema()` themselves, but that's a power-user escape hatch, not a default API.
- **Add `to_mcp_tool()` in the same ADR.** Deferred. MCP is covered by ADR-0002 (bidirectional MCP bridge). MCP is the only format that carries `outputSchema`, which makes it substantively different. Keep this ADR tight.
- **Convenience aggregators `mesh.as_openai_tools()` / `mesh.as_anthropic_tools()`.** Rejected. The one-liner `[c.to_tool_schema() for c in await mesh.discover(...)]` is explicit and composable with filtering. Aggregators can be added later if the pattern proves noisy.
- **Strict mode on by default for OpenAI.** Rejected. Strict imposes destructive schema transforms and is incompatible with `parallel_tool_calls`. Surface it as opt-in.
- **Prefix tool name with channel** (`finance__scorer`). Rejected for the default. Tool name collisions are rare within a selected subset, and prefixed names are ugly in LLM outputs. Callers can post-process if needed.
- **Silently mangle invalid names.** Rejected. Raising a clear `ValueError` at conversion time pushes the fix upstream to the `AgentSpec` where it belongs.

## Risks and Implications

- The strict-mode cleaner is a small, opinionated implementation of OpenAI's undocumented-in-spec schema constraints. Provider changes may break it; the constraints have shifted once before. Tests pin the current shape.
- Appending "Returns: ..." to description is visible to the LLM and uses a few tokens. Acceptable trade for preserving output information.
- `name` with a dot raises `ValueError` at conversion. Teams that already registered agents with dotted names will see this when exposing them as LLM tools for the first time. Document in the tool-selection cookbook recipe.
- Tool-name sanitization is lossy (`finance.scorer` and an existing `finance_scorer` would collide). Unlikely in practice; surface via a test case.
- Frameworks that need a callable (PydanticAI, CrewAI) cannot use these methods directly. A future ADR should address bridge functions that wrap `mesh.call()` as a framework-native tool. This ADR intentionally stays at the schema level.
