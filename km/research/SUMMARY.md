# Project Research Summary

**Project:** AgentMesh Python SDK
**Domain:** NATS-based agent-to-agent communication fabric
**Researched:** 2026-04-04
**Confidence:** HIGH

---

## Spec Corrections Required Before Implementation

These are not implementation choices — they are bugs in the current spec that will cause hard failures:

### 1. KV Bucket Names Cannot Contain Dots

The current spec names `mesh.catalog` and `mesh.registry`. The NATS server rejects bucket names with dots. The Go client validates against `^[a-zA-Z0-9_-]+$` (sourced from `nats.go/kv.go`). Rename now, before any code is written:

| Spec name | Valid replacement |
|-----------|------------------|
| `mesh.catalog` | `mesh-catalog` |
| `mesh.registry` | `mesh-registry` |

Note: dots are valid in KV _keys_, so the per-agent key format `{channel}.{name}` (e.g., `nlp.summarizer`) inside `mesh-registry` is fine.

### 2. Pydantic `$defs`/`$ref` Break OpenAI Tool Projections

Pydantic v2's `model_json_schema()` emits `$ref` pointers and a `$defs` block for nested models. OpenAI structured outputs does not resolve `$ref`. The stored contract in KV can use `$defs` (valid JSON Schema), but `to_openai_tool()` and `to_anthropic_tool()` must flatten/inline `$defs` before returning. This is a ~30-line utility; it is not optional — shipping without it means tool projections will break for any non-trivial Pydantic model.

### 3. nats-py Dispatches Subscription Callbacks Serially

nats-py delivers messages to a subscription callback one at a time — the next message is not delivered until the coroutine for the current message returns. For agents doing slow LLM work, this means one in-flight request at a time per process. The `@mesh.agent` handler wrapper must spawn `asyncio.create_task(process_message(msg))` instead of awaiting the handler inline. This is the correct pattern from the official nats-py concurrent processing examples.

---

## Executive Summary

AgentMesh is a developer-first agent-to-agent communication fabric built on NATS. The positioning is well-founded: MCP solves agent-to-tool (static, point-to-point), A2A defines cross-org federation (HTTP spec, no runtime), and enterprise options like AGNTCY/SLIM require gRPC certificate infrastructure that rules them out for team-scale use. No Python library occupies the NATS + contract registry + Pydantic + LLM tool projection niche. The gap is real and unoccupied.

The recommended implementation approach follows standard Python SDK conventions: `pyproject.toml` with hatchling, `src/agentmesh/` layout, Typer CLI, nats-py for all NATS operations, and download-at-first-use for the NATS binary. None of these are controversial choices — the research converges on each. The spec's core design decisions are validated: two-tier discovery (catalog + full contract), A2A superset contract format, queue groups for load balancing, and the embedded NATS download pattern. These are all correct.

The primary implementation risks are the three spec corrections above (bucket names, schema flattening, serial callback dispatch) plus the operational complexity of `AgentMesh.local()` (platform binary detection, subprocess lifecycle, health-check polling). Everything else follows established, well-documented patterns with HIGH-confidence sources.

---

## Key Findings

### Recommended Stack

The stack is clear and non-controversial. Every major decision has a high-confidence rationale.

**Core technologies:**

- **nats-py >= 2.7.0** — only async Python NATS client; actively maintained (v2.14.0, Feb 2026); full JetStream KV support including CAS. Queue group subscription is one parameter.
- **Pydantic v2** — `model_json_schema()` produces JSON Schema for contracts; Field descriptions flow into LLM tool schemas; validation on input/output is built-in.
- **hatchling** — PyPA-recommended build backend; supports build hooks for the `py.typed` marker; handles `src/` layout correctly; can swap to `uv_build` later with no API changes.
- **Typer >= 0.12.0** — type-hint-driven CLI; Pydantic-centric codebase fit; `asyncio.run()` wrapper is the documented pattern for async commands (not native, but 4-line overhead per command).
- **urllib.request** (stdlib) — binary download; no additional dependency; Playwright and Terraform wrappers use this pattern.
- **asyncio.create_subprocess_exec** (stdlib) — subprocess management for embedded NATS; non-blocking; use `terminate()` then `kill()` fallback on shutdown.
- **nats-server >= 2.11** — minimum version; per-message TTL (`msg_ttl` parameter on KV put/update) is essential for heartbeat-based agent health without a cron cleanup process.

