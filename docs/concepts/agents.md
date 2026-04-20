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

The SDK infers capabilities from the handler's signature at decoration time. No explicit `type` or capability flags needed.

| Pattern | Handler shape | Capabilities |
|---------|--------------|--------------|
| Non-streaming | `async def f(req: In) -> Out: return ...` | `invocable=True, streaming=False` |
| Streaming | `async def f(req: In) -> Chunk: yield ...` | `invocable=True, streaming=True` |
| Trigger | `async def f() -> Out: return ...` | `invocable=True, streaming=False` |
| Publisher | `async def f() -> Event: yield ...` | `invocable=False, streaming=True` |
| Watcher | `async def f() -> None: ...` | `invocable=False, streaming=False` |

The non-streaming pattern is the one shown in the [registration example above](#registering-an-agent). The other patterns are below.

### Streaming agent

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

A trigger is invocable but takes no input. The call itself is the signal. The handler returns a result to the caller.

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

The contract has `input_schema: null` and `output_schema` with the result model. The absent input schema signals to consumers that no payload is needed.

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

A watcher coordinates through shared state rather than messages. It has no input parameter and does not yield. The handler body typically contains a KV watch loop.

```python
spec = AgentSpec(name="extract", channel="pipeline", description="Watches for raw documents and extracts entities.")

@mesh.agent(spec)
async def extract():
    async for value in mesh.kv.watch("pipeline.*.raw"):
        doc = Document.model_validate_json(value)
        extracted = do_extraction(doc)
        await mesh.kv.put(f"pipeline.{doc.id}.extracted", extracted.model_dump_json())
```

Watcher agents are visible in the catalog and participate in liveness tracking, but are not invocable. Use `mesh.catalog(invocable=True)` to exclude them when selecting tools for LLM invocation.

!!! note "Scaling watchers"
    Watcher agents do not benefit from queue-group scaling. Every instance receives every KV update. For expensive processing, delegate to an invocable agent via `mesh.call()`, which scales via queue groups. The watcher becomes a thin routing layer; the processing agent scales independently.

## Lifecycle

Agents follow a predictable lifecycle:

1. **Start.** `mesh.run()` (blocking) or `async with mesh:` (non-blocking context manager)
2. **Register.** Subscribe to NATS subject (invocable agents) or launch background task (publishers and watchers), write contract to KV
3. **Serve.** Handle incoming requests via queue group (invocable), emit events (publishers), or react to state changes (watchers)
4. **Stop.** Exiting the context manager: cancel tasks, unsubscribe, drain, deregister, disconnect

## Queue Groups

Every invocable agent subscribes via a NATS queue group. This means multiple instances of the same agent automatically load-balance with no configuration changes. Deploy three replicas of `summarizer` and NATS distributes requests across them.

Publishers and watchers run as background tasks and do not use queue groups. See the [scaling note above](#watcher) for the recommended pattern when watcher processing needs to scale.
