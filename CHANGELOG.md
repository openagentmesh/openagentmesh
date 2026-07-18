# Changelog

All notable changes to OpenAgentMesh will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Mesh-native observability** (ADR-0048): agents publish structured, level-gated log events to `mesh.logs.{name}` with zero code changes — registration/deregistration at `info`, per-request events with durations at `debug`, failures and validation errors at `warn`. Tail them live with `oam observe logs [agent] [--level warn]` or in code via `async for event in mesh.observe.logs(...)`. Log levels change at runtime with no restart: `oam observe set <agent> --log-level debug` (or `--global`) writes a `mesh-observability` KV bucket that every host watches; `oam observe config` shows what's in effect and where it came from. Default settings publish nothing per request, so the steady-state overhead is zero.

- **Instant failure detection** (ADR-0016): a mesh health monitor turns NATS disconnect advisories into sub-second cleanup when an agent host crashes — the dead agent leaves the catalog immediately (not after a stale window) and a death notice is published on `mesh.death.{name}` for orchestrators, spawners, and dashboards to react to (`mesh.subscribe(subject="mesh.death.>")`). Graceful shutdowns publish their own notice. Replicated agents are handled correctly: notices fire only when the last instance goes, and shutting down one replica no longer removes the shared catalog entry. `AgentMesh.local()` and `oam mesh up` run the monitor automatically; secured meshes run `oam mesh monitor --sys-creds ... --creds ...`.
- **Fast-fail for in-flight requests** (ADR-0040): `mesh.call()` and `mesh.stream()` race every request against the target's death notices. An agent that dies holding your request now raises `AgentDied` (code `agent_died`) in well under a second instead of stalling until the timeout — chaos-tested by SIGKILLing an agent mid-request.

- **Mesh authentication (SDK)** (ADR-0038): connect to a secured mesh with `AgentMesh(url=..., creds="./agent.creds")` using standard NATS NKey + JWT credentials. Credentials also resolve from the `OAM_CREDS` environment variable or a `creds` field in `.oam-url`, which now accepts a small TOML form (`url = "..."`, `creds = "..."`) alongside the legacy bare-URL line. Optional mTLS via `tls_cert=`, `tls_key=`, `tls_ca=`. A server that rejects the connection raises `ConnectionDenied` (code `connection_denied`) explaining which credentials were used, instead of a generic connection failure. `AgentMesh.local()` stays open and ignores ambient credentials.
- **`oam auth` CLI** (ADR-0038): `oam auth init` bootstraps a complete NKey/JWT credential tree (wrapping `nsc`) with a ready-to-run `server.conf`; `oam auth user add <name> --role worker|invoker|observer` mints role-templated `.creds` files; `oam auth user revoke` revokes a user; `oam auth whoami` shows the identity the CLI would connect with. `oam mesh connect --creds` persists credentials next to the mesh URL.
- **MCP export bridge** (ADR-0002/0003): any MCP client (Claude Code, Claude Desktop, Cursor) can list and call mesh agents as tools. Opt agents in per-agent with `@mesh.agent(spec, mcp=True/False)` and set the mesh policy via `mesh.run_mcp(default_mcp=...)` (blocking) or `await mesh.serve_mcp(...)` (async). `oam mcp serve --url nats://...` gateways an already-running mesh — register it with `claude mcp add mesh -- oam mcp serve`. Requires the new `mcp` extra: `pip install 'openagentmesh[mcp]'`.
- `contract.to_agent_card(url=None)` (ADR-0012): project a contract to an A2A Agent Card — the registry document minus `x-agentmesh`, with the `url` injected at the federation boundary.
- npm release workflow for `@openagentmesh/sdk`: pushing an `sdk-ts-v*` tag runs the full TS suite and publishes to npm.
- `py.typed` marker: the package now advertises its inline type annotations to type checkers (PEP 561), and the codebase passes `ty check` with zero diagnostics.
- CI on GitHub Actions: every push and PR runs ruff, ty, the Python test suite, and the TypeScript SDK typecheck + test suite.

### Changed

- Calling an agent nobody serves now raises `NotFound` immediately (NATS no-responders) instead of leaking the raw `nats.errors.NoRespondersError` — the error-handling cookbook's retry pattern now works as documented.
- The dev NATS servers started by `oam mesh up` and `AgentMesh.local()` now run with a small accounts config (anonymous clients still connect exactly as before) and a 10s ping interval, so network partitions are detected in ~20s instead of NATS's ~4-minute default.
- `mesh.kv` and `mesh.workspace` accessed before connecting now raise `ConnectionFailed` with a clear message instead of surfacing as `AttributeError: 'NoneType' object has no attribute ...` at the first call site.

### Fixed

- `mesh.call()` timeouts now raise `MeshTimeout` (part of the `MeshError` taxonomy) instead of leaking the raw `nats.errors.TimeoutError`. When the timeout was actually caused by the server denying the publish (missing permissions), the call raises `ConnectionDenied` explaining which permission is missing.
- `@openagentmesh/sdk` package metadata declared Apache-2.0; the project license is MIT. Corrected before first npm publish.
- `mesh.contract()` now restores `input_schema`/`output_schema` from the registry document; contracts fetched from the registry previously lost their schemas (breaking tool projection for remote agents).
- TypeScript SDK test harness: agent simulators now flush their subscription interest before tests proceed, eliminating intermittent "No agent serving" failures in full-suite runs.

