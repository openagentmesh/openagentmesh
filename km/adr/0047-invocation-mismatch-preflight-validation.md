# ADR-0047: Invocation mismatch pre-flight validation

- **Type:** api-design
- **Date:** 2026-04-21
- **Status:** documented
- **Amends:** ADR-0031 (extends capability checks to all invocation methods), ADR-0005 (replaces `StreamingNotSupported`/`StreamingRequired` with unified `InvocationMismatch`)
- **Source:** conversation (calling a Publisher with `mesh.call()` produces a misleading NATS `NoRespondersError`)

## Context

ADR-0031 defines five handler shapes from two capability booleans (`invocable`, `streaming`). The SDK previously validated only the streaming axis with two separate error classes (`StreamingNotSupported`, `StreamingRequired`), using `_check_responder` and `_check_streaming` methods.

The invocability axis had no equivalent check. When a caller runs `mesh.call("price-feed")` against a Publisher (invocable=false, streaming=true), the SDK publishes a NATS request to a subject nobody subscribes to. NATS returns `NoRespondersError: nats: no responders available for request`. This is a NATS transport detail leaking through the SDK abstraction.

All verb/shape mismatches are the same category of error: the caller used the wrong invocation pattern for the target agent's capabilities. Three separate error classes (`StreamingNotSupported`, `StreamingRequired`, `NotInvocable`) fragment what is conceptually one problem.

## Decision

Replace all verb/shape mismatch errors with a single `InvocationMismatch` error class. Each invocation method (`call`, `stream`, `send`) has its own pre-flight check that validates both invocability and streaming compatibility in one pass. The error message describes the specific mismatch and suggests the correct verb.

### Error class

```python
class InvocationMismatch(MeshError):
    """Raised when the invocation verb doesn't match the agent's capabilities."""

    def __init__(self, agent: str = "", message: str = "", request_id: str = ""):
        super().__init__(
            code="invocation_mismatch",
            message=message or f"Invocation mismatch for agent '{agent}'",
            agent=agent,
            request_id=request_id,
        )
```

### Mismatch matrix

| Verb | Target shape | Message |
|------|-------------|---------|
| `call()` on Publisher | invocable=false, streaming=true | "is a publisher and cannot be called. Subscribe to its events instead" |
| `call()` on Watcher | invocable=false, streaming=false | "is a background task and cannot be called" |
| `call()` on Streamer | invocable=true, streaming=true | "is streaming-only. Use stream() instead" |
| `stream()` on Responder/Trigger | invocable=true, streaming=false | "does not support streaming. Use call() instead" |
| `stream()` on Publisher | invocable=false, streaming=true | "is a publisher and cannot be streamed. Subscribe to its events instead" |
| `stream()` on Watcher | invocable=false, streaming=false | "is a background task and cannot be streamed" |
| `send()` on Publisher | invocable=false, streaming=true | "is a publisher and cannot be sent to. Subscribe to its events instead" |
| `send()` on Watcher | invocable=false, streaming=false | "is a background task and cannot be sent to" |

### Pre-flight checks

Each invocation method has a dedicated check (`_check_call`, `_check_stream`, `_check_send`) that reads from a shared `_capabilities` helper:

```python
def _capabilities(self, name: str) -> tuple[bool, bool] | None:
    """Return (invocable, streaming) for a known agent, or None if unknown."""
    if name in self._agents:
        _, _, contract = self._agents[name]
        return contract.invocable, contract.streaming
    entry = self._catalog_cache.get(name)
    if entry is not None:
        return entry.invocable, entry.streaming
    return None
```

### Eager catalog seeding on connect

The catalog cache is seeded from the current KV snapshot during `__aenter__`, before the catalog change watcher starts. This ensures that all agents already registered on the mesh are available for pre-flight checks from the first invocation, even if the caller process has no local agents. The watcher (ADR-0032) keeps the cache warm after that.

### CLI hints

The CLI (`oam agent call/stream`) catches `InvocationMismatch` and appends a `Try:` line with the correct CLI command:

```
Error [invocation_mismatch] Agent 'price-feed' is a publisher and cannot be called. Subscribe to its events instead

Try: oam agent subscribe price-feed
```

No `Try:` hint is shown for watchers (no applicable CLI command).

### Code sample

```python
from openagentmesh import AgentMesh, InvocationMismatch

mesh = AgentMesh()

async with mesh:
    try:
        result = await mesh.call("price-feed", {"symbol": "AAPL"})
    except InvocationMismatch as e:
        print(e.message)
        # "Agent 'price-feed' is a publisher and cannot be called. Subscribe to its events instead"

        async for event in mesh.subscribe(agent="price-feed"):
            print(event["symbol"], event["price"])
```

## Consequences

- `InvocationMismatch` replaces `StreamingNotSupported`, `StreamingRequired`, and `NotInvocable` as a single `MeshError` subclass with code `invocation_mismatch`.
- `_check_call`, `_check_stream`, `_check_send` replace the previous `_check_invocable`, `_check_responder`, `_check_streaming` methods.
- `MeshError` gains a `self.message` attribute for direct access (previously only in `args[0]`).
- `_seed_catalog_cache` fetches the catalog KV snapshot during `__aenter__`, ensuring the pre-flight check works from the first invocation even for pure-caller processes with no local agents.
- The defense-in-depth server-side check (for raw NATS messages with mismatched headers) also raises `InvocationMismatch`.
- `InvocationMismatch` is exported from the package. `StreamingNotSupported`, `StreamingRequired`, and `NotInvocable` are removed.

## Alternatives Considered

**Keep separate error classes per mismatch type.** Three classes (`StreamingNotSupported`, `StreamingRequired`, `NotInvocable`) for typed exception handling. Rejected: all mismatches are the same conceptual error (wrong verb for shape); the specifics belong in the message, not the class hierarchy. One `except InvocationMismatch` catches everything.

**Diagnose `NoRespondersError` after the fact.** Catch `NoRespondersError` from NATS, then query the registry to determine the right SDK error. Rejected: reactive rather than preventive; seeding the cache on connect is simpler.

**Unified `invoke()` method that auto-dispatches.** A single entry point that reads the contract and picks the right pattern. Rejected: the caller's consumption pattern (await one value vs. iterate a stream vs. fire-and-forget) requires different code at the call site. A unified method would return a union type or use runtime magic, both worse DX than explicit verbs.
