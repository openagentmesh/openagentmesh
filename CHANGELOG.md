# Changelog

All notable changes to OpenAgentMesh will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/openagentmesh/openagentmesh/releases/tag/v0.1.0
