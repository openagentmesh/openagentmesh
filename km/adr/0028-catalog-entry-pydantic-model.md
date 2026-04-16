# ADR-0028: `mesh.catalog()` returns typed `CatalogEntry` Pydantic models

- **Type:** api-design
- **Date:** 2026-04-14
- **Status:** spec
- **Source:** conversation (cookbook design discussion on catalog consumer DX)

## Context

All existing documentation, recipes, and spec examples show `mesh.catalog()` returning a raw list of dicts:

```python
catalog = await mesh.catalog()
for entry in catalog:
    print(entry["name"], "-", entry["description"])
```

The rest of the SDK is strongly typed throughout: handler inputs and outputs are Pydantic `BaseModel` instances, `mesh.contract()` returns `AgentContract` objects, and `mesh.discover()` returns `list[AgentContract]`. Using raw dicts for catalog entries is inconsistent and loses IDE support for the most common discovery operation.

The question surfaced when writing cookbook recipes where consumers iterate the catalog and access fields. `entry["name"]` is fragile (KeyError on typo), not autocompleted, and not self-documenting. The catalog is a first-class developer surface — it is the primary way both humans and LLMs browse available agents.

## Decision

`mesh.catalog()` returns `list[CatalogEntry]` where `CatalogEntry` is a Pydantic `BaseModel`.

```python
catalog = await mesh.catalog()
for entry in catalog:
    print(entry.name, "-", entry.description)

# Filtering still works as before
nlp_agents = await mesh.catalog(channel="nlp")
tagged = await mesh.catalog(tags=["summarization"])
```

### `CatalogEntry` model

`CatalogEntry` mirrors the lightweight catalog index fields defined in ADR-0021 and the spec:

```python
class CatalogEntry(BaseModel):
    name: str
    channel: str | None = None
    description: str
    version: str
    tags: list[str] = []
    type: str = "agent"   # "agent" | "tool" | "publisher" | "mcp_bridge"
```

All fields match what is already stored in the `mesh-catalog` KV key. No additional data is fetched; the model is deserialized from the existing catalog payload.

### LLM tool selection pattern

The catalog is frequently fed to an LLM for tool selection. `CatalogEntry` provides a clean projection without pulling full `AgentContract` objects:

```python
catalog = await mesh.catalog(channel="nlp")
# Pass to LLM — CatalogEntry.model_dump() produces clean dicts when needed
tools_for_llm = [e.model_dump(include={"name", "description", "tags"}) for e in catalog]
```

When the LLM selects an agent, the consumer fetches the full contract:

```python
contract = await mesh.contract(selected_name)
tool_def = contract.to_anthropic_tool()
```

## Consequences

- All documentation, recipes, and examples that use `entry["name"]` must be updated to `entry.name`.
- The internal deserialization in `mesh.catalog()` changes from returning raw parsed JSON to constructing `CatalogEntry` instances. This is a small implementation change.
- `CatalogEntry` must be exported from the `openagentmesh` public package.
- `CatalogEntry` is intentionally a subset of `AgentContract`. Callers who need the full schema call `mesh.contract(name)`.

## Alternatives Considered

**Keep raw dicts.** No SDK changes needed. Rejected: inconsistent with the rest of the API, loses IDE support, fragile for typos.

**dataclass or NamedTuple.** Lighter than Pydantic. Rejected: the entire SDK uses Pydantic for validation and serialization. Introducing a second type system for one class would be inconsistent and would lose `model_dump()` / JSON round-trip support needed for LLM tool injection.
