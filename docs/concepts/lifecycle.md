# Lifecycle Gates

Some agents should only be online while a condition holds. A wildfire
response fleet has no business consuming requests between incidents; a
batch enricher should sit out business hours; a canary agent should serve
only while a feature flag is set. Checking the condition inside the handler
works, but the agent still accepts (then rejects) requests, still occupies
its queue-group slot, and scatters lifecycle logic across every handler.

`active_when` declares the condition once, on the decorator. The SDK
watches it and subscribes or unsubscribes the agent as the condition flips
— no controller process, no restarts.

```python
import json
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

# Only subscribes while the incident.mode KV key is "active".
@mesh.agent(
    AgentSpec(
        name="wildfire.coordinator",
        description="Assigns tasks to response fleets during active wildfire incidents",
    ),
    active_when=mesh.kv_condition("incident.mode", lambda v: json.loads(v) == "active" if v else False),
)
async def coordinator(brief: IncidentBrief) -> TaskAssignment:
    return await llm.assign_tasks(brief)
```

Set `incident.mode` to `"active"` — from any process on the mesh — and the
coordinator subscribes. Set it to anything else and the coordinator drains
in-flight work, then unsubscribes.

```python
await mesh.kv.put("incident.mode", json.dumps("active"))    # gate opens
await mesh.kv.put("incident.mode", json.dumps("contained")) # gate closes
```

## Conditions

Two condition factories ship with the SDK:

| Factory | Signal | Predicate receives |
|---------|--------|--------------------|
| `mesh.kv_condition(key, predicate)` | A key in the shared `mesh-context` KV bucket | The key's raw `bytes` value, or `None` when absent/deleted |
| `mesh.subject_condition(subject, predicate)` | Messages on a plain NATS subject | Each message's payload `bytes` |

Both accept two keyword arguments:

- `initial` (default `False`) — the agent's state before the first signal.
  For KV conditions this rarely matters: the SDK reads the key's current
  value when the mesh starts and applies the predicate immediately, so
  `initial` is only the fallback when that read fails (e.g. missing
  permissions). For subject conditions it is the state until the first
  message arrives.
- `drain_timeout` (default `30.0`) — how long in-flight handlers may run
  after the gate closes before the agent unsubscribes anyway.

Any object with `predicate`, `initial`, and `drain_timeout` attributes
satisfies the `Condition` protocol; `KVCondition` and `SubjectCondition`
are the shipped implementations.

## What a closed gate means

- **The RPC subscription is gone.** The agent has left its queue group, so
  NATS stops routing requests to it. Other replicas whose gates are open
  keep serving.
- **Sources are gated too.** No `kv_source` or `subject_source` delivers
  messages while the agent is offline; `sources` and `active_when` compose.
- **The catalog entry stays.** The catalog describes capability, not
  availability — discovery still lists the agent, and its contract is
  unchanged.

## `not_available` vs `not_found`

Calling an agent whose gate is closed raises `NotAvailable`
(`not_available` on the wire): the request got no responders, but the agent
is still in the catalog, so it exists and may come back. Calling an agent
that was never registered raises `NotFound`. The distinction tells a caller
whether to retry later or give up.

One edge: a request published in the instant the gate is closing can be
dropped rather than answered — the caller sees a `MeshTimeout` for that
request, and `NotAvailable` from the next one. Treat both as retryable.

```python
from openagentmesh import NotAvailable

try:
    result = await mesh.call("wildfire.coordinator", {"summary": "smoke report"})
except NotAvailable:
    ...  # gated offline — retry when the incident activates
```

## Drain semantics

When the gate closes, the agent first leaves its queue group — new
requests stop arriving — and in-flight handlers get up to `drain_timeout`
seconds to finish. Requests that complete within the window return their
results normally, even though the gate is already closed. Only then are
source subscriptions and background tasks torn down.

## Multiple instances

Each instance watches the condition independently. All instances see the
same KV value and the same predicate, so they converge on the same state
without coordination — closing a gate takes every replica offline, opening
it brings them all back.

## Observability

Gate transitions publish `agent_activated` and `agent_deactivated` log
events at `info` level on the agent's `mesh.logs.{name}` subject — visible
in `oam observe logs` like every other [observability event](observability.md).

## Secured meshes

Gates ride existing permission surfaces: `kv_condition` needs read access
to the `mesh-context` bucket (all shipped [roles](security.md) have it),
and `subject_condition` needs subscribe permission on its subject — the
same constraint as `subject_source`. No extra grants are required.
