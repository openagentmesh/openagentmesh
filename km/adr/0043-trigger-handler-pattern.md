# ADR-0043: Trigger handler pattern

- **Type:** api-design
- **Date:** 2026-04-20
- **Status:** documented
- **Amends:** ADR-0031 (refines invocability inference), ADR-0042 (distinguishes trigger from watcher)
- **Source:** conversation (invocable agents that need no input payload)

## Context

ADR-0042 introduced the watcher handler shape: `async def f(): ...` with no input and no yield. This covers background-task agents that react to shared state.

There is a second valid use case for a no-input handler: a **trigger**. A trigger is an invocable agent that starts a workflow when called, without requiring any input payload. The call itself is the signal. Examples: cache refresh, migration runner, nightly report generator, pipeline flush.

The difference between a trigger and a watcher is intent:

- A **trigger** returns a result to the caller. Someone is waiting for it.
- A **watcher** runs indefinitely as a background task. Nobody calls it.

This maps naturally to the handler's return type. If the handler declares an output model, it promises a result to someone; if it doesn't, it's a background process.

## Decision

Refine the invocability inference rule. A handler is invocable if it has an input model **or** if it has an output model and does not stream.

### Updated inference rule

```
invocable = has_input_model or (has_output_model and not streaming)
```

Previous rule (ADR-0031 + ADR-0042):
```
invocable = has_input_model
```

### Updated handler shape table

| Pattern | Handler shape | Capabilities |
|---------|--------------|--------------|
| Responder | `async def f(req: In) -> Out: return ...` | `invocable=True, streaming=False` |
| Streamer | `async def f(req: In) -> Chunk: yield ...` | `invocable=True, streaming=True` |
| **Trigger** | **`async def f() -> Out: return ...`** | **`invocable=True, streaming=False`** |
| Publisher | `async def f() -> Event: yield ...` | `invocable=False, streaming=True` |
| Watcher | `async def f() -> None: ...` | `invocable=False, streaming=False` |

The trigger row is new. The discriminator between trigger and watcher is the output model: present means invocable, absent means background task.

### Code sample

```python
class RefreshResult(BaseModel):
    keys_refreshed: int
    duration_ms: float

spec = AgentSpec(
    name="refresh-cache",
    channel="ops",
    description="Flushes and rebuilds the cache. Returns refresh stats.",
)

@mesh.agent(spec)
async def refresh_cache() -> RefreshResult:
    stats = await rebuild_cache()
    return RefreshResult(keys_refreshed=stats.count, duration_ms=stats.elapsed)
```

Called without payload:

```python
result = await mesh.call("refresh-cache")
print(f"Refreshed {result['keys_refreshed']} keys in {result['duration_ms']}ms")
```

### Contract representation

A trigger contract has:
- `invocable: true`
- `streaming: false`
- `input_schema: null`
- `output_schema: { ... }` (the output model's JSON Schema)

The absent `input_schema` signals to consumers that `mesh.call()` requires no payload.

### No plumbing changes needed

The existing `_handle_responder` method already supports calling handlers with no arguments when `input_model` is None. The existing `mesh.call()` already accepts `payload=None`. Only the inference rule in `inspect_handler` changes.

## Consequences

- `_handler.py`: update `invocable` assignment from `input_model is not None` to include the output-model-without-streaming case.
- ADR-0031's inference table gains the trigger row.
- `docs/concepts/agents.md`: add Trigger to the handler shapes table with code sample.
- Existing publisher behavior is unaffected: publishers have output models and stream, so `has_output_model and not streaming` is false for them.

## Alternatives Considered

**Explicit `invocable=True` on AgentSpec.** Would work but breaks the ADR-0031 principle that capabilities are always inferred from the handler shape. Adding manual overrides creates a second source of truth that can drift from the actual handler behavior.

**Treat all no-input handlers as invocable.** Would make watchers invocable, which is wrong: calling a watcher that runs an infinite loop and never returns would hang the caller.
