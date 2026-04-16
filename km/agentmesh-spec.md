# AgentMesh: A NATS-Based Agent Communication and Composition Protocol

**Version:** 0.1 — Draft Specification  
**Date:** April 2026  
**Status:** Pre-implementation design document

---

## 1. Executive Summary

AgentMesh is a lightweight, event-driven protocol and SDK for decoupled agent-to-agent communication, built on NATS as its messaging backbone. It enables AI agents — regardless of framework, language, or runtime — to register, discover, and invoke each other through a shared message bus with self-describing contracts.

The core premise: agent-to-agent communication today is fragmented across monolithic harnesses (LangChain, CrewAI, AutoGen) that assume agents live in the same process or behind HTTP. AgentMesh introduces a service-mesh-like abstraction for cognitive workloads, where registration equals discoverability equals invocability with zero coupling.

The project targets a gap between existing protocol efforts (Google A2A, Anthropic MCP, Cisco AGNTCY) — which focus on cross-organizational federation over HTTP/gRPC — and the developer need for a fast, lightweight, event-native fabric for composing multi-agent systems within a team or organization.

---

## 2. Problem Statement

### 2.1 Current State of Agent Communication

Modern AI agent frameworks (PydanticAI, LangChain, CrewAI, AutoGen, Google ADK) treat agent composition as an in-process concern. Agents call each other through hardcoded function calls, shared memory, or at best, HTTP APIs. This creates several problems:

- **Tight coupling.** Adding, removing, or replacing an agent requires code changes in every agent that references it.
- **Monolingual lock-in.** Agents must be written in the same language and often the same framework.
- **No dynamic discovery.** An agent cannot learn at runtime what other agents exist or what they can do.
- **Scaling barriers.** Scaling a single agent independently requires extracting it into a separate service with custom HTTP plumbing.
- **Observability gaps.** Tracing a request across agents inside a monolithic process is ad-hoc; there is no standard envelope or trace context propagation.

### 2.2 The Silo Problem Across Platforms

The no-code/low-code agent builder market (Lindy, n8n, Make, Glean, Zapier, MindStudio, Relevance AI) compounds the problem at the organizational level. Each platform creates agents that are trapped inside its ecosystem. A Lindy agent cannot collaborate with an n8n agent. A Salesforce Agentforce agent cannot invoke an AWS Bedrock agent. Organizations adopting multiple platforms end up with fragmented agent populations that duplicate effort and miss cross-system insights.

### 2.3 What Exists Today

| Initiative | Transport | Model | Strength | Gap |
|---|---|---|---|---|
| **Anthropic MCP** | JSON-RPC over stdio/HTTP | Agent-to-tool (client-server) | Ecosystem adoption, typed tool schemas | Point-to-point only; no agent-to-agent; no pub/sub |
| **Google A2A** | JSON-RPC over HTTP | Agent-to-agent (client-server) | Linux Foundation governance, 150+ partners, Agent Cards | HTTP request-response; no native event-driven triggers; cross-org focus |
| **Cisco AGNTCY** | gRPC + SLIM (pub/sub extension) | Infrastructure layer (discovery, identity, messaging, observability) | Comprehensive; Linux Foundation; real production use cases | Enterprise-heavy; complex setup; gRPC certificate infrastructure |
| **No-code platforms** | Proprietary internal | Agents live inside the platform | Fast time-to-value for non-technical users | Closed ecosystems; no cross-platform interoperability |
| **Framework-native** (LangChain, CrewAI) | In-process function calls | Agents share a runtime | Simple to start | Monolithic; single-language; no scaling boundary |

### 2.4 The Gap

No existing solution provides a lightweight, event-driven, developer-first fabric for agent-to-agent communication that:

- Works in under 30 seconds with zero infrastructure setup
- Supports pub/sub, req/reply, and streaming as native primitives
- Is polyglot by design (protocol-first, not SDK-first)
- Enables dynamic runtime discovery with LLM-compatible tool schemas
- Scales from a single-process prototype to a distributed production system without architectural changes

---

## 3. Proposed Solution

### 3.1 Architecture Overview

AgentMesh is a protocol layer built on top of NATS that adds:

1. **A contract registry** — agent metadata and schemas stored in NATS JetStream KV
2. **A subject convention** — deterministic NATS subject naming for agent invocation
3. **A message envelope** — standardized headers and payload structure
4. **A Python reference SDK** — decorator-based agent registration with Pydantic v2 validation

NATS provides the transport (pub/sub, req/reply, streaming, KV store) as a single lightweight binary. AgentMesh provides the semantics (registration, discovery, contracts, error handling, observability context).

### 3.2 Why NATS

- Single Go binary, ~20MB, zero external dependencies
- Sub-millisecond latency on localhost, low single-digit ms over network
- Native pub/sub, request/reply, and queue groups (built-in load balancing)
- JetStream for durable streaming, at-least-once delivery, and KV storage
- Built-in multi-tenancy via accounts and user-level permissions
- CNCF incubating project with SDKs in Go, Rust, JavaScript, TypeScript, Python, Java, C#, C, Ruby, Elixir, and 30+ community clients
- Operational simplicity compared to Kafka, RabbitMQ, or gRPC service mesh infrastructure
- Suitable for air-gapped and edge deployments

### 3.3 Positioning

- **MCP** is the USB of agents — how agents plug into tools.
- **A2A** is the HTTP of agents — a cross-organizational communication *specification*.
- **AgentMesh** is the LAN of agents — how agents discover, communicate, and compose in real-time with minimal latency and zero ceremony.

A2A defines what cross-org agent collaboration should look like; AgentMesh is what it can run on. A2A is a protocol with no runtime implementation — it specifies how to describe agents and exchange messages but provides no transport, registry, or infrastructure. NATS accounts provide exactly the trust isolation model A2A requires (separate namespaces per organization, selective subject import/export at trust boundaries), with a working implementation. AgentMesh can be the runtime that makes A2A semantics real, not just a spec.

For tool access, MCP remains the right boundary. For cross-org agent federation, AgentMesh via NATS accounts is the implementation path. An A2A serialization layer (Agent Cards, task vocabulary) can be exposed at the boundary for clients that speak that protocol, without changing the internal fabric.

---

## 4. Protocol Specification

### 4.1 Subject Naming Convention

```
mesh.agent.{channel}.{name}            # Agent invocation (req/reply)
mesh.agent.{name}                      # Agent invocation for root-level agents (no channel)
mesh.agent.{channel}.{name}.events     # Publisher agent event emissions (pub/sub)
mesh.stream.{request_id}               # Per-request streaming chunks
mesh.registry.{channel}.{name}         # Contract storage key in KV
mesh.catalog                           # Lightweight catalog index (single KV key)
mesh.errors.{channel}.{name}           # Dead-letter / error subject
mesh.results.{request_id}              # Async callback reply subject
mesh.health.{channel}.{name}           # Heartbeat / liveness subject
mesh.death.{channel}.{name}            # Death notice on deregistration or crash
mesh.workspace.{name}                  # Object Store namespace for shared blobs and artifacts
```

