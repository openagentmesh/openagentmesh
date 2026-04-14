# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

Pre-implementation. This repository currently contains only specification documents — no source code exists yet. The task is to implement the OpenAgentMesh (OAM) Python SDK from these specs.

Key specs and ideas are found in the km/ directory (knowledge management):
- `agentmesh-spec.md` — Protocol specification (authoritative)
- `agentmesh-developer-experience.md` — SDK design and DX philosophy
- `agentmesh-registry-and-discovery.md` — Registry, channels, catalog, and discovery patterns
- `agentmesh-liveness-and-failure.md` — Liveness checks, failure modes, death notices
- `ideas.md` — Unresolved design questions and future ideas

## What OpenAgentMesh Is

OpenAgentMesh (OAM) is a NATS-based protocol and Python SDK for agent-to-agent communication. Agents register on a shared NATS message bus, publish typed contracts, and discover/invoke each other at runtime without direct coupling. Analogous to a service mesh (Istio/Linkerd) but for AI agents.

**Positioning:** "The LAN of agents" — internal fabric (vs. MCP for tools, A2A for cross-org federation).

**Naming convention:** Project/brand is "OpenAgentMesh" / "OAM". Code class name stays `AgentMesh` for ergonomics (`from openagentmesh import AgentMesh`).

## Architecture

### Core Abstractions

**`AgentMesh`** — the central class. Manages NATS connection, subscriptions, heartbeat loops, and lifecycle. Instantiated with a connection string or no arguments (defaults to `nats://localhost:4222`). `AgentMesh.local()` is an async context manager for tests and demos that starts an embedded NATS subprocess with scoped lifecycle.

**`@mesh.agent` decorator** — turns any async function into a mesh participant. Internally: subscribes to a NATS queue group, deserializes/validates via Pydantic v2, calls the handler, serializes the response, writes the contract to KV on startup.

**Contract registry** — NATS JetStream KV store. Two tiers:

- `mesh.catalog` — single KV key containing a JSON array of lightweight entries (name, channel, description, version, tags). Updated via CAS on every registration/deregistration.
- `mesh.registry.{channel}.{name}` — per-agent full contract with JSON Schemas, SLA metadata, and error schema.

**Channels** — hierarchical namespace prefix (e.g., `nlp`, `finance.risk`). Map directly to NATS subject hierarchy, enabling wildcard subscriptions. Channels represent domains/teams, not technical categories. Optional — agents without a channel register at root.

### Subject Naming

```
mesh.agent.{channel}.{name}      # invocation subject (queue group subscription)
mesh.agent.{name}                # invocation for root-level agents (no channel)
mesh.registry.{channel}.{name}   # KV registry key for full contract
mesh.catalog                     # KV key for lightweight catalog index
mesh.health.{channel}.{name}     # heartbeat subject
mesh.agent.{channel}.{name}.events  # pub/sub event emissions
mesh.errors.{channel}.{name}     # dead-letter subject
mesh.results.{request_id}        # async callback reply subject
```

### Message Envelope

All messages use NATS headers for metadata, JSON body for payload.

Request headers: `X-Mesh-Request-Id`, `X-Mesh-Source`, `X-Mesh-Reply-To` (async pattern), `traceparent` (W3C Trace Context).
Response headers: `X-Mesh-Request-Id` (echoed), `X-Mesh-Source`, `X-Mesh-Status: ok | error`.

Error body when `X-Mesh-Status: error`:
```json
{"code": "validation_error|handler_error|timeout|not_found|rate_limited", "message": "...", "agent": "...", "request_id": "...", "details": {}}
```

### Invocation Patterns

1. **Sync req/reply** — `mesh.call()` — NATS native request/reply, caller blocks.
2. **Async callback** — `mesh.send(reply_to=...)` — caller sets `X-Mesh-Reply-To`, continues working, subscribes to callback subject independently.
3. **Pub/sub** — `mesh.agent.{name}.events` — no invocation, fan-out events.

## SDK API Surface

### Provider (registering an agent)

```python
mesh = AgentMesh("nats://localhost:4222")   # connect to NATS
mesh = AgentMesh()                          # same, using default localhost URL

# For tests and demos only:
async with AgentMesh.local() as mesh:       # embedded NATS, stops on exit
    ...

@mesh.agent(name="summarizer", channel="nlp", description="...", tags=[...])
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    ...

mesh.register(name=..., channel=..., description=...,
              input_model=..., output_model=..., handler=...)

mesh.run()             # blocking (like uvicorn.run)
await mesh.start()     # non-blocking (embed in existing async app)
await mesh.stop()      # graceful: unsubscribe → drain → deregister → disconnect
```

### Consumer (using the mesh)

```python
# Discovery
catalog  = await mesh.catalog()                    # lightweight list
catalog  = await mesh.catalog(channel="nlp")       # filtered
catalog  = await mesh.catalog(tags=["summarization"])
agents   = await mesh.discover()                   # full AgentContract objects
agents   = await mesh.discover(channel="nlp")
contract = await mesh.contract("summarizer")       # single agent

# AgentContract methods
contract.to_anthropic_tool()
contract.to_openai_tool()
contract.to_generic_tool()
contract.to_agent_card(url=None)  # thin projection; injects url if provided

# Invocation
result = await mesh.call("summarizer", payload, timeout=30.0)
await mesh.send("summarizer", payload, reply_to="mesh.results.abc")
```

