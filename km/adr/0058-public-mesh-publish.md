# ADR-0058: Public `mesh.publish(subject, payload)` for arbitrary-subject emission

- **Type:** api-design
- **Date:** 2026-05-08
- **Status:** spec
- **Source:** wildfire demo shaping in `km/specs/wildfire/` (sdk-desiderata.md #2). Multiple agents and non-agents (fire-sim, scenario UI, drones, action fleets, ticker, narrator) need to emit events to flat subjects without hitting `mesh._nc.publish`.
- **Related:** ADR-0034 (publisher emission via `yield` on agents — adjacent but distinct), ADR-0049 (dotted agent name), ADR-0019 (OAM positioning).

## Context

Today's SDK has two emission paths:

1. **Agent publisher pattern** (ADR-0034): an agent declared with `async def f(): yield Event(...)` runs at startup and publishes to its auto-mapped subject `mesh.agent.{name}.events`. Subject is bound to the agent's identity.

2. **Direct NATS publish:** code reaches into `mesh._nc.publish(subject, body, headers=...)`. Subject can be anything but the path is private API; users must JSON-encode by hand and remember the OAM header conventions.

Use cases that fit neither cleanly:
- Fire-sim broadcasts a `ThermalGrid` to `mesh.environment.thermal` at 1 Hz. The subject is part of a domain protocol, not derived from the agent's name. Publisher pattern would force the subject to be `mesh.agent.fire-sim.events`.
- Drones emit `SurveyResult` to `mesh.survey.{instance_id}` for visibility — instance-id-suffixed subjects do not auto-derive.
- Scenario UI publishes `mesh.fire.spawn` and `mesh.chaos.kill.{id}` from a non-agent process.
- Stats ticker, narrator: similar — flat subjects (`mesh.swarm.stats`, `mesh.swarm.narrative`).
- Action fleets emit status feeds (`mesh.action.heli.{id}.status`).

Every one of these reaches into private API today. The fix is a single public method that publishes a typed payload to an arbitrary subject with OAM header conventions applied.

## Decision

Add `AgentMesh.publish` as a public coroutine method.

```python
async def publish(
    self,
    subject: str,
    payload: BaseModel | bytes | str,
    *,
    headers: dict[str, str] | None = None,
) -> None:
    """Publish a payload to an arbitrary NATS subject.

    payload acceptable forms:
      - pydantic.BaseModel: JSON-encoded via model_dump_json
      - bytes: published as-is
      - str: encoded as UTF-8 bytes

    The SDK auto-stamps OAM headers (request ID, instance ID per
    ADR-0059) onto the published message. User-supplied headers are
    merged on top.
    """
```

### Headers

Auto-stamped on every publish:

| Header | Source | Purpose |
|---|---|---|
| `X-Mesh-Request-Id` | `uuid.uuid4().hex` per call | Correlation / tracing |
| `X-Mesh-Instance-Id` | `mesh.instance_id` (ADR-0059) | Source attribution |
| `X-Mesh-Content-Type` | `application/json` for BaseModel, `application/octet-stream` for bytes, `text/plain` for str | Receiver hint for deserialization |

User-supplied `headers=` merge over auto-stamped (user can override). Reserved header names (anything starting `X-Mesh-`) print a warning if user attempts to override.

### Subject validation

`subject` is a NATS subject. Wildcards (`*`, `>`) are NOT valid in publish (only in subscribe). The SDK validates the subject is a syntactically valid NATS subject and raises `ValueError` if it isn't (e.g., contains a wildcard or invalid character).

### Semantics

- Connection state required: `mesh` must be in `__aenter__` context. Publishing without connection raises `MeshNotConnected` (or AssertionError, matching current convention).
- Fire-and-forget. No reply consumed by `publish`. For request/reply, use `mesh.call`.
- No queue group. Plain core-NATS publish; every subscriber receives.

### Code sample (DX contract)

```python
from openagentmesh import AgentMesh

mesh = AgentMesh()

async def fire_sim_loop():
    async with mesh:
        while True:
            grid = build_grid()  # ThermalGrid
            await mesh.publish("mesh.environment.thermal", grid)
            await asyncio.sleep(1.0)

async def drone_survey(detection):
    # ... compute SurveyResult ...
    await mesh.publish(
        f"mesh.survey.{mesh.instance_id}",
        survey_result,
    )

# Non-agent caller (scenario UI backend):
await mesh.publish(
    "mesh.fire.spawn",
    FireSpawn(coords=(2.5, 1.0), magnitude=300.0),
)
```

## Consequences

- New public method on `AgentMesh`. Implementation wraps `self._nc.publish` with payload encoding and header stamping.
- Removes legitimate reasons to access `mesh._nc` from user code.
- Subjects in user code are explicit (no auto-derivation), giving demos and protocols full control over their subject namespaces.
- Composes cleanly with the source pattern (ADR-0052): `mesh.subject_source(...)` on the receiver side reads what `mesh.publish(...)` sends, with type-hint-driven deserialization.
- ADR-0034 (publisher emission) remains: the `yield` form is sugar for "publish to my own auto-mapped subject from a long-running task." It can be re-implemented internally as `mesh.publish` plus the per-agent subject convention; user-facing semantics unchanged.

## Alternatives Considered

**Force everything through Publisher pattern (ADR-0034).** Rejected: ties subjects to agent identity. Demo's flat domain subjects (`mesh.environment.thermal`, `mesh.swarm.stats`) cannot be expressed without subject overrides on the agent, which gets messy fast.

**Make `mesh._nc.publish` the canonical path with a warning that it's private.** Rejected: leaks NATS-specific encoding requirements (bytes vs JSON), header conventions, and connection lifecycle assumptions to every caller. Boilerplate proliferates.

**Different name (`emit`, `send`, `broadcast`).** Rejected: `publish` matches NATS terminology; `send` is taken (fire-and-forget invocation, ADR-0034); `emit` is an internal verb, less user-facing.

**Type the `payload` as `BaseModel` only.** Rejected: bytes and str cover edge cases (already-serialized payloads, plain text channels) without forcing a wrapper model.