**Project layout:**

```
src/agentmesh/
  __init__.py
  py.typed           # PEP 561 — inline types
  mesh.py            # AgentMesh class
  agent.py           # @mesh.agent decorator
  contract.py        # AgentContract model
  discovery.py       # catalog(), discover(), contract()
  local.py           # AgentMesh.local() + EmbeddedNATSServer
  _binary.py         # NATS binary download
  cli/
    main.py          # Typer app: up, status, init
```

**Requires Python >= 3.10** (not 3.8 — use union syntax `X | Y` and match statements cleanly; 3.10 is the current PyPA guidance minimum for new SDKs).

### Expected Features (Phase 1 Scope)

Based on the spec and research validation:

**Must have (Phase 1 table stakes):**
- `AgentMesh(url)` connect + `AgentMesh.local()` embedded NATS
- `@mesh.agent` decorator — subscribe, validate, register contract in KV
- `mesh.call()` — sync req/reply via `nc.request()`
- `mesh.send()` — async callback pattern via publish + reply subject
- `mesh.catalog()` + `mesh.discover()` — two-tier discovery
- `AgentContract.to_openai_tool()` / `.to_anthropic_tool()` / `.to_agent_card()` — LLM projections
- `mesh.run()` blocking + `await mesh.start()` / `await mesh.stop()` non-blocking lifecycle
- `agentmesh up` CLI — download binary, start NATS, create KV buckets, block
- `agentmesh status` CLI — show registered agents
- CAS-based catalog registration (retry on `KeyWrongLastSequenceError`)
- Heartbeat loop (`mesh.health.{channel}.{name}`)
- Graceful shutdown: drain + deregister + disconnect

**Should have (post-Phase 1):**
- `agentmesh init` — Docker Compose stack
- Per-message TTL on heartbeat registrations (requires nats-server >= 2.11)
- Semaphore-based concurrency control (expose `max_concurrent` on `@mesh.agent`)
- `agentmesh status` rich table output

**Defer (v2+):**
- OTel / traceparent propagation
- TypeScript SDK
- Admin UI
- Middleware hooks
- NATS account-based multi-tenancy
- Spawning agents from specs

### Architecture Approach

The architecture is a thin async wrapper over NATS primitives — there is no framework to build, just a clean Python API that maps directly onto NATS operations. The key structural decision is that every `@mesh.agent` registers two things on startup: a subscription to `mesh.agent.{channel}.{name}` with a queue group (load balancing), and a KV entry in `mesh-registry` under key `{channel}.{name}` (full contract). The `mesh-catalog` bucket holds a single JSON blob (the lightweight index) updated via CAS. All operations are async/await; no threads, no background loops except heartbeat tasks spawned via `asyncio.create_task`.

**Major components:**

1. **`AgentMesh`** — NATS connection lifecycle, JetStream context, KV bucket handles, heartbeat task management, SIGTERM registration. Single instance per process.
2. **`@mesh.agent` decorator** — wraps an async handler: validates input via Pydantic, generates contract from type hints, registers in KV, subscribes to invocation subject with queue group, spawns `asyncio.create_task` per message.
3. **`AgentContract`** — Pydantic model holding the full A2A-compatible JSON contract. Methods: `to_openai_tool()`, `to_anthropic_tool()`, `to_generic_tool()`, `to_agent_card(url)`. Includes `_flatten_schema()` utility used by LLM projection methods.
4. **`EmbeddedNATSServer`** (`local.py`) — downloads binary via `_binary.py`, writes temp config file, starts subprocess via `asyncio.create_subprocess_exec`, polls `/healthz?js-enabled-only=true` on port 8222 for readiness.
5. **CLI** (`cli/main.py`) — Typer app with `up`, `status`, `init` commands; each wraps an async impl function with `asyncio.run()`.

**Key patterns:**
- Queue group convention: queue name == subject name (e.g., `mesh.agent.nlp.summarizer`)
- CAS retry: catch `KeyWrongLastSequenceError`, re-read entry for current revision, retry `kv.update()`
- Handler concurrency: `asyncio.create_task(process_message(msg))` inside the subscription callback — never `await` slow work directly
- Shutdown sequence: SIGTERM → cancel heartbeat tasks → `await nc.drain()` → CAS-remove from catalog → `await nc.close()`
- Health check: poll `http://127.0.0.1:8222/healthz?js-enabled-only=true` (requires monitoring port enabled; `-m 8222`)
- `msg.headers` is `None` when absent, not `{}`; always guard before access

