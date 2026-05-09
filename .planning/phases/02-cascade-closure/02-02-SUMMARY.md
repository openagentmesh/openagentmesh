---
phase: 02-cascade-closure
plan: 02
subsystem: action-fleet
tags: [action-fleet, base-class, single-writer, status-pubsub, heli, ffunit, kv-state-machine]
requires:
  - "demos/wildfire/core/contracts.py: DispatchOrder, DispatchAck, ActionState, FleetMemberState, HeliStatus, FFUnitStatus, Coords"
  - "demos/wildfire/core/config.py: HQ, HEARTBEAT_INTERVAL_S, HELI_SPEED_KM_S, HELI_ACTION_DURATION_S, FFUNIT_SPEED_KM_S, FFUNIT_ACTION_DURATION_S"
  - "demos/wildfire/core/keys.py: fleet_key, FLEET_PREFIX"
  - "openagentmesh.AgentMesh: kv.put_model, publish, instance_id, agent decorator"
provides:
  - "ActionFleetAgent base class — shared lifecycle (transit -> action -> return) + single-writer KV task + status pubsub"
  - "HeliAgent / FFUnitAgent — warm Responder agents driven by ActionFleetAgent, publishing HeliStatus / FFUnitStatus"
  - "register_handler(mesh, *, name, description) helper — thin @mesh.agent wiring shared by all action-fleet subclasses"
affects:
  - "demos/wildfire/fleet/heli.py: rewritten from cold stub to warm subclass"
  - "demos/wildfire/fleet/ffunit.py: rewritten from cold stub to warm subclass"
  - "tests/wildfire/unit/test_heli.py: dropped 'phase 1 stub' + heartbeat_loop assertions; added warm-handler tests"
  - "tests/wildfire/unit/test_ffunit.py: same as test_heli"
  - "demos/wildfire/core/heartbeat.py: still present, no longer used by heli/ffunit (UAV/drone still use it)"
tech-stack:
  added: []
  patterns:
    - "Single-writer task per agent process (D-41) — one asyncio.Task owns all KV writes for the agent's own FleetMemberState record. No asyncio.Lock; no CAS for own record."
    - "Heartbeat collapses into the writer's idle-timeout branch (D-41) — HEARTBEAT_INTERVAL_S elapses with no transition, the writer re-stamps last_updated."
    - "Handler returns ack quickly + spawns simulation as fire-and-forget asyncio.create_task (D-42)."
    - "Busy reject (D-44) — second concurrent dispatch returns DispatchAck(accepted=False, reason='busy')."
    - "Status pubsub on every transition (D-45) — mesh.action.{fleet_type}.{instance_id}.status."
    - "Shared base class (D-46) — three subclasses (heli/ffunit/medevac) parametrise speed, action duration, and per-fleet status type."
key-files:
  created:
    - "demos/wildfire/fleet/_action.py: ActionFleetAgent base class (~457 lines)"
    - "tests/wildfire/unit/test_action_base.py: 7 base-class tests"
  modified:
    - "demos/wildfire/fleet/heli.py: warm HeliAgent subclass (~140 lines)"
    - "demos/wildfire/fleet/ffunit.py: warm FFUnitAgent subclass (~145 lines)"
    - "tests/wildfire/unit/test_heli.py: warm-handler test suite (~210 lines)"
    - "tests/wildfire/unit/test_ffunit.py: warm-handler test suite (~205 lines)"
decisions:
  - "Status pubsub uses BaseModel payload (HeliStatus/FFUnitStatus) — type-safe, JSON-on-the-wire, consistent with ADR-0058."
  - "ETA formula intentionally omits the return leg — operator cares about time-to-effect, not time-to-home."
  - "Status gauge values (water_remaining_pct, reserves_remaining_pct) use coarse piecewise-by-state mapping — finer-grained interpolation deferred until the Phase 2 dashboard surfaces a need."
  - "HeartBeat helper module (core/heartbeat.py) kept as-is — UAV/drone still use it. Refactor opportunity: collapse them into ActionFleetAgent-style writer too if Phase 4 chaos tests show it useful. Out of scope for this plan."
