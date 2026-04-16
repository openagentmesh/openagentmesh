# ADR-0015: Prefer PATH nats-server over auto-download

- **Type:** dx
- **Date:** 2026-04-04
- **Status:** accepted
- **Source:** .specstory/history/2026-04-04_09-50-29Z.md

## Context

`AgentMesh.local()` needs a NATS server binary. The original design only auto-downloaded it to `~/.agentmesh/bin/`. The question was whether to also detect a user-managed `nats-server` already on PATH.

## Decision

Check PATH first. If `nats-server` is already available (e.g., installed via package manager, present in CI images), use it directly. Only fall back to downloading if not found. This reduces CI complexity and respects user-managed installs.

## Risks and Implications

- PATH `nats-server` may be an incompatible version (too old, missing JetStream support). The embedded server startup should validate the version and fail fast with a clear message if unsupported.
- Users may not realize which binary is being used. `agentmesh up` should log which nats-server binary it found and its version.