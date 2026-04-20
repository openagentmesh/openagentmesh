# AgentMesh

The central class. Manages NATS connection, agent subscriptions, and lifecycle.

## Construction

```python
from openagentmesh import AgentMesh

# Connect to an existing NATS server
mesh = AgentMesh("nats://localhost:4222")

# Connect using default localhost URL
mesh = AgentMesh()
```

### `AgentMesh(url: str = "nats://localhost:4222")`

Connect to a running NATS server. Defaults to `nats://localhost:4222` when no URL is provided.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str` | `"nats://localhost:4222"` | NATS connection URL |

### `AgentMesh.local()`

Async context manager that starts an embedded NATS subprocess with JetStream and pre-created KV buckets. For tests and quick demos only. The NATS process stops when the context exits.

```python
async with AgentMesh.local() as mesh:
    # embedded NATS starts, KV buckets created
    result = await mesh.call("echo", {"message": "hello"})
    # NATS stops when context exits
```

## Lifecycle

Two lifecycle models, one for each [participation pattern](../concepts/participation.md).

### `mesh.run()`

Blocking lifecycle for providers and hybrids. Connects to NATS, subscribes all registered agents, and blocks until interrupted. Similar to `uvicorn.run()`.

```python
mesh.run()
```

This is the standard entry point for any process that registers agents with `@mesh.agent`.

### `async with mesh:`

Scoped lifecycle for consumers. Connects on entry, disconnects on exit. No agent registration; used by scripts, notebooks, and orchestrators that only discover and call agents.

```python
async with mesh:
    result = await mesh.call("echo", {"message": "hello"})
```

Embedding in an existing async application (e.g. FastAPI lifespan):

```python
async def lifespan(app):
    async with mesh:
        yield
```

## Registration

### `@mesh.agent(spec)`

Decorator to register an async function as a mesh agent. Takes a single `AgentSpec` instance.

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

spec = AgentSpec(
    name="summarizer",
    channel="nlp",
    description="Summarizes text to a target length.",
    tags=["text", "summarization"],
)

@mesh.agent(spec)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    ...
```

Capabilities are inferred from the handler shape at decoration time. `AgentSpec` carries only human-authored metadata; `invocable` and `streaming` are never declared manually.

| Handler shape | `invocable` | `streaming` | Consumer API |
|---------------|-------------|-------------|--------------|
| `async def f(req) -> Out: return ...` | `True` | `False` | `mesh.call()` |
| `async def f(req) -> Chunk: yield ...` | `True` | `True` | `mesh.stream()` |
| `async def f() -> Event: yield ...` | `False` | `True` | `mesh.subscribe()` |

## Invocation

Four interaction modes. See [Invocation](../concepts/invocation.md) for patterns and semantics.

### `await mesh.call(name, payload, *, timeout=30.0)`

Synchronous request/reply. Blocks until the agent responds or times out.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent name |
| `payload` | `dict \| BaseModel` | required | Input payload (dict or Pydantic model) |
| `timeout` | `float` | `30.0` | Timeout in seconds |

**Returns:** `dict` with the deserialized response payload.

### `async for chunk in mesh.stream(name, payload, *, timeout=60.0)`

Streaming request. Yields response chunks as dicts.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent name |
| `payload` | `dict \| BaseModel` | required | Input payload |
| `timeout` | `float` | `60.0` | Total stream timeout in seconds |

**Yields:** `dict` chunks.

### `await mesh.send(name, payload, *, on_reply, on_error, reply_to, timeout)`

Async callback invocation. Three modes: fire-and-forget, managed callback, or manual reply subject.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent name |
| `payload` | `dict \| BaseModel` | required | Input payload |
| `on_reply` | `Callable[[dict], Awaitable[None]] \| None` | `None` | Callback for each reply message |
| `on_error` | `Callable[[MeshError], Awaitable[None]] \| None` | `None` | Callback for timeout or error |
| `reply_to` | `str \| None` | `None` | Manual reply subject (mutually exclusive with `on_reply`) |
| `timeout` | `float` | `60.0` | Inactivity timeout (only applies with `on_reply`) |

```python
# Managed callback
await mesh.send("summarizer", payload, on_reply=handle, on_error=on_err, timeout=30.0)

# Fire-and-forget
await mesh.send("summarizer", payload)

# Manual reply subject
await mesh.send("summarizer", payload, reply_to="mesh.results.abc")
```

