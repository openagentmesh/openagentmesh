# ADR-0059: `mesh.instance_id` stable per-process identifier

- **Type:** api-design
- **Date:** 2026-05-08
- **Status:** spec
- **Source:** wildfire demo shaping in `km/specs/wildfire/` (sdk-desiderata.md #8). Multiple fleet processes register the same agent name and need a stable per-process identifier for outbound payloads, KV records, and observability headers.
- **Related:** ADR-0058 (public publish, auto-stamps `X-Mesh-Instance-Id`), ADR-0049 (dotted agent name), ADR-0008 (DX-first), ADR-0014 (catalog identity).

## Context

OAM's catalog identity is the agent name. Multiple replicas of the same agent (e.g. 5 drones registered as `low-alt.drone`) share the catalog entry; load balancing happens at the NATS queue group on the auto-mapped invocation subject.

Replicas are however distinct at runtime. They have different positions, different state, different work in flight. User code today generates a per-process UUID at startup if it needs to distinguish replicas in payloads (e.g., `detector_id` field on `ThermalDetection`, `drone_id` on `SurveyResult`, key for KV position records). Boilerplate proliferates and there is no shared convention.

OAM also has no built-in way to attribute outbound messages to a specific replica. The catalog identifies the agent class; nothing identifies the replica in headers. Admin UI cannot show "active instances of `low-alt.drone`" without per-demo plumbing.

The fix is a one-line affordance:

```python
mesh.instance_id  # str, stable for the lifetime of the AgentMesh instance
```

with the same value auto-stamped on every outbound message header.

## Decision

### Public attribute

`AgentMesh` gains a public `instance_id` attribute.

```python
class AgentMesh:
    instance_id: str   # generated at __init__, lower-case hex UUID4

    def __init__(self, url: str = "nats://localhost:4222"):
        self.instance_id = uuid.uuid4().hex
        ...
```

The value is read-only after construction (a property is not strictly required; the field convention is fine, with a docstring noting do-not-mutate).

The full UUID hex is the canonical form. Loggers and the admin UI can render the first 8 characters as a short form, but the full value is what travels in headers and KV keys to keep collisions zero in practice.

### Auto-stamped on outbound messages

All public emission paths apply `X-Mesh-Instance-Id: {mesh.instance_id}` to the message headers if not already set:

- `mesh.publish` (ADR-0058)
- `mesh.call`, `mesh.send`, `mesh.stream`
- Reply messages from agent handlers (subjects auto-stamp the responder's instance ID)
- Catalog change emissions (ADR-0032 stream): the source instance ID

User-supplied headers retain priority: if a caller passes `headers={"X-Mesh-Instance-Id": "spoofed"}`, that wins. Documented as "the SDK provides the default; tests and bridges may override; production code should not."

### Catalog projection

The catalog entry for an agent does NOT include the instance ID. Catalog identity stays at the agent-name level (per the existing model). Per-instance presence is a separate concern (see ADR-0056 / sdk-desiderata.md #6).

A future ADR may add a runtime "presence" surface (e.g., a system bucket `mesh-presence` keyed by agent name + instance ID) that the admin UI consumes. This ADR scopes only to the local affordance + outbound headers.

### Code sample (DX contract)

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()
print(mesh.instance_id)
# => "e7b3...c9a2"  (hex UUID4)

@mesh.agent(AgentSpec(name="low-alt.drone", description="Survey drone"))
async def drone(req: SurveyRequest) -> SurveyResult:
    return SurveyResult(
        drone_id=mesh.instance_id,        # stable per-process
        coords=req.coords,
        ...
    )

# KV record key uses the instance ID:
await mesh.kv.put(
    f"wildfire.fleet.low-alt.drone.{mesh.instance_id}",
    state.model_dump_json(),
)
```

Receivers see the source instance via headers automatically:

```python
@mesh.agent(spec, sources=[mesh.subject_source("mesh.survey.>")])
async def briefer(msg: MeshMessage[SurveyResult]) -> None:
    source_instance = msg.headers["X-Mesh-Instance-Id"]
    # logging, attribution, etc.
```

## Consequences

- One read-only attribute on `AgentMesh`. Negligible memory cost.
- One header stamped on outbound messages. Adds ~50 bytes per message; trivial for nearly all workloads.
- Convention becomes part of the OAM protocol: any OAM client/server must honor `X-Mesh-Instance-Id` if they read it; receivers are not required to read it.
- Demo and admin UI can attribute messages to replicas without per-demo plumbing.
- Tests that compare full headers in golden assertions will see the new header. Existing tests at v0.2.x do not currently make such assertions; new tests should treat `X-Mesh-Instance-Id` as auto-applied.

## Alternatives Considered

**Use NATS connection client_id.** Rejected: not stable across reconnects, server-assigned numeric, leaks NATS to the OAM protocol layer.

**Generate at first emit, lazily.** Rejected: lazy generation makes the attribute observable mid-lifetime, complicating reasoning. Eager generation at `__init__` is simpler and the cost is one UUID4 call.

**Expose as a method (`mesh.instance_id()`) instead of attribute.** Rejected: it never changes during the instance's lifetime; an attribute matches the data it represents.

**Allow user to set it explicitly.** Rejected for v1. If a use case emerges (e.g., deterministic tests, named replicas), revisit. The simplest API wins until there is a concrete reason otherwise.

**Stamp ALL emissions vs. opt-in.** Rejected opt-in: the value of the convention is uniformity. Per-call opt-out via user-supplied headers is enough escape hatch.
