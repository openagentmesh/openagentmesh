# Changelog

All notable changes to OpenAgentMesh will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