### 4.2 Contract Schema

Each agent publishes a contract to the `mesh.registry.{name}` KV bucket. The contract schema is a superset of the A2A Agent Card format: A2A-defined fields appear at the top level, and AgentMesh-specific fields are namespaced under `x-agentmesh`. This means any stored contract is a valid A2A Agent Card when a `url` is injected at a federation boundary — no structural transformation required.

```json
{
  "name": "summarizer",
  "description": "Summarizes input text to a target length. Suitable for documents, articles, and raw text.",
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true
  },
  "defaultInputModes": ["application/json"],
  "defaultOutputModes": ["application/json"],
  "skills": [
    {
      "id": "summarizer",
      "name": "Summarize text",
      "description": "Summarizes input text to a target length. Suitable for documents, articles, and raw text.",
      "tags": [],
      "inputModes": ["application/json"],
      "outputModes": ["application/json"],
      "inputSchema": { },
      "outputSchema": { }
    }
  ],
  "x-agentmesh": {
    "type": "agent",
    "channel": "nlp",
    "subject": "mesh.agent.nlp.summarizer",
    "chunk_schema": {
      "type": "object",
      "properties": {
        "delta": { "type": "string" }
      },
      "required": ["delta"]
    },
    "sla": {
      "expected_latency_ms": 30000,
      "timeout_ms": 60000,
      "retry_policy": "none",
      "max_retries": 0
    },
    "error_schema": { },
    "metadata": {
      "framework": "custom",
      "language": "python",
      "registered_at": "2026-04-01T10:00:00Z",
      "heartbeat_interval_ms": 10000
    }
  }
}
```

**Key design decisions:**

- `skills[0].inputSchema` and `skills[0].outputSchema` are JSON Schema objects. When using the Python SDK with Pydantic v2, these are generated automatically via `BaseModel.model_json_schema()`. The Python `AgentContract` object exposes them as `contract.input_schema` and `contract.output_schema` for convenience.
- `description` (top-level and in `skills[0]`) must be written for LLM consumption. It should clearly state what the agent does, what input formats it handles, and when it should or should not be invoked.
- `version` follows semver. Breaking changes to input/output schemas require a major version bump.
- `x-agentmesh.sla` is critical for callers to set appropriate timeouts. Agents with wildly different latency profiles (2ms deterministic function vs. 30s LLM agent) cannot be treated identically. SLA defaults differ by type: `"tool"` agents default to `expected_latency_ms: 1000`, `retry_policy: "idempotent"`; `"agent"` types default to `expected_latency_ms: 30000`, `retry_policy: "none"`.
- `x-agentmesh.type` describes the agent's behavior profile. Values: `"agent"` (LLM-powered, streaming by default), `"tool"` (deterministic function, buffered by default), `"publisher"` (emits events to `.events` subject, not invocable), `"subscriber"` (reserved, not yet designed). See ADR-0023.
- `x-agentmesh.chunk_schema` is present for streaming agents (`capabilities.streaming: true`). It is the JSON Schema of the typed chunk model yielded by the handler. Absent for buffered agents. See ADR-0024.
- `capabilities.streaming` is set automatically by the SDK based on the handler shape (yields → `true`, returns → `false`). Manual override is permitted.
- `url` is not stored in the registry — it is context-dependent (gateway hostname, external routing). An A2A-compliant gateway injects it when serving the card externally.

### 4.3 Message Envelope

All messages on the mesh use NATS headers for metadata and a JSON body for the payload.

**Request headers:**

```
X-Mesh-Request-Id: uuid
X-Mesh-Source: caller-agent-name
X-Mesh-Reply-To: mesh.results.{request_id}  (optional, for async callback)
traceparent: 00-{trace_id}-{span_id}-01       (W3C Trace Context)
tracestate: agentmesh=...                      (optional)
```

**Response headers:**

```
X-Mesh-Request-Id: uuid (echoed from request)
X-Mesh-Source: responder-agent-name
X-Mesh-Status: ok | error
X-Mesh-Usage: {"input_tokens": N, ...}    (optional, see §8.3)
traceparent: ...
```

**Body:** The raw JSON payload conforming to the agent's declared `input_schema` (for requests) or `output_schema` (for responses).

> **Note:** JSON-RPC 2.0 is explicitly not adopted as the internal wire format. NATS subjects replace `method`, NATS headers replace `id`, and the AgentMesh error envelope is semantically richer than JSON-RPC error codes. JSON-RPC 2.0 is used only at external boundaries: the A2A gateway (Phase 4) and MCP bridge adapters. See ADR-0001.

### 4.4 Error Envelope

When `X-Mesh-Status: error`, the body conforms to:

```json
{
  "code": "validation_error | handler_error | timeout | not_found | rate_limited | streaming_not_supported | not_invocable",
  "message": "Human-readable error description",
  "agent": "summarizer",
  "request_id": "uuid",
  "details": { }
}
```

Error codes:
- `streaming_not_supported` — caller sent `X-Mesh-Stream: true` to a buffered agent, or called `mesh.stream()` against an agent with `capabilities.streaming: false`.
- `not_invocable` — caller attempted to invoke a `"publisher"` or `"subscriber"` type agent via `mesh.call()` or `mesh.stream()`.

This is a first-class contract. Every reply is either a valid `output_schema` payload or a `MeshError`. The caller side must handle both.

### 4.5 Invocation Patterns

**Pattern 1: Synchronous Request/Reply**

The caller publishes to `mesh.agent.{name}` using NATS req/reply. NATS generates a unique inbox reply subject. The agent processes the request and publishes the response to the reply subject. The caller blocks until the response arrives or the timeout expires.

Use when: the caller needs the result before proceeding; latency is acceptable; simple call-and-wait semantics.

**Pattern 2: Asynchronous Callback**

The caller publishes to `mesh.agent.{name}` with the `X-Mesh-Reply-To` header set to a caller-specified subject (e.g., `mesh.results.{request_id}`). The agent processes the request and publishes the response to the specified callback subject. The caller subscribes to the callback subject independently and can continue other work while waiting.

Use when: the caller wants to fire-and-forget; the agent has high latency; the caller needs to handle responses out of order; webhook-style decoupling is preferred.

Note: The async callback pattern requires a correlation/timeout manager on the caller side. The mesh SDK should provide this as a built-in utility. Without it, there is no mechanism to detect that an agent never responded to a callback.

**Pattern 3: Streaming Request/Reply**

The caller sends a request with the `X-Mesh-Stream: true` header. The agent publishes typed chunks to `mesh.stream.{request_id}`. The caller consumes chunks as an async generator via `mesh.stream()`. The agent must declare `capabilities.streaming: true`.

Use when: the agent produces incremental output (LLM token streams, progressive results); the consumer wants to display or process output before it is complete.

See §4.5.1 and ADR-0005 for the wire protocol. See ADR-0024 for the provider-side handler contract.

**Pattern 4: Pub/Sub (Publisher Agents)**

