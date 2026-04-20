# ADR-0031: Capabilities over type taxonomy

- **Type:** api-design
- **Date:** 2026-04-17
- **Status:** documented
- **Supersedes:** ADR-0023b (type taxonomy portion only; single decorator decision stands)
- **Source:** conversation (type taxonomy creates arbitrary classifications with confusing edge cases)

## Context

ADR-0023b introduced a `type` field on `@mesh.agent` with four values: `"agent"`, `"tool"`, `"publisher"`, `"subscriber"`. The intent was to carry behavioral signal for consumers. In practice, the agent/tool distinction is arbitrary. ADR-0023b itself acknowledges the problem: "a cached LLM function is both."

The type taxonomy forces developers to self-classify into categories that don't have clean boundaries. Is a fast LLM call with caching a "tool" or an "agent"? Is a deterministic function that takes 5 seconds a "tool" (it's deterministic) or should it have agent-like SLA defaults? These edge cases create friction at registration time for no structural benefit.

Meanwhile, the information consumers actually need is mechanical:

1. **Can I send it a request?** Determines whether `mesh.call()` / `mesh.stream()` work.
2. **Does the response stream?** Determines whether to use `mesh.call()` or `mesh.stream()`.
3. **How fast is it?** SLA fields.
4. **What does it do?** Description.

Items 1 and 2 are already inferable from the handler shape. Items 3 and 4 are already explicit fields. The `type` label was encoding what capabilities and SLA already express structurally.

## Decision

Remove the `type` field from `AgentSpec` and the contract schema. Replace it with two capability booleans, both inferred from the handler shape:

| Capability | Meaning | Inferred from |
|------------|---------|---------------|
| `invocable` | Accepts requests via `mesh.call()` or `mesh.stream()` | Handler has a request parameter, or has an output model without streaming |
| `streaming` | Streams response chunks | Handler is an async generator (`yield`) |

These produce five valid combinations:

| Pattern | `invocable` | `streaming` | Consumer API | Example |
|---------|-------------|-------------|--------------|---------|
| Responder | `true` | `false` | `mesh.call()` | NER extraction, sentiment classifier |
| Streamer | `true` | `true` | `mesh.stream()` | LLM summarizer, translator |
| Trigger | `true` | `false` | `mesh.call()` | Cache refresh, migration runner |
| Event emitter | `false` | `true` | `mesh.subscribe()` | Price feed, log stream |
| Watcher | `false` | `false` | N/A (reacts to KV) | Pipeline stage, state reactor |

The watcher combination was added by ADR-0042. The trigger combination was added by ADR-0043.

### Updated `AgentSpec`

```python
class AgentSpec(BaseModel):
    name: str
    description: str
    channel: str | None = None
    tags: list[str] = []
    version: str = "0.1.0"
```

No `type` field. The capabilities are inferred by the SDK at registration time and stored in the contract, not declared by the developer.

### Updated `CatalogEntry`

```python
class CatalogEntry(BaseModel):
    name: str
    channel: str | None = None
    description: str
    version: str
    tags: list[str] = []
    invocable: bool
    streaming: bool
```

The `type` field is replaced by `invocable` and `streaming`. Catalog filtering uses these booleans:

```python
# Find all streaming agents in the NLP channel
streaming_nlp = await mesh.catalog(channel="nlp", streaming=True)

# Find all non-streaming (responder) agents
tools = await mesh.catalog(streaming=False)

# Find all event emitters
publishers = await mesh.catalog(invocable=False)
```

### Registration examples

```python
# Responder handler — inferred invocable=True, streaming=False
spec = AgentSpec(
    name="classifier",
    channel="nlp",
    description="Classifies text sentiment",
)

@mesh.agent(spec)
async def classify(req: ClassifyInput) -> ClassifyOutput:
    return ClassifyOutput(label="positive", confidence=0.95)


# Streamer handler — inferred invocable=True, streaming=True
spec = AgentSpec(
    name="summarizer",
    channel="nlp",
    description="Summarizes text using an LLM, streaming tokens as they arrive",
)

@mesh.agent(spec)
async def summarize(req: SummarizeInput) -> SummarizeChunk:
    async for token in call_llm_stream(req.text):
        yield SummarizeChunk(delta=token)


# Event emitter — inferred invocable=False, streaming=True
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

No developer decision required. The handler shape carries the structural truth.

### SLA defaults

ADR-0023b tied default SLA values to `type` (tools got 1000ms, agents got 30000ms). Without type, explicit SLA on the spec is the right path. The SDK can set a single reasonable default (e.g. no timeout assumption), and developers override it when they know their latency profile:

```python
spec = AgentSpec(
    name="classifier",
    channel="nlp",
    description="Classifies text sentiment",
    sla=SLA(expected_latency_ms=500),
)
```

This is better than type-based defaults anyway: a "tool" that calls an external API might be slow, and an "agent" with a cached response might be fast. Explicit SLA is always more accurate than a guess based on taxonomy.

## Consequences

- `type` is removed from `AgentSpec`, `CatalogEntry`, and the contract schema.
- ADR-0023b's single-decorator decision and handler shape inference remain valid. Only the type taxonomy is superseded.
- ADR-0030's `AgentSpec` model is updated: `type` field removed.
- All code samples referencing `type="tool"`, `type="publisher"`, etc. must be updated.
- Catalog filtering changes from `mesh.catalog(type="tool")` to `mesh.catalog(streaming=False)` or similar capability-based predicates.
- The `x-agentmesh.type` field in the A2A-compatible contract schema (ADR-0012) is removed. The capabilities object carries the equivalent information.

## Alternatives Considered

**Keep type as an optional hint.** Let developers set `type` as a human-readable label while capabilities carry the structural truth. Rejected: if type is optional and non-functional, it will be inconsistently applied and become noise in the catalog. If it's functional, we're back to the taxonomy problem.

**Reduce to two types: "invocable" and "emitter".** Cleaner than four, but still an arbitrary label for what two booleans express more precisely. Rejected: unnecessary indirection.