### Critical Pitfalls

1. **Dot in KV bucket names** — `mesh.catalog` and `mesh.registry` are invalid. Use `mesh-catalog` and `mesh-registry`. Dots are valid in KV keys. Confidence: HIGH — validated against nats.go source.

2. **Serial callback dispatch blocks concurrent handling** — nats-py delivers one message at a time per subscription. Any `await` inside the callback delays the next message. Always use `asyncio.create_task(process_message(msg))` in the subscription callback. Blocking CPU work needs `loop.run_in_executor()`.

3. **Pydantic `$defs` breaks LLM tool projections** — `model_json_schema()` emits `$ref` pointers for nested models. OpenAI structured outputs requires flat schemas. Build `_flatten_schema()` utility in Phase 1 and use it in all `to_*_tool()` projections.

4. **No `-q` quiet flag on nats-server** — `nats-server -q` does not exist. Silence subprocess output via `stdout=subprocess.DEVNULL` or `asyncio.subprocess.PIPE` + log drainer task.

5. **Monitoring port required for health checks** — without `-m 8222` in the embedded NATS config, `/healthz` is not available. The subprocess readiness poll will hang. Always include `http_port: 8222` in generated config.

6. **macOS binary archives are `.zip`, not `.tar.gz`** — the python-packaging researcher noted Linux uses `.tar.gz`, macOS uses `.zip`, Windows uses `.zip`. The platform detection must branch on extension type for extraction. The nats-server researcher's table confirms this discrepancy.

7. **`js.key_value()` vs `js.create_key_value()`** — `key_value()` binds to existing bucket; raises `NotFoundError` if absent. `create_key_value()` with same config is idempotent. Use `create_key_value()` in `agentmesh up` initialization; no need to check first.

8. **NATS 2.12 strict JetStream validation** — requests silently ignored in 2.10/2.11 now return errors. Test CI against nats-server 2.12.x. Handle `APIError` defensively.

---

## Implications for Roadmap

### Phase 1: Core Transport and Registration

**Rationale:** Everything else depends on a working NATS connection, queue-group subscription, and KV registration. This is the foundation — no consumer API, no CLI, no binary download yet. Use a locally installed `nats-server` in tests.

**Delivers:** `AgentMesh` class with connect/disconnect, `@mesh.agent` decorator with KV registration and queue-group subscription, `mesh.call()` sync req/reply, CAS catalog update, heartbeat loop, graceful shutdown.

**Implements:** `mesh.py`, `agent.py`, `contract.py` skeleton (no LLM projections yet).

**Must avoid:** Serial dispatch pitfall — handler wrapper must spawn `asyncio.create_task` from day one. KV bucket names must use `mesh-catalog` and `mesh-registry` from the first line of code.

**Research flag:** Standard patterns, skip phase research. nats-py docs and nats-py.md cover all required operations with HIGH confidence.

---

### Phase 2: Discovery and LLM Projections

**Rationale:** Depends on Phase 1's contract storage. `mesh.catalog()`, `mesh.discover()`, `mesh.contract()` read from KV. LLM projections (`to_openai_tool()`, `to_anthropic_tool()`, `to_agent_card()`) depend on having a correct `AgentContract` model.

**Delivers:** Full consumer API (`catalog()`, `discover()`, `contract()`), `AgentContract` with all projection methods, `_flatten_schema()` utility for OpenAI compatibility.

**Implements:** `discovery.py`, full `contract.py`.

**Must avoid:** Shipping `to_openai_tool()` without schema flattening — this will silently produce broken schemas for nested Pydantic models.

**Research flag:** The A2A Agent Card fields are verified (ecosystem.md, HIGH confidence). Schema flattening approach is known; ~30 lines of resolver code. Skip phase research.

---

### Phase 3: Embedded NATS and CLI

**Rationale:** `AgentMesh.local()` and the CLI are operationally self-contained. They don't affect the protocol or SDK API surface. Building them last lets the core be testable against a real installed NATS server before adding subprocess complexity.