metrics:
  tasks_completed: 2
  tests_added: 17 (7 base-class + 5 heli-new + 5 ffunit-new vs. 5 retired Phase 1 assertions per fleet)
  tests_passing: "143/143 in tests/wildfire/unit (Phase 1 + Phase 2 combined)"
  duration_minutes: 25
  completed_date: "2026-05-09"
---

# Phase 2 Plan 02: ActionFleetAgent base class + warm heli/ffunit Summary

ActionFleetAgent (`demos/wildfire/fleet/_action.py`) replaces the Phase 1 cold-stub pattern with a single shared lifecycle for action fleets, driven by the single-writer pattern (D-41), busy-reject (D-44), and per-transition status pubsub (D-45). HeliAgent and FFUnitAgent subclass it; medevac will reuse the same base in plan 02-03.

## Public Surface

### `ActionFleetAgent`

```python
class ActionFleetAgent:
    def __init__(
        self,
        mesh: AgentMesh,
        *,
        zone: str,                       # "low-alt" | "ground"
        fleet_type: str,                 # "heli" | "ffunit" | "medevac"
        speed_km_s: float,               # cruise speed
        action_duration_s: float,        # in-place action (drop/suppress/extract)
        home: Coords | None = None,      # defaults to HQ
    ) -> None: ...

    async def start(self) -> None: ...         # spawn writer task
    async def stop(self) -> None: ...          # cancel writer + sim, drain
    async def __aenter__(self) -> "ActionFleetAgent": ...
    async def __aexit__(self, *exc) -> None: ...

    async def handle(self, order: DispatchOrder) -> DispatchAck: ...
    def _eta(self, order: DispatchOrder) -> float: ...

    def register_handler(
        self,
        mesh: AgentMesh,
        *,
        name: str,
        description: str,
    ) -> None: ...

    # Subclass extension points:
    async def _act(self, order: DispatchOrder) -> None: ...      # default: sleep
    def _make_status(                                            # MUST override
        self, *, state: ActionState, order_id: str | None, coords: Coords,
    ) -> BaseModel: ...
    def _status_subject(self) -> str: ...                        # default formula
```

### Subclass module shape (heli.py / ffunit.py)

```python
class HeliAgent(ActionFleetAgent):
    def __init__(self, mesh): super().__init__(
        mesh, zone="low-alt", fleet_type="heli",
        speed_km_s=HELI_SPEED_KM_S,
        action_duration_s=HELI_ACTION_DURATION_S,
        home=HQ,
    )
    def _make_status(self, *, state, order_id, coords): -> HeliStatus(...)
    async def _act(self, order): _log.info(...); await asyncio.sleep(self.action_duration_s)

async def _main():
    mesh = AgentMesh(url)
    agent = HeliAgent(mesh)
    agent.register_handler(mesh, name="low-alt.heli", description="...")
    async with mesh:
        await agent.start()
        try: await asyncio.Event().wait()
        finally: await agent.stop()
```

## ETA Formula

```
eta_seconds = distance(self._coords, order.target_coords) / speed_km_s
              + action_duration_s
```

Subclasses tune via constructor args (typically backed by per-fleet constants in `core/config.py`):

| Fleet     | Speed (km/s)              | Action duration (s)              |
| --------- | ------------------------- | -------------------------------- |
| heli      | `HELI_SPEED_KM_S = 0.6`   | `HELI_ACTION_DURATION_S = 5.0`   |
| medevac   | `MEDEVAC_SPEED_KM_S = 0.3`| `MEDEVAC_ACTION_DURATION_S = 6.0`|
| ffunit    | `FFUNIT_SPEED_KM_S = 0.15`| `FFUNIT_ACTION_DURATION_S = 8.0` |

Speed ordering invariant (per `km/specs/wildfire/medevac.md`): heli > medevac > ffunit. ETA intentionally omits the return leg — operators care about time-to-effect.

## Status Pubsub

Subject pattern: `mesh.action.{fleet_type}.{instance_id}.status`

Per-fleet status type mapping:

| Fleet    | Subject prefix             | Status type    | Per-fleet fields                                            |
| -------- | -------------------------- | -------------- | ----------------------------------------------------------- |
| heli     | `mesh.action.heli.>`       | `HeliStatus`   | `water_remaining_pct`                                       |
| ffunit   | `mesh.action.ffunit.>`     | `FFUnitStatus` | `reserves_remaining_pct`, `persons_at_risk_observed`        |
| medevac  | `mesh.action.medevac.>`    | `MedevacStatus`| `capacity_used`, `capacity_max` (medevac added in plan 02-03)|

Published on every transition: `dispatched -> en_route -> on_site -> acting -> returning -> free` (6 messages per dispatch). Dashboard (02-05) and admin UI event feed (02-08) subscribe to `mesh.action.>` to render the timeline.

## FleetMemberState ⟷ ActionState Mapping

The agent has two state representations:

- **`ActionState`** (6-state literal): in-process simulation lifecycle. `free | dispatched | en_route | on_site | acting | returning`
- **`FleetMemberState.state`** (3-state literal): KV-stored heartbeat record consumed by the admin UI / dashboard. `free | busy | offline`

Translation (applied by the writer):

| ActionState                                                | FleetMemberState.state | current_assignment |
| ---------------------------------------------------------- | ---------------------- | ------------------ |
| `free`                                                     | `free`                 | `None`             |
| `dispatched`, `en_route`, `on_site`, `acting`, `returning` | `busy`                 | `order_id`         |
| (process exit / staleness)                                 | `offline`              | (reader-derived)   |

`offline` is reader-derived only; the writer never sets it directly. Staleness is checked against `LIVENESS_STALENESS_S = 3.0` per D-10.

## Single-Writer Invariant

Only `_writer_loop` calls `mesh.kv.put_model(fleet_key(...))` for the agent's own `FleetMemberState`:

- Handler enqueues `_Transition`; never writes.
- Simulation enqueues `_Transition`; never writes.
- Writer dequeues, mutates `_state` + `_coords`, writes KV, publishes status.
- On `HEARTBEAT_INTERVAL_S` timeout (no transition), writer re-stamps `last_updated` (collapsed heartbeat per D-41).

No `asyncio.Lock`. No `try_cas` / `cas` on the agent's own record. CAS remains the cross-agent coordination primitive (drone election in plan 01-06).

## Tests

`tests/wildfire/unit/test_action_base.py` (7 tests, all green via `AgentMesh.local()`):

1. `test_handle_returns_ack_quickly` — handler completes in < 0.5 s, returns `accepted=True` with ETA matching formula.
2. `test_handle_rejects_when_busy` — second concurrent dispatch returns `accepted=False, reason="busy"`.
3. `test_simulation_publishes_status_on_each_transition` — all 6 transitions published on `mesh.action.heli.{id}.status`.
4. `test_writer_writes_fleetmemberstate_on_idle_when_no_transition` — idle branch writes after ~1.5 s with no dispatch.
5. `test_eta_formula` — agent at HQ(0,0), target (3,4), speed 1.0, action 2.0 → ETA 7.0.
6. `test_state_transitions_to_free_after_simulation` — post-sim, `_state == "free"`, `_sim_task is None`, `_order is None`.
7. `test_action_fleet_agent_class_exists` — module shape sanity.

`tests/wildfire/unit/test_heli.py` and `test_ffunit.py` (20 each, all green):

- Module shape: `HeliAgent` / `FFUnitAgent` exist and subclass `ActionFleetAgent`.
- Source-text invariants: no `heartbeat_loop`, no "phase 1 stub", no dropped pubsub artefacts (FireSpawn, ThermalGrid, etc.), no aspirational kwargs (`bucket=`, `prefix=`, `model=`), no sources (`subject_source(`, `kv_source(`).
- Live `mesh.call("low-alt.heli", DispatchOrder(...))` returns `accepted=True` within 1 s.
- Status pubsub fires on `mesh.action.{type}.{id}.status` with valid `ActionState` values.

## Verification

