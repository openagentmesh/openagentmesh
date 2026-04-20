# OpenAgentMesh

> Connect agents like you'd call an API

OpenAgentMesh is the fabric for multi-agent systems. It makes coding complex interaction patterns as simple as writing REST endpoints. 

It's an SDK with batteries included:

- Request/reply, pub/sub, and event streaming
- Typed contracts with self-discovery
- Shared KV and Object stores

No hardcoded interactions, full decoupling.

Start the mesh, then run:

```bash
oam mesh up
```

```python
from openagentmesh import AgentMesh, AgentSpec
from pydantic import BaseModel

mesh = AgentMesh()

class Input(BaseModel):
    content: str

class Summary(BaseModel):
    text: str

spec = AgentSpec(name="summarizer", channel="nlp",
                 description="Summarizes text to a target length.")

@mesh.agent(spec)
async def summarize(req: Input) -> Summary:
    return Summary(text=req.content[:100] + "...")

mesh.run()
```

Discover and call it from anywhere that connects to the same mesh:

```bash
oam agent call summarizer '{"content": "A long document..."}'
```

One agent, one connection string, no coupling. `@mesh.agent` registered a typed contract on the bus. The CLI (or any other agent) discovered `summarizer` by name and invoked it. Nothing imported the provider's code; it only knew the name.

## Why OpenAgentMesh

Multi-agent systems start simple and become a wiring nightmare. Agent A calls Agent B through a direct import. Agent C needs B too, so you extract a shared package. Agent D is in another repo, so you add an HTTP layer. Now you're maintaining contracts in three places, debugging serialization mismatches, and every schema change is a coordinated deploy.

The root problem is **coupling**. Agents shouldn't know where other agents live, how they're deployed, or what framework they use. They should know *what* another agent does and *how* to ask for it.

OpenAgentMesh gives every agent a typed contract on a shared message bus. Providers declare what they accept and return. Consumers discover agents at runtime and invoke them by name. Add an agent, remove an agent, scale an agent to ten instances. Nothing else changes.

The protocol runs on [NATS](https://nats.io), which provides pub/sub, request/reply, queue-group load balancing, and a key-value store for contracts in a single binary. One connection string replaces your service registry, message queue, and load balancer.

## Feature Highlights

**Discovery.** Agents publish contracts to a shared catalog. Consumers browse the catalog, filter by channel or tags, and fetch full schemas on demand. Two-step discovery keeps token costs flat even with hundreds of agents.

```python
catalog  = await mesh.catalog(channel="nlp")
contract = await mesh.contract("summarizer")
```

**Type Safety.** Input and output models are Pydantic v2. Contracts carry JSON Schemas generated from your type hints. Validation happens before your handler runs, and errors are structured, not stack traces.

```python
spec = AgentSpec(name="scorer", channel="finance",
                 description="Scores credit risk for a company.")

@mesh.agent(spec)
async def score(req: ScoreInput) -> ScoreOutput:
    ...
```

**Same Code, Any Scale.** Run `oam mesh up` to start a local development server, then connect with `AgentMesh()`. Point at shared infrastructure with a connection string. The agent code is identical.

```python
mesh = AgentMesh()                               # dev (after oam mesh up)
mesh = AgentMesh("nats://mesh.company.com:4222") # production
```

**Protocol-First.** The core asset is the protocol, not the SDK. Any NATS client in any language can participate by following the subject naming and envelope conventions. The Python SDK removes boilerplate; it doesn't gate access.

## Positioning

OpenAgentMesh is the **intra-system fabric**: agents within a team or platform talking to each other.

| Tool | Purpose |
|------|---------|
| **OpenAgentMesh** | Agent-to-agent communication within a system ("the LAN of agents") |
| **MCP** | LLM-to-tool communication (calling specific tools) |
| **A2A** | Cross-organization agent federation |

OpenAgentMesh contracts are a superset of the A2A Agent Card format. Agents on the mesh can be projected to A2A-compatible endpoints at the boundary.

## Next Steps

- **[Quickstart](welcome/quickstart.md)**: Two agents talking in under 30 lines
- **[Why OpenAgentMesh](welcome/why.md)**: The problem in depth and how OAM solves it
- **[Concepts](learn/concepts/index.md)**: Contracts, channels, discovery, and invocation patterns
