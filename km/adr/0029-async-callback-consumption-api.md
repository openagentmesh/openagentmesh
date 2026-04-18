# ADR-0029: Async callback consumption API

- **Type:** api-design
- **Date:** 2026-04-14
- **Status:** superseded by ADR-0034
- **Source:** conversation (cookbook design discussion on async pipeline use cases)

## Context

The mesh supports three invocation patterns (spec §4.5):

1. **Synchronous req/reply** — `mesh.call()` — caller blocks until the agent responds.
2. **Async callback** — `mesh.send(reply_to=...)` — caller fires a message and receives the response on a named subject later.
3. **Pub/sub** — `mesh.subscribe()` — fan-out events, no correlation.

The SDK fully implements Pattern 1 and Pattern 3. Pattern 2 is half-implemented: `mesh.send(name, payload, reply_to=...)` sends the request, but nothing in the SDK helps the caller receive the response.

The spec acknowledges this: *"The async callback pattern requires a correlation/timeout manager on the caller side. The mesh SDK should provide this as a built-in utility. Without it, there is no mechanism to detect that an agent never responded to a callback."* (§4.5, Pattern 2)

Without a receive-side helper, developers must write raw NATS subscription code:

```python
import uuid, asyncio, json
from nats.aio.client import Client as NATS

request_id = uuid.uuid4().hex
reply_subject = f"mesh.results.{request_id}"

# Developer must manage their own NATS connection and subscription
nc = NATS()
await nc.connect("nats://localhost:4222")

future = asyncio.get_event_loop().create_future()
async def on_reply(msg):
    future.set_result(json.loads(msg.data))

sub = await nc.subscribe(reply_subject, cb=on_reply)
await mesh.send("summarizer", payload, reply_to=reply_subject)
result = await asyncio.wait_for(future, timeout=30.0)
await sub.unsubscribe()
```

This drops the caller back into raw NATS, bypassing all SDK abstractions (typed responses, `MeshError` handling, structured errors). It also requires the developer to manage their own NATS connection in parallel with the SDK's internal one.

## Options

### Option A: No helper — `mesh.send()` remains intentionally low-level

The SDK does not provide a receive-side helper. `mesh.send()` is a low-level primitive for advanced use cases where callers manage the reply subscription themselves.

The primary pattern for callers who need a response is `mesh.call()` (synchronous). `mesh.send()` is reserved for pipeline architectures where a separate agent or service is the intended recipient of the callback, not the caller itself.

This keeps the SDK surface minimal and avoids building a correlation/timeout manager whose semantics may not fit all use cases.

### Option B: `mesh.receive(subject, timeout=...)` — one-shot awaitable

Add a method that subscribes to a subject, waits for one message, and unsubscribes:

```python
request_id = uuid.uuid4().hex
reply_subject = f"mesh.results.{request_id}"

await mesh.send("summarizer", payload, reply_to=reply_subject)
# Continue other work...
result = await mesh.receive(reply_subject, timeout=30.0)
# result is a dict (or MeshError on error status)
```

`mesh.receive()` is general-purpose: it works for any subject, not just `mesh.send()` callbacks. Callers who want typed responses pass a model:

```python
result = await mesh.receive(reply_subject, model=SummarizeOutput, timeout=30.0)
```

Simpler than Option C — no correlation tracking, no request ID management. The caller manually constructs the reply subject (as they already do for `reply_to=`). Error handling follows the same `MeshError` convention as `mesh.call()`.

Downside: the caller is still responsible for generating the request ID and constructing the reply subject. `mesh.send()` and `mesh.receive()` are separate calls with no linkage in the SDK.

### Option C: `mesh.send()` returns a coroutine or awaitable response handle

Integrate the correlation directly into `mesh.send()`:

```python
# mesh.send() returns a handle for the pending response
handle = await mesh.send("summarizer", payload, timeout=30.0)

# Continue other work...
result_a = await mesh.call("other-agent", other_payload)

# Await the original response when ready
result = await handle
```

The SDK generates the request ID and reply subject internally. The caller never sees them. `handle` is an awaitable that resolves when the response arrives or raises `MeshError` on timeout/error. Multiple in-flight handles can be awaited concurrently.

This is the closest to how `asyncio.Task` and `asyncio.Future` work — fire now, await later. The SDK's correlation manager handles subject lifecycle, cleanup, and timeout enforcement.

Downside: `await mesh.send(...)` currently returns `None` (it's fire-and-forget). Changing the return type to an awaitable handle is a breaking change to the semantics. Callers who genuinely want fire-and-forget would need a different call (`mesh.send(..., fire_and_forget=True)`?) or would always have to discard the handle explicitly.

### Option D: `mesh.send()` auto-generates `reply_to` and returns a coroutine (simplified C)

A constrained version of Option C: `mesh.send()` always generates the reply subject internally. Fire-and-forget is no longer the default; the caller awaits or discards the handle.

```python
# Always awaitable — the SDK manages the reply subject
summary = await (await mesh.send("summarizer", {"text": doc, "max_length": 500}))

# Or equivalently via a named pattern
handle = await mesh.send("summarizer", {"text": doc, "max_length": 500})
# Do other things...
summary = await handle
```

Simpler for callers: no `reply_to` parameter, no subject construction. The explicit `reply_to` parameter is removed or made optional (defaulting to auto-generated).

Downside: `reply_to` as an explicit parameter is useful when the *response recipient is a different agent*, not the caller. Removing it breaks the pipeline composition case where Agent A fires to Agent B and the response should go to Agent C.

## Relationship to `mesh.call()`

`mesh.call()` is already the right answer for the common case (caller wants the response, latency is acceptable). The async callback pattern is most valuable when:

- The caller fires multiple requests and wants to await them concurrently (fan-out)
- The caller wants to continue other work between send and receive
- The response recipient is a different agent or service (true fire-and-forget with directed callback)

Options B and C both preserve the third case (directed callback to another agent). Option D does not.

## Open Questions

- Is the primary motivation for `mesh.send()` fire-and-forget (no response expected), fan-out (multiple concurrent requests), or directed callback (response goes to another agent)?
- Does Option C's handle pattern conflict with the use case where `reply_to` points to a different agent?
- Should the correlation/timeout manager be the SDK's responsibility (Options C/D) or is Option B's lighter touch sufficient?
- Is Phase 1 the right time to resolve this, or is `mesh.call()` sufficient for all Phase 1 cookbook recipes?