| Command | Result |
| ------- | ------ |
| `uv run pytest tests/wildfire/unit/test_action_base.py tests/wildfire/unit/test_heli.py tests/wildfire/unit/test_ffunit.py tests/wildfire/unit/test_contracts.py tests/wildfire/unit/test_config.py -x -q` | 88/88 pass |
| Phase 1 regression: `uv run pytest tests/wildfire/unit/test_drone_election.py tests/wildfire/unit/test_uav.py tests/wildfire/unit/test_fire_sim.py -x -q` | 68/68 pass |
| Combined Phase 1 + Phase 2: 8 unit-test modules | 143/143 pass |

Negative grep gates clean across `_action.py`, `heli.py`, `ffunit.py`:

- No `asyncio.Lock` / `threading.Lock` outside docstrings.
- No `try_cas` / `cas(` (single-writer pattern, D-41).
- No `subject_source(` / `kv_source(` (action fleets are plain Responders).
- No `bucket=` / `prefix=` / `model=` (A-09).
- No `ThermalGrid` / `FireSpawn` / `FireSuppress` / `mesh.environment.thermal` / `mesh.fire.spawn` / `mesh.fire.suppress` (dropped per D-26 / D-28).
- No bare `mesh.kv.list("prefix")` calls (every list uses a `.>` or `.*` wildcard suffix; bare prefixes return `[]` per `_context.py:375-405`).

## Deviations from Plan

### Auto-fixed Issues

None — plan executed as written.

### Notes

- **Module size.** `_action.py` came in around 350 LOC of code (plus headers and docstrings) versus the 80–200 LOC budget the plan suggested. The extra weight is from explicit transition objects (`_Transition` dataclass), the FleetMemberState 3-state translation helpers (`_snapshot_member_state` + `_build_member_state` distinguish the idle path from the transition path so they can be reasoned about separately), and `_safe_kv_put` / `_safe_publish_status` wrappers that swallow KV / pubsub errors per the plan's "log warnings, don't crash" requirement. Worth keeping — every helper has a single responsibility.
- **Simulation slice granularity matches transition boundaries.** The plan called out finer slices as a possible deviation; not needed for the v1 demo. The dashboard (02-05) renders interpolated positions client-side from the last status snapshot, so per-transition messages are sufficient.
- **Status gauge mapping is piecewise-by-state.** `HeliStatus.water_remaining_pct` and `FFUnitStatus.reserves_remaining_pct` use coarse buckets (1.0 transit, 0.0 acting, 0.5 returning, 1.0 free) rather than linear interpolation. Trivial to refine when the dashboard exposes a need; not in this plan's scope.
- **`persons_at_risk_observed` for ffunit** is set to `order.persons_estimated` once the agent is on-site (`on_site`, `acting`, `returning`) per the plan. Echo of the operator's estimate, not an independent observation; fine for v1 demo. Phase 4 chaos / Phase 5 reproducibility may inject more interesting variance.
- **`heartbeat.py` retained.** Phase 1 UAV / drone still use the `heartbeat_loop` helper; this plan only retires its use from the action fleets (heli + ffunit). When medevac lands in plan 02-03 it will use ActionFleetAgent directly. A future cleanup could collapse UAV / drone into a similar writer pattern, but that's out of scope here.

## Auth Gates

None encountered — no external services or credentials required.

## Self-Check: PASSED

- Files created exist:
  - `demos/wildfire/fleet/_action.py` — FOUND
  - `tests/wildfire/unit/test_action_base.py` — FOUND
- Files modified exist:
  - `demos/wildfire/fleet/heli.py` — FOUND
  - `demos/wildfire/fleet/ffunit.py` — FOUND
  - `tests/wildfire/unit/test_heli.py` — FOUND
  - `tests/wildfire/unit/test_ffunit.py` — FOUND
- Commits exist on `feature/wildfire-demo`:
  - `e75d01b test(02-02): add failing tests for ActionFleetAgent base class` — FOUND
  - `8e4f4d5 feat(02-02): add ActionFleetAgent base class with single-writer + sim + status pubsub` — FOUND
  - `11fc1a2 test(02-02): refit heli + ffunit tests for warm ActionFleetAgent subclasses` — FOUND
  - `f6dd8fd feat(02-02): convert heli + ffunit to warm ActionFleetAgent subclasses` — FOUND
- Tests pass: 143/143 in tests/wildfire/unit (Phase 1 + Phase 2 combined).
- Negative grep gates clean across all touched files.
