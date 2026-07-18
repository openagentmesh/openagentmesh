# ADR-0040: Death-notice triggered fast failure for in-flight requests

- **Type:** architecture
- **Date:** 2026-04-20
- **Status:** spec
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

## Amendment (2026-07-18): shaped to spec, implemented with ADR-0016

Decisions closing this ADR's open questions:

- **Always on, no opt-in flag.** `mesh.call()` and `mesh.stream()` race the
  death subject unconditionally. The cost is one extra core-NATS subscription
  per in-flight invocation — negligible at OAM's target scale. The
  shared-subscription-per-target optimization from Risks stays future work.
- **New error class `AgentDied`** (`code="agent_died"`), a `MeshError`
  subclass, carrying the death notice payload in `details`. The code sample
  above is the DX contract and the source for the tests.
- **Multi-instance resolution via ADR-0016's last-instance rule.** The
  monitor publishes a death notice only when the *last* instance serving an
  agent disconnects, so a notice always means "this agent is fully gone" and
  fast-failing on it is always correct. The undetectable case — our request
  was on the one replica that died while others live — falls back to the
  timeout, exactly as today. Header-echo correlation stays deferred.
- **`no responders` maps to `NotFound`.** When the monitor has already
  deregistered the dead agent (or it never existed), NATS reports
  no-responders on the request; the SDK raises `NotFound` instead of leaking
  `nats.errors.NoRespondersError`. This closes the §3.3 gap in
  km/agentmesh-liveness-and-failure.md: dead-agent calls fail in
  milliseconds once the catalog is clean, and sub-second while the notice is
  still in flight.
- **`stream()` behavior:** the death listener stays active until the
  end-of-stream marker; a notice mid-stream raises `AgentDied` from the
  generator. `send(on_reply=...)` keeps timeout semantics in v1 (its reply
  subscription is already managed; racing it adds complexity for a
  fire-and-forget verb).

### Chaos test (stage exit criterion)

A subprocess host serves a deliberately slow agent on an embedded mesh; the
test SIGKILLs the host mid-request and asserts the caller gets `AgentDied`
in well under the request timeout (and that the catalog no longer lists the
agent), rather than waiting out a `MeshTimeout`.
