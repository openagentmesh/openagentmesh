# nats-py API Research

**Library:** nats-py (nats-io/nats.py)
**Researched:** 2026-04-04
**Version scope:** v2.x (current stable)
**Confidence:** HIGH — verified against official docs, module source, and natsbyexample.com

---

## Installation

```bash
pip install nats-py
pip install nats-py[nkeys]   # add NKEYS/JWT auth support
```

Python 3.8+ required. The library is fully async (asyncio). There is no sync API.

---

## 1. Connecting

### Basic connection

```python
import nats

nc = await nats.connect("nats://localhost:4222")
```

### Connection with lifecycle callbacks

All callbacks must be `async def`. The `error_cb` receives an `Exception`; the others take no arguments.

```python
async def disconnected_cb():
    print("disconnected")

async def reconnected_cb():
    print("reconnected")

async def error_cb(e):
    print(f"error: {e}")

async def closed_cb():
    print("connection closed")

nc = await nats.connect(
    "nats://localhost:4222",
    error_cb=error_cb,
    disconnected_cb=disconnected_cb,
    reconnected_cb=reconnected_cb,
    closed_cb=closed_cb,
    max_reconnect_attempts=-1,   # unlimited
    reconnect_time_wait=2,       # seconds between attempts
    connect_timeout=2,
)
```

### Running alongside an existing async app

nats-py uses whatever asyncio event loop is currently running. No special configuration is needed — just `await nats.connect()` inside any coroutine. There is no internal thread, no background loop. The connection is managed as tasks in the calling loop.

```python
# Embed in FastAPI, uvicorn, or any other asyncio app:
async def lifespan(app):
    nc = await nats.connect("nats://localhost:4222")
    app.state.nc = nc
    yield
    await nc.drain()
```

### Blocking "run forever" pattern

```python
import asyncio
import nats

async def main():
    nc = await nats.connect("nats://localhost:4222")
    # ... register subscriptions ...
    await asyncio.Event().wait()   # block forever
    await nc.drain()

asyncio.run(main())
```

---

## 2. Publish and Subscribe

### Publish

```python
await nc.publish("subject", b"payload")

# With reply subject (for async callback pattern)
await nc.publish("subject", b"payload", reply="mesh.results.abc123")

# With headers (NATS 2.2+, nats-py v2.0+)
await nc.publish(
    "subject",
    b"payload",
    headers={
        "X-Mesh-Request-Id": "abc123",
        "X-Mesh-Source": "summarizer",
        "X-Mesh-Status": "ok",
    },
)
```

### Subscribe (callback style — recommended for agents)

```python
async def handler(msg):
    subject = msg.subject
    reply   = msg.reply        # set if sender used nc.request() or set msg.reply
    data    = msg.data         # bytes
    headers = msg.headers      # dict[str, str] | None

    # Reply using the reply subject
    await msg.respond(b"response payload")
    # or equivalently:
    await nc.publish(msg.reply, b"response payload")

sub = await nc.subscribe("mesh.agent.nlp.summarizer", cb=handler)
```

### Subscribe (iterator style — useful for one-shot consumers)

```python
sub = await nc.subscribe("greet.*")
async for msg in sub.messages:
    print(msg.data)
```

### Unsubscribe

```python
await sub.unsubscribe()
# or auto-unsubscribe after N messages:
await sub.unsubscribe(limit=1)
```

---

## 3. Queue Groups

Queue groups are the native NATS load-balancing primitive. Multiple instances subscribing to the same subject with the same queue name share the message stream — each message goes to exactly one member.

```python
async def handler(msg):
    data = msg.data.decode()
    print(f"worker got: {data}")
    await msg.respond(b"done")

# All instances use the same subject AND queue name
sub = await nc.subscribe(
    "mesh.agent.nlp.summarizer",
    queue="mesh.agent.nlp.summarizer",   # convention: queue == subject
    cb=handler,
)
```

**Key points:**
- The queue name is an arbitrary string. Convention for AgentMesh: use the subject as the queue name.
- Multiple processes/instances subscribe identically — no coordination needed.
- Scaling out means starting another process with the same subscription code.
- The NATS server selects one recipient per message (random distribution).
- Unsubscribing one member does not affect others; the group shrinks gracefully.

