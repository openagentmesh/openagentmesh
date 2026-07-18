# ADR-0055: Agent lifecycle gates (`active_when`)

- **Type:** api-design
- **Date:** 2026-05-06
- **Status:** documented
- **Amends:** ADR-0042 (formally retires Watcher as a handler shape), ADR-0031 (removes Watcher row from capability table)
- **Depends on:** ADR-0052 (generic sources), ADR-0031 (capability inference)
- **Amended:** 2026-07-18 (implementation shaping; see Amendment section)

## Context

ADR-0052 introduced `sources` as declarative trigger bindings on `@mesh.agent`. A source fires the handler whenever a message arrives on a NATS subject. This handles the "what triggers the handler" question cleanly.

A second question remains unanswered: **what controls whether an agent is subscribed at all?**

Today, an agent either runs (subscribed to its RPC subject and any sources) or does not run (not registered). There is no first-class way to say "this agent should only be online while condition X holds." Workarounds:

1. Check the condition inside every handler invocation. Works, but the agent still accepts requests and burns resources when offline.
2. Write a controller that calls a hypothetical `mesh.start()` / `mesh.stop()` API. Does not exist; also requires out-of-band coordination.
3. Use the Watcher shape to watch a condition and restart the target agent. Fragile; requires process-level restart logic.

The wildfire demo (ADR-0054) makes the gap concrete: response fleet agents (UAV dispatcher, medivac coordinator, etc.) should only subscribe during an active incident. Wiring this through handler-body checks scatters lifecycle logic and keeps the agents consuming queue-group slots when no incident is active.

### Watcher shape status

ADR-0042 introduced Watcher (`invocable=False, streaming=False`) as a handler shape for KV-watch loops. ADR-0052 subsumed it: a source-only agent with no `mesh.call()` surface. With ADR-0055, the Watcher shape has no remaining use cases that cannot be expressed by `sources` + `active_when`. It is formally retired.

## Decision

Add `active_when` as a third keyword argument on `@mesh.agent`, alongside `sources`.

```python
@mesh.agent(spec: AgentSpec, *, sources: list[Source] = [], active_when: Condition | None = None)
```

When `active_when` is set, the SDK watches the condition and:
- **On true:** subscribes the agent to its RPC subject and activates all sources.
- **On false:** drains in-flight handlers, then unsubscribes from all subjects and sources.

## Amendment (2026-07-18, implementation shaping)

Four corrections against the repo as shipped, recorded before implementation:

1. **Conditions are mesh factory methods, not a public submodule.** The original
   sample imported from `openagentmesh.lifecycle`, but the package has no public
   submodules (private `_modules` + top-level exports throughout), and ADR-0052
   shipped sources as factories on the mesh (`mesh.kv_source(...)`). Conditions
   follow the same pattern: `mesh.kv_condition(key, predicate, *, initial=False,
   drain_timeout=30.0)` and `mesh.subject_condition(subject, predicate, *,
   initial=False, drain_timeout=30.0)`. The dataclasses (`KVCondition`,
   `SubjectCondition`) and the `Condition` protocol live in `_lifecycle.py` and
   are exported top-level for typing. The sample's bare `kv_source(...)` is
   likewise corrected to `mesh.kv_source(...)`.
2. **`not_available` is a caller-side mapping, not an agent reply.** The original
   mechanics said drain-phase callers "receive `not_available`" — but an agent
   that has left its queue group cannot reply with anything. Actual mechanics:
   when a request gets NATS no-responders, the caller consults its catalog cache
   — agent present in the catalog → `NotAvailable` (`not_available`), absent →
   `NotFound` (`not_found`). This refines ADR-0040's no-responders→`not_found`
   mapping and gives one consistent behavior for both the drain window and the
   fully-offline gate state. It leans on this ADR's own catalog-visibility rule
   (gated agents stay in the catalog).
3. **`kv_condition` watches the `mesh-context` bucket** (the same bucket as
   `kv_source` and `mesh.kv`), so gates compose with the KV the wildfire agents
   already share. The predicate receives the raw `bytes` value, or `None` when
   the key is absent or deleted.
