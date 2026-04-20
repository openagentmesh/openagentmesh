# ADR-0042: Watcher agent pattern

- **Type:** api-design
- **Date:** 2026-04-20
- **Status:** documented
- **Amends:** ADR-0031 (adds fourth capability combination)
- **Source:** conversation (reactive pipeline stages are invisible to the mesh)

## Context

ADR-0031 established three valid handler shapes based on `invocable` and `streaming` capability booleans. The fourth combination (`invocable=false, streaming=false`) was explicitly excluded: "there is no use case for a non-invocable, non-streaming agent."

The reactive pipeline cookbook (and any KV-watch-based coordination pattern) proves otherwise. Stages that watch for state changes, process data, and write results are real participants in the mesh, but today they must run as bare consumers (`async with mesh:` without registration). This makes them invisible to discovery, excluded from liveness tracking, and absent from the catalog.

Registering them as publishers is wrong: they don't emit events to subscribers. Registering them with a dummy input model is wrong: they're not invocable. The handler constraint in `_handler.py` blocks the honest representation.

### Scaling concern

Invocable agents scale horizontally via NATS queue groups: deploy three replicas and requests distribute automatically. KV watchers have no such mechanism; every instance receives every update. Naive horizontal scaling of a watcher means duplicate processing.

This is not a defect to fix; it reflects the nature of KV watching. If the watching itself needs to scale, the architecture likely needs a stream processor, not more watchers. The recommended pattern is:

1. **One watcher instance** reacts to KV changes (thin routing layer).
2. **Processing is delegated** to invocable agents via `mesh.call()`, which scale via queue groups.
3. The watcher does minimal work; the invocable agents handle the heavy computation.

This keeps scaling where NATS handles it natively and avoids distributed locking or deduplication.

## Decision

Allow a fourth handler shape: `invocable=false, streaming=false`. This represents a **watcher agent** that coordinates through shared state rather than messages.

### Updated handler shape table (amends ADR-0031)

| Pattern | Handler shape | Capabilities |
|---------|--------------|--------------|
| Responder | `async def f(req: In) -> Out: return ...` | `invocable=True, streaming=False` |
| Streamer | `async def f(req: In) -> Chunk: yield ...` | `invocable=True, streaming=True` |
| Publisher | `async def f() -> Event: yield ...` | `invocable=False, streaming=True` |
| **Watcher** | **`async def f() -> None: ...`** | **`invocable=False, streaming=False`** |

### Handler shape

A watcher handler is an async function with no request parameter and no yield. It returns `None` (or has no return annotation). The handler body contains the watch loop:

```python
spec = AgentSpec(
    name="extract",
    channel="pipeline",
    description="Watches for raw documents and extracts entities.",
)

@mesh.agent(spec)
async def extract():
    async for value in mesh.kv.watch("pipeline.*.raw"):
        doc = Document.model_validate_json(value)
        extracted = do_extraction(doc)
        await mesh.kv.put(f"pipeline.{doc.id}.extracted", extracted.model_dump_json())
```

### Scaling pattern

For pipelines where the processing step is expensive, delegate to an invocable agent:

```python
@mesh.agent(AgentSpec(
    name="extract-watcher",
    channel="pipeline",
    description="Routes raw documents to the extract processor.",
))
async def extract_watcher():
    async for value in mesh.kv.watch("pipeline.*.raw"):
        doc = Document.model_validate_json(value)
        await mesh.call("extract-processor", {"id": doc.id, "body": doc.body})
```

The watcher is a single instance. The `extract-processor` agent scales via queue groups.

### Catalog filtering

Watcher agents appear in `mesh.catalog()` by default. Consumers selecting tools for LLM invocation should filter with `invocable=True`, which already excludes both publishers and watchers:

```python
tools = await mesh.catalog(invocable=True)
```

No new filtering parameter needed.

### Contract representation

A watcher contract has:
- `invocable: false`
- `streaming: false`
- `input_schema: null`
- `output_schema: null`
- `chunk_schema: null`

It appears in the registry and catalog like any other agent. The capabilities object carries the behavioral signal.

## Consequences

- `_handler.py`: remove the `TypeError` for the `not invocable and not streaming` case. Allow async functions with no request parameter and no yield.
- ADR-0031's capability table gains a fourth row. The statement "the fourth combination is not valid" is superseded.
- `docs/concepts/agents.md`: add Watcher to the handler shapes table.
- `docs/concepts/participation.md`: no change needed; watchers are a hybrid pattern (registered + uses mesh services). The participation patterns (provider/consumer/hybrid) describe mesh interaction style, not handler shape.
- `docs/cookbook/reactive-pipeline.md`: update stages 2 and 3 to use `@mesh.agent` with watcher handlers. Add the scaling pattern as a tip.
- Watcher agents do not benefit from queue-group scaling. The ADR documents the recommended delegation pattern for scaling the processing step.

## Alternatives Considered

**Register watchers as publishers.** Technically possible (add a dummy yield), but semantically wrong. Publishers emit events; watchers consume state. Misrepresenting the handler shape to satisfy a constraint is the kind of hack that erodes trust in the capability system.

**Add advisory locking for KV watchers.** Would enable horizontal scaling of watchers via CAS-based claim on each key. Rejected: adds significant complexity, the scaling need is rare, and the delegation pattern handles it cleanly without new primitives.

**Leave watchers unregistered.** The status quo. Works but sacrifices visibility, liveness, and catalog completeness. The mesh can't report what it can't see.