### CLI

```bash
agentmesh up      # start local NATS with JetStream + pre-created KV buckets
agentmesh init    # generate Docker Compose stack for team dev
agentmesh status  # show registered agents and health
```

## Documentation

- **Tool:** Zensical (Rust-based successor to Material for MkDocs). Reads `mkdocs.yml` natively.
- **Source:** `docs/` (Markdown). **Build output:** `site/` (gitignored).
- **Dev server:** `uv run zensical serve`
- **See:** ADR-0018

## Key Design Decisions

- **Pydantic v2** for input/output validation and JSON Schema generation. Type hints on the handler function are used for introspection — explicit `input_model`/`output_model` parameters are the fallback.
- **Queue groups** for every invocation subscription — native NATS load balancing enables multiple instances of the same agent with no config changes.
- **CAS on catalog updates** — concurrent registration retries read-modify-write until KV revision matches. Catalog may be momentarily stale (milliseconds); `mesh.contract()` is authoritative.
- **No framework adapters** — the handler function body is the developer's territory. Wrapping existing agents is a thin bridge function, not an SDK concern.
- **Two-step discovery at scale** — `catalog()` for LLM-based selection (20–30 tokens/agent), then `contract()` for targeted schema fetch. No RAG or vector DB needed up to ~500 agents.
- **Embedded NATS** (`AgentMesh.local()`) is an async context manager that downloads the NATS binary to `~/.agentmesh/bin/`, runs as a subprocess with JetStream + KV pre-configured. Scoped to tests and demos; the standard dev workflow uses `agentmesh up` + `AgentMesh()`.

## Workflow

A feature flows through two phases. A feature can enter the DESIGN phase at any stage, but the DESIGN phase must be complete (docs updated) before DEVELOPMENT begins.

### DESIGN phase

```
Discussion → Spec document (km/) / ADR → Docs (docs/)
```

1. **Discussion** — Conversations, notes (`km/notes/`), SpecStory transcripts. Ideas explored, trade-offs weighed.
2. **Spec document** — Decision crystallized into a km/ spec file (internal, authoritative). ADR extracted to `docs/adr/` to track the decision.
3. **Docs** — User-facing documentation updated to reflect the decision. This is the gate: no code changes that imply doc changes until docs are updated first.

### DEVELOPMENT phase

```
Tests → Implementation (red → green → refactor)
```

1. **DX first** — Write example code showing exactly how a library user would use the feature. This is the contract. If it looks awkward to write, fix the API before touching implementation.
2. **Tests second** — Write tests that exercise the example code from step 1. Tests must fail (red).
3. **Implementation last** — Write the minimum code that makes the tests pass (green). No speculative abstractions. Then refactor.

### ADR as tracking tool

ADRs in `docs/adr/` track each decision through the workflow via the **Status** field:

| Status | Meaning |
|--------|---------|
| `discussion` | Decision identified in conversation/notes, not yet spec'd |
| `spec` | Written into km/ spec document |
| `documented` | User-facing docs updated |
| `implemented` | Code exists and tests pass |
| `accepted` | Legacy status — treat as `implemented` or `documented` |
| `superseded by ADR-NNNN` | Replaced by a later decision |

## Development Phases

The spec defines four phases. **Phase 1 is the current target:**

**Phase 1 (MVP):** `AgentMesh` class, `@mesh.agent` decorator, Pydantic v2 validation, `mesh.call()` / `mesh.send()` / `mesh.discover()`, lifecycle management, `AgentMesh.local()` async context manager for tests, `agentmesh up` CLI, "Hello World" in <30 lines.

Not in Phase 1: middleware hooks, OTel, Docker Compose tier, admin UI, TypeScript SDK, spawning from specs.

## Contract Schema Reference

The contract schema is a superset of the A2A Agent Card format. A2A fields are at the top level; AgentMesh-specific fields are under `x-agentmesh`. The `url` field is the only A2A field not stored in the registry — it is gateway-provided at federation time. `.to_agent_card(url=None)` is a thin projection, not a conversion.

```json
{
  "name": "summarizer",
  "description": "Written for LLM consumption: what it does, what inputs it handles, when NOT to use it.",
  "version": "1.0.0",
  "capabilities": { "streaming": false, "pushNotifications": true },
  "defaultInputModes": ["application/json"],
  "defaultOutputModes": ["application/json"],
  "skills": [
    {
      "id": "summarizer",
      "name": "Summarize text",
      "description": "Written for LLM consumption...",
      "tags": ["text", "summarization"],
      "inputModes": ["application/json"],
      "outputModes": ["application/json"],
      "inputSchema": {},
      "outputSchema": {}
    }
  ],
  "x-agentmesh": {
    "type": "agent",
    "channel": "nlp",
    "subject": "mesh.agent.nlp.summarizer",
    "sla": {
      "expected_latency_ms": 5000,
      "timeout_ms": 30000,
      "retry_policy": "idempotent",
      "max_retries": 2
    },
    "error_schema": {},
    "metadata": {
      "framework": "custom",
      "language": "python",
      "registered_at": "ISO8601",
      "heartbeat_interval_ms": 10000
    }
  }
}
```

The `description` field (top-level and in `skills[0]`) is consumed by LLMs for tool selection — it must state what the agent does, what input formats it handles, and what it should NOT be used for.