Publisher agents (`type: "publisher"`) emit typed events to `mesh.agent.{channel}.{name}.events`. Consumers subscribe via `mesh.subscribe()` and receive events as an async generator. No request/reply semantics — publishers are not invocable.

Use when: event-driven architectures; fan-out notifications; decoupled pipelines where the producer does not need to know or wait for consumers.

```python
# Provider
@mesh.agent(name="price-feed", channel="finance", type="publisher", description="...")
async def monitor_prices() -> PriceEvent:
    while True:
        yield PriceEvent(symbol="AAPL", price=await fetch_price())
        await asyncio.sleep(1)

# Consumer
async for event in mesh.subscribe("price-feed"):
    print(event.symbol, event.price)

# Channel-scoped — all publishers in the finance channel
async for event in mesh.subscribe(channel="finance"):
    print(event.source, event.data)
```

`mesh.subscribe("name")` subscribes to `mesh.agent.{channel}.{name}.events`. `mesh.subscribe(channel="...")` subscribes to `mesh.agent.{channel}.>` (all event subjects under that channel).

**Design note: Task lifecycle is the contract's responsibility, not the protocol's.**

Protocols like A2A define a fixed task state machine (`submitted → working → input-required → completed | failed`). This is an opinionated 1:1 model. AgentMesh deliberately has no opinion on how a task should be carried out.

Multi-turn interactions, human-in-the-loop approval gates, parallel agent collaboration, and complex state machines are all expressible on the mesh by designing the right contracts and subjects. An agent handling a long-running task can:

- Emit intermediate state to `mesh.agent.{name}.events` (subscribers observe progress)
- Wait for human input by publishing to a `mesh.agent.{name}.pending` subject and subscribing to a response subject
- Coordinate with n other agents by publishing to their invocation subjects in parallel and collecting results

The mesh provides the primitives; the contract defines the protocol for a specific workflow. This makes AgentMesh more general than fixed-lifecycle protocols, at the cost of requiring the developer to design the state machine explicitly for complex workflows.

### 4.5.1 Streaming Protocol

Streaming is a first-class invocation pattern for agents that produce incremental output (LLM token streams, progressive results). In v1, an agent is either buffered or streaming — not both. See ADR-0024.

#### Handler shapes

```python
# Buffered agent — returns typed response
@mesh.agent(name="classifier", channel="nlp", description="...")
async def classify(req: ClassifyInput) -> ClassifyOutput:
    return ClassifyOutput(label="positive", confidence=0.95)

# Streaming agent — yields typed chunks
@mesh.agent(name="summarizer", channel="nlp", description="...")
async def summarize(req: SummarizeInput) -> SummarizeChunk:
    async for token in call_llm_stream(req.text):
        yield SummarizeChunk(delta=token)
```

The SDK infers `capabilities.streaming` from the handler shape at registration time: `inspect.isasyncgenfunction(handler)` → `true`; plain async function → `false`. Return type annotation is always required and validated against `output_schema` (buffered) or `chunk_schema` (streaming).

#### Streaming Subject Convention
```
mesh.stream.{request_id}    # per-request streaming subject
```

The caller sends a request to the agent's invocation subject with the header `X-Mesh-Stream: true`. The agent publishes each chunk to `mesh.stream.{request_id}` with headers:
- `X-Mesh-Stream-Seq: N` (0-indexed sequence number)
- `X-Mesh-Stream-End: true|false` (final chunk indicator)

The caller subscribes to `mesh.stream.{request_id}` before sending the request and consumes chunks as an async generator via `mesh.stream()`. The agent must declare `capabilities.streaming: true`. Agents without the capability reject streaming requests with `code: "streaming_not_supported"`. Calling `mesh.call()` against a streaming agent also returns `code: "streaming_not_supported"` — modes are strict and non-interchangeable in v1.

See ADR-0005 (wire protocol), ADR-0024 (handler contract).

### 4.6 Discovery

Any agent can query the registry KV bucket to discover available agents:

1. List all keys in the `mesh.registry.*` bucket to enumerate registered agents.
2. Read individual contract entries to inspect schemas and descriptions.
3. Use the `description` and `input_schema` / `output_schema` fields to construct LLM tool definitions.

The SDK provides a `mesh.discover()` method that returns a list of `AgentContract` objects, each with convenience methods for converting the contract to provider-specific tool formats:

- `.to_openai_tool()` — OpenAI function calling format
- `.to_anthropic_tool()` — Anthropic tool use format
- `.to_generic_tool()` — Framework-agnostic JSON Schema representation
- `.to_agent_card(url=None)` — A2A Agent Card (thin projection; injects `url` if provided)

This discovery-to-tool-injection pipeline is the bridge between "service mesh" and "agent mesh." Without it, the system is just NATS with extra steps.

Because the contract schema is a superset of the A2A Agent Card format, `.to_agent_card()` performs no structural transformation — it returns the stored contract with an optional `url` injected. Any agent can serve its card over HTTP for external discovery by reading its own registry entry and calling `.to_agent_card(url=gateway_url)`. A2A compatibility is a property of the schema, not of the transport.

**Open question: Tool selection at scale.** If the registry contains 200 agents, injecting all 200 as tools into an LLM context is impractical — it degrades decision quality and may exceed context limits. A routing layer or meta-agent that pre-selects relevant tools based on task context is likely necessary. This is a v2 concern but should inform contract design (e.g., tagging agents with categories or capability keywords for pre-filtering).

### 4.7 Registration and Deregistration

**On startup:**

1. Agent connects to NATS.
2. Agent subscribes to its invocation subject (`mesh.agent.{name}`) using a queue group (enabling multiple instances for load balancing).
3. Agent publishes its contract to the KV registry at `mesh.registry.{name}`.
4. Agent begins emitting heartbeats to `mesh.health.{name}` at the interval specified in its contract.

**On graceful shutdown:**

1. Agent unsubscribes from its invocation subject.
2. Agent drains in-flight messages (completes any active request handling).
3. Agent deletes its contract from the KV registry.
4. Agent disconnects from NATS.

**On crash (ungraceful termination):**

The mesh uses a hybrid detection strategy. See `km/agentmesh-liveness-and-failure.md` for the full specification.

1. **Primary: NATS disconnect advisories** (`$SYS.ACCOUNT.*.DISCONNECT`). The NATS server emits an advisory when any client's TCP connection drops. The mesh health monitor subscribes to these advisories and immediately deregisters the dead agent from the catalog and registry KV. Detection latency: sub-second for process crashes, 10-20 seconds for network partitions (with tuned `ping_interval`).
2. **Secondary: Heartbeat timeout.** If no heartbeat is received within 3x the declared `heartbeat_interval_ms`, the health monitor marks the agent as unhealthy. This catches zombie agents (process alive but unresponsive) that maintain their TCP connection.

On any detection, a death notice is published to `mesh.death.{channel}.{name}` for orchestrators, monitoring, and auto-scaling subscribers.

See ADR-0016.

### 4.8 Schema Versioning

The `version` field in the contract follows semantic versioning:

