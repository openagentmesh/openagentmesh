# Changelog

All notable changes to OpenAgentMesh will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/openagentmesh/openagentmesh/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/openagentmesh/openagentmesh/releases/tag/v0.1.0
