# AgentMesh

The central class. Manages NATS connection, agent subscriptions, heartbeat loops, and lifecycle.

## Construction

```python
from agentmesh import AgentMesh

# Connect to an existing NATS server
mesh = AgentMesh("nats://localhost:4222")

# Start an embedded NATS subprocess (dev only)
mesh = AgentMesh.local()
```

### `AgentMesh(url: str)`

Connect to a running NATS server.

| Parameter | Type | Description |
|-----------|------|-------------|
| `url` | `str` | NATS connection URL |

### `AgentMesh.local()`

Start an embedded NATS subprocess with JetStream and pre-created KV buckets. For development only.

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

Graceful shutdown: unsubscribe → drain → deregister → disconnect.

## Registration

### `@mesh.agent()`

Decorator to register an async function as a mesh agent.

```python
@mesh.agent(
    name="summarizer",
    channel="nlp",
    description="Summarizes text to a target length.",
    tags=["text", "summarization"],
)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    ...
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Unique agent name |
| `description` | `str` | required | LLM-consumable description |
| `channel` | `str \| None` | `None` | Hierarchical namespace |
| `tags` | `list[str]` | `[]` | Searchable tags |

### `mesh.register()`

Imperative registration for cases where decorators don't fit.

```python
mesh.register(
    name="summarizer",
    description="Summarizes text to a target length.",
    handler=summarize_handler,
    input_model=SummarizeInput,
    output_model=SummarizeOutput,
    channel="nlp",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Unique agent name |
| `description` | `str` | required | LLM-consumable description |
| `handler` | `Callable` | required | Async handler function |
| `input_model` | `type[BaseModel]` | required | Pydantic v2 input model |
| `output_model` | `type[BaseModel]` | required | Pydantic v2 output model |
| `channel` | `str \| None` | `None` | Hierarchical namespace |

## Invocation

### `await mesh.call(name, payload, *, timeout=30.0)`

Synchronous request/reply. Blocks until the agent responds or times out.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent name |
| `payload` | `dict` | required | JSON-serializable input |
| `timeout` | `float` | `30.0` | Timeout in seconds |

**Returns:** `dict`: deserialized response payload.

### `await mesh.send(name, payload, *, reply_to)`

Async callback invocation. Fire-and-forget with a reply subject.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent name |
| `payload` | `dict` | required | JSON-serializable input |
| `reply_to` | `str` | required | Subject for the response |

## Discovery

### `await mesh.catalog(*, channel=None, tags=None)`

Lightweight listing of registered agents.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `channel` | `str \| None` | `None` | Filter by channel prefix |
| `tags` | `list[str] \| None` | `None` | Filter by tags |

**Returns:** `list[dict]`: entries with `name`, `description`, `version`, `tags`.

```python
catalog = await mesh.catalog(channel="nlp")

# [
#   {"name": "summarizer", "channel": "nlp", "description": "Summarizes text to a target length.",
#    "version": "1.0.0", "tags": ["text", "summarization"]},
#   {"name": "sentiment", "channel": "nlp", "description": "Classifies sentiment of input text.",
#    "version": "1.2.0", "tags": ["text", "classification"]},
# ]
```

### `await mesh.discover(*, channel=None)`

Full `AgentContract` objects for all matching agents.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `channel` | `str \| None` | `None` | Filter by channel prefix |

**Returns:** `list[AgentContract]`

```python
agents = await mesh.discover(channel="nlp")

# [
#   AgentContract(name="summarizer", channel="nlp", version="1.0.0", ...),
#   AgentContract(name="sentiment", channel="nlp", version="1.2.0", ...),
# ]
```

### `await mesh.contract(name)`

Fetch a single agent's full contract. This is the authoritative source.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent name |

**Returns:** `AgentContract`

```python
contract = await mesh.contract("summarizer")

# AgentContract(
#   name="summarizer",
#   description="Summarizes text to a target length.",
#   version="1.0.0",
#   capabilities={"streaming": False, "pushNotifications": True},
#   skills=[Skill(id="summarizer", tags=["text", "summarization"], ...)],
#   x_agentmesh={"type": "agent", "channel": "nlp", "sla": {...}},
# )
```