- **Patch (1.0.x):** Bug fixes, no schema changes. Transparent to callers.
- **Minor (1.x.0):** Additive changes (new optional fields in output). Existing callers unaffected.
- **Major (x.0.0):** Breaking changes to input or output schema. Callers holding the old contract will fail.

On a major version change, the agent should register under a versioned subject (`mesh.agent.summarizer.v2`) while maintaining the previous version on the original subject during a deprecation period. The registry contract includes a `deprecated` flag and an optional `successor` field pointing to the new version.

This is essential for production stability. Without schema versioning, any agent update risks silent failures across all callers.

### 4.9 Shared Workspace (Object Store)

NATS JetStream provides an Object Store — a blob storage layer backed by the same JetStream infrastructure as KV and streams. This is a first-class component of the mesh, not an afterthought.

**The split between transport and storage:**

- JetStream streams carry signals, coordination messages, and small structured payloads (JSON).
- Object Store carries data: markdown documents, PDFs, images, audio, embeddings, serialized model outputs — any blob that is too large or too binary to embed in a message.

Agents communicate by reference: an agent stores a blob in Object Store, publishes a message containing the object key, and downstream agents fetch the object directly. This keeps the message bus fast and payload-agnostic.

**Use cases:**

- **Artifact passing.** A `pdf-extractor` agent stores extracted text as an Object Store blob, publishes its key to `mesh.agent.documents.pdf-extractor`. A `summarizer` agent reads the blob, processes it, stores the summary, and passes the new key forward.
- **Shared context/memory.** An orchestrator writes a working document (task state, accumulated results, conversation history) to Object Store at the start of a workflow. All participating agents read and potentially update it as the workflow progresses.
- **Multi-modal agent inputs.** An image or audio file uploaded by a user is stored in Object Store. Its key is passed to whichever agent handles that media type, without routing the binary through the message bus.

**Workspace API (SDK):**

```python
# Store a blob — returns an object key
key = await mesh.workspace.put("pipeline-123/extracted.md", content_bytes)

# Retrieve a blob by key
content = await mesh.workspace.get(key)

# Watch for changes to a workspace object (pub/sub on updates)
async for update in mesh.workspace.watch("pipeline-123/"):
    process(update)

# Delete when done
await mesh.workspace.delete(key)
```

**Concurrency and consistency:**

NATS Object Store is not transactional. Concurrent writes to the same object key require coordination at the application layer. The SDK exposes optimistic concurrency control via revision-based updates (the same CAS mechanism used for the catalog):

```python
# Read with revision
obj, revision = await mesh.workspace.get_with_revision(key)

# Conditional update — fails if revision has changed since the read
await mesh.workspace.put_if_revision(key, new_content, expected_revision=revision)
```

Agents that need shared mutable state must implement a read-modify-write loop with retry on revision conflict. The SDK provides this as a helper. Agents that only append or overwrite independently (no read-modify-write) can use plain `put()` without revision tracking.

**Workspace vs. KV:**

| | KV Store | Object Store |
|---|---|---|
| Max value size | Small (KB) | Large (up to GB) |
| Content type | JSON / text | Any binary |
| Revision tracking | Built-in | Built-in |
| Use in mesh | Registry, catalog, health state | Artifacts, shared memory, media |

### 4.10 MCP Interoperability

AgentMesh integrates with the Model Context Protocol (MCP) ecosystem in both directions. Internally, the mesh uses NATS headers and raw JSON — never JSON-RPC 2.0 (see §4.3). JSON-RPC translation happens only at bridge boundaries.

#### 4.10.1 Outbound: `mesh.run_mcp()` — Exposing Agents as MCP Tools

Starts an MCP server (stdio or HTTP/SSE) that proxies `tools/list` and `tools/call` to the mesh. MCP clients (Claude Desktop, Cursor, etc.) see mesh agents as standard MCP tools.

```python
mesh.run_mcp()                                  # stdio transport (default)
mesh.run_mcp(transport="http", port=8080)       # HTTP/SSE for remote clients
mesh.run_mcp(channel="nlp")                     # only expose agents in a channel
mesh.run_mcp(allow=["summarizer", "classifier"]) # explicit allowlist

# Non-blocking variant for embedding alongside mesh.start()
await mesh.start()
await mesh.start_mcp(transport="http", port=8080)
```

Contract-to-MCP-tool conversion is trivial — `AgentContract` already holds JSON Schema. MCP's tool format is essentially identical to what `.to_anthropic_tool()` produces. MCP does not define output schemas; the agent's `output_schema` becomes documentation in the description.

**Export flag.** Not all agents should be visible to MCP clients. A boolean `mcp` flag on the decorator controls per-agent visibility:

```python
@mesh.agent(name="summarizer", channel="nlp", mcp=True)   # MCP-visible
@mesh.agent(name="chunk-router", channel="internal", mcp=False)  # internal only
```

Mesh-level default policy:

```python
mesh.run_mcp(default_mcp=True)   # opt-out: everything visible unless mcp=False
mesh.run_mcp(default_mcp=False)  # opt-in: nothing visible unless mcp=True
```

Local dev default: opt-out. Production default: opt-in. See ADR-0003.

**SLA gating.** MCP clients block on `tools/call` (client-initiated, single-tool invocation with streamed response). The term "synchronous" here refers to this blocking call pattern, not MCP's transport layer (which supports SSE streaming and server-initiated notifications). OAM's differentiator is topology: any-to-any agent communication on a shared bus with runtime discovery, vs. MCP's 1:1 client-server model. See ADR-0019.

Agents with long timeouts (e.g., human-in-the-loop) would stall the MCP client. The bridge enforces a maximum SLA:

```python
mesh.run_mcp(max_timeout_ms=30_000, on_sla_violation="skip")
```

Both the export flag and SLA check must pass: `export check → SLA check → appears in tools/list`. See ADR-0006.

**Phase placement:** Phase 2.

#### 4.10.2 Inbound: `mesh.add_mcp()` — Consuming External MCP Servers

Connects to an external MCP server, enumerates its tools via `tools/list`, and registers them as **virtual agents** (type: `mcp_bridge`) in the mesh catalog. Mesh agents call them via `mesh.call()` transparently.

```python
# stdio MCP server
await mesh.add_mcp("uvx mcp-server-filesystem", channel="tools.filesystem")

# HTTP/SSE MCP server
await mesh.add_mcp(
    "https://mcp.github.com/sse",
    channel="tools.github",
    auth={"token": os.environ["GITHUB_TOKEN"]},
)

# Explicit command list (safer than shell string)
await mesh.add_mcp(
    ["npx", "-y", "@modelcontextprotocol/server-brave-search"],
    channel="tools.search",
    env={"BRAVE_API_KEY": os.environ["BRAVE_API_KEY"]},
)
```

The bridge manages the MCP session lifecycle: spawn/connect, `initialize`, `tools/list`, register virtual agents, subscribe to NATS subjects, maintain session (reconnect on failure), deregister on shutdown.

