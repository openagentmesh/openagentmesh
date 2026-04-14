# ADR-0022: Make AgentMesh.local() an async context manager for tests and demos

- **Type:** api-design
- **Date:** 2026-04-14
- **Status:** documented
- **Source:** conversation (design discussion on local() lifecycle coupling)

## Context

`AgentMesh.local()` was designed as a class method that starts an embedded NATS subprocess and returns an `AgentMesh` instance. This couples the NATS server lifecycle to the SDK process, creating three problems:

1. **Multi-process dev is broken.** Only one process can own the NATS subprocess. A second script calling `local()` either fails or needs "detect and skip" logic.
2. **Lifecycle entanglement.** If the Python process crashes, the NATS child process becomes orphaned. Signal handling gets complex when managing both a server subprocess and async agent handlers.
3. **Port contention.** A second `local()` call must decide whether an existing NATS on that port is "ours," compatible, and JetStream-enabled.

Meanwhile, `agentmesh up` already provides a clean way to run a local NATS server, and multi-process development (provider in one terminal, consumer in another) is the normal workflow.

## Decision

Redefine `AgentMesh.local()` as an **async context manager** scoped to tests and quick single-file demos. The embedded NATS subprocess starts on entry and stops on exit, making the lifecycle explicit and bounded.

```python
async with AgentMesh.local() as mesh:
    # embedded NATS starts, KV buckets created
    ...
    # NATS stops when context exits
```

The standard development workflow becomes `agentmesh up` in one terminal, then `AgentMesh()` (no args, defaults to `nats://localhost:4222`) in application code. This cleanly separates server lifecycle from client lifecycle.

**New constructor semantics:**

| Constructor | Use case |
|------------|----------|
| `AgentMesh()` | Default, connects to `nats://localhost:4222` |
| `AgentMesh("nats://...")` | Explicit NATS URL |
| `async with AgentMesh.local() as mesh:` | Tests and demos, embedded NATS with scoped lifecycle |

## Alternatives Considered

- **Keep `local()` as-is:** Simple for single-file demos but misleading for real development. Users would hit the multi-process wall quickly.
- **Smart start-or-connect:** `local()` detects existing NATS and skips starting. Fragile (is that NATS ours? right config? JetStream enabled?) and hides important operational details.
- **Drop `local()` entirely:** Clean, but loses the zero-config test story. `agentmesh up` is one extra command, but context manager is better for automated tests.

## Risks and Implications

- All existing documentation and spec references to `AgentMesh.local()` as a general-purpose constructor must be updated.
- The hello world example adds one prerequisite step (`agentmesh up`), slightly increasing the "time to first agent." The trade-off is worth it because the multi-process workflow works immediately.
- `AgentMesh()` with no arguments is a new convention that must be documented clearly.
