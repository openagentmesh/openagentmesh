# Roadmap: AgentMesh

## Overview

AgentMesh is built in four phases that follow a strict dependency chain. Phase 1 delivers the working transport and registration layer — the core protocol without which nothing else functions. Phase 2 adds the consumer-facing discovery API and LLM tool projections that depend on the contracts Phase 1 writes. Phase 3 adds the embedded NATS binary and CLI, completing the developer experience. Phase 4 hardens everything for PyPI publication. The result is a publishable Python SDK that lets any agent discover and invoke any other agent at runtime, typed and load-balanced, in under 30 lines of code.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Core Transport and Registration** - Working `@mesh.agent` + `mesh.call()` + `mesh.send()` + lifecycle; agents can register and invoke each other
- [ ] **Phase 2: Discovery and LLM Projections** - Two-tier discovery (`catalog()`, `discover()`, `contract()`) and LLM tool adapters with flattened schemas
- [ ] **Phase 3: Embedded NATS and CLI** - `AgentMesh.local()` factory and `agentmesh up`/`status` CLI; dev experience complete
- [ ] **Phase 4: Packaging, Testing, and Publishing** - Production-quality package published to PyPI as `agentmesh`

## Phase Details

### Phase 1: Core Transport and Registration
**Goal**: Agents can connect to NATS, register typed handlers, and invoke each other with validated request/reply
**Depends on**: Nothing (first phase)
**Requirements**: TRAN-01, TRAN-03, TRAN-04, TRAN-05, REGS-01, REGS-02, REGS-03, REGS-04, REGS-05, REGS-06, REGS-07, REGS-08, INVK-01, INVK-02, INVK-03, INVK-04, INVK-05, LIFE-01, LIFE-02, LIFE-03, PKG-03
**Success Criteria** (what must be TRUE):
  1. Developer can decorate an async function with `@mesh.agent` and have it subscribe, validate input via Pydantic v2, and write its contract to `mesh-registry` KV on startup
  2. `await mesh.call("agent-name", payload)` returns the validated response from the remote agent, or raises `MeshTimeoutError` / `MeshNotFoundError` on failure
  3. `await mesh.send("agent-name", payload, reply_to="mesh.results.abc")` publishes the message without blocking and the agent processes it concurrently
  4. Multiple instances of the same agent on the same NATS server load-balance requests automatically via queue groups with no extra configuration
  5. `await mesh.stop()` drains in-flight messages, removes the agent from `mesh-catalog` and `mesh-registry`, then disconnects cleanly
**Plans**: 2 plans

Plans:
- [ ] 01-01: `mesh.py` + `agent.py` + `contract.py` skeleton — `AgentMesh` class with NATS connect/disconnect, `@mesh.agent` decorator with Pydantic validation, queue-group subscription, KV registration, CAS catalog update, heartbeat task, and graceful shutdown sequence; produces a working two-agent hello-world example at `examples/hello_world.py`
- [ ] 01-02: `mesh.call()` + `mesh.send()` + lifecycle — synchronous req/reply invocation with timeout and structured error responses, async callback invocation with reply subject, `mesh.run()` blocking entry point and `await mesh.start()` / `await mesh.stop()` non-blocking lifecycle; all invocation paths covered by tests against a locally installed `nats-server`

### Phase 2: Discovery and LLM Projections
**Goal**: Consumers can list available agents, fetch full contracts, and generate LLM-ready tool definitions with correct flattened JSON Schemas
**Depends on**: Phase 1
**Requirements**: DISC-01, DISC-02, DISC-03, DISC-04, DISC-05, DISC-06
**Success Criteria** (what must be TRUE):
  1. `await mesh.catalog()` returns a list of lightweight entries (name, channel, description, version, tags) and supports filtering by `channel=` and `tags=`
  2. `await mesh.contract("summarizer")` reads from `mesh-registry` KV (not the catalog) and returns an authoritative `AgentContract` object
  3. `contract.to_openai_tool()` and `contract.to_anthropic_tool()` return schemas with no `$ref` or `$defs` — all nested models are inlined
  4. `contract.to_agent_card(url="https://example.com")` returns a valid A2A Agent Card with `x-agentmesh` extension fields and the injected `url`
