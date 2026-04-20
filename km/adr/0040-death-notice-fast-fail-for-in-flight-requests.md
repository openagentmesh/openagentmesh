# ADR-0040: Death-notice triggered fast failure for in-flight requests

- **Type:** architecture
- **Date:** 2026-04-20
- **Status:** discussion
- **Depends on:** ADR-0016 (disconnect advisories)
- **Source:** conversation on failure modes during mid-request agent death

## Context

When an agent dies after accepting a request (process crash, OOM, network partition), the caller currently waits for the full timeout period before receiving a `MeshTimeout`. With NATS request/reply, `no responders` only fires when zero subscribers exist at publish time; it does not fire when a subscriber dies after receiving the message.

ADR-0016 introduces disconnect advisories and death notices (`mesh.death.{channel}.{name}`), enabling sub-second detection of agent death. However, the caller's `mesh.call()` and `mesh.stream()` do not currently react to these signals. The timeout window (up to 60s for agent-type SLAs) is wasted.

This matters most for orchestrators dispatching work across multiple agents: a 60s stall on one downstream call delays the entire workflow.

## Decision

The SDK's `mesh.call()` and `mesh.stream()` should optionally race against death notices for the target agent. When a death notice arrives during an in-flight request, the call fails immediately with a dedicated error code instead of waiting for the timeout.

### Caller-side behavior

```python
try:
    result = await mesh.call("summarizer", payload, timeout=30.0)
except MeshError as e:
    if e.code == "agent_died":
        # Agent died during our request; sub-second detection
        print(f"Fast-fail: {e.message}")
    elif e.code == "timeout":
        # No death notice; agent may be alive but slow (zombie)
        print(f"Slow-fail: {e.message}")
```

### Implementation sketch

Inside `mesh.call()`:

1. Before publishing the request, subscribe to `mesh.death.{channel}.{name}` (or `mesh.death.*.{name}` if channel is unknown).
2. Race the NATS reply inbox against the death notice subscription.
3. If the death notice wins, unsubscribe, raise `MeshError(code="agent_died")`.
4. If the reply wins, unsubscribe from death notices, process normally.
5. If the timeout wins, unsubscribe from death notices, raise `MeshTimeout`.

For `mesh.stream()`, the same race applies, but the death notice listener stays active until the stream ends (`X-Mesh-Stream-End: true`).

### Multi-instance agents

When an agent runs as multiple queue-group instances, a single instance dying does not mean the request is lost. NATS delivered the message to one specific instance. The death notice tells us *an* instance died, but not *which one* received our request.

Options:

- **Optimistic:** ignore death notices for multi-instance agents (the request likely went to a surviving instance). Risk: the specific instance that took our request was the one that died.
- **Pessimistic:** fail fast on any instance death. Risk: false positives when a non-relevant instance dies.
- **Correlation:** the responding agent echoes a connection ID or instance ID in early headers; the death notice includes the same ID. Precise, but requires protocol extension.

Recommendation: start with the pessimistic approach for single-instance agents; skip fast-fail for multi-instance agents until correlation is available.

## Alternatives Considered

- **Timeout only (current):** Simple, already works. Acceptable for Phase 1, but 60s wasted on dead agents is costly for orchestration workflows.
- **Application-level heartbeat during processing:** the agent periodically sends "still working" frames. Catches zombies faster but adds protocol complexity and doesn't help with crashes (the agent can't heartbeat if it's dead).
- **NATS JetStream with ack/nak:** use JetStream for request delivery so unacknowledged messages get re-delivered. Changes the transport model significantly; not compatible with vanilla NATS request/reply.

## Risks and Implications

- Adds a subscription per in-flight call. For high-throughput callers, this could be many concurrent subscriptions. Mitigated by sharing a single death notice subscription per target agent across all in-flight calls to that agent.
- Depends on the health monitor (ADR-0016) being active and publishing death notices. If the health monitor is down, the fast-fail path is simply absent; callers fall back to timeout.
- Multi-instance correlation is a rabbit hole. The pessimistic/skip approach is good enough for initial implementation.

## Phase

Not Phase 1. Depends on ADR-0016 (health monitor, death notices) being implemented first. Target: Phase 2.
