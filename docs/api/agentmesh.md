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

### `mesh.run()`

Start the event loop and block until interrupted. Similar to `uvicorn.run()`.

```python
mesh.run()
```

### `await mesh.start()`

Start in non-blocking mode. Use this to embed the mesh in an existing async application.

```python
async def lifespan(app):
    await mesh.start()
    yield
    await mesh.stop()
```

### `await mesh.stop()`

Graceful shutdown: unsubscribe, drain, deregister, disconnect.

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

Capabilities are inferred from the handler shape at decoration time:

| Handler shape | `invocable` | `streaming` | Consumer API |
|---------------|-------------|-------------|--------------|
| `async def f(req) -> Out: return ...` | `True` | `False` | `mesh.call()` |
| `async def f(req) -> Chunk: yield ...` | `True` | `True` | `mesh.stream()` |
| `async def f() -> Event: yield ...` | `False` | `True` | `mesh.subscribe()` |

## Invocation

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

### `await mesh.send(name, payload, *, reply_to)`

Async callback invocation. Fire-and-forget with a reply subject.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent name |
| `payload` | `dict \| BaseModel` | required | Input payload |
| `reply_to` | `str \| None` | `None` | Subject for the response |

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

## Context

Shared KV store for structured data exchange between agents.

### `await mesh.context.put(key, value)`

Store a value.

### `await mesh.context.get(key)`

Retrieve a value by key. Returns `str`.

### `async with mesh.context.cas(key) as entry`

Single-attempt compare-and-swap. Read `entry.value`, modify it, and the new value is written on exit with CAS semantics. For concurrent access, use `update()` instead.

### `await mesh.context.update(key, fn)`

CAS update with automatic retry. `fn` receives the current value and returns the new value. On revision conflict, the value is re-read and `fn` is called again.

```python
def increment(value: str) -> str:
    return str(int(value) + 1)

await mesh.context.update("counter", increment)
```

### `async for value in mesh.context.watch(key)`

Watch a key for changes. Yields the new value on each update.