```python
await mesh.add_mcp(
    "https://mcp.github.com/sse",
    channel="tools.github",
    reconnect=True,
    reconnect_backoff="exponential",
)
```

Virtual agents appear naturally in `mesh.catalog()` and are filterable by type:

```python
catalog = await mesh.catalog(type="agent")       # native only
catalog = await mesh.catalog(type="mcp_bridge")  # MCP-bridged only
```

**Phase placement:** Phase 3.

#### 4.10.3 Schema Quality Tiers

External MCP servers have inconsistent schema quality. The bridge runs an intake normalization pipeline with four quality tiers:

| Tier | Meaning | Action |
|---|---|---|
| `validated` | Passes JSON Schema meta-schema check | Used as-is |
| `normalized` | Partial (missing `type`, `required`) | SDK fills gaps |
| `inferred` | Empty or missing | Passthrough `{"type": "object", "additionalProperties": true}` + warning |
| `overridden` | Developer supplied Pydantic model | Full validation via `schema_overrides` |

```python
await mesh.add_mcp(
    "npx @modelcontextprotocol/server-github",
    channel="tools.github",
    schema_overrides={
        "create-issue": {
            "input_model": GitHubCreateIssueInput,
            "output_model": GitHubCreateIssueOutput,
        }
    },
    on_bad_schema="warn",  # "warn" | "skip" | "raise"
)
```

The `schema_quality` field surfaces in the contract under `x-agentmesh` and in the catalog, enabling filtering: `mesh.catalog(min_schema_quality="normalized")`.

MCP output is inherently untyped (content blocks, not JSON Schema). The bridge normalizes results into an `MCPToolResult` envelope. Developer-supplied `output_model` overrides enable Pydantic validation on the mesh side.

See ADR-0002, ADR-0003, ADR-0004, ADR-0006.

---

## 5. Python Reference SDK

### 5.1 Design Principles

- **Decorator-based registration.** Inspired by FastAPI's route decorators. The developer writes a function; the framework handles subscription, deserialization, dispatch, serialization, and reply.
- **Pydantic v2 for contracts.** Input and output models are Pydantic `BaseModel` subclasses. Validation is automatic and fast (Pydantic-core is written in Rust; validation overhead is microseconds, negligible compared to NATS round-trip latency). JSON Schema generation is free via `model_json_schema()`.
- **Instance-based, not static.** The `AgentMesh` class is instantiated with a NATS connection URL. It manages connection state, active subscriptions, heartbeat loops, and graceful shutdown. A static `register` method would imply no instance, but the mesh connection is inherently stateful.
- **Framework-agnostic.** The SDK does not depend on LangChain, CrewAI, PydanticAI, or any agent framework. Any Python async function can be an agent handler.

### 5.2 Agent-Side API (Registering an Agent)

```python
from agentmesh import AgentMesh
from pydantic import BaseModel

mesh = AgentMesh("nats://localhost:4222")

class SummarizeRequest(BaseModel):
    text: str
    max_length: int = 200

class SummarizeResponse(BaseModel):
    summary: str
    token_count: int

@mesh.agent(
    name="summarizer",
    description="Summarizes input text to a target length. Handles documents, articles, and raw text. Not suitable for code or structured data.",
    input_model=SummarizeRequest,
    output_model=SummarizeResponse,
)
async def summarize(msg: SummarizeRequest) -> SummarizeResponse:
    summary = await call_my_llm(msg.text, msg.max_length)
    return SummarizeResponse(
        summary=summary,
        token_count=len(summary.split())
    )

if __name__ == "__main__":
    mesh.run()
```

**What the `@mesh.agent` decorator does internally:**

1. Subscribes to NATS subject `mesh.agent.summarizer` using a queue group.
2. On incoming message: deserializes the payload through `SummarizeRequest` (validation happens here; bad messages get a `MeshError` on the reply subject).
3. Calls the decorated function with the validated Pydantic object.
4. Serializes the return value through `SummarizeResponse`.
5. Publishes to the reply subject (req/reply) or the callback subject (async pattern).
6. On startup: publishes the contract (including JSON Schemas from both Pydantic models) to the KV registry.

### 5.3 Caller-Side API (Invoking an Agent)

```python
# Typed call — caller knows the target agent and its contract
response = await mesh.call(
    "summarizer",
    SummarizeRequest(text="Long document here..."),
    response_model=SummarizeResponse,
    timeout=30.0,
)

# Dynamic discovery — caller doesn't know what's available
tools = await mesh.discover()
# Returns list of AgentContract objects
llm_tools = [t.to_anthropic_tool() for t in tools]

# Async callback pattern
await mesh.send(
    "summarizer",
    SummarizeRequest(text="..."),
    reply_to="mesh.results.my-workflow-123",
)
```

### 5.4 Lifecycle Management

```python
mesh.run()            # Blocking; runs the async event loop (like uvicorn.run)
await mesh.start()    # Non-blocking; for embedding in an existing async application
await mesh.stop()     # Graceful shutdown: unsubscribe, deregister, drain in-flight
```

### 5.5 Middleware

The SDK supports middleware hooks for cross-cutting concerns:

```python
@mesh.middleware
async def trace_propagation(msg, next_handler):
    with otel_span(msg.headers.get("traceparent")):
        return await next_handler(msg)

@mesh.middleware
async def logging_middleware(msg, next_handler):
    logger.info(f"Received request {msg.headers['X-Mesh-Request-Id']}")
    response = await next_handler(msg)
    logger.info(f"Completed request {msg.headers['X-Mesh-Request-Id']}")
    return response
```

Anticipated middleware use cases: OTel trace context injection/propagation, structured logging, auth token propagation, rate limiting, input sanitization, metrics collection.

---

## 6. Deployment Tiers

### 6.1 Tier 1 — Local Development (Subprocess Pattern)

The SDK ships with a utility that downloads the NATS server binary for the host platform, caches it in `~/.agentmesh/bin/`, and spawns it as a subprocess. The primary dev workflow is `agentmesh up` (CLI). `AgentMesh.local()` is an async context manager for tests and demos that starts the subprocess with scoped lifecycle (see ADR-0022).

- NATS server starts with an embedded configuration: JetStream enabled, all KV/Object Store buckets pre-created, ephemeral storage.

#### JetStream Bucket Specification

| Bucket | Type | Purpose | Key Pattern |
|--------|------|---------|-------------|
| `mesh-catalog` | KV | Single-key lightweight catalog index (CAS updates) | `catalog` |
| `mesh-registry` | KV | Per-agent full contract storage | `{channel}.{name}` or `{name}` |
| `mesh-context` | KV | Shared context data between agents | Application-defined |
| `mesh-artifacts` | Object Store | Binary artifact storage between agents | Application-defined |

All buckets are pre-created by `agentmesh up` and the embedded NATS startup. Bucket names use hyphens (see ADR-0013). TTL for `mesh-context`, max object size for `mesh-artifacts`, and replica counts are deployment-configurable (defaults TBD). See ADR-0021.

