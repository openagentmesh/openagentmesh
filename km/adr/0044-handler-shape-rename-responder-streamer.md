# ADR-0044: Rename handler shapes to Responder/Streamer

- **Type:** api-design
- **Date:** 2026-04-20
- **Status:** spec
- **Source:** conversation ("Buffered" implies a transport-level buffering mechanism that doesn't exist)

## Context

The five handler shapes are named: Buffered, Streaming, Trigger, Publisher, Watcher.

Two problems:

1. **"Buffered" is misleading.** The handler takes a request and returns a response. No buffering occurs. The name implies a transport mechanism that doesn't exist, confusing developers who expect actual buffering behavior.

2. **"Streaming" breaks the naming pattern.** Trigger, Publisher, and Watcher are all agent-like nouns (the "-er" form). "Streaming" is a gerund. Consistency matters when scanning a table of five patterns.

## Decision

Rename two handler shapes:

| Before | After |
|--------|-------|
| Buffered | **Responder** |
| Streaming | **Streamer** |

The full set becomes: **Responder, Streamer, Trigger, Publisher, Watcher**. Five role nouns describing what the handler does.

### Error class rename

`BufferedNotSupported` referenced the old terminology and described the error indirectly. Both error classes should describe the streaming capability mismatch:

| Before | After | Code | When raised |
|--------|-------|------|-------------|
| `BufferedNotSupported` | `StreamingRequired` | `streaming_required` | `mesh.call()` targets a streamer |
| `StreamingNotSupported` | unchanged | `streaming_not_supported` | `mesh.stream()` targets a responder |

`StreamingRequired` means "this agent only streams; use `mesh.stream()`." Symmetric with `StreamingNotSupported` meaning "this agent doesn't stream; use `mesh.call()`."

### Internal method rename

| Before | After |
|--------|-------|
| `_handle_buffered` | `_handle_responder` |
| `_check_buffered` | `_check_responder` |

### Handler shapes table (updated)

| Pattern | Handler shape | Invocable | Streaming |
|---------|--------------|-----------|-----------|
| Responder | `async def f(req: In) -> Out: return ...` | Yes | No |
| Streamer | `async def f(req: In) -> Chunk: yield ...` | Yes | Yes |
| Trigger | `async def f() -> Out: return ...` | Yes | No |
| Publisher | `async def f() -> Event: yield ...` | No | Yes |
| Watcher | `async def f(): ...` | No | No |

## Consequences

- `BufferedNotSupported` renamed to `StreamingRequired` in `src/openagentmesh/_models.py` and re-exported from `__init__.py`.
- Error code changes from `buffered_not_supported` to `streaming_required` in wire protocol. This is a breaking change for consumers matching on error codes.
- Internal methods `_handle_buffered` and `_check_buffered` renamed in `_mesh.py`.
- All references in `docs/`, `tests/`, `km/`, and `CLAUDE.md` updated.
- ADR-0024 title and body still reference "buffered"; updated in place with a note pointing to this ADR.

## Alternatives Considered

**"Standard" for Buffered.** Implies the other shapes are non-standard. Rejected: all five shapes are equally valid.

**"Tool" for Buffered.** Collides with MCP/function-calling "tool" concept in the AI ecosystem. Rejected: too much baggage for the target audience.

**"Reply" for Buffered.** Short, NATS-native term. Rejected: could confuse with NATS reply subjects.

**Docs-only rename.** Cheaper, but creates a terminology split between what users read and what the code says. Rejected: consistency across layers matters for a DX-first project.