---

## 4. Request / Reply

### Sync request (caller blocks)

```python
from nats.errors import TimeoutError, NoRespondersError

try:
    response = await nc.request(
        "mesh.agent.nlp.summarizer",
        b'{"text": "hello world"}',
        timeout=30.0,
    )
    print(response.data)
    print(response.headers)   # access response headers
except TimeoutError:
    # No response within timeout — agent exists but is slow or crashed mid-flight
    print("timeout")
except NoRespondersError:
    # Nobody is subscribed to that subject at all
    print("agent not registered")
```

`nc.request()` internally creates a unique inbox subject (`_INBOX.xxxx`), subscribes to it, publishes the request with that inbox as the reply subject, and waits for the reply. This is all handled by the library.

### Async callback pattern (fire-and-forget + reply later)

```python
# Sender: publish with an explicit reply subject
reply_subject = f"mesh.results.{request_id}"
await nc.publish(
    "mesh.agent.nlp.summarizer",
    b'{"text": "hello world"}',
    reply=reply_subject,
    headers={"X-Mesh-Request-Id": request_id, "X-Mesh-Reply-To": reply_subject},
)

# Separately, subscribe to the reply subject
async def on_result(msg):
    print(f"got result: {msg.data}")
    await result_sub.unsubscribe()

result_sub = await nc.subscribe(reply_subject, cb=on_result)
```

### Handler side: replying to both patterns

The handler does not need to know which invocation pattern the caller used. `msg.reply` is set in both cases.

```python
async def handler(msg):
    if msg.reply:
        await nc.publish(
            msg.reply,
            b'{"summary": "..."}',
            headers={
                "X-Mesh-Request-Id": msg.headers.get("X-Mesh-Request-Id", ""),
                "X-Mesh-Status": "ok",
            },
        )
```

---

## 5. NATS Headers

Headers are available from NATS Server 2.2+ and nats-py v2.0+.

### Sending headers

```python
await nc.publish(
    "subject",
    b"body",
    headers={
        "X-Mesh-Request-Id": "abc",
        "X-Mesh-Source":     "agent-name",
        "X-Mesh-Status":     "ok",
        "traceparent":       "00-trace-parent-value",
    },
)
```

### Receiving headers

```python
async def handler(msg):
    headers = msg.headers   # dict[str, str] | None
    if headers:
        request_id = headers.get("X-Mesh-Request-Id")
        status     = headers.get("X-Mesh-Status")
```

**Gotcha — multi-value headers:** The NATS protocol supports multiple values per header key (space-separated or as a list). The Python client stores them as `dict[str, str]`. If you send multi-value headers from another client, nats-py may give you only the last value or a concatenated string. For AgentMesh, keep all headers single-valued.

**Gotcha — None check required:** `msg.headers` is `None` when no headers were sent (not an empty dict). Always guard with `if msg.headers:` before accessing keys.

---

## 6. JetStream KV Store

JetStream must be enabled on the NATS server. KV is built on top of JetStream streams.

### Get a JetStream context

```python
js = nc.jetstream()
```

### Create a bucket

```python
from nats.js.api import KeyValueConfig

kv = await js.create_key_value(bucket="mesh.catalog")

# With configuration
kv = await js.create_key_value(
    config=KeyValueConfig(
        bucket="mesh.registry",
        history=1,        # revisions per key (default 1, max 64)
        ttl=None,         # float seconds, None = never expires
        replicas=1,       # 1 for dev, 3 for production cluster
        max_value_size=-1,  # bytes, -1 = unlimited
    )
)
```

### Bind to an existing bucket (don't recreate)

```python
kv = await js.key_value("mesh.catalog")
```

### Basic put / get

```python
# put returns the revision number (int)
revision = await kv.put("some-key", b'{"agents": []}')

# get returns a KeyValue.Entry object
entry = await kv.get("some-key")
print(entry.value)       # bytes
print(entry.revision)    # int — the sequence number, used for CAS
print(entry.key)         # str
print(entry.bucket)      # str
print(entry.operation)   # None, "DEL", or "PURGE"
```