- Developer writes pure Python. No Docker, no config files, no infrastructure knowledge required.
- Single-machine only. Suitable for prototyping, demos, testing.
- Inspired by how MinIO and LocalStack handle embedded infrastructure in developer workflows.

Goal: a developer can go from `pip install agentmesh` to two agents discovering and calling each other in under 30 seconds and fewer than 30 lines of code.

### 6.2 Tier 2 — Team Development (Docker Compose)

A CLI command (`agentmesh init`) generates a Docker Compose stack:

- NATS server with persistent JetStream storage
- Pre-configured KV buckets and retention policies
- Optional admin UI container (web-based registry browser, agent health dashboard)
- Bootstrap script that seeds the mesh registry

One command (`agentmesh up`) starts the entire stack. Suitable for team development, staging environments, and early production use.

### 6.3 Tier 3 — Production (BYO NATS or Hosted)

The SDK connects to an existing NATS cluster (self-managed or hosted via Synadia Cloud / NGS). No lifecycle management by the SDK — that is the operations team's responsibility.

The mesh layer adds:

- Autoscaling via the spawner control plane (see Section 7)
- Self-healing with heartbeat-based crash detection and agent respawn
- Cost controls with per-agent rate limits and budget caps
- Full OTel integration for distributed tracing across the mesh

### 6.4 Tier 4 — Enterprise

All Tier 3 capabilities plus:

- Admin UI with authentication, RBAC, and SSO
- Multi-tenant namespace isolation via NATS accounts
- Encrypted prompt/implementation storage in KV (separated from public contracts)
- Audit logging for all agent invocations and registry changes
- Advanced retention policies on JetStream streams
- Distributed NATS cluster across regions/clouds
- Compliance reporting

---

## 7. Agent Spawning from Specs (Tier 3+)

### 7.1 Concept

If the contract registry stores not just the interface (name, description, schemas) but also the implementation details (system prompt, model config, runtime parameters), the mesh can instantiate agents on demand rather than waiting for someone to deploy them.

The mesh transitions from passive infrastructure (routing messages between externally deployed agents) to active infrastructure (materializing agents from declarative specs).

### 7.2 Extended Contract for Spawnable Agents

```yaml
name: summarizer
version: "1.0.0"
description: "Summarizes input text to a target length."
input_schema: { ... }
output_schema: { ... }
sla:
  expected_latency_ms: 5000
  timeout_ms: 30000

implementation:
  type: llm
  model: claude-sonnet-4-20250514
  system_prompt: |
    You are a summarization specialist. Given input text,
    produce a concise summary under the target length.
    Respond only with the summary, no preamble.
  temperature: 0.3
  max_tokens: 500

scaling:
  min_instances: 1
  max_instances: 10
  scale_trigger: queue_depth > 50
  cooldown_seconds: 60

cost:
  max_requests_per_minute: 100
  max_daily_spend_usd: 50.0
```

### 7.3 Implementation Types

| Type | Behavior | Use Case |
|---|---|---|
| `llm` | Mesh spawns a generic LLM agent process, injects system prompt and model config, wires to NATS subject | Non-developers creating agents from prompts; rapid prototyping |
| `docker` | Mesh pulls and runs a container image with specified env vars | Complex agents with custom dependencies |
| `function` | Mesh runs a Python function from a registered module | Lightweight code-based agents |
| `external` | Mesh does not spawn; expects the agent to self-register and manage its own lifecycle | Current model; agents deployed independently |

The `llm` type is the highest-leverage starting point. It enables non-developers to create agents by writing a system prompt and defining input/output schemas — effectively a "no-code" agent creation path built on open infrastructure.

### 7.4 Critical Considerations

**IP and system prompt exposure.** The system prompt is intellectual property. If stored in NATS KV in plaintext, anyone with KV read access sees every agent's implementation. This requires:

- **Contract vs. implementation separation.** The public part of the spec (name, description, schemas) is discoverable by all agents. The private part (system prompt, model config, API keys) is stored separately with restricted access.
- **Encryption at rest.** Private spec fields encrypted in KV, decryptable only by the spawner service.
- **RBAC on the registry.** NATS account-level permissions scoped so agents can read public contracts but only the mesh control plane can read implementation details.
- **Trust model transparency.** Even with encryption and RBAC, the mesh operator can see everything. This is the same trust model as any cloud platform, but it must be explicitly communicated to enterprise customers.

**The spawner is a privileged control plane.** The component that reads specs and creates agent processes requires access to LLM API keys, Docker sockets (if spawning containers), the private KV store, and process management. It must be designed as a distinct, hardened service from day one.

**Cost control.** Auto-spawning LLM agents that auto-scale means the system can burn through API credits rapidly with no human in the loop. Required safeguards:

- Per-agent rate limits and budget caps (defined in the spec)
- Mesh-level aggregate spend tracking and circuit breakers
- Alerting on anomalous cost trajectories
- Runaway agent loop detection

**Self-healing.** If an agent crashes, the mesh detects the missed heartbeat, reads the spec from KV, and respawns it. The spec is the source of truth; the running process is disposable. This enables versioning and rollback by pointing at older spec revisions in KV history.

---

## 8. Observability

### 8.1 OpenTelemetry Integration

The mesh must be fully compatible with OpenTelemetry (OTel). Every message on the mesh carries W3C Trace Context headers (`traceparent`, `tracestate`) in the NATS message headers, enabling distributed tracing across agent boundaries.

The SDK middleware layer handles:

- Trace context injection on outgoing messages
- Trace context extraction on incoming messages
- Span creation for each agent invocation (with attributes for agent name, request ID, latency, status)
- Metric emission (request count, latency histogram, error rate, queue depth per agent)

### 8.2 Observability Challenges

- **Req/reply tracing** is straightforward: one span per call.
- **Async callback tracing** requires correlating the original request span with the eventual response, potentially minutes later. The `X-Mesh-Request-Id` and trace context headers in both the request and callback response must match.
- **Pub/sub fan-out** creates multiple child spans from a single publish. Each subscriber creates its own span linked to the publisher's trace context.
- **Cross-framework tracing.** Agents built with different frameworks (or no framework) must all propagate trace context consistently. The protocol-level header spec makes this framework-agnostic, but the SDK must make it effortless.

### 8.3 LLM Cost Model and Usage Attribution

**AgentMesh is transport. It does not call LLMs, manage API keys, or bill for inference.**

LLM tokens are consumed at up to three sites in a mesh interaction, each with clear ownership:

| Site | Who pays | Why |
|------|----------|-----|
| **Orchestrating LLM** (consumer discovers agents, converts to tools, LLM decides which to call) | Consumer | Consumer runs their own LLM; the mesh is not involved |
| **Agent's internal LLM** (handler calls Claude, GPT, etc.) | Provider | Provider deployed the agent with their own API key |
| **Mesh-spawned agents** (`type: llm`, Tier 3+) | Operator | Spawner control plane holds the API keys |

