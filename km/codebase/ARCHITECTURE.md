<!-- refreshed: 2026-05-08 -->
# Architecture

**Analysis Date:** 2026-05-08

## System Overview

OpenAgentMesh (OAM) is a protocol and SDK for multi-agent interaction built on NATS JetStream. Agents register on a shared message bus, publish typed contracts, and discover/invoke each other at runtime without direct coupling.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          User Application Layer                             │
│  @mesh.agent decorator, mesh.call(), mesh.stream(), mesh.subscribe(), etc.  │
│                      `src/openagentmesh/_mesh.py`                           │
└──────────────────────────┬──────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┬──────────────────┐
        │                  │                  │                  │
        ▼                  ▼                  ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Invocation   │  │ Discovery    │  │ Handler      │  │ Error        │
│ Primitives   │  │ Primitives   │  │ Inspection   │  │ Taxonomy     │
│ call, stream │  │ catalog,     │  │ shape        │  │ (exceptions) │
│ send, sub    │  │ contract     │  │ inference    │  │              │
│              │  │              │  │              │  │              │
│_invocation.py│  │_discovery.py │  │_handler.py   │  │_errors.py    │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────────────┘
       │                 │                  │
       └─────────────────┴──────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────────────┐
        │   NATS Connection & Bucket Management       │
        │  _connect(), _ensure_buckets(),             │
        │  _subscribe_agent(), _handle_*()            │
        │   `src/openagentmesh/_mesh.py`              │
        └────────┬───────────────────────────────────┘
                 │
    ┌────────────┼────────────┬──────────────┐
    ▼            ▼            ▼              ▼
┌────────┐  ┌────────┐  ┌────────┐  ┌──────────┐
│ mesh-  │  │ mesh-  │  │ mesh-  │  │ mesh-    │
│ catalog│  │registry│  │context │  │artifacts │
│ (KV)   │  │ (KV)   │  │ (KV)   │  │ (Object) │
└────────┘  └────────┘  └────────┘  └──────────┘
    │            │            │          │
    └────────────┴────────────┴──────────┘
              │
              ▼
       ┌─────────────────┐
       │  NATS JetStream │
       │   via nats-py   │
       └─────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **AgentMesh** | Core class: client, host, and async context manager | `src/openagentmesh/_mesh.py` |
| **InvocationMixin** | Invocation methods: call(), stream(), send(), subscribe() | `src/openagentmesh/_invocation.py` |
| **DiscoveryMixin** | Discovery methods: catalog(), contract(), discover() | `src/openagentmesh/_discovery.py` |
| **HandlerInfo** | Result of handler shape inspection | `src/openagentmesh/_handler.py` |
| **AgentSpec** | Agent registration metadata (name, description, tags) | `src/openagentmesh/_models.py` |
| **AgentContract** | Full agent contract (spec + schema + capabilities) | `src/openagentmesh/_models.py` |
| **CatalogEntry** | Lightweight catalog entry (for LLM tool selection) | `src/openagentmesh/_models.py` |
| **MeshError** | Error taxonomy (InvalidInput, HandlerError, etc.) | `src/openagentmesh/_errors.py` |
| **KVStore** | Public API wrapper for mesh-context KV bucket | `src/openagentmesh/_context.py` |
| **Workspace** | Public API wrapper for mesh-artifacts Object Store | `src/openagentmesh/_workspace.py` |
| **EmbeddedNats** | Embedded NATS server for tests/demos (downloads binary) | `src/openagentmesh/_local.py` |
| **CLI** | Command-line interface (mesh, agent, demo commands) | `src/openagentmesh/cli/` |
| **Demos** | Reference implementations (hello_world, llm_tool_selection, etc.) | `src/openagentmesh/demos/` |

## Pattern Overview

**Overall:** Async message-oriented API built on NATS JetStream. The pattern separates concerns via mixin inheritance and functional closures. Registration and invocation are decoupled: agents register metadata and handlers at startup, then listen for requests on NATS subjects. Callers discover agents via a lightweight catalog or full contract lookup, then invoke using one of four patterns (call, stream, send, subscribe).

