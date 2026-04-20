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
| Publisher | `async def f() -> Event: yield ...` | `invocable=False, streaming=True` |

The non-streaming pattern is the one shown in the [registration example above](#registering-an-agent). The two yielding patterns are below.

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

## Lifecycle

Agents follow a predictable lifecycle:

1. **Start.** `mesh.run()` (blocking) or `async with mesh:` (non-blocking context manager)
2. **Register.** Subscribe to NATS subject, write contract to KV
3. **Serve.** Handle incoming requests via queue group
4. **Stop.** Exiting the context manager: unsubscribe, drain, deregister, disconnect

## Queue Groups

Every agent subscribes via a NATS queue group. This means multiple instances of the same agent automatically load-balance with no configuration changes. Deploy three replicas of `summarizer` and NATS distributes requests across them.
