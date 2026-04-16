# AgentMesh — Developer Experience Design

**Status:** Working design document  
**Last updated:** April 2026

---

## 1. Core Design Philosophy

AgentMesh should do for multi-agent systems what FastAPI did for backend web applications: create a developer experience so intuitive and well-documented that any engineer can go from zero to a working multi-agent system in minutes.

The library is **protocol-first**. The NATS-based protocol is the product. The Python SDK is a convenience implementation that makes the protocol effortless to use. Any developer with a raw NATS client in any language can participate in the mesh — the SDK just removes the boilerplate.

NATS is not just a transport layer — it provides the complete infrastructure stack the mesh needs: sub-millisecond pub/sub, durable streams, a KV store for the registry and state, an Object Store for artifacts and shared memory, and account-based multi-tenancy for cross-org trust isolation. The SDK exposes all of these as mesh-native concepts rather than raw NATS primitives.

---

## 2. The Adoption Continuum

AgentMesh does not have two separate modes. It has a single architecture where local development and enterprise scale are endpoints on a continuum. The same code, same patterns, and same mental model apply everywhere. The only thing that changes is the NATS connection string.

### 2.1 Enclosed Mode (The Onramp)

A developer installs the library, runs a local NATS server, builds a few agents, and immediately feels the difference between hardwiring agents together and composing them through a message bus. The "aha" moment — adding a new agent without changing anything else — is what drives adoption.

```python
# Enclosed: local development, one developer, everything in one place
mesh = AgentMesh()  # connects to agentmesh up (localhost:4222)
```

### 2.2 Composable Mode (The Destination)

The developer shares the NATS URL with a teammate. Agents from different repos, different teams, different runtimes start appearing on the mesh. The system becomes a shared fabric.

```python
# Composable: connect to shared infrastructure
mesh = AgentMesh("nats://mesh.company.com:4222")
```

### 2.3 The Transition Is Invisible

The agent code is identical in both cases. Moving from enclosed to composable requires changing one line — the connection string. No refactoring, no architectural changes, no new abstractions.

---

## 3. Three Personas, One Protocol

### 3.1 Mesh Operator

Starts NATS, configures KV buckets, manages health monitoring. In enclosed mode, this is the developer themselves (via `agentmesh up`). In composable mode, this is a platform or DevOps team.

The SDK provides convenience tooling for operators but does not require it. Any existing NATS deployment is a valid mesh target.

### 3.2 Agent Provider

Connects to an existing mesh, registers an agent, and handles incoming requests. Providers don't know or care who started NATS. They have a URL and credentials, and they plug in.

### 3.3 Agent Consumer

Connects to the mesh, discovers what's available, and calls agents. Consumers might be other agents, orchestrators, CLI tools, notebooks, or web applications. They never register anything — they use the mesh as a service catalog and invocation layer.

---

## 4. Registration: Two Paths

### 4.1 The Core Tension

Existing agents are **imperative** — you call them (`agent.invoke(...)`). Mesh agents need to be **reactive** — they listen for messages and respond. Registration bridges this gap by inverting control: the mesh owns the event loop, not the developer.

`register()` (or the `@mesh.agent` decorator) does three things internally:

1. **Introspects** — extracts input/output schemas from type hints or explicit models.
2. **Subscribes** — wires a NATS subscription that routes incoming messages to the handler.
3. **Publishes** — writes the agent's contract to the KV registry for discovery.

Then `mesh.run()` starts the event loop — analogous to `uvicorn.run()` in FastAPI.

### 4.2 Path 1: Function-First (Primary DX)

The flagship experience. Inspired by FastAPI's route decorators. The developer writes a function; the framework handles everything else.

**Buffered agent** — for deterministic or fast functions that return a complete typed response:

```python
from openagentmesh import AgentMesh
from pydantic import BaseModel

mesh = AgentMesh()

class ClassifyInput(BaseModel):
    text: str

class ClassifyOutput(BaseModel):
    label: str
    confidence: float

@mesh.agent(
    name="classifier",
    channel="nlp",
    type="tool",
    description="Classifies text sentiment. Returns positive, negative, or neutral.",
)
async def classify(req: ClassifyInput) -> ClassifyOutput:
    result = await run_classifier(req.text)
    return ClassifyOutput(label=result.label, confidence=result.score)

mesh.run()
```

**Streaming agent** — for LLM-powered agents that produce incremental output:

```python
from openagentmesh import AgentMesh
from pydantic import BaseModel

mesh = AgentMesh()

class SummarizeInput(BaseModel):
    text: str
    max_length: int = 200

class SummarizeChunk(BaseModel):
    delta: str

@mesh.agent(
    name="summarizer",
    channel="nlp",
    description="Summarizes input text to a target length. Handles documents, articles, and raw text.",
)
async def summarize(req: SummarizeInput) -> SummarizeChunk:
    async for token in call_llm_stream(req.text, req.max_length):
        yield SummarizeChunk(delta=token)

mesh.run()
```

**Publisher agent** — for agents that emit events without being invoked:

```python
@mesh.agent(
    name="price-feed",
    channel="finance",
    type="publisher",
    description="Emits real-time AAPL price updates every second.",
)
async def monitor_prices() -> PriceEvent:
    while True:
        yield PriceEvent(symbol="AAPL", price=await fetch_price())
        await asyncio.sleep(1)
```

**What the decorator does internally:**

1. Inspects the handler's type hints and signature shape (`isasyncgenfunction`, request param presence).
2. Determines `type` (if not explicit) and `capabilities.streaming` from the handler shape.
3. Generates JSON Schemas via Pydantic's `model_json_schema()` for input, output, and chunk models.
4. Subscribes to the agent's NATS subject using a queue group (invocable agents only).
5. On startup: writes the full contract (including inferred capabilities) to the KV registry.

The function body is framework-agnostic. Use PydanticAI, LangChain, CrewAI, raw API calls, or deterministic code inside. The mesh does not care.

### 4.3 Path 2: Bring-Your-Agent (Secondary DX)

For developers who already have a working agent and want to expose it on the mesh. The developer provides a handler function that bridges between the mesh's typed interface and their agent's native API.

```python
from pydantic_ai import Agent
from agentmesh import AgentMesh
from pydantic import BaseModel

pydantic_agent = Agent("claude-sonnet-4-20250514", system_prompt="You are a summarizer...")

mesh = AgentMesh("nats://localhost:4222")

class SummarizeInput(BaseModel):
    text: str
    max_length: int = 200

class SummarizeOutput(BaseModel):
    summary: str

async def handle_summarize(req: SummarizeInput) -> SummarizeOutput:
    result = await pydantic_agent.run(req.text)
    return SummarizeOutput(summary=result.data)

mesh.register(
    name="summarizer",
    channel="nlp",
    description="Summarizes input text to a target length.",
    input_model=SummarizeInput,
    output_model=SummarizeOutput,
    handler=handle_summarize,
)

mesh.run()
```

### 4.4 What We Explicitly Do NOT Build

**Framework-specific adapters** (e.g., `agentmesh.adapters.langchain`) are deprioritized. Major agent frameworks ship breaking changes frequently. Maintaining adapters for PydanticAI, LangChain, CrewAI, and others would create an unsustainable maintenance treadmill. The handler-function pattern puts the developer in control of the translation layer without requiring us to track upstream churn.

**Framework protocol/interface** (e.g., a `MeshCompatible` abstract class for frameworks to implement) is a future option. If frameworks want to integrate with AgentMesh natively, they implement the protocol on their side. That's their initiative, not ours.

---

## 5. SDK Surface

### 5.1 Connection

```python
mesh = AgentMesh("nats://...")        # connect to existing NATS
mesh = AgentMesh()                    # connect to localhost:4222 (default)
```

### 5.2 Provider Side (Registering Agents)

```python
# Buffered agent (type="tool" inferred — returns value)
@mesh.agent(name=..., channel=..., description=...)
async def handler(req: InputModel) -> OutputModel:
    return OutputModel(...)

# Streaming agent (type="agent" inferred — yields chunks)
@mesh.agent(name=..., channel=..., description=...)
async def handler(req: InputModel) -> ChunkModel:
    async for item in produce_output(req):
        yield ChunkModel(delta=item)

# Publisher agent (no request param, yields events)
@mesh.agent(name=..., channel=..., type="publisher", description=...)
async def handler() -> EventModel:
    while True:
        yield EventModel(...)

# Explicit registration (bring-your-own handler)
mesh.register(name=..., channel=..., description=...,
              input_model=..., output_model=..., handler=...)
```

**Handler signature summary:**

