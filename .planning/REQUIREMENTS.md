# Requirements: AgentMesh

**Defined:** 2026-04-04
**Core Value:** Any agent can discover and call any other agent at runtime — typed, validated, load-balanced — with zero coupling between them.

## v1 Requirements

### Core Transport

- [ ] **TRAN-01**: Developer can connect `AgentMesh` to an existing NATS server via connection string
- [ ] **TRAN-02**: Developer can start an embedded NATS subprocess via `AgentMesh.local()` (downloads binary to `~/.agentmesh/bin/` on first use)
- [ ] **TRAN-03**: NATS connection uses NATS headers for all message metadata (request ID, source, status, reply-to)
- [ ] **TRAN-04**: All request/reply messages conform to the AgentMesh envelope spec (headers + JSON body)
- [ ] **TRAN-05**: Input validation errors return structured error response (`{"code": "validation_error", ...}`) with `X-Mesh-Status: error` header

### Agent Registration

- [ ] **REGS-01**: Developer can register an agent via `@mesh.agent` decorator on an async function
- [ ] **REGS-02**: `@mesh.agent` infers input/output models from Pydantic v2 type hints on the handler
- [ ] **REGS-03**: Developer can register an agent imperatively via `mesh.register(name, channel, handler, ...)`
- [ ] **REGS-04**: Registered agent subscribes to a NATS queue group so multiple instances load-balance automatically
- [ ] **REGS-05**: Agent contract (JSON Schema + SLA + metadata) is written to NATS JetStream KV on startup
- [ ] **REGS-06**: Catalog (`mesh-catalog` KV key) is updated via CAS read-modify-write on every registration and deregistration
- [ ] **REGS-07**: Agent emits heartbeat on `mesh.health.{channel}.{name}` at a configurable interval (default 10s)
- [ ] **REGS-08**: Agent deregisters cleanly on stop: unsubscribe → drain → remove from catalog and registry → disconnect

### Invocation

- [ ] **INVK-01**: Developer can invoke an agent synchronously via `await mesh.call(name, payload, timeout=30.0)`
- [ ] **INVK-02**: Developer can invoke an agent asynchronously via `await mesh.send(name, payload, reply_to="mesh.results.{id}")`
- [ ] **INVK-03**: `mesh.call()` raises `MeshTimeoutError` on timeout and `MeshNotFoundError` when no agent is registered
- [ ] **INVK-04**: Invocation uses correct subject routing: `mesh.agent.{channel}.{name}` for channeled agents, `mesh.agent.{name}` for root-level agents
- [ ] **INVK-05**: `X-Mesh-Request-Id` is generated per-call and echoed in the response header

### Discovery

- [ ] **DISC-01**: Developer can list all agents via `await mesh.catalog()` — returns lightweight entries (name, channel, description, version, tags)
- [ ] **DISC-02**: `catalog()` supports filtering by `channel=` and `tags=` keyword arguments
- [ ] **DISC-03**: Developer can fetch full agent contracts via `await mesh.discover()` (full `AgentContract` objects)
- [ ] **DISC-04**: Developer can fetch a single agent contract via `await mesh.contract("name")` — always authoritative (reads from registry KV, not catalog)
- [ ] **DISC-05**: `AgentContract` exposes `.to_anthropic_tool()`, `.to_openai_tool()`, `.to_generic_tool()` — LLM-ready tool definitions with flattened JSON Schemas (no `$ref`)
- [ ] **DISC-06**: `AgentContract` exposes `.to_agent_card(url=None)` — A2A-compatible Agent Card format with `x-agentmesh` extension fields

### Lifecycle

- [ ] **LIFE-01**: Developer can run the mesh blocking with `mesh.run()` (analogous to `uvicorn.run`)
- [ ] **LIFE-02**: Developer can embed the mesh in an existing async app with `await mesh.start()` / `await mesh.stop()`
- [ ] **LIFE-03**: Graceful shutdown drains in-flight messages before disconnecting

### CLI

