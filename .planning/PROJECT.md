# AgentMesh

## What This Is

A protocol and Python SDK for agent-to-agent communication over a shared message bus. Agents register, publish typed contracts, and discover/invoke each other at runtime without direct coupling — analogous to a service mesh (Istio/Linkerd) but for AI agents.

**The real value is the protocol.** NATS is the first transport implementation (pub/sub, req/reply, KV registry, object store — all in one low-overhead system), and Python is the first SDK. The same contract model could be implemented over other transports or in other languages.

## Core Value

Any agent can discover and call any other agent at runtime — typed, validated, load-balanced — with zero coupling between them.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Phase 1 — MVP:**
- [ ] `AgentMesh` class: connect to NATS or start embedded NATS subprocess (`AgentMesh.local()`)
- [ ] `@mesh.agent` decorator: register an async function as a typed mesh participant with Pydantic v2 validation
- [ ] `mesh.call()`: synchronous request/reply invocation with timeout
- [ ] `mesh.send()`: async callback invocation with reply subject
- [ ] `mesh.discover()` / `mesh.catalog()` / `mesh.contract()`: two-tier discovery (lightweight catalog + full contract)
- [ ] `AgentContract.to_anthropic_tool()`, `.to_openai_tool()`, `.to_generic_tool()`, `.to_agent_card()`: LLM tool adapters
- [ ] Lifecycle management: `mesh.run()` (blocking), `await mesh.start()` / `await mesh.stop()` (async)
- [ ] Contract registry: NATS JetStream KV with two-tier schema (`mesh.catalog` + `mesh.registry.{channel}.{name}`)
- [ ] Heartbeat emission and health tracking
- [ ] `agentmesh up` CLI: start local NATS with JetStream + KV buckets pre-created
- [ ] "Hello World" example: two agents discovering and calling each other in <30 lines
- [ ] OSS packaging: published to PyPI as `agentmesh`

**Later phases:**
- [ ] Middleware hook system (Phase 2)
- [ ] OpenTelemetry trace propagation (Phase 2)
- [ ] Docker Compose stack for team dev (Phase 2)
- [ ] Schema versioning and deprecation (Phase 2)
- [ ] Admin UI — registry browser, agent health (Phase 2)
- [ ] `type: llm` agent spawning from contract specs (Phase 3)
- [ ] Autoscaling, self-healing, cost controls (Phase 3)
- [ ] TypeScript SDK (Phase 4)
- [ ] Multi-tenant namespace isolation (Phase 4)
- [ ] A2A gateway — expose mesh agents as A2A endpoints (Phase 4)
- [ ] Hosted mesh offering (Phase 4)

### Out of Scope

- Middleware hooks — Phase 1 only; added in Phase 2
- OTel integration — Phase 2
- Docker Compose tier — Phase 2
- Admin UI — Phase 2
- TypeScript SDK — Phase 4
- Spawning agents from specs — Phase 3
- YAML workflow orchestration — Phase 4
- HTTP adapters / FastAPI integration — not a Phase 1 concern; the SDK is transport-level
- Authentication/authorization beyond what NATS provides natively — Phase 4 or later
- Shared memory/context via ObjectStore — future (locking semantics unresolved)

## Context

**Protocol-first positioning:** AgentMesh is "the LAN of agents" — internal fabric for agent-to-agent communication within a team or system. Complementary to MCP (tool calling) and A2A (cross-org federation), not a replacement.

**Why NATS:** Single technology provides pub/sub, request/reply, queue groups (native load balancing), JetStream KV (contract registry), and ObjectStore — no extra infrastructure. The protocol concept is transport-agnostic; future implementations may use other backends.

**Two-tier discovery:** `catalog()` returns lightweight entries (~20-30 tokens/agent) for LLM-based agent selection. `contract()` returns full JSON Schema + SLA metadata for targeted invocation. Scales to ~500 agents without RAG.

**Contract schema:** Superset of A2A Agent Card format. AgentMesh-specific fields live under `x-agentmesh`. `url` is the only A2A field not stored — it's gateway-provided at federation time.

**Developer experience target:** "Hello World" in <30 lines. A `@mesh.agent` decorator that just works. Wrapping existing agents should be a thin bridge, not an SDK concern.

## Constraints

- **Tech Stack**: Python SDK uses Pydantic v2 for validation and JSON Schema generation — not negotiable
- **Transport**: Phase 1 uses NATS exclusively; protocol is designed to be transport-agnostic for future ports
- **Load balancing**: Every invocation subscription uses NATS queue groups — zero-config horizontal scaling is a protocol guarantee
- **Consistency**: CAS (compare-and-swap) on catalog updates — `catalog()` may be momentarily stale; `contract()` is always authoritative
- **Distribution**: OSS, published to PyPI as `agentmesh`

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| NATS as Phase 1 transport | Provides pub/sub, req/reply, KV, ObjectStore in one system with low overhead | — Pending |
| Pydantic v2 for validation | JSON Schema generation, type introspection from handler annotations | — Pending |
| Queue groups for all invocations | Native NATS load balancing, zero config for multi-instance agents | — Pending |
| Two-tier discovery (catalog + contract) | LLM-friendly at scale without vector DB; up to ~500 agents | — Pending |
| Protocol-first design | Core value is the contract spec, not the transport — NATS/Python are first impl | — Pending |
| No framework adapters in SDK | Handler body is developer's territory; bridge is thin | — Pending |
| Embedded NATS for local dev | Download binary to `~/.agentmesh/bin/`, run as subprocess — dev only | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-04 after initialization*