| Shape | Inferred type | `capabilities.streaming` | Consumer method |
|---|---|---|---|
| `async def f(req: I) -> O: return ...` | `"tool"` | `false` | `mesh.call()` |
| `async def f(req: I) -> C: yield ...` | `"agent"` | `true` | `mesh.stream()` |
| `async def f() -> E: yield ...` | `"publisher"` | n/a | `mesh.subscribe()` |

### 5.3 Consumer Side (Using the Mesh)

```python
# Discovery
agents = await mesh.discover()                     # all agents, full contracts
agents = await mesh.discover(channel="nlp")        # filtered by channel
catalog = await mesh.catalog()                     # lightweight listing
catalog = await mesh.catalog(channel="nlp")        # filtered lightweight listing
contract = await mesh.contract("summarizer")       # single agent's full details

# Invocation — buffered (capabilities.streaming: false)
result = await mesh.call("classifier", payload, timeout=10.0)

# Invocation — streaming (capabilities.streaming: true)
async for chunk in mesh.stream("summarizer", payload, timeout=60.0):
    print(chunk.delta, end="")

# Async callback (fire-and-forget)
await mesh.send("summarizer", payload, reply_to="mesh.results.abc")

# Pub/sub — subscribe to publisher events
async for event in mesh.subscribe("price-feed"):
    print(event.symbol, event.price)

async for event in mesh.subscribe(channel="finance"):   # all finance publishers
    print(event.source, event.data)

# Shared workspace (Object Store)
key = await mesh.workspace.put("pipeline-123/doc.md", content_bytes)
content = await mesh.workspace.get(key)
await mesh.workspace.delete(key)
```

### 5.4 Lifecycle

```python
mesh.run()             # blocking — starts the NATS event loop (like uvicorn.run)
await mesh.start()     # non-blocking — for embedding in existing async apps
await mesh.stop()      # graceful shutdown: unsubscribe, deregister, drain in-flight
```

### 5.5 CLI

```bash
agentmesh up           # start local NATS, create KV buckets
agentmesh init         # generate Docker Compose stack for team development
agentmesh status       # show registered agents and health
```

---

## 6. The Service Mesh Analogy

AgentMesh applies the service mesh pattern — proven in enterprise infrastructure by systems like Istio, Linkerd, and MuleSoft — to AI agent architectures.

| Service Mesh Concept | AgentMesh Equivalent |
|---|---|
| Envoy sidecar proxy | SDK (handles serialization, validation, tracing, health) |
| Service registry (Consul, etcd) | NATS KV contract registry |
| Service endpoint | NATS subject (`mesh.agent.{channel}.{name}`) |
| Load balancer | NATS queue groups (built-in) |
| Control plane (istiod) | Spawner service + registry management (Tier 3+) |
| DNS / service discovery | `mesh.discover()` / `mesh.catalog()` |
| Sidecar middleware | SDK middleware hooks (tracing, auth, rate limiting) |
| Shared filesystem / artifact store | NATS Object Store via `mesh.workspace` |
| Network policy / org boundary | NATS accounts (cross-org trust and subject isolation) |

The critical difference: service meshes route based on network-level rules (URLs, headers, IP ranges). AgentMesh routes based on **semantic understanding** — what the agent does, what it accepts, and whether it's the right fit for a given task. This is the agent-native value on top of the service mesh concept.

---

## 7. Design Principles Summary

1. **One architecture, not two modes.** Enclosed and composable are points on a continuum, not separate products.
2. **The connection string is the only configuration.** Same agent code runs against local or production NATS.
3. **Functions are agents.** The decorator turns any async function into a mesh participant — regardless of what is behind it. A deterministic NER function and a multi-step LLM reasoner are both agents: they both subscribe to a subject, respond to requests, and publish contracts. Autonomy is a spectrum; the participation model is uniform.
4. **Handler shape is the contract.** Whether a handler returns or yields determines streaming capability. Whether it takes a request parameter determines if it is invocable. The SDK infers these from the function signature — no flags required.
5. **The mesh is a client, not a server.** `AgentMesh` connects to NATS — it doesn't own it. Local NATS is a convenience, not the core abstraction.
6. **Discovery is the killer feature.** In composable mode, discovery across team boundaries is what transforms a message bus into an agent platform.
7. **Protocol first, SDK second.** The protocol spec is the product. SDKs are convenience layers. Any NATS client can participate.
8. **No framework lock-in.** The function body is the developer's territory. Use any LLM framework, any model, any logic inside.