**Key Characteristics:**
- **Type-driven:** Pydantic v2 infers input/output schemas from handler function type hints. No explicit schema declaration required.
- **Shape-based capability inference:** Handler shape (sync/async, generators, parameters) determines agent capabilities (invocable, streaming) automatically.
- **Multi-instance load balancing:** NATS queue groups enable multiple instances of the same agent with no config changes.
- **Two-tier discovery:** Lightweight catalog for LLM-based selection, authoritative contract fetch for schema details.
- **Embedded NATS for tests:** `AgentMesh.local()` is an async context manager that manages a subprocess-based NATS server with JetStream and KV pre-configured.

## Layers

**API/Public Layer:**
- Purpose: Expose the mesh protocol to users via Python async methods and decorators
- Location: `src/openagentmesh/_mesh.py` (main), `src/openagentmesh/_invocation.py`, `src/openagentmesh/_discovery.py`
- Contains: `@mesh.agent()` decorator, `mesh.call()`, `mesh.stream()`, `mesh.send()`, `mesh.subscribe()`, `mesh.catalog()`, `mesh.contract()`, `mesh.discover()`, `mesh.run()`
- Depends on: NATS client, Pydantic, handler inspection, error taxonomy
- Used by: User applications, demos, CLI

**Handler Inspection Layer:**
- Purpose: Introspect async function signatures to infer capabilities and extract type schemas
- Location: `src/openagentmesh/_handler.py`
- Contains: `inspect_handler()`, `HandlerInfo` dataclass
- Depends on: Python inspect, typing, Pydantic TypeAdapter
- Used by: Agent registration decorator (`@mesh.agent`)

**Storage & Context Layer:**
- Purpose: Provide public APIs for shared state (KV context store, artifact storage)
- Location: `src/openagentmesh/_context.py` (KVStore), `src/openagentmesh/_workspace.py` (Workspace)
- Contains: Compare-and-swap primitives, artifact get/put/delete
- Depends on: NATS KV and Object Store clients
- Used by: User handlers, for inter-agent communication state

**Error Taxonomy Layer:**
- Purpose: Define structured error types and wire envelope serialization (ADR-0057)
- Location: `src/openagentmesh/_errors.py`
- Contains: `MeshError` base class, categorical subclasses (InvalidInput, HandlerError, etc.), envelope serialization
- Depends on: JSON, typing
- Used by: Invocation layer, handlers, callers

**Data Models Layer:**
- Purpose: Pydantic models for metadata and contracts
- Location: `src/openagentmesh/_models.py`
- Contains: `AgentSpec`, `AgentContract`, `CatalogEntry`
- Depends on: Pydantic v2, validation rules
- Used by: Registration, discovery, serialization

**Subject Computation Layer:**
- Purpose: Map agent names to NATS subjects consistently
- Location: `src/openagentmesh/_subjects.py`
- Contains: `compute_subject()`, `compute_error_subject()`, `compute_event_subject()`
- Depends on: String formatting
- Used by: Subscription, publication, routing

**Embedded NATS Layer:**
- Purpose: Manage the embedded NATS binary for tests and demos
- Location: `src/openagentmesh/_local.py`
- Contains: `EmbeddedNats` class, binary download and management
- Depends on: subprocess, asyncio, network sockets, curl
- Used by: `AgentMesh.local()` context manager

**CLI Layer:**
- Purpose: Command-line interface for mesh operations and agent inspection
- Location: `src/openagentmesh/cli/`
- Contains: Typer-based commands (mesh, agent, demo)
- Depends on: Typer, async NATS connection, rich/formatting
- Used by: Users at terminal

## Data Flow

### Primary Request Path (call)

1. **Caller invokes agent** (`mesh.call("agent_name", payload)`) at `_invocation.py:InvocationMixin.call`
2. **Payload serialization** (`_serialize_payload`) - JSON encode or Pydantic dump
3. **NATS request-reply** - Publish to subject `mesh.agent.{name}` with reply subject
4. **Handler receives** - NATS subscription callback in `_subscribe_agent` receives message
5. **Input validation** - Pydantic `TypeAdapter.validate_json()` for caller-fault errors (InvalidInput)
6. **Handler execution** - Call `info.func(payload)` inside try/except for provider-fault errors (HandlerError)
7. **Response serialization** - Pydantic `dump_json()` or JSON encode
8. **Reply published** - Publish response to reply subject with status header
9. **Caller receives** - NATS request() returns response, parsed as dict