This mirrors how every API economy works: the caller pays for their own compute to make the request; the service owner pays for their compute to handle it; the platform operator pays for infrastructure. In the primary OAM use case — within-company orchestration — all three roles map to the same organization, so inter-party billing is not a concern. What matters is **cost attribution**: which agents and workflows are consuming tokens, and how much.

#### Usage reporting convention

Agents optionally self-report token usage via the `X-Mesh-Usage` response header:

```
X-Mesh-Usage: {"input_tokens": 1500, "output_tokens": 300, "model": "claude-sonnet-4-20250514"}
```

| Field | Type | Description |
|-------|------|-------------|
| `input_tokens` | `int` | Tokens consumed in the LLM input/prompt |
| `output_tokens` | `int` | Tokens generated in the LLM output |
| `total_tokens` | `int` | Sum, if the provider reports it separately |
| `model` | `string` | Model identifier used for this call |
| `estimated_cost_usd` | `float` | Agent-computed cost estimate (advisory) |

All fields are optional. Non-LLM agents (deterministic functions, database lookups) omit the header entirely. The mesh propagates the header; it does not generate, validate, or aggregate it. Usage data is agent-reported and unverified — acceptable for within-org attribution, not suitable for cross-org billing.

#### Usage in OTel spans

When the OTel middleware is active (Phase 2+), usage data from `X-Mesh-Usage` is recorded as span attributes:

- `mesh.usage.input_tokens`
- `mesh.usage.output_tokens`
- `mesh.usage.model`
- `mesh.usage.estimated_cost_usd`

This connects per-call usage to the distributed trace. A multi-agent workflow produces a trace where each span carries its own cost, enabling full cost attribution across the entire request path.

#### SDK helper

The Python SDK provides a `Usage` object so agent authors don't construct the header manually:

```python
from openagentmesh import AgentMesh, Usage

@mesh.agent(name="summarizer", channel="nlp")
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    result = await call_llm(req.text)
    return SummarizeOutput(
        summary=result.text,
        usage=Usage(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model="claude-sonnet-4-20250514",
        ),
    )
```

The `Usage` object is not part of the output schema — the SDK intercepts it and moves it to the `X-Mesh-Usage` header before serializing the response body. Callers never see it in the JSON payload.

#### What the mesh explicitly does NOT do

- **Metering or billing.** No running totals, no budgets, no invoicing. External monitoring tools aggregate usage from traces and headers.
- **Credential passthrough.** No mechanism for consumers to send their own API keys. This is a per-agent implementation concern, not a protocol concern.
- **Mandatory reporting.** Usage reporting is opt-in. Agents that don't report usage are not degraded.

See ADR-0023.

---

## 9. Polyglot Support Strategy

### 9.1 Protocol First, SDKs Second

The protocol specification (this document) is the product. SDKs are convenience implementations of the protocol. Any developer can participate in the mesh using a raw NATS client in any language, provided they follow the subject naming, message envelope, contract schema, and registration/deregistration conventions defined here.

### 9.2 SDK Roadmap

| Priority | Language | Rationale |
|---|---|---|
| **P0** | Python | Reference implementation. Largest AI/ML developer community. Pydantic v2 integration for schema validation and generation. |
| **P1** | TypeScript | JS/TS agent ecosystem (Vercel AI SDK, LangChain.js). Enables web-based admin UI, playground, and observability dashboard that connects to the mesh directly. |
| **P2** | Go / Rust | Community-contributed or demand-driven. High-performance agents and infrastructure tooling. |

### 9.3 Risk: Framework Extension Maintenance Treadmill

An earlier design consideration explored extending popular framework classes (PydanticAI, LangChain, CrewAI Agent classes) to make them mesh-aware. This approach is explicitly deprioritized due to:

- Rapid upstream API churn in all major frameworks
- Maintenance burden of tracking breaking changes across multiple frameworks
- Coupling to specific framework abstractions

Instead, the SDK is framework-agnostic. Any async Python function can be a mesh agent. Framework users can wrap their existing agents in a thin handler function without requiring framework-specific extensions.

---

## 10. Workflow Orchestration (Future Scope)

### 10.1 YAML Workflow Specs

A natural extension of the mesh is declarative workflow composition: a YAML file that defines a sequence or graph of agent invocations.

```yaml
name: document-analysis-pipeline
version: "1.0.0"

steps:
  - name: extract
    agent: pdf-extractor
    input:
      document_url: "{{ trigger.document_url }}"

  - name: summarize
    agent: summarizer
    input:
      text: "{{ steps.extract.output.text }}"
      max_length: 500

  - name: classify
    agent: classifier
    input:
      text: "{{ steps.summarize.output.summary }}"
    parallel_with: sentiment

  - name: sentiment
    agent: sentiment-analyzer
    input:
      text: "{{ steps.summarize.output.summary }}"
```

### 10.2 Scope Boundaries

Workflow orchestration is explicitly a v2 concern. The moment workflows support conditional branching, error handling with compensation, state persistence, human approval gates, and retry policies, the system enters workflow engine territory (Temporal, Prefect, Airflow, Step Functions).

The design principle: **the mesh is a protocol, not a workflow engine.** V1 proves the value of decoupled agent-to-agent calls. Workflow orchestration is layered on top once the protocol and registry are stable.

Key questions to resolve before building workflow orchestration:

- Where does intermediate state live between steps? (JetStream streams? KV?)
- How does a workflow pause for human approval and resume?
- How are compensation/rollback actions expressed?
- What is the execution model — a dedicated orchestrator agent, or distributed choreography?

---

## 11. Security Model

### 11.1 NATS-Level Security

NATS provides:

- TLS/mTLS for encrypted transport
- Token, username/password, NKey, and JWT-based authentication
- Account-level isolation (multi-tenancy)
- Subject-level publish/subscribe permissions per user/account

### 11.2 Mesh-Level Security

On top of NATS security, the mesh adds:

- **Contract registry access control.** Public contracts (name, description, schemas) readable by all mesh participants. Private implementation details (system prompts, model configs) readable only by the spawner control plane.
- **Agent identity.** Each agent authenticates to NATS with its own credentials. Agent-to-agent calls carry the caller's identity in the `X-Mesh-Source` header.
- **Audit logging.** All registry changes (registration, deregistration, contract updates) and optionally all invocations are logged to a JetStream stream for compliance.
- **Rate limiting.** Per-agent invocation rate limits enforceable via middleware or a gateway service.

### 11.3 Cross-Organizational Trust via NATS Accounts

NATS accounts provide the trust isolation model that cross-org agent collaboration requires, without needing an HTTP gateway or external federation protocol.

Each organization (or team, or tenant) operates under a separate NATS account. Accounts are fully isolated by default — subjects in Account A are invisible to Account B. Cross-org collaboration is enabled through explicit, declarative import/export:

```
Organization A (account: org-a)
  exports: { stream: "mesh.agent.nlp.>" }   # exposes NLP agents to trusted partners

Organization B (account: org-b)
  imports: { stream: { account: org-a, subject: "mesh.agent.nlp.>" } }
  # can now call org-a's NLP agents directly on the mesh
```