**Plans**: 1 plan

Plans:
- [ ] 02-01: `discovery.py` + full `contract.py` — `mesh.catalog()`, `mesh.discover()`, `mesh.contract()` reading from KV; `AgentContract` Pydantic model with `to_openai_tool()`, `to_anthropic_tool()`, `to_generic_tool()`, `to_agent_card()` methods; `_flatten_schema()` recursive `$ref` resolver utility used by all LLM projection methods; tests verify flattening for nested Pydantic models
**UI hint**: no

### Phase 3: Embedded NATS and CLI
**Goal**: Developer can run `AgentMesh.local()` or `agentmesh up` with no external NATS installation required
**Depends on**: Phase 2
**Requirements**: TRAN-02, CLI-01, CLI-02
**Success Criteria** (what must be TRUE):
  1. `AgentMesh.local()` downloads the pinned `nats-server` binary to `~/.agentmesh/bin/` on first use, starts it as a subprocess with JetStream enabled, polls `/healthz?js-enabled-only=true` for readiness, and returns a connected `AgentMesh` instance
  2. `agentmesh up` starts a local NATS server, pre-creates the `mesh-catalog` and `mesh-registry` KV buckets, and blocks; works on macOS (`.zip`) and Linux (`.tar.gz`) without extra setup
  3. `agentmesh status` connects to a running mesh and prints registered agents with their health state
  4. The 30-line hello-world example from Phase 1 works end-to-end using only `AgentMesh.local()` with no pre-installed NATS
**Plans**: 2 plans

Plans:
- [ ] 03-01: `_binary.py` + `local.py` — NATS binary download with platform detection (macOS `.zip` / Linux `.tar.gz`), extraction to `~/.agentmesh/bin/`, `PATH` fallback check, pinned version constant with env var override; `EmbeddedNATSServer` class that starts `nats-server` via `asyncio.create_subprocess_exec` with `-js -m 8222`, polls `/healthz?js-enabled-only=true` with 10s timeout, and handles clean termination; `AgentMesh.local()` factory that tries `nats.connect()` first (reuse if already running) before starting subprocess
- [ ] 03-02: `cli/main.py` — Typer app with `agentmesh up` (download binary if needed, start NATS, create KV buckets via nats-py client, block) and `agentmesh status` (connect to mesh, call `mesh.discover()`, print formatted agent table); each command wraps async implementation with `asyncio.run()`

### Phase 4: Packaging, Testing, and Publishing
**Goal**: `pip install agentmesh` installs a typed, tested package from PyPI
**Depends on**: Phase 3
**Requirements**: PKG-01, PKG-02
**Success Criteria** (what must be TRUE):
  1. `pip install agentmesh` from PyPI succeeds and `import agentmesh` works with correct type information visible to mypy
  2. The integration test suite passes against nats-server 2.12+ covering registration, invocation, discovery, embedded NATS startup, and graceful shutdown
  3. The package wheel is `py3-none-any` (no platform binary bundled); the nats-server binary is download-at-first-use
**Plans**: 1 plan

Plans:
- [ ] 04-01: `pyproject.toml` + `tests/` + publish workflow — hatchling build backend with src layout, `py.typed` PEP 561 marker, `agentmesh` console script entry point, correct dependency pins (`nats-py>=2.7.0`, `pydantic>=2.0`, `typer>=0.12.0`); `pytest-asyncio` integration test suite covering all phases against a real nats-server process; `uv publish` workflow targeting TestPyPI then PyPI

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Core Transport and Registration | 0/2 | Not started | - |
| 2. Discovery and LLM Projections | 0/1 | Not started | - |
| 3. Embedded NATS and CLI | 0/2 | Not started | - |
| 4. Packaging, Testing, and Publishing | 0/1 | Not started | - |