**Error flow (call):**
- Caller-fault (InvalidInput): Caught at validation step, published as error response with status header
- Provider-fault (HandlerError): Caught at handler execution, wrapped and published
- Error reconstruction: Caller's `from_envelope()` maps wire code back to exception class

### Streaming Request Path (stream)

1. **Caller invokes** (`mesh.stream("agent_name", payload)`) at `_invocation.py:InvocationMixin.stream`
2. **Request published** - Publish to subject with header `X-Mesh-Stream: true`, reply subject, stream subject
3. **Handler receives** - Subscription callback in `_subscribe_agent`
4. **Stream mode branching** - Routes to `_handle_streaming()` instead of `_handle_responder()`
5. **Handler yields chunks** - Async generator yields values until exhaustion
6. **Chunk publication loop** - Each chunk published to stream subject with sequence number header
7. **End marker** - Final publish with `X-Mesh-Stream-End: true` header
8. **Caller collects chunks** - Listens on stream subject, yields each chunk to caller
9. **Sequence validation** - Caller checks sequence numbers; out-of-order raises ChunkSequenceError

**State Management:**
- Catalog cache: In-memory dict `_catalog_cache`, seeded on connect, continuously watched
- Subscription tracking: Set `_subscribed` tracks which agents have been registered
- Request IDs: UUID per request for tracing across error reports

### Publisher/Watcher Patterns

**Publisher** (async generator without request param):
- Handler runs continuously in background task (`_emit_publisher_events`)
- Each yielded chunk published to `mesh.agent.{name}.events` subject
- Sequence number tracked and sent in headers
- No subscription needed from callers; they subscribe to event subject directly

**Watcher** (async def without request param, no return):
- Handler runs once in background task (`_run_watcher`)
- No input, no output; purely side-effect based
- Cancelled cleanly during shutdown

## Key Abstractions

**Handler Shape:**
- Purpose: Encapsulate the type and capability information of an async function
- Examples: Responder (input+output), Streamer (input+async gen), Publisher (async gen), Trigger (output), Watcher (no input/output)
- Pattern: Inspect function signature and type hints to infer `invocable` and `streaming` flags; build Pydantic TypeAdapters for validation and serialization

**Agent Name & Subject Mapping:**
- Purpose: Dotted identifiers map consistently to NATS subjects
- Examples: `"finance.risk.scorer"` → `"mesh.agent.finance.risk.scorer"`
- Pattern: Validation enforces alphanumeric + underscore + hyphen per segment; enforces no leading/trailing dots or consecutive dots (ADR-0049)

**Contract & Catalog:**
- Purpose: Two-tier discovery for scale
- Pattern: Catalog (lightweight, cached) for LLM-based tool selection; contract (full schema) for detailed invocation info. Catalog updated via CAS (compare-and-swap) to handle concurrent registrations.

**Error Envelope:**
- Purpose: Structured error serialization across the wire
- Pattern: Each error carries `code`, `message`, `agent`, `request_id`, `details`. Wire-side deserialization maps codes back to local exception classes (ADR-0057).

**KV Context Store & Workspace:**
- Purpose: Enable inter-agent communication state and artifact sharing
- Pattern: Public API (`mesh.kv`, `mesh.workspace`) wraps NATS KV and Object Store buckets. CAS primitives for concurrent mutations.

## Entry Points

**Application Entry:**
- Location: `src/openagentmesh/__init__.py`
- Triggers: `from openagentmesh import AgentMesh`
- Responsibilities: Expose public API (AgentMesh, AgentSpec, AgentContract, error classes)

**Context Manager Entry:**
- Location: `src/openagentmesh/_mesh.py:AgentMesh.__aenter__`
- Triggers: `async with mesh:` or `async with AgentMesh.local():`
- Responsibilities: Connect to NATS, ensure KV buckets, seed catalog cache, start watchers, subscribe pending agents

**Handler Registration:**
- Location: `src/openagentmesh/_mesh.py:AgentMesh.agent` (decorator)
- Triggers: `@mesh.agent(spec)` on async function
- Responsibilities: Inspect handler shape, build contract with schemas, register in `_agents` dict

**Invocation Entry:**
- Location: `src/openagentmesh/_invocation.py`
- Triggers: `await mesh.call()`, `async for chunk in mesh.stream()`, etc.
- Responsibilities: Publish request, manage subscriptions for responses, deserialize, error handling

