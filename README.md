<br />
<div align="center">
  <a href="https://openagentmesh.github.io/openagentmesh/">
    <img src="https://raw.githubusercontent.com/openagentmesh/openagentmesh/main/logo/logo.png" alt="OpenAgentMesh" width="100" height="100">
  </a>

  <h3 align="center">OpenAgentMesh</h3>

  <p align="center">
    The fabric for multi-agent systems, with the simplicity of a REST endpoint.
    <br />
    <a href="https://openagentmesh.github.io/openagentmesh/"><strong>Documentation</strong></a>
  </p>

  [![PyPI](https://img.shields.io/pypi/v/openagentmesh)](https://pypi.org/project/openagentmesh/)
  [![Python](https://img.shields.io/pypi/pyversions/openagentmesh)](https://pypi.org/project/openagentmesh/)
  [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
</div>

## ✨ Highlights

- **Decoupled multi-agent system** Run agents and tools however you want. Have them talk to each other as if they were running in the same process.
- **Bring your own agent.** Works with any agentic framework (LangChain, CrewAI, PydanticAI, etc.).
- **Agents as functions.** Just wrap your agents in a handler function and the `@mesh.agent` decorator. Done.
- **Batteries included.** Agent catalog with runtime discovery, sync/async requests, pub/sub, shared KV and Object store, load balancing. All from a single infrastructure dependency.
- **Protocol-first.** The protocol is the product. Python SDK and CLI facilitate use. Any NATS client in any language can participate by following the subject and envelope format.
- **No-effort scaling.** Code remains the same. Just add instances.

## 📦 Installation

```bash
pip install openagentmesh
```

## 🎬 See it in action

```bash
oam demo
```

## 🚀 Quickstart

**1. Start a local mesh:**

```bash
oam mesh up
```

**2. Register an agent** (`agent.py`):

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

@mesh.agent(AgentSpec(name="echo", description="Echoes a message back."))
async def echo(req: str) -> str: 
    return f"Echo: {req}"

mesh.run()
```

```bash
python agent.py
```

**3. Discover and call it from the terminal:**

```bash
oam mesh catalog               # list registered agents
oam agent contract echo        # view the full contract
oam agent call echo '"hello"'  # invoke it
```

No hardcoded addresses. The CLI discovers `echo` from the mesh, reads its contract, and calls it.

## 🔗 How OAM relates to MCP and A2A

OAM is not a replacement for MCP or A2A. It complements both.

**MCP** is the standard for connecting LLMs to tools. OAM adds value where MCP alone hits friction: context bloat from loading too many tool schemas, patterns beyond request/reply (pub/sub, async callbacks, shared context), and automatic cross-team discovery.

**A2A** is Google's protocol for cross-organization agent federation over HTTP. OAM contracts are an A2A-compatible superset: A2A fields at top level, OAM extensions under `x-agentmesh`. Use OAM internally, project to A2A at the boundary where internal meets external.

| Concern | MCP | OAM | A2A |
|---------|-----|-----|-----|
| Scope | Third party toolsets | Agent-to-agent/tool (internal) | Agent-to-agent (cross-org) |
| Transport | stdio / SSE | NATS | HTTP |
| Discovery | Manual config | Automatic | Agent Card directory |
| Load balancing | N/A | NATS queue groups | External |
| Interaction | Streaming | Request/reply, streaming, async callback, pub/sub, reactive watcher | Request/reply, streaming |

## 📖 How to use

Any async function can be an agent: LLM chains, deterministic tools, data transformers, event publishers. The `@mesh.agent` decorator inspects the function signature to infer capabilities automatically.

Five handler patterns, determined by the function shape:

| Pattern | Signature | What it does |
|---------|-----------|-------------|
| **Responder** | `async def f(req: TypeIn) -> TypeOut` (returns) | Takes input, returns output |
| **Streamer** | `async def f(req: In) -> TypeOut` (yields) | Takes input, streams data back |
| **Trigger** | `async def f() -> TypeOut` (returns)| No input, returns output on call |
| **Publisher** | `async def f() -> TypeOut` (yields) | Emits events continuously |
| **Watcher** | `async def f()` | No input/output. Background task (KV watch, polling) |

No capability flags to set. The handler shape is the source of truth.

## 📡 Invocation patterns

Four ways to interact with agents:

```python
# Synchronous request/reply
result = await mesh.call("summarizer", {"text": doc})

# Streaming
async for chunk in mesh.stream("summarizer", {"text": doc}):
    print(chunk["delta"], end="")

# Async callback (non-blocking)
await mesh.send("summarizer", payload, on_reply=callback)

# Pub/sub events
async for event in mesh.subscribe(agent="price-feed"):
    print(event["price"])
```

## 🔍 Discovery

Two-tier discovery designed for efficient agent selection, including by LLMs:

```python
# Tier 1: lightweight catalog (~20-30 tokens per agent)
catalog = await mesh.catalog() # Get summary of all agents on the mesh
catalog = await mesh.catalog(channel="finance.risk") # Filter the catalog

# Tier 2: full contract with JSON Schemas (only for the agent you need)
contract = await mesh.contract("summarizer")
contract.input_schema   # JSON Schema dict
contract.description    # LLM-consumable description
```

Catalog entries are compact enough for direct LLM consumption. The LLM picks from the catalog, then only the selected agent's full schema is fetched. Channels and tags narrow the candidate set further.

## 💾 Shared state

Agents can share context through **KV Store** and binary artifacts through **Workspace**, and watch for changes in both.

```python
# KV: structured data with watch and compare-and-swap
await mesh.kv.put("config/threshold", "0.85")
value = await mesh.kv.get("config/threshold")

async for value in mesh.kv.watch("pipeline.*.status"): 
    print(f"Status changed: {value}")

# Workspace: binary artifacts (files, images, embeddings)
await mesh.workspace.put("docs/report.pdf", pdf_bytes)
data = await mesh.workspace.get("docs/report.pdf")
```

## 🤝 Participation patterns

Two ways to participate: register agents, or just connect and call.

**Registered** processes use `@mesh.agent` to declare agents. They appear in the catalog, have contracts, and participate in liveness tracking.

**Unregistered** processes connect, discover, call, and disconnect. Scripts, notebooks, CLI tools can use this pattern:

```python
async with mesh:
    catalog = await mesh.catalog()
    result = await mesh.call("summarizer", {"text": "..."})
```

## ⚙️ Technology

OAM uses **NATS** as its single infrastructure dependency. One embedded binary provides everything, no need for additional servers/services:

| NATS capability | OAM use |
|----------------|---------|
| Pub/sub | Event fan-out, callbacks, streaming |
| Request/reply | `mesh.call()` |
| Queue groups | Automatic load balancing across agent instances |
| KV store | Contract registry, agent catalog, shared context |
| Object store | Shared workspace for artifacts |

No Consul for discovery. No Redis for state. No RabbitMQ or Kafka for messaging. One connection, all primitives.

**Pydantic v2** generates JSON Schemas from type hints for every agent contract. Runtime validation at the mesh boundary; malformed requests are rejected before reaching your handler.

**Protocol-first.** The protocol is the product, the Python SDK and CLI are the first implementation. Any NATS client in any language (Javascript, Go, Rust, etc.) can participate by following the subject naming and envelope format. Dedicated SDKs will come in the future.

## Scaling

Deploy multiple instances of the same agent. NATS queue groups distribute requests automatically:

```python
# Same code, any number of instances. No config changes.
@mesh.agent(AgentSpec(name="summarizer", channel="nlp", description="..."))
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    ...
```

Local and production use the same architecture. The only thing that changes is the connection string:

```python
mesh = AgentMesh()                                # local (oam mesh up)
mesh = AgentMesh("nats://mesh.company.com:4222")  # production
```

## 💻 CLI

The `oam` CLI is installed with the SDK:

| Command | Description |
|---------|-------------|
| `oam demo` | Launch interactive demo with sample agents |
| `oam mesh up` | Start local dev server (NATS + JetStream + KV) |
| `oam mesh down` | Stop local server |
| `oam mesh connect <url>` | Point at a remote mesh |
| `oam mesh listen <subject>` | Subscribe to live traffic |
| `oam mesh catalog` | List registered agents |
| `oam agent contract <name>` | View an agent's contract |
| `oam agent call <name> <json>` | Invoke an agent |
| `oam agent stream <name> <json>` | Stream from an agent |
| `oam agent subscribe <name>` | Subscribe to publisher events |

See the [full documentation](https://openagentmesh.github.io/openagentmesh/) for more details.

## 🤲 Contributing

Contributions are welcome. Open an [issue](https://github.com/openagentmesh/openagentmesh/issues) for bugs or new features before submitting a pull request.

For bug fixes, include a failing test that demonstrates the issue. For new features, start with the use case: describe what you're trying to build and why the current API doesn't cover it.

⭐️ Hit the star if you like this! ⭐️

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.