The mesh operator controls which subjects each account can publish to and subscribe from. An organization's agents are only visible to external accounts when explicitly exported. This is a working implementation of the trust boundary model that A2A describes as a specification.

**Cross-org deployment model:**

- Each org runs its own agents against a shared NATS cluster (Synadia Cloud / NGS for managed hosting, or a self-hosted NATS cluster with multi-account config).
- The mesh operator manages account credentials and import/export grants.
- An org can expose a curated subset of its agents externally while keeping internal agents private.
- Authentication between orgs uses NKey + JWT — no OAuth2 or API key management required.

### 11.4 Enterprise Security (Tier 4)

- SSO/SAML/OIDC integration for the admin UI
- RBAC with role-based access to registry operations, agent invocation, and observability data
- Encrypted KV storage for sensitive contract fields
- Compliance-ready audit trails (SOX, GDPR, HIPAA depending on deployment)

---

## 12. Known Open Questions and Risks

### 12.1 Technical Open Questions

1. **Tool selection at scale.** How does an LLM-based agent efficiently select from a large registry of available tools without injecting all contracts into its context? Pre-filtering by category/tag? A meta-routing agent?
2. **Schema evolution notifications.** How are consumers notified when a producer's contract changes? Push notification via a `mesh.registry.changes` event stream? Polling?
3. **Exactly-once semantics.** NATS JetStream provides at-least-once delivery. For non-idempotent agent operations, deduplication logic is needed at the handler level.
4. **Backpressure.** A slow agent (human-in-the-loop, high-latency LLM) with a deep queue creates cascading timeouts for callers. The queue group pattern distributes load but does not solve the fundamental throughput mismatch.
5. **Contract validation enforcement.** NATS is payload-agnostic. Schema validation currently happens at the SDK level. Agents not using the SDK (polyglot, external) may send non-conforming messages. Options include a validation proxy/gateway or accepting that validation is best-effort outside the SDK.

### 12.2 Business and Strategic Risks

1. **A2A dominance.** If Google's A2A protocol becomes the universal standard before AgentMesh gains traction, the HTTP-based model may be accepted as "good enough" and the event-driven advantage becomes harder to sell. Mitigation: A2A is a specification with no runtime implementation. AgentMesh can implement A2A semantics (Agent Cards, task vocabulary) as a serialization layer on top of the mesh, positioning AgentMesh as the runtime that makes A2A real rather than a competing standard. The `.to_agent_card()` method and NATS account-based cross-org trust model are the technical foundation for this.
2. **NATS licensing.** In May 2025, Synadia (NATS maintainer) briefly threatened to pull NATS from the CNCF and re-license under BSL. The dispute was resolved and NATS remains under Apache 2.0, but this signals potential future licensing risk. Mitigation: the protocol is transport-agnostic by design; NATS is the reference implementation but the spec could theoretically be implemented over other pub/sub systems.
3. **Solo founder velocity.** The scope is large. The risk is building a workflow engine when the goal is a protocol, or building four SDKs when one is not finished. Mitigation: strict phase discipline (see Section 13).

---

## 13. Development Phases

### Phase 1 — Protocol and Python SDK (Target: MVP)

**Deliverables:**

- Protocol specification document (this document, finalized)
- Python SDK (`agentmesh` package) with:
  - `AgentMesh` class with NATS connection management
  - `@mesh.agent` decorator for registration
  - Pydantic v2 input/output model validation
  - `mesh.call()` for typed synchronous invocation
  - `mesh.discover()` for registry enumeration
  - `mesh.send()` for async callback pattern
  - `mesh.run()` / `mesh.start()` / `mesh.stop()` lifecycle
  - Standard `MeshError` handling
  - Heartbeat emission and health check
- `mesh-artifacts` (Object Store) and `mesh-context` (KV) for shared workspace between agents (see ADR-0010)
- Tier 1 deployment: subprocess-based local NATS spawning with all four JetStream buckets pre-created
- CLI: `agentmesh up` for local development
- "Hello World" example: two agents discovering and calling each other in <30 lines
- README, quickstart guide, basic documentation

**Not in scope for Phase 1:** Middleware, OTel integration, workflow orchestration, spawning from specs, admin UI, TypeScript SDK, Docker Compose tier.

### Phase 2 — Production Readiness

**Deliverables:**

- Middleware hook system
- OpenTelemetry trace context propagation (W3C headers)
- Tier 2 deployment: Docker Compose stack with persistent storage
- Schema versioning support (versioned subjects, deprecation flags)
- Graceful shutdown with drain and deregister
- Basic admin UI (web-based registry browser, agent health status)
- `mesh.discover()` to LLM tool definition conversion (`.to_openai_tool()`, `.to_anthropic_tool()`)
- Comprehensive test suite
- Published to PyPI

### Phase 3 — Spawning and Scaling

**Deliverables:**

- `type: llm` agent spawning from extended contract specs
- Contract vs. implementation separation in KV (public/private split)
- Autoscaling based on queue depth
- Self-healing with crash detection and automatic respawn
- Cost controls (per-agent rate limits, budget caps, circuit breakers)
- Tier 3 deployment: production NATS cluster integration

### Phase 4 — Enterprise and Ecosystem

**Deliverables:**

- TypeScript SDK
- Multi-tenant namespace isolation
- Encrypted KV storage for private contract fields
- RBAC and SSO for admin UI
- Audit logging to JetStream
- A2A gateway (expose mesh agents as A2A-compatible endpoints at the boundary)
- Platform connectors (bridge agents from external platforms into the mesh)
- YAML workflow orchestration (scoped to serial/parallel execution without full saga semantics)
- Hosted mesh offering (managed NATS + control plane as a service)

---

## 14. Appendix

### A. Glossary

| Term | Definition |
|---|---|
| **Agent** | A registered participant on the mesh that can receive and process messages. May be an LLM-backed service, a deterministic function, a human-in-the-loop application, or any program in any language. |
| **Contract** | The JSON document stored in the KV registry that describes an agent's name, capabilities, input/output schemas, SLA metadata, and optionally its implementation details. |
| **Mesh** | The combination of the NATS transport layer, the KV contract registry, the subject naming conventions, and the message envelope format that together enable agent discovery and communication. |
| **Spawner** | The privileged control plane service that can read extended contracts (including implementation details) and instantiate agent processes on demand. |
| **Tool** | An agent as seen by another agent — a callable capability with typed inputs and outputs, discoverable at runtime. |

### B. Comparison with Analogous Systems

| Concept | AgentMesh Equivalent |
|---|---|
| Kubernetes Pod manifest | Agent contract (declarative spec that the platform materializes) |
| Kubernetes Service | NATS subject (stable address that routes to agent instances) |
| Kubernetes scheduler | Spawner control plane (decides when/where to create agent instances) |
| DNS / service registry | KV contract registry (name to capability mapping) |
| Istio / Linkerd sidecar | SDK middleware layer (observability, auth, rate limiting at the agent boundary) |
| Helm chart | YAML workflow spec (declarative composition of multiple agents) |