## Subscription

### `async for msg in mesh.subscribe(*, agent, channel, subject, timeout)`

Subscribe to events on a subject, agent, or channel. Returns an async generator yielding dicts.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent` | `str \| None` | `None` | Agent name (resolves to event subject) |
| `channel` | `str \| None` | `None` | Channel name (wildcard for all events) |
| `subject` | `str \| None` | `None` | Raw NATS subject |
| `timeout` | `float \| None` | `None` | Inactivity timeout in seconds |

At least one of `agent`, `channel`, or `subject` must be provided. `agent` and `subject` are mutually exclusive. `channel` can accompany `agent` to override the default channel.

```python
# Subscribe to an agent's event stream
async for event in mesh.subscribe(agent="price-feed"):
    print(event["symbol"], event["price"])

# Subscribe to all events in a channel
async for event in mesh.subscribe(channel="finance"):
    print(event)

# Subscribe to a raw subject
async for msg in mesh.subscribe(subject="mesh.results.abc123", timeout=30.0):
    print(msg)
    break
```

## Discovery

### `await mesh.catalog(*, channel=None, tags=None, streaming=None, invocable=None)`

Lightweight listing of registered agents. Returns typed `CatalogEntry` objects.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `channel` | `str \| None` | `None` | Filter by channel |
| `tags` | `list[str] \| None` | `None` | Filter by tags (all must match) |
| `streaming` | `bool \| None` | `None` | Filter by streaming capability |
| `invocable` | `bool \| None` | `None` | Filter by invocable capability |

**Returns:** `list[CatalogEntry]`

```python
catalog = await mesh.catalog(channel="nlp")

for entry in catalog:
    print(entry.name, "-", entry.description)
    # entry.invocable, entry.streaming, entry.version, entry.tags also available
```

### `await mesh.discover(*, channel=None)`

Full `AgentContract` objects for all matching agents.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `channel` | `str \| None` | `None` | Filter by channel |

**Returns:** `list[AgentContract]`

### `await mesh.contract(name)`

Fetch a single agent's full contract. This is the authoritative source.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent name |

**Returns:** `AgentContract`

```python
contract = await mesh.contract("summarizer")

contract.name             # "summarizer"
contract.description      # "Summarizes text..."
contract.input_schema     # JSON Schema dict
contract.output_schema    # JSON Schema dict
contract.invocable        # True
contract.streaming        # False
```

## KV Store

Shared KV store for structured data exchange between agents.

### `await mesh.kv.put(key, value)`

Store a value.

### `await mesh.kv.get(key)`

Retrieve a value by key. Returns `str`.

### `async with mesh.kv.cas(key) as entry`

Single-attempt compare-and-swap. Read `entry.value`, modify it, and the new value is written on exit with CAS semantics. For concurrent access, use `update()` instead.

### `await mesh.kv.update(key, fn)`

CAS update with automatic retry. `fn` receives the current value and returns the new value. On revision conflict, the value is re-read and `fn` is called again.

```python
def increment(value: str) -> str:
    return str(int(value) + 1)

await mesh.kv.update("counter", increment)
```

### `async for value in mesh.kv.watch(key)`

Watch a key for changes. Yields the new value on each update.

## Workspace (Object Store)

Shared binary artifact storage backed by the NATS JetStream Object Store (`mesh-artifacts` bucket). Use for files, images, embeddings, or any binary payload too large for the KV store.

### `await mesh.workspace.put(key, data)`

Store a binary artifact.

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `str` | Artifact key (supports `/` for hierarchy, e.g. `docs/report.pdf`) |
| `data` | `bytes \| str` | Content to store. Strings are UTF-8 encoded. |

### `await mesh.workspace.get(key)`

Retrieve an artifact by key. Returns `bytes`.

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `str` | Artifact key |

**Returns:** `bytes`

### `await mesh.workspace.delete(key)`

Delete an artifact.

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `str` | Artifact key |

```python
# Store and retrieve a binary artifact
await mesh.workspace.put("results/output.png", image_bytes)
data = await mesh.workspace.get("results/output.png")
await mesh.workspace.delete("results/output.png")
```