4. **Startup evaluation is a synchronous read, not just `initial`.** On
   `__aenter__` the SDK reads the key's current value and applies the predicate
   immediately (deterministic: a mesh entered while the gate is already true
   comes online before `__aenter__` returns). `initial` remains the fallback
   state when the initial read fails (e.g. permissions). The background watcher
   then re-evaluates on every change; transitions are idempotent, which absorbs
   the get-then-watch race. The drain timeout is a per-condition parameter
   (`drain_timeout`, default 30 s) — resolves the TBD below.

### `Condition` Protocol

```python
from typing import Protocol, Callable, Any

class Condition(Protocol):
    """A lifecycle gate for an agent.

    The SDK evaluates the condition whenever the underlying signal changes.
    When predicate returns True, the agent comes online. When it returns
    False, the agent goes offline after draining in-flight handlers.
    """
    subject: str          # NATS subject or KV key to watch
    predicate: Callable[[Any], bool]  # receives the current value; None if key absent
    initial: bool         # default state before first signal arrives (default: False)
```

The SDK provides `mesh.kv_condition` as the primary concrete implementation (a factory method, per the amendment):

```python
mesh.kv_condition(key: str, predicate: Callable[[bytes | None], bool], *, initial: bool = False, drain_timeout: float = 30.0) -> KVCondition
```

A subject-based condition (`mesh.subject_condition`) follows the same shape but watches a plain NATS subject: the predicate receives each message's payload bytes. Future conditions (e.g., cron-activated windows, HTTP health checks) implement the same Protocol.

### Code sample (the DX contract)

```python
import json
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

# Only subscribes while the incident.mode KV key is "active".
@mesh.agent(
    AgentSpec(name="wildfire.coordinator", description="Assigns tasks to response fleets during active wildfire incidents"),
    active_when=mesh.kv_condition("incident.mode", lambda v: json.loads(v) == "active" if v else False),
)
async def coordinator(brief: IncidentBrief) -> TaskAssignment:
    return await llm.assign_tasks(brief)

# Source-only agent (no invocable surface) that is also lifecycle-gated.
@mesh.agent(
    AgentSpec(name="wildfire.monitor", description="Watches perimeter sensors during active incidents"),
    sources=[mesh.kv_source("sensors.*.perimeter")],
    active_when=mesh.kv_condition("incident.mode", lambda v: json.loads(v) == "active" if v else False),
)
async def monitor(reading: PerimeterReading) -> None:
    await alert_if_critical(reading)
```

When `incident.mode` is set to `"active"`, both agents subscribe. When it changes to anything else, both drain in-flight handlers and unsubscribe.

### Lifecycle mechanics

1. **Startup:** On `mesh.__aenter__`, the SDK evaluates `initial` (default: `False`). If `False`, the agent does not subscribe. The SDK begins watching the condition's subject in the background.
2. **Gate opens (predicate returns True):** The agent subscribes to its RPC subject and activates all sources. Normal operation.
3. **Gate closes (predicate returns False):** The agent leaves its queue group (stops accepting new requests). In-flight handlers are allowed to complete (with a configurable drain timeout, default: 30 s). Source subscriptions are also torn down. Callers who send to the RPC subject during drain receive `not_available`.
4. **Shutdown:** On `mesh.__aexit__`, all agents drain and unsubscribe regardless of gate state.

### Multi-instance behavior

Each instance independently watches the condition. All instances see the same KV value. When the gate closes, all instances unsubscribe. Requests mid-flight on an instance that closes are drained before unsubscription. No distributed locking required: the predicate is deterministic given the same KV value.

### Error code: `not_available`

Add `not_available` to the error taxonomy (amends `docs/concepts/errors.md`):

> `not_available` -- The agent is registered in the catalog but is currently offline due to a lifecycle gate. The agent exists; it is not currently accepting requests. Retry when the condition changes, or wait for a liveness event (future ADR).

This is distinct from `not_found` (agent not registered) and `not_invocable` (agent has no RPC surface).