### Compare-and-Swap (CAS) update

CAS is the correct pattern for concurrent catalog updates. `update()` only succeeds if `last` matches the current revision. On mismatch it raises `KeyWrongLastSequenceError`.

```python
from nats.js.errors import KeyWrongLastSequenceError, KeyNotFoundError

async def update_catalog_with_retry(kv, key: str, new_value: bytes):
    while True:
        try:
            entry = await kv.get(key)
            current_revision = entry.revision
        except KeyNotFoundError:
            # Key doesn't exist yet — use put (first write wins)
            await kv.put(key, new_value)
            return

        try:
            await kv.update(key, new_value, last=current_revision)
            return   # success
        except KeyWrongLastSequenceError:
            # Another writer updated the key concurrently — retry
            await asyncio.sleep(0)   # yield to event loop, then retry
            continue
```

### Create (put-if-not-exists)

```python
# Raises error if key already exists
revision = await kv.create("some-key", b"value")
```

### Delete and purge

```python
await kv.delete("some-key")   # leaves a tombstone, preserves history
await kv.purge("some-key")    # removes key and all history
```

### Watch a key or pattern

```python
# Watch a specific key
watcher = await kv.watch("some-key")
async for entry in watcher:
    if entry is None:
        break   # initial values exhausted signal
    print(f"updated: {entry.key} = {entry.value}")

# Watch all keys matching a pattern
watcher = await kv.watch("mesh.registry.*")

# Watch everything
watcher = await kv.watchall()
```

**Note:** On first iteration, the watcher replays the current value(s) before switching to live updates. The `None` sentinel signals the end of initial values; ongoing updates follow.

### List keys

```python
keys = await kv.keys()   # list[str] of keys with current values (no tombstones)
```

