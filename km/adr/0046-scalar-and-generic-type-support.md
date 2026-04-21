# ADR-0046: Scalar and generic type support via TypeAdapter

- **Type:** api-design
- **Date:** 2026-04-21
- **Status:** documented
- **Amends:** ADR-0031 (broadens type inference beyond BaseModel)
- **Source:** conversation (verbose BaseModel wrappers for simple types)

## Context

All five handler shapes (ADR-0031, ADR-0043) require `BaseModel` subclasses for input and output types. Handlers that accept or return a simple value force the developer to create a wrapper model:

```python
# Current: wrapper model just for a string
class GreetInput(BaseModel):
    name: str

class GreetOutput(BaseModel):
    message: str

@mesh.agent(spec)
async def greet(req: GreetInput) -> GreetOutput:
    return GreetOutput(message=f"Hello, {req.name}")
```

This is unnecessary ceremony when the payload is a single scalar. The developer should be able to write:

```python
@mesh.agent(spec)
async def greet(name: str) -> str:
    return f"Hello, {name}"
```

The same applies to other scalar types (`int`, `float`, `bool`), standard library types (`datetime`, `UUID`), and generic containers (`list[str]`, `dict[str, int]`, `Optional[X]`).

## Decision

Replace all `BaseModel`-specific type checks in the handler inspection and message handling paths with Pydantic v2's `TypeAdapter`. TypeAdapter handles both `BaseModel` and any type Pydantic can validate, providing a uniform interface for schema generation, validation, and serialization.

### What changes

1. **`inspect_handler()`**: Accept any type hint for input/output, not just `BaseModel` subclasses. Store `TypeAdapter` instances instead of raw model classes.
2. **`HandlerInfo`**: Replace `input_model: type[BaseModel] | None` with `input_adapter: TypeAdapter | None` (same for output).
3. **Schema generation** in `agent()` decorator: Call `adapter.json_schema()` instead of `model.model_json_schema()`.
4. **Input validation**: Call `adapter.validate_json(data)` instead of `model.model_validate_json(data)`.
5. **Output serialization**: Call `adapter.dump_json(result)` instead of `model.model_dump_json()` or `json.dumps()`.

### What stays the same

- Handler shape inference rules (ADR-0031, ADR-0042, ADR-0043) are unchanged. The five patterns still map to the same capability combinations.
- `BaseModel` types work identically; TypeAdapter wraps them transparently.
- Client-side `mesh.call()` and `mesh.stream()` still return `dict` (or scalar). No change to `_serialize_payload`.
- Contract schema fields (`input_schema`, `output_schema`, `chunk_schema`) remain JSON Schema dicts.

### Accepted types

Any type that Pydantic v2's `TypeAdapter` can process. This includes:

- Scalars: `str`, `int`, `float`, `bool`
- Standard library: `datetime`, `date`, `UUID`, `Path`, `Decimal`, `Enum` subclasses
- Generics: `list[X]`, `dict[str, X]`, `set[X]`, `tuple[X, ...]`
- Optionals and unions: `Optional[X]`, `X | None`, `Union[X, Y]`
- Literals: `Literal["a", "b"]`
- Pydantic models: `BaseModel` subclasses (unchanged behavior)

Types that cannot produce a JSON Schema (callables, IO objects, raw `TypeVar`) raise `PydanticSchemaGenerationError` at decoration time, not at runtime.

### Code sample

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

# Scalar input and output
spec = AgentSpec(name="greet", description="Greets by name.")

@mesh.agent(spec)
async def greet(name: str) -> str:
    return f"Hello, {name}"

# Generic container output
spec_words = AgentSpec(name="split", description="Splits text into words.")

@mesh.agent(spec_words)
async def split(text: str) -> list[str]:
    return text.split()

# Scalar trigger (no input)
spec_count = AgentSpec(name="agent-count", description="Returns the number of registered agents.")

@mesh.agent(spec_count)
async def agent_count() -> int:
    catalog = await mesh.catalog()
    return len(catalog)
```

### Contract representation

Scalar types produce standard JSON Schema:

```json
{
  "name": "greet",
  "input_schema": { "type": "string" },
  "output_schema": { "type": "string" }
}
```

```json
{
  "name": "split",
  "input_schema": { "type": "string" },
  "output_schema": { "type": "array", "items": { "type": "string" } }
}
```

### Invocability inference

The inference rule does not change. A handler is invocable when it has an input type (any type, not just BaseModel) or has an output type without streaming:

```
invocable = has_input or (has_output and not streaming)
```

This means `async def f(x: str) -> str` is now correctly recognized as a Responder, where previously it was silently treated as a Watcher.

## Consequences

- `_handler.py`: Replace `issubclass(*, BaseModel)` checks with `TypeAdapter` construction. Store adapters on `HandlerInfo`.
- `_mesh.py`: Use adapter `.json_schema()`, `.validate_json()`, `.dump_json()` throughout registration and message handling.
- Existing tests continue to pass unchanged (BaseModel types still work via TypeAdapter).
- New tests cover scalar input/output for each handler shape.
- `docs/concepts/agents.md`: Add note and examples showing scalar types.

## Alternatives Considered

**Allowlist of scalar types.** Would require maintaining a list and special-casing each one. TypeAdapter already handles this uniformly.

**Auto-wrap scalars in a BaseModel.** Would preserve the BaseModel-only code paths but adds hidden complexity, produces confusing schemas (wrapper model appears in the JSON Schema), and breaks the principle that the handler's type hints are the source of truth.