### Relationship to `sources`

`sources` and `active_when` are orthogonal. Both live on the decorator, not in `AgentSpec`. Sources define _how the handler is triggered_; `active_when` defines _whether the agent is subscribed_. When a gate is set, sources are also gated: no source delivers messages while the agent is offline.

### Catalog visibility

The agent's contract remains in the catalog regardless of gate state. The catalog describes capability, not availability. A future observability surface (ADR-0048) may expose per-instance active state as deployment metadata. That is runtime state, not contract.

### Watcher shape retirement

The Watcher handler shape (`async def f() -> None`) is formally retired. What was a Watcher is now expressed as either:

- A source-only agent: `@mesh.agent(spec, sources=[kv_source(...)])` with a `None`-returning handler.
- A lifecycle-gated agent: any handler shape with `active_when=...`.
- Both combined: a source-only agent that only runs when a condition holds.

The `invocable=False, streaming=False` capability combination remains valid: it means "source-only, no `mesh.call()` surface." It no longer implies a specific handler shape.

ADR-0042 status changes to `superseded by ADR-0055`.

### Handler-body KV loops (legacy)

The handler-body watch loop form from ADR-0042 (`async for value in mesh.kv.watch(...): ...`) is not removed. It remains a valid pattern for cases where the watch logic is bespoke (conditional restarts, partial key watches, merge logic across multiple keys). `active_when` is the idiomatic form for simple on/off gating; body loops remain the escape hatch.

## Consequences

- `@mesh.agent` decorator gains `active_when: Condition | None = None` keyword argument.
- `Condition` Protocol, `KVCondition`, `SubjectCondition` in `_lifecycle.py` (new private module), exported top-level; `mesh.kv_condition` / `mesh.subject_condition` factories (amended).
- SDK runtime: on `mesh.__aenter__`, evaluates the current KV value (fallback `initial`); starts background watcher for the condition; subscribes/unsubscribes on predicate changes.
- New error code `not_available` (`NotAvailable`) added to error taxonomy and `docs/concepts/errors.md`; caller-side no-responders mapping refined per the amendment.
- Drain timeout: per-condition `drain_timeout` parameter, default 30 s (TBD resolved by the amendment).
- ADR-0042 → `superseded by ADR-0055`. Handler-body KV loop form remains supported.
- ADR-0031 capability table: Watcher row removed. Add note: "`invocable=False, streaming=False` means source-only agent; see ADR-0052."
- `docs/concepts/agents.md`: remove Watcher from handler shapes table.
- New `docs/concepts/lifecycle.md` page documenting `active_when`, `Condition`, drain semantics, and the multi-instance guarantee.

## Alternatives Considered

**`active_when` inside `AgentSpec`.** Rejected for the same reason sources were rejected from `AgentSpec` (ADR-0052): contains callables, deployment-specific, not catalog material.

**Imperative `mesh.start(name)` / `mesh.stop(name)`.** Useful, but requires a controller agent that must itself stay alive, adding an orchestration dependency. Declarative `active_when` requires no controller: every instance self-manages. An imperative API may be added in a future ADR as a complement (useful for testing and operational overrides), but it should not be the primary lifecycle primitive.

**Gate as a special `Source` type (`LifecycleSource`).** Would keep the decorator surface to two kwargs (`spec`, `sources`). Rejected: sources are trigger inputs (they feed data to the handler); lifecycle gates control subscription state. Conflating the two into one list loses the semantic distinction and complicates the runtime (the SDK must distinguish "fire handler" from "change subscription state" when iterating sources).

**Check condition inside handler body.** Already the status quo. Works, but the agent consumes queue-group slots and accepts (then rejects) requests while offline. Does not gate source subscriptions. Lifecycle logic scattered across every handler instead of declared once on the decorator.

**Restart the agent process on condition change.** Too coarse. Process restarts lose all in-flight state, take seconds, and require external orchestration (systemd, Kubernetes). `active_when` is subscription-level, not process-level: in-flight handlers complete, other agents in the same process are unaffected.