- `mesh.instance_id`: stable per-process identifier (UUID4 hex), auto-stamped as `X-Mesh-Instance-Id` header on every outbound message (ADR-0059). Lets receivers attribute messages to a specific replica when multiple instances of the same agent name are running.
- `mesh.publish(subject, payload, *, headers=None)`: public method to publish a Pydantic model, bytes, or str to an arbitrary NATS subject (ADR-0058). Auto-stamps OAM headers (`X-Mesh-Request-Id`, `X-Mesh-Instance-Id`, `X-Mesh-Content-Type`); rejects wildcard subjects. Replaces the need to reach into `mesh._nc.publish` for flat domain subjects.
- KV ergonomics extensions on `mesh.kv` (ADR-0060):
  - `list(prefix)` returns a snapshot of entries under a NATS subject wildcard pattern.
  - `try_cas(key)` is a non-raising CAS context manager for election semantics; exposes `entry.committed` after exit.
  - `create(key, value)` is put-if-absent; raises `KVKeyExists` if the key collides.
  - Pydantic helpers (`put_model`, `get_model`, `cas_model`, `try_cas_model`, `list_models`) cut JSON round-trip boilerplate.
  - New `KVEntry` public dataclass and `KVKeyExists` error joining the ADR-0057 taxonomy.
- **TypeScript client SDK** `@openagentmesh/sdk` (ADR-0061): an isomorphic (browser + Node) client that consumes a mesh from JavaScript/TypeScript. `AgentMesh.connect()` then `call` / `stream` / `send` / `publish` / `subscribe`, two-tier discovery (`catalog` / `contract` / `discover`), and shared-context KV read/watch (`mesh.kv`). Speaks the exact OAM wire protocol over `@nats-io` v3 (WebSocket in the browser, TCP in Node). Consume-only for now: it invokes and observes agents but does not host them. Lives at `sdk-ts/`.
- Agent sources (ADR-0052): `@mesh.agent(spec, sources=[...])` binds an agent to declarative trigger surfaces. `mesh.subject_source(subject, *, queue_group=None)` and `mesh.kv_source(pattern, *, queue_group=None, on_init="replay"|"skip")` create source objects. The handler's first-parameter type hint drives input dispatch: `bytes`, a Pydantic model, `KVEntry[T]` (full KV envelope), or `MeshMessage[T]` (full NATS envelope). Source-driven agents with envelope inputs are non-invocable; sources are runtime wiring not part of the catalog. Replaces (and supersedes the narrow form of) the ADR-0042 watcher pattern.

## [0.2.1] - 2026-04-23

### Changed

- Internal: removed the `compute_registry_key` helper. Post-ADR-0049 the registry key equals the agent name verbatim, so the indirection was dead weight. No user-visible change.

## [0.2.0] - 2026-04-22

### Changed

- **Breaking:** agent names are now dotted identifiers (ADR-0049). The `channel` field on `AgentSpec`, `CatalogEntry`, and `AgentContract` is removed; the channel hierarchy is encoded as leading dot-segments of `name` (e.g. `finance.risk.scorer` instead of `name="scorer", channel="finance.risk"`). Wire subjects are unchanged. `catalog(channel=X)` now performs prefix matching on the name; `subscribe(channel=X)` still subscribes to `mesh.agent.{X}.>`; `contract()` no longer accepts a `channel` argument.

### Added

- Name validation at registration time: names must be a non-empty sequence of dot-separated segments matching `[a-zA-Z0-9_-]+` (ADR-0049).

## [0.1.6] - 2026-04-21

### Fixed

- Use absolute URL for logo so PyPI renders it correctly.

## [0.1.5] - 2026-04-21

### Changed

- Redesigned README with centered logo header, badges, highlights section, section emojis, and MCP/A2A positioning.
- Extended Python compatibility to 3.11+ (previously 3.12+).

### Added

- PyPI classifiers for Python 3.11, 3.12, and 3.13.
- Contributing and License sections in README.

## [0.1.4] - 2026-04-21

### Changed

- Updated documentation to reflect latest SDK changes and improved README.

### Added

- Discussion ADR on observability strategy.

## [0.1.3] - 2026-04-21

### Fixed

- `oam mesh up` now detects port conflicts before starting NATS, preventing stale PID files when another service (e.g. Docker) already occupies the port.

## [0.1.2] - 2026-04-21

### Added

- Startup banner with mesh art and block-letter OAM for `oam demo` and `oam mesh up`.

### Changed

- Simplified `oam demo` from sub-commands (`list`, `show`, `run`) to a single command that launches the hello-world demo.

## [0.1.1] - 2026-04-21

### Added

- Scalar and generic type support in handler signatures (ADR-0046).
- Interactive hello_world demo, decoupled from cookbook tests.

### Fixed

- Flush NATS after each streaming chunk for real-time delivery.
- Fail fast with clear error when mesh is unreachable.
- Isolate embedded NATS from parent signals.

## [0.1.0] - 2026-04-20

Initial release. History before this point not documented.

[Unreleased]: https://github.com/openagentmesh/openagentmesh/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/openagentmesh/openagentmesh/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.6...v0.2.0
[0.1.6]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/openagentmesh/openagentmesh/releases/tag/v0.1.0