- [ ] **CLI-01**: `agentmesh up` starts a local NATS server with JetStream enabled and pre-creates KV buckets (`mesh-catalog`, `mesh-registry`)
- [ ] **CLI-02**: `agentmesh status` shows registered agents and their health state

### Packaging

- [ ] **PKG-01**: Package is installable via `pip install agentmesh` from PyPI
- [ ] **PKG-02**: Package uses `pyproject.toml` (hatchling build backend), src layout, and includes `py.typed` marker
- [ ] **PKG-03**: "Hello World" example: two agents discovering and calling each other in <30 lines

## v2 Requirements

### Production Readiness (Phase 2)

- **PROD-01**: Middleware hook system (pre/post invocation)
- **PROD-02**: OpenTelemetry trace context propagation (W3C `traceparent` header)
- **PROD-03**: Docker Compose stack for team dev (`agentmesh init`)
- **PROD-04**: Schema versioning and deprecation flags
- **PROD-05**: Admin UI — registry browser, agent health dashboard
- **PROD-06**: Comprehensive integration test suite
- **PROD-07**: Published to PyPI with stable API

### Spawning and Scaling (Phase 3)

- **SPWN-01**: `type: llm` agent spawning from extended contract specs
- **SPWN-02**: Autoscaling based on queue depth
- **SPWN-03**: Self-healing with crash detection and automatic respawn
- **SPWN-04**: Cost controls (per-agent rate limits, budget caps, circuit breakers)
- **SPWN-05**: Production NATS cluster integration

### Enterprise and Ecosystem (Phase 4)

- **ENT-01**: TypeScript SDK
- **ENT-02**: Multi-tenant namespace isolation
- **ENT-03**: RBAC and SSO for admin UI
- **ENT-04**: A2A gateway — expose mesh agents as A2A-compatible endpoints
- **ENT-05**: Audit logging to JetStream
- **ENT-06**: Hosted mesh offering (managed NATS + control plane)

## Out of Scope

| Feature | Reason |
|---------|--------|
| HTTP/REST transport | Protocol is NATS-native; HTTP gateway is a Phase 4 concern |
| FastAPI / framework adapters | Handler body is developer's territory; bridge is a thin wrapper, not SDK concern |
| Authentication / authz beyond NATS defaults | Deferred to Phase 4 |
| Shared memory via ObjectStore | Locking semantics unresolved; deferred |
| YAML workflow orchestration | Phase 4 |
| In-process (non-NATS) transport | Future protocol port; not Phase 1 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TRAN-01 | Phase 1 | Pending |
| TRAN-02 | Phase 3 | Pending |
| TRAN-03 | Phase 1 | Pending |
| TRAN-04 | Phase 1 | Pending |
| TRAN-05 | Phase 1 | Pending |
| REGS-01 | Phase 1 | Pending |
| REGS-02 | Phase 1 | Pending |
| REGS-03 | Phase 1 | Pending |
| REGS-04 | Phase 1 | Pending |
| REGS-05 | Phase 1 | Pending |
| REGS-06 | Phase 1 | Pending |
| REGS-07 | Phase 1 | Pending |
| REGS-08 | Phase 1 | Pending |
| INVK-01 | Phase 1 | Pending |
| INVK-02 | Phase 1 | Pending |
| INVK-03 | Phase 1 | Pending |
| INVK-04 | Phase 1 | Pending |
| INVK-05 | Phase 1 | Pending |
| DISC-01 | Phase 2 | Pending |
| DISC-02 | Phase 2 | Pending |
| DISC-03 | Phase 2 | Pending |
| DISC-04 | Phase 2 | Pending |
| DISC-05 | Phase 2 | Pending |
| DISC-06 | Phase 2 | Pending |
| LIFE-01 | Phase 1 | Pending |
| LIFE-02 | Phase 1 | Pending |
| LIFE-03 | Phase 1 | Pending |
| CLI-01 | Phase 3 | Pending |
| CLI-02 | Phase 3 | Pending |
| PKG-01 | Phase 4 | Pending |
| PKG-02 | Phase 4 | Pending |
| PKG-03 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 32 total
- Mapped to phases: 32
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-04*
*Last updated: 2026-04-04 after initial definition*