**Delivers:** `EmbeddedNATSServer` with download-at-first-use binary management, `AgentMesh.local()` factory, `agentmesh up` and `agentmesh status` CLI commands. Complete Phase 1 hello-world in <30 lines.

**Implements:** `_binary.py`, `local.py`, `cli/main.py`.

**Must avoid:**
- macOS `.zip` vs Linux `.tar.gz` extraction branching (don't assume `.tar.gz` everywhere)
- Missing monitoring port in generated NATS config (`http_port: 8222` required)
- `asyncio.sleep(0.2)` as a proxy for readiness — use `/healthz?js-enabled-only=true` polling loop with 10s timeout
- JetStream store dir conflicts between concurrent `AgentMesh.local()` instances

**Research flag:** May benefit from brief research-phase on port conflict detection (checking if 4222 is already in use before starting subprocess). Everything else is well-documented.

---

### Phase 4: Packaging, Testing, and Publishing

**Rationale:** Final hardening before PyPI. Integration tests, type checking, publishing workflow.

**Delivers:** Correct `pyproject.toml` with hatchling, `py.typed` marker, `pytest-asyncio` integration test suite against real nats-server, `mypy --strict` passing, `uv publish` to TestPyPI.

**Implements:** `pyproject.toml`, `tests/`, CI workflow.

**Research flag:** Standard patterns (python-packaging.md, HIGH confidence). Skip phase research.

---

### Phase Ordering Rationale

- Phase 1 before 2: discovery reads contracts that Phase 1 writes; cannot test discovery without registration working.
- Phase 2 before 3: LLM projections need the full `AgentContract` model; CLI `status` command calls `discover()`.
- Phase 3 before 4: packaging should capture the complete feature set; integration tests need `AgentMesh.local()`.
- Concurrency (create_task pattern) is a Phase 1 concern, not an optimization — it must be correct from the start.

### Research Flags

Phases needing deeper research during planning:
- **Phase 3 (port conflict detection):** How to detect that port 4222 is already in use before starting the embedded subprocess. Options: `socket.connect()` probe, `psutil`, or just let nats-server fail and parse stderr. Needs a decision.

Phases with standard patterns (skip research-phase):
- **Phase 1:** nats-py operations, queue groups, CAS — all HIGH confidence with working code examples.
- **Phase 2:** Pydantic schema generation, A2A Agent Card fields — verified against official specs.
- **Phase 4:** Python packaging with hatchling, pytest-asyncio — PyPA-documented, nothing custom.

---

## Open Questions for Implementation

Not blocking Phase 1, but need decisions before the relevant phase ships:

1. **`AgentMesh.local()` KV persistence across restarts** — the current `EmbeddedNATSServer` implementation uses a temp dir for the JetStream store, which means registrations are lost on restart. Is this correct for dev? The spec says "dev only" which implies ephemeral is fine, but a persistent store at `~/.agentmesh/jetstream/` would make iterative development faster. Decision: use persistent store at `~/.agentmesh/jetstream/` for `agentmesh up` CLI (which is long-lived), and temp dir for `AgentMesh.local()` (which is process-scoped).

2. **Port 4222 conflict detection** — `AgentMesh.local()` and `agentmesh up` should detect if NATS is already running on 4222 and either reuse it or fail fast with a clear error. Recommended: attempt `nats.connect()` first; if it succeeds, skip server start (matches the `agentmesh up` sequence in nats-server.md section 6).

3. **NATS binary version pinning vs latest** — pin `NATS_VERSION = "v2.12.6"` in `_binary.py` with `AGENTMESH_NATS_VERSION` env var override. Do not auto-fetch latest on every install (network call at import time is unacceptable). Upgrade the pinned version on SDK releases.

4. **Checksum verification** — the nats-server SHA256SUMS file is published alongside each release. Skipping verification is a security gap. Defer to post-Phase 1, document explicitly as a known gap in `_binary.py`.

5. **`path in PATH` fallback** — if `nats-server` is already in `PATH`, prefer it over downloading. Reduces CI complexity and respects user-managed installs.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| NATS protocol and nats-py API | HIGH | Verified against official docs, module source, natsbyexample.com |
| KV bucket name constraint | HIGH | Validated against nats.go source (`kv.go:validBucketRe`) |
| Serial callback dispatch behavior | HIGH | Official nats-py concurrent processing examples, GitHub discussion #555 |
| Python packaging (hatchling, src layout) | HIGH | PyPA official guides, multiple authoritative sources agree |
| Binary download pattern | MEDIUM | Pattern is established (Playwright, Terraform); URL format confirmed; specific extraction code is original |
| Pydantic $defs flattening | MEDIUM | Problem is confirmed HIGH; the ~30-line solution approach is established but specific implementation is original |
| Typer async workaround | MEDIUM | GitHub discussion confirmed `asyncio.run()` pattern; some informal sources incorrectly claim native async support |
| A2A superset contract design | HIGH | Verified against a2a-protocol.org spec; extension namespaces explicitly permitted |
| Ecosystem positioning | HIGH | MCP/A2A/AGNTCY gap analysis confirmed by multiple sources; no competing NATS+Python+registry library found |
| nats-server >= 2.11 requirement | HIGH | Per-message TTL added in 2.11; confirmed from Synadia blog + NATS 2.12 release notes |

**Overall confidence: HIGH**

### Gaps to Address

- **Schema flattening implementation:** The need is confirmed; the exact implementation (custom `GenerateJsonSchema` subclass vs. recursive `$ref` resolver) needs a decision during Phase 2 planning. Recommend the recursive resolver (simpler, no Pydantic internals coupling).
- **Windows support depth:** Binary extraction and path handling for Windows is specified but not integration-tested in research. Phase 3 should include explicit Windows CI or document Windows as best-effort for v0.1.
- **CAS bursty registration:** Under simultaneous mass-startup (hundreds of agents), the CAS retry loop may spin excessively. This is acceptable for Phase 1 (teams, not fleets). Document the limit explicitly.

---

## Sources

### Primary (HIGH confidence)

- [nats-io/nats.py official docs](https://nats-io.github.io/nats.py/) — all nats-py API surface, error types, KV operations
- [nats.go kv.go source](https://github.com/nats-io/nats.go/blob/main/kv.go) — `validBucketRe` bucket name constraint
- [NATS Server Flags docs](https://docs.nats.io/running-a-nats-service/introduction/flags) — embedded server flags
- [NATS Subject naming docs](https://docs.nats.io/nats-concepts/subjects) — subject rules, wildcard semantics
- [NATS KV Store docs](https://docs.nats.io/using-nats/developer/develop_jetstream/kv) — KV operations, CAS pattern
- [NATS Server Monitoring docs](https://docs.nats.io/running-a-nats-service/nats_admin/monitoring) — `/healthz` endpoint
- [NATS ADR-8 KV Architecture](https://github.com/nats-io/nats-architecture-and-design/blob/main/adr/ADR-8.md) — KV design rationale
- [NATS 2.12 release notes](https://docs.nats.io/release-notes/whats_new/whats_new_212) — strict JetStream validation
- [A2A Protocol Specification](https://a2a-protocol.org/latest/specification/) — Agent Card format, extension namespaces
- [Pydantic JSON Schema docs](https://docs.pydantic.dev/latest/concepts/json_schema/) — `$defs` behavior, Field descriptions
- [Python Packaging User Guide](https://packaging.python.org/en/latest/) — pyproject.toml, src layout, PEP 561
- [natsbyexample.com — concurrent processing Python](https://natsbyexample.com/examples/messaging/concurrent/python) — create_task pattern

### Secondary (MEDIUM confidence)

- [What's New in NATS 2.11 — Synadia](https://www.synadia.com/blog/per-message-ttl-nats-2-11) — per-message TTL feature
- [Python Build Backends 2025 comparison](https://medium.com/@dynamicy/python-build-backends-in-2025-what-to-use-and-why-uv-build-vs-hatchling-vs-poetry-core-94dd6b92248f) — hatchling recommendation
- [Typer GitHub Discussion #864](https://github.com/fastapi/typer/discussions/864) — asyncio.run() workaround pattern
- [Top AI Agent Protocols in 2026 — GetStream.io](https://getstream.io/blog/ai-agent-protocols/) — ecosystem positioning
- [OpenAI JSON Schema Sanitizer for Pydantic](https://gist.github.com/aviadr1/2d1186625d67fba9c8f421d273bf7a53) — $defs flattening approach

---

*Research completed: 2026-04-04*
*Ready for roadmap: yes*
