# Agents

An agent is an async function registered on the mesh. It receives typed input, does work, and returns typed output.

In practice, **any async function can be registered as an agent**, not just LLM-driven code: deterministic tools, data transformers, event publishers, or anything else that fits the function shape. The library was designed primarily for multi-agent systems, so the "agent" name stuck in the API even though the abstraction is more general.

## Registering an Agent

Define an `AgentSpec` with the agent's metadata, then apply `@mesh.agent`. This first example uses a **non-streaming** handler (the most common shape): take input, return one output.

```python
from pydantic import BaseModel
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

class EchoInput(BaseModel):
    message: str

class EchoOutput(BaseModel):
    reply: str

spec = AgentSpec(name="echo", description="Echoes a message back.")

@mesh.agent(spec)
async def echo(req: EchoInput) -> EchoOutput:
    return EchoOutput(reply=f"Echo: {req.message}")
```

The decorator:

1. Inspects the handler shape to determine capabilities
2. Builds an `AgentContract` from the spec and handler type hints
3. On entering the context manager, subscribes to a NATS queue group at `mesh.agent.{channel}.{name}`
4. Deserializes and validates input via Pydantic v2
5. Calls your handler function
6. Serializes the response and writes the contract to the registry

## Handler Shapes

The SDK infers two things from the handler's signature at decoration time:

1. **Invocable.** Does the handler promise a response to a caller? If so, the SDK subscribes it to a NATS request subject (with queue group for load balancing). Callers reach it via `mesh.call()` or `mesh.stream()`. A handler promises a response when it accepts input (has a request parameter) or returns a typed result (has an output model without streaming).
2. **Streaming.** Is the handler an async generator (`yield`)? If so, the response uses the streaming wire protocol instead of a single reply.

Handlers that are neither invocable nor streaming run as background tasks: the SDK launches them at startup and cancels them at shutdown. They never receive requests; they do their own work (watching KV, polling external systems, etc.).

These two properties combine into five common patterns:

| Pattern | Handler shape | Invocable | Streaming |
|---------|--------------|-----------|-----------|
| Responder | `async def f(req: In) -> Out: return ...` | Yes (has input) | No |
| Streamer | `async def f(req: In) -> Chunk: yield ...` | Yes (has input) | Yes |
| Trigger | `async def f() -> Out: return ...` | Yes (has output) | No |
| Publisher | `async def f() -> Event: yield ...` | No | Yes |
| Watcher | `async def f(): ...` | No | No |

No explicit `type` or capability flags. The handler shape is the source of truth.

### Responder

The most common pattern: accept typed input, return typed output. Shown in the [registration example above](#registering-an-agent).

### Streamer

```python
class SummarizeChunk(BaseModel):
    delta: str

spec = AgentSpec(name="summarizer", channel="nlp", description="Streams a summary.")

@mesh.agent(spec)
async def summarize(req: SummarizeInput) -> SummarizeChunk:
    async for token in call_llm_stream(req.text):
        yield SummarizeChunk(delta=token)
```

### Trigger

No input parameter, but returns a typed result. The call itself is the signal. Because the handler declares an output model, the SDK knows a caller is waiting for a response and subscribes it to a request subject.

```python
class RefreshResult(BaseModel):
    keys_refreshed: int
    duration_ms: float

spec = AgentSpec(name="refresh-cache", channel="ops", description="Flushes and rebuilds the cache. Returns refresh stats.")

@mesh.agent(spec)
async def refresh_cache() -> RefreshResult:
    stats = await rebuild_cache()
    return RefreshResult(keys_refreshed=stats.count, duration_ms=stats.elapsed)
```

Called without payload:

```python
result = await mesh.call("refresh-cache")
print(f"Refreshed {result['keys_refreshed']} keys")
```

### Publisher

```python
class PriceEvent(BaseModel):
    symbol: str
    price: float

spec = AgentSpec(name="price-feed", channel="finance", description="Emits price events.")

@mesh.agent(spec)
async def monitor_prices() -> PriceEvent:
    while True:
        yield PriceEvent(symbol="AAPL", price=await fetch_price())
        await asyncio.sleep(1)
```

### Watcher

No input, no output, no yield. Runs as a background task. The handler body typically contains a KV watch loop or other long-running coordination logic.

```python
spec = AgentSpec(name="extract", channel="pipeline", description="Watches for raw documents and extracts entities.")

@mesh.agent(spec)
async def extract():
    async for value in mesh.kv.watch("pipeline.*.raw"):
        doc = Document.model_validate_json(value)
        extracted = do_extraction(doc)
        await mesh.kv.put(f"pipeline.{doc.id}.extracted", extracted.model_dump_json())
```

All agents (including publishers and watchers) are visible in the catalog and participate in liveness tracking. Use `mesh.catalog(invocable=True)` to select only agents that accept calls.

!!! note "Scaling background agents"
    Publishers and watchers run as background tasks and do not use queue groups. Every instance receives every KV update or emits its own event stream. For expensive processing in a watcher, delegate to an invocable agent via `mesh.call()`, which scales via queue groups. The watcher becomes a thin routing layer; the processing agent scales independently.

## Type Hints

Handler type hints can be any type that Pydantic v2 can validate, not just `BaseModel` subclasses. Use scalar types, generics, or standard library types when a full model would be unnecessary ceremony.

### Scalar types

```python
spec = AgentSpec(name="greet", description="Greets by name.")

@mesh.agent(spec)
async def greet(name: str) -> str:
    return f"Hello, {name}"
```

The contract schema reflects the scalar type:

```json
{
  "input_schema": { "type": "string" },
  "output_schema": { "type": "string" }
}
```

### Generic containers

```python
spec = AgentSpec(name="split", description="Splits text into words.")

@mesh.agent(spec)
async def split(text: str) -> list[str]:
    return text.split()
```

### Supported types

Any type Pydantic's `TypeAdapter` can handle:

- **Scalars:** `str`, `int`, `float`, `bool`
- **Standard library:** `datetime`, `date`, `UUID`, `Path`, `Decimal`, `Enum` subclasses
- **Generics:** `list[X]`, `dict[str, X]`, `set[X]`, `tuple[X, ...]`
- **Optionals and unions:** `X | None`, `Optional[X]`, `Union[X, Y]`
- **Literals:** `Literal["a", "b"]`
- **Pydantic models:** `BaseModel` subclasses

Types that cannot produce a JSON Schema (callables, IO objects) raise an error at decoration time.

Use `BaseModel` when your payload has multiple fields or when you want named, self-documenting schemas in the contract. Use scalar or generic types when the payload is a single value.

## Lifecycle

Agents follow a predictable lifecycle:

1. **Start.** `mesh.run()` (blocking) or `async with mesh:` (non-blocking context manager)
2. **Register.** Invocable agents subscribe to a NATS request subject. Publishers and watchers launch as background tasks. All agents write their contract to the registry.
3. **Serve.** Invocable agents handle requests via queue group. Publishers emit events. Watchers react to state changes.
4. **Stop.** Exiting the context manager: cancel background tasks, unsubscribe, drain, deregister, disconnect.

## Queue Groups

Every invocable agent subscribes via a NATS queue group. This means multiple instances of the same agent automatically load-balance with no configuration changes. Deploy three replicas of `summarizer` and NATS distributes requests across them.
