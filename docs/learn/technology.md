# Technology Stack

## Why NATS

Most agent frameworks cobble together separate systems for messaging, service discovery, and state management. OAM uses **NATS** -- a single deployment that provides everything the mesh needs:

```python
from openagentmesh import AgentMesh

# One connection string. Everything included.
mesh = AgentMesh("nats://mesh.company.com:4222")
```

What NATS provides out of the box:

| Capability | What OAM uses it for |
|-----------|----------------------|
| **Pub/sub** | Agent event fan-out, real-time notifications |
| **Request/reply** | Synchronous agent invocation (`mesh.call()`) |
| **Queue groups** | Automatic load balancing across agent instances |
| **KV store** | Contract registry, agent catalog |
| **Object store** | Shared workspace for artifacts between agents |

No Consul for discovery. No Redis for state. No RabbitMQ for messaging. No Nginx for load balancing. One binary, one connection, all primitives.

!!! tip "Sub-millisecond latency"
    NATS routes messages in microseconds. Agent-to-agent invocation overhead is negligible compared to LLM inference time.

### Queue groups: free load balancing

When multiple instances of the same agent connect to the mesh, NATS automatically distributes requests across them. No configuration, no load balancer, no code changes:

```python
# Deploy 3 instances of the same agent -- NATS handles the rest
@mesh.agent(name="summarizer", channel="nlp", description="...")
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    ...

# Consumers don't know or care how many instances exist
result = await mesh.call("summarizer", payload)
```

## Why Pydantic v2

Every agent on the mesh publishes a typed contract with input/output JSON Schemas. Pydantic v2 generates these schemas directly from Python type hints:

```python
from pydantic import BaseModel

class SummarizeInput(BaseModel):
    text: str
    max_length: int = 200

class SummarizeOutput(BaseModel):
    summary: str
    token_count: int

@mesh.agent(name="summarizer", channel="nlp", description="...")
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    ...
# The decorator introspects type hints, generates JSON Schemas,
# and publishes them to the registry. No manual schema authoring.
```

What you get from Pydantic:

- **JSON Schema generation** from type hints -- schemas that LLMs can consume for tool selection
- **Runtime validation** at the mesh boundary -- malformed requests are rejected before reaching your handler
- **Serialization/deserialization** -- the SDK handles JSON encoding automatically

## Why protocol-first

The NATS protocol **is** the product. The Python SDK is a convenience layer.

Any NATS client in any language can participate in the mesh by following the subject naming conventions and message envelope format. A Go service, a Rust CLI tool, or a Node.js application can register agents, discover the catalog, and invoke other agents -- no SDK required.

```
# Subject conventions (any NATS client can use these directly)
mesh.agent.{channel}.{name}      # invocation
mesh.registry.{channel}.{name}   # contract in KV
mesh.catalog                     # lightweight index in KV
mesh.health.{channel}.{name}     # heartbeat
```

This means OAM is not locked to Python. The protocol is language-agnostic by design.

## The service mesh analogy

If you've built microservices with Istio or Linkerd, the architecture will feel familiar:

| Service Mesh Concept | OAM Equivalent |
|---|---|
| Service registry (Consul, etcd) | NATS KV contract registry |
| Service endpoint | NATS subject (`mesh.agent.{channel}.{name}`) |
| Load balancer | NATS queue groups (built-in) |
| DNS / service discovery | `mesh.discover()` / `mesh.catalog()` |
| Sidecar proxy (Envoy) | SDK (validation, serialization, tracing, health) |
| Sidecar middleware | SDK middleware hooks |
| Shared filesystem | NATS Object Store via `mesh.workspace` |

The key difference: service meshes route based on network rules (URLs, headers, IP ranges). OAM routes based on **semantic understanding** -- what the agent does, what it accepts, and whether it's the right fit for a given task.

## Same code, any scale

The agent code is identical whether you're running locally or across a multi-region cluster:

```python
# Development: embedded NATS subprocess
mesh = AgentMesh.local()

# Production: shared NATS infrastructure
mesh = AgentMesh("nats://mesh.company.com:4222")
```

`AgentMesh.local()` downloads the NATS binary to `~/.agentmesh/bin/`, starts it as a subprocess with JetStream and KV pre-configured. Your agent code doesn't change. Your interaction patterns don't change. The only thing that changes is the connection string.

!!! info "Not two modes -- one continuum"
    Local and production are endpoints on the same architecture. Moving from one developer experimenting locally to a team sharing a NATS cluster requires changing one line of code.

For how OAM fits in the broader multi-agent ecosystem, see [The Multi-Agent Landscape](enterprise-landscape.md).