**Gotcha:** `kv.keys()` with a filter currently fetches ALL keys from the server and filters client-side (issue #768). For large registries this is a significant performance problem. For AgentMesh's catalog, prefer the single-key `mesh.catalog` pattern (one JSON blob) over per-key enumeration.

---

## 7. Error Handling Reference

### Core errors (`from nats.errors import ...`)

| Error | When it occurs |
|-------|---------------|
| `TimeoutError` | `nc.request()` or `sub.next_msg()` exceeded timeout |
| `NoRespondersError` | `nc.request()` with no subscribers on subject |
| `ConnectionClosedError` | Operation on already-closed connection |
| `ConnectionDrainingError` | Operation during drain (shutdown in progress) |
| `SlowConsumerError` | Subscriber's pending buffer full; messages dropped |
| `NoServersError` | Could not connect to any server |
| `AuthorizationError` | Bad credentials |
| `DrainTimeoutError` | `drain()` took too long |

### JetStream errors (`from nats.js.errors import ...`)

| Error | When it occurs |
|-------|---------------|
| `KeyNotFoundError` | `kv.get()` on missing or deleted key |
| `KeyWrongLastSequenceError` | `kv.update()` CAS mismatch |
| `KeyDeletedError` | Key exists but was deleted (tombstone) |
| `NotFoundError` | Stream or consumer not found |
| `BadRequestError` | Invalid JetStream API request |
| `APIError` | General JetStream server error |

### Recommended error handling pattern for AgentMesh

```python
from nats.errors import TimeoutError, NoRespondersError, ConnectionClosedError
from nats.js.errors import KeyNotFoundError, KeyWrongLastSequenceError

async def call_agent(nc, subject, payload, timeout=30.0):
    try:
        response = await nc.request(subject, payload, timeout=timeout)
        return response
    except NoRespondersError:
        raise AgentNotFoundError(f"No agent registered at {subject}")
    except TimeoutError:
        raise AgentTimeoutError(f"Agent at {subject} did not respond in {timeout}s")
    except ConnectionClosedError:
        raise MeshConnectionError("NATS connection is closed")
```

---

## 8. Subscription Concurrency — Critical Gotcha

**The problem:** nats-py dispatches messages to a callback *serially* for each subscription. The second message is not delivered to the callback until the coroutine for the first message returns (or awaits). If your handler does significant async work, messages queue up in the pending buffer.

**What this means for AgentMesh:** A single `@mesh.agent` process handling slow LLM calls will process one invocation at a time per subscription. This is usually fine — queue groups distribute across instances. But if one instance is slow, it holds messages.

**The correct pattern for concurrent handling within one process:**

```python
async def handler(msg):
    # DON'T await slow work directly here — it blocks the next message
    # DO spawn a task instead:
    asyncio.create_task(process_message(msg))

async def process_message(msg):
    # Do the actual slow work here
    result = await call_llm(msg.data)
    if msg.reply:
        await nc.publish(msg.reply, result)
```

**Iterator pattern for explicit concurrency control:**

```python
sub = await nc.subscribe("mesh.agent.nlp.summarizer", queue="mesh.agent.nlp.summarizer")
semaphore = asyncio.Semaphore(10)  # max 10 concurrent in-flight

async def process(msg):
    async with semaphore:
        result = await call_llm(msg.data)
        if msg.reply:
            await nc.publish(msg.reply, result)

async for msg in sub.messages:
    asyncio.create_task(process(msg))
```

**For blocking (CPU/IO) work:** Use `loop.run_in_executor()` to avoid blocking the event loop entirely:

```python
loop = asyncio.get_running_loop()
result = await loop.run_in_executor(None, blocking_function, args)
```

---

## 9. Lifecycle — drain() vs close()

| Method | Behavior |
|--------|---------|
| `await nc.drain()` | Graceful: unsubscribes, flushes outbound, processes inflight, then closes. Preferred for shutdown. |
| `await nc.close()` | Immediate: drops pending messages, closes socket. Use only if drain hangs. |

For AgentMesh's `await mesh.stop()`, the sequence should be:
1. Stop accepting new subscriptions (unsubscribe)
2. `await nc.drain()` — flushes and closes

---

## 10. Embedded NATS Server (nats-server package)

The `nats-server` package (separate from `nats-py`) provides a Python API to manage NATS server processes for dev/testing. This is separate from the AgentMesh embedded NATS approach (which downloads the binary directly).

```bash
pip install nats-server
```

```python
from nats.server import Server

server = Server()
await server.start()      # starts nats-server subprocess
# ... use nats-py client normally ...
await server.stop()
```

For `AgentMesh.local()`, it is likely simpler to use `subprocess` or `asyncio.create_subprocess_exec` to manage the NATS binary directly, rather than taking the `nats-server` package as a dependency.

---

## 11. Subscription Pending Buffer Limits

The default pending buffer per subscription is generous: 524,288 messages or 128 MB. For high-throughput scenarios, these can be tuned:

```python
sub = await nc.subscribe(
    "subject",
    cb=handler,
    pending_msgs_limit=1000,
    pending_bytes_limit=5 * 1024 * 1024,  # 5 MB
)
```

When the buffer fills, `SlowConsumerError` is raised in the `error_cb` and messages are dropped. For AgentMesh agents this is unlikely to be an issue — agents are expected to process and reply; the queue group distributes load across instances.

---

## 12. Patterns for AgentMesh

### Agent registration flow

```python
nc = await nats.connect("nats://localhost:4222")
js = nc.jetstream()

# Bind to (or create) the registry KV bucket
try:
    registry = await js.key_value("mesh.registry")
except nats.js.errors.NotFoundError:
    registry = await js.create_key_value(bucket="mesh.registry")

# Write contract
await registry.put(
    f"{channel}.{name}",
    contract_json.encode(),
)

# Subscribe with queue group for invocations
sub = await nc.subscribe(
    f"mesh.agent.{channel}.{name}",
    queue=f"mesh.agent.{channel}.{name}",
    cb=invocation_handler,
)
```

### Catalog CAS update pattern

The `mesh.catalog` key holds a JSON array updated by all registering agents. CAS prevents corruption under concurrent registration:

```python
async def register_in_catalog(kv, entry: dict):
    while True:
        try:
            existing = await kv.get("catalog")
            catalog = json.loads(existing.value)
            catalog.append(entry)
            await kv.update("catalog", json.dumps(catalog).encode(), last=existing.revision)
            return
        except KeyNotFoundError:
            await kv.put("catalog", json.dumps([entry]).encode())
            return
        except KeyWrongLastSequenceError:
            await asyncio.sleep(0)   # back off, retry
```

### Subject naming convention

```python
def invocation_subject(channel: str | None, name: str) -> str:
    if channel:
        return f"mesh.agent.{channel}.{name}"
    return f"mesh.agent.{name}"

def registry_key(channel: str | None, name: str) -> str:
    if channel:
        return f"{channel}.{name}"
    return name
```

### Heartbeat publisher

```python
async def heartbeat_loop(nc, subject, interval_ms=10000):
    while True:
        await nc.publish(subject, b'{"status": "ok"}')
        await asyncio.sleep(interval_ms / 1000)

task = asyncio.create_task(
    heartbeat_loop(nc, f"mesh.health.{channel}.{name}")
)
# cancel task on shutdown
task.cancel()
```

---

## 13. Known Issues and Gotchas Summary

| Issue | Impact | Mitigation |
|-------|--------|-----------|
| Callbacks are serial per subscription | Slow handlers block message intake | Spawn `asyncio.create_task()` inside handler |
| Blocking code in async handler kills throughput | Connection drops / slow consumer | Use `run_in_executor` for sync/CPU work |
| `kv.keys()` with filter fetches all keys client-side | Perf issue for large registries | Use single catalog-key JSON pattern instead |
| `msg.headers` is `None` (not `{}`) when absent | `KeyError` if unchecked | Always guard: `if msg.headers: headers.get(...)` |
| Multi-value headers may truncate | Silent data loss for multi-value headers | Keep all AgentMesh headers single-valued |
| `create_key_value()` vs `key_value()` — recreating on startup | Race condition on concurrent startup | Use `key_value()` first, fall back to `create_key_value()` on `NotFoundError` |
| `ConnectionClosedError` during shutdown | Errors in cleanup path | Wrap drain/close in try/except |
| TLS misconfiguration causes infinite reconnect loop | Process hangs | Set `max_reconnect_attempts` and handle `NoServersError` |
| `update()` (CAS) raises `KeyWrongLastSequenceError` on collision | Lost update if not retried | Always wrap in retry loop |
| `nc.request()` timeout ≠ "agent not running" | Ambiguous error | Distinguish `NoRespondersError` (not registered) from `TimeoutError` (slow/crashed) |

---

## Sources

- [nats-io/nats.py GitHub](https://github.com/nats-io/nats.py) — MEDIUM confidence (README, not full source)
- [nats.py official docs — modules](https://nats-io.github.io/nats.py/modules.html) — HIGH confidence
- [nats.py KV source](https://nats-io.github.io/nats.py/_modules/nats/js/kv.html) — HIGH confidence
- [nats.py errors source](https://nats-io.github.io/nats.py/_modules/nats/errors.html) — HIGH confidence
- [nats.py v2.0.0 release notes](https://nats-io.github.io/nats.py/releases/v2.0.0.html) — HIGH confidence
- [NATS KV docs](https://docs.nats.io/using-nats/developer/develop_jetstream/kv) — HIGH confidence
- [natsbyexample.com — request-reply Python](https://natsbyexample.com/examples/messaging/request-reply/python) — HIGH confidence
- [natsbyexample.com — concurrent processing Python](https://natsbyexample.com/examples/messaging/concurrent/python) — HIGH confidence
- [Discussion #555 — concurrent callbacks](https://github.com/nats-io/nats.py/discussions/555) — HIGH confidence
- [oneuptime.com — NATS Python guide (Feb 2026)](https://oneuptime.com/blog/post/2026-02-02-nats-python/view) — MEDIUM confidence
- [oneuptime.com — NATS KV guide (Feb 2026)](https://oneuptime.com/blog/post/2026-02-02-nats-kv-store/view) — MEDIUM confidence