**Discovery Entry:**
- Location: `src/openagentmesh/_discovery.py`
- Triggers: `await mesh.catalog()`, `await mesh.contract()`, `await mesh.discover()`
- Responsibilities: Query cache or registry KV, filter by channel/tags/capability, return entries or contracts

**CLI Entry:**
- Location: `src/openagentmesh/cli/__main__.py`
- Triggers: `python -m openagentmesh` or `oam` command
- Responsibilities: Parse commands, route to mesh/agent/demo subcommands

## Architectural Constraints

- **Threading:** Single-threaded async event loop. All operations are async/await. NATS subscriptions are handled via callbacks in the same event loop.
- **Global state:** `AgentMesh._agents` (dict of registered handlers), `_catalog_cache` (dict of catalog entries), `_subscriptions` (list of NATS subscription handles). These are instance-scoped, not module-level singletons.
- **Circular imports:** Mitigated via TYPE_CHECKING guards in `_invocation.py`, `_discovery.py`. These modules import `AgentMesh` only for type hints, not at runtime.
- **Connection lifecycle:** NATS connection opened in `__aenter__`, closed in `__aexit__`. All operations require connection; methods assert `self._nc is not None`.
- **Catalog consistency:** Catalog is updated via CAS (compare-and-swap) with retry logic in `_update_catalog()`. Momentarily stale (milliseconds) is acceptable; `mesh.contract()` is authoritative.
- **Embedding:** `AgentMesh.local()` spawns a subprocess-based NATS server. Scoped to tests/demos only. Production uses `AgentMesh()` + external `agentmesh up`.

## Anti-Patterns

### Direct Use of NATS Client

**What happens:** Code accesses `mesh._nc` or `mesh._js` directly to publish/subscribe outside the SDK's primitives.

**Why it's wrong:** Bypasses handler inspection, input validation, error envelope construction, and catalog updates. Breaks the contract model and makes debugging harder.

**Do this instead:** Use `mesh.call()`, `mesh.stream()`, `mesh.send()`, `mesh.subscribe()` for invocation; use `mesh.kv` and `mesh.workspace` for state sharing. If a use case isn't covered, raise an issue or extend the SDK.

### Mixing Sync and Async Code

**What happens:** Handler contains `time.sleep()`, blocking I/O, or sync functions instead of `await`.

**Why it's wrong:** Blocks the event loop, freezing all other handlers and subscriptions. Other agents on the mesh timeout.

**Do this instead:** Use `await asyncio.sleep()`, `aiohttp` for HTTP, async drivers for databases. If wrapping sync code, use `asyncio.to_thread()` (Python 3.9+) or `loop.run_in_executor()`.

### Directly Modifying `_catalog_cache`

**What happens:** User code mutates `mesh._catalog_cache[name]` directly.

**Why it's wrong:** Cache is continuously watched and updated by background task; direct mutations are lost on next watch event. Leads to stale data in callers' views.

**Do this instead:** Use `mesh.catalog()` and `mesh.contract()` for read-only access. All mutations are driven by the mesh's background watcher.

## Error Handling

**Strategy:** Structured error taxonomy (ADR-0057). Caller-fault errors (InvalidInput) are distinguished from provider-fault errors (HandlerError). Both are serialized to wire envelopes and deserialized locally, allowing `except InvalidInput` to catch remote errors.

**Patterns:**
- Validation errors (schema mismatch): Caught at input validation, wrapped in InvalidInput with error details
- Handler exceptions: Caught at execution, wrapped in HandlerError with message + traceback
- Connection errors: ConnectionFailed when NATS unavailable
- Timeout errors: MeshTimeout when request exceeds timeout parameter
- Mismatch errors: InvocationMismatch when caller uses wrong invocation verb (call vs. stream)
- Sequence errors: ChunkSequenceError when streaming chunks arrive out of order
- Not found: NotFound when agent doesn't exist in registry

## Cross-Cutting Concerns

**Logging:** Uses Python standard logging. Module-level logger at `_log = logging.getLogger("openagentmesh")`. Debug logs for NATS events; info for significant state changes.

**Validation:** Pydantic v2 is the single source of truth for input/output validation. Type hints on handler functions are introspected via `TypeAdapter`. No manual JSON schema construction.

**Authentication:** Not implemented in Phase 1. NATS server may have auth; the SDK passes url to nats.connect().

---

*Architecture analysis: 2026-05-08*
