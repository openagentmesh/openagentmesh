# ADR-0030: `AgentSpec` Pydantic model as decorator argument

- **Type:** api-design
- **Date:** 2026-04-17
- **Status:** documented
- **Source:** conversation (visual scanability of multiline decorators)

## Context

The `@mesh.agent` decorator (ADR-0023b) accepts registration metadata as keyword arguments: `name`, `channel`, `description`, and others. As agents gain more metadata fields (tags, version, SLA defaults), the decorator call grows into a multiline expression that is hard to scan visually:

```python
@mesh.agent(
    name="classifier",
    channel="nlp",
    description="Classifies text sentiment",
    tags=["nlp", "classification"],
    version="1.0.0",
)
async def classify(req: ClassifyInput) -> ClassifyOutput:
    ...
```

The decorator line should tell you one thing at a glance: "this function is a mesh agent." The metadata belongs in a data object, not stuffed into decorator parentheses.

Three options were considered:

1. **kwargs on the decorator** (status quo). Gets unwieldy as fields grow. Hard to scan.
2. **Dict unpacked with `**config`**. Solves line length but loses type safety and IDE support.
3. **Pydantic model passed as a single argument**. Typed, validated, composable, and keeps the decorator a one-liner.

## Decision

Introduce `AgentSpec`, a Pydantic `BaseModel` that carries all agent registration metadata. The `@mesh.agent` decorator accepts a single `AgentSpec` instance.

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

spec = AgentSpec(
    name="classifier",
    channel="nlp",
    description="Classifies text sentiment",
    tags=["nlp", "classification"],
)

@mesh.agent(spec)
async def classify(req: ClassifyInput) -> ClassifyOutput:
    return ClassifyOutput(label="positive", confidence=0.95)
```

Three visual blocks, each with a single responsibility:

1. **Spec** declares what this agent is.
2. **Decorator** binds the spec to the handler (one line, always).
3. **Handler** declares what this agent does.

### `AgentSpec` model

```python
class AgentSpec(BaseModel):
    name: str
    description: str
    channel: str | None = None
    tags: list[str] = []
    version: str = "0.1.0"
```

No `type` field. Behavioral capabilities (`invocable`, `streaming`) are inferred from the handler shape by the SDK at registration time (see ADR-0031).

Fields align with `CatalogEntry` (ADR-0028) and the contract schema. `AgentSpec` is the provider-side declaration; `CatalogEntry` is the consumer-side projection. They share a common core but serve different audiences.

### Streaming agent example

```python
spec = AgentSpec(
    name="summarizer",
    channel="nlp",
    description="Summarizes text using an LLM, streaming tokens as they arrive",
)

@mesh.agent(spec)
async def summarize(req: SummarizeInput) -> SummarizeChunk:
    async for token in call_llm_stream(req.text):
        yield SummarizeChunk(delta=token)
```

### Event emitter example

```python
spec = AgentSpec(
    name="price-feed",
    channel="finance",
    description="Emits real-time price events for equities",
)

@mesh.agent(spec)
async def monitor_prices() -> PriceEvent:
    while True:
        yield PriceEvent(symbol="AAPL", price=await fetch_price())
        await asyncio.sleep(1)
```

### Capability inference

The SDK infers `invocable` and `streaming` from the handler shape at registration time (ADR-0031). The developer does not declare these; the spec carries only human-authored metadata.

### Reuse and composition

Because `AgentSpec` is a Pydantic model, specs can be built programmatically, loaded from config files, or composed:

```python
# Shared defaults
nlp_base = dict(channel="nlp", tags=["nlp"])

classifier_spec = AgentSpec(name="classifier", description="...", **nlp_base)
summarizer_spec = AgentSpec(name="summarizer", description="...", **nlp_base)
```

### Relationship to `AgentContract`

`AgentSpec` is what the developer provides at registration time. `AgentContract` is the full contract stored in the registry, which includes spec fields plus SDK-inferred fields (`capabilities.streaming`, input/output schemas, SLA defaults). The SDK constructs the `AgentContract` from the `AgentSpec` plus handler introspection.

## Consequences

- All code samples in docs, ADRs, and cookbook recipes must be updated to use `AgentSpec`.
- `AgentSpec` must be exported from the `openagentmesh` public package alongside `AgentMesh`.
- The decorator signature changes from `mesh.agent(**kwargs)` to `mesh.agent(spec: AgentSpec)`. This is a breaking change to the API surface defined in ADR-0023b, but no implementation exists yet.
- Quickstart "hello world" gains one extra line (the spec assignment) but the decorator stays a one-liner. Net readability improves for anything beyond trivial examples.

## Alternatives Considered

**Keep kwargs, recommend dict unpacking for long calls.** `@mesh.agent(**config)` solves line length but `config` is an untyped dict. No validation until decoration time, no IDE autocomplete on the dict keys. Rejected: half-measure that loses the main benefit of Pydantic.

**Accept both kwargs and AgentSpec (hybrid).** `@mesh.agent(name="...", ...)` for simple cases, `@mesh.agent(spec)` for complex ones. Two code paths, two documentation styles, and the kwargs form still encourages multiline decorators. Rejected: API surface complexity not justified. One way to do it is clearer.
