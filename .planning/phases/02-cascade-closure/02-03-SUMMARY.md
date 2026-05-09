---
phase: 02-cascade-closure
plan: 03
subsystem: wildfire
tags: [medevac, action-fleet, ground, capacity, scn-07, d-46]
requires:
  - "demos/wildfire/fleet/_action.py (ActionFleetAgent base from 02-02)"
  - "demos/wildfire/core/contracts.py:MedevacStatus (from 02-01)"
  - "demos/wildfire/core/config.py:MEDEVAC_* constants (from 02-01)"
provides:
  - "demos/wildfire/fleet/medevac.py (third action-fleet warm Responder)"
  - "ActionFleetAgent._on_transition subclass hook (post-transition mutator)"
  - "Capacity rejection path (DispatchAck reason='capacity')"
affects:
  - "demos/wildfire/fleet/_action.py (added _on_transition hook + writer call site)"
tech-stack:
  added: []
  patterns:
    - "Subclass-overrides-hook pattern for per-fleet state mutation inside the writer task"
    - "Capacity check BEFORE busy check so a full unit declines without pretending to be free"
key-files:
  created:
    - "demos/wildfire/fleet/medevac.py"
    - "tests/wildfire/unit/test_medevac.py"
  modified:
    - "demos/wildfire/fleet/_action.py (added _on_transition hook)"
decisions:
  - "Capacity rejection sits in MedevacAgent.handle() BEFORE super().handle() — defensive ordering so a full unit always declines, even if writer hasn't published the busy state yet."
  - "Capacity bookkeeping uses the new _on_transition hook (not _simulate override or _act wrapper). Increment fires on 'acting' entry, reset on 'free' entry. Synchronous, runs inside the writer, no concurrency hazards."
  - "build_agent(mesh) returns the agent (rather than just registering and discarding) so tests can manage start/stop. _main() consumes the same helper. Heli/ffunit kept their inline pattern; not refactoring them in this plan to keep the blast radius minimal."
  - "Plan 02-03's suggestion to refactor test_heli/test_ffunit to use build_agent was NOT taken: those tests already use the inline-instantiate pattern (agent = HeliAgent(mesh) + agent.register_handler(...)) which mirrors what test_medevac does. No test churn needed."
metrics:
  duration: "~25min"
  tasks_completed: 1
  commits: 4
  tests_added: 23
  tests_passing: 228
---

# Phase 2 Plan 03: ground.medevac Agent Summary

Third action-fleet member lands. `MedevacAgent` subclasses `ActionFleetAgent` (built in 02-02), adds capacity tracking, and exposes a capacity-rejection path that returns `DispatchAck(accepted=False, reason="capacity")` when a dispatch would overflow `capacity_max`.

## What was built

### `demos/wildfire/fleet/medevac.py` (~110 LOC)

- `class MedevacAgent(ActionFleetAgent)` with `zone="ground"`, `fleet_type="medevac"`, `speed_km_s=MEDEVAC_SPEED_KM_S` (0.3 km/s), `action_duration_s=MEDEVAC_ACTION_DURATION_S` (6.0 s), `capacity_max=MEDEVAC_CAPACITY_MAX` (4 persons).
- Per-instance counter `self._capacity_used: int = 0`.
- `handle(order)` checks `order.persons_estimated + self._capacity_used > self.capacity_max` first; if so, returns `DispatchAck(accepted=False, instance_id=mesh.instance_id, eta_seconds=None, reason="capacity")`. Otherwise delegates to `super().handle(order)` for the standard busy check + accept path.
- `_on_transition(state, order_id)` (the new D-46 hook) increments `self._capacity_used += self._order.persons_estimated` on entering `"acting"` and resets `self._capacity_used = 0` on entering `"free"` (drop-off at the single holding point per medevac.md "Holding point: single for v1").
- `_make_status(state, order_id, coords)` returns `MedevacStatus` with live `capacity_used` + `capacity_max` for dashboard rendering.
- `_act(order)` logs an "extracting persons at ..." line for demo narration, then sleeps for `action_duration_s`.
- `build_agent(mesh) -> MedevacAgent` returns the agent so tests can call `agent.start()` / `agent.stop()` themselves.
- `_main()` mirrors heli.py / ffunit.py shape, runnable via `python -m demos.wildfire.fleet.medevac`.

### `demos/wildfire/fleet/_action.py` (small additive change)

Added `_on_transition(*, state, order_id)` hook to `ActionFleetAgent`. Default no-op; called by `_writer_loop` immediately after each transition is applied to in-memory state but **before** the status publish, so subclass-mutated counters (medevac's `capacity_used`) appear in the same status frame as the transition that triggered them.

Heli + ffunit do not override the hook; the default no-op preserves their behaviour. All 47 prior action-fleet unit tests stay green.

### `tests/wildfire/unit/test_medevac.py` (23 tests)

- 4 module-shape tests (class exists, build_agent exists, subclasses ActionFleetAgent, `_main` is async).
- 9 source-text invariant tests (registers `ground.medevac`, no `heartbeat_loop`, no `subject_source`/`kv_source`, no `bucket=`/`prefix=`/`model=`, no `asyncio.Lock`/`try_cas`/`cas()`, uses `reason="capacity"`).
- 6 dropped-artefact gates (parametrised over `ThermalGrid`, `FireSpawn`, etc).
- 4 live `AgentMesh.local()` boot tests:
  - `test_medevac_dispatch_returns_accepted_ack` — `mesh.call("ground.medevac", DispatchOrder(...))` returns accepted ack within 1 s.
  - `test_medevac_publishes_status_on_dispatch` — status pubsub fires on `mesh.action.medevac.{id}.status`; payload has `capacity_used` + `capacity_max=4`.
  - `test_medevac_rejects_when_over_capacity` — pre-set `agent._capacity_used=3`, dispatch with `persons_estimated=2`, assert `accepted=False`, `reason="capacity"`.
  - `test_medevac_rejects_concurrent_dispatch_with_busy` — first dispatch accepted, second mid-flight returns `reason="busy"` (inherits base behaviour).

## How the capacity rejection works

The medevac handler is layered on top of the base handler. The plan suggested overriding `_simulate` or wiring a hook; the chosen path uses **both**:

1. **Pre-base capacity check in `handle()`** — runs before `super().handle()` so an over-capacity request is rejected without touching `_state` / `_sim_task` / `_writer_queue`. `instance_id` is still reported so the operator knows which unit declined.

2. **Post-transition counter mutation via `_on_transition`** — the writer task calls `_on_transition` after applying each transition. Medevac increments on `state == "acting"` (extraction starts, persons aboard) and resets on `state == "free"` (returned to base, dropped off). Synchronous; runs inside the single-writer task; no concurrency.

The two pieces compose cleanly: the pre-base check uses the counter that the post-transition mutator maintains. No locks, no CAS on the agent's own record (D-41 single-writer preserved).

## Plan deviations

### `_on_transition` hook addition (deviation Rule 2 — missing critical functionality)

Plan 02-03's `<action>` block names this option ("add a `_on_transition(self, new_state, order)` hook to ActionFleetAgent in 02-02 if not already present"). 02-02 did not add it. I added the hook in this plan as the cleanest path (preserves base reuse; subclass override stays readable). Default no-op so heli/ffunit are unaffected. Committed separately (`a4082f3`) so the additive base-class change has a clear history.

Hook signature: `_on_transition(self, *, state: ActionState, order_id: str | None) -> None`. Called from `_writer_loop` after `self._coords` / `self._state` are mutated and before `_safe_kv_put` + `_safe_publish_status`. Subclass invariants:
- Synchronous (writer task runs in a single coroutine; no scheduling).
- Same writer-task context as KV writes; mutations are serialised by definition.
- Status published in the same tick reflects the mutation (capacity_used appears live in the MedevacStatus frame).

### `build_agent` not back-ported to heli/ffunit (deviation Rule 4 — out-of-scope)

The plan suggested optionally refactoring `test_heli` / `test_ffunit` to use `build_agent`. Heli and ffunit already inline `agent = HeliAgent(mesh)` + `agent.register_handler(...)` in their `_main()` and tests, which mirrors what `test_medevac` does. The marginal value of churning two unrelated test files is negative (more diff, no behaviour change); skipped per Rule 4 scope boundary.

If a future plan introduces a registry / multi-agent boot helper that benefits from a uniform `build_agent`, refactor heli + ffunit then.

## Verification

```
$ uv run pytest tests/wildfire/unit/test_medevac.py -v
... 23 passed in 0.57s

$ uv run pytest tests/wildfire/unit -x -q
... 228 passed in 14.98s
```

Plan invariants (all pass):
- `grep -c "class MedevacAgent(ActionFleetAgent)" demos/wildfire/fleet/medevac.py` -> 1
- `grep -c 'name="ground.medevac"' demos/wildfire/fleet/medevac.py` -> 1
- `grep -c "MedevacStatus(" demos/wildfire/fleet/medevac.py` -> 1
- `grep -c 'reason="capacity"' demos/wildfire/fleet/medevac.py` -> 2 (handler + module docstring)
- `grep -E "subject_source\(|kv_source\(" demos/wildfire/fleet/medevac.py` -> no matches
- `grep -E "bucket=|prefix=|model=" demos/wildfire/fleet/medevac.py | grep -v '^#'` -> no matches
- `grep -E "ThermalGrid|FireSpawn|FireSuppress|mesh.environment.thermal|mesh.fire.spawn|mesh.fire.suppress" demos/wildfire/fleet/medevac.py` -> no matches
- `grep -E "asyncio\.Lock|try_cas|cas\(" demos/wildfire/fleet/medevac.py` -> no matches
- `uv run python -c "from demos.wildfire.fleet.medevac import _main; assert callable(_main)"` -> exit 0

## Notes for plan 02-09 (orchestrator)

- Spawn `MEDEVAC_COUNT = 3` instances of `python -m demos.wildfire.fleet.medevac` (the constant lives at `demos.wildfire.core.config.MEDEVAC_COUNT`).
- Three instances share queue group `q.ground.medevac` automatically per `src/openagentmesh/_mesh.py:_subscribe_agent` (one catalog name -> one queue group). No per-instance config needed.
- Optional but recommended: stagger startup by ~100ms so the three writers don't write the same `wildfire.fleet.ground.medevac.{instance_id}` second-stamp simultaneously (tiny KV write contention; cosmetic only because instance_id keys are unique).

## TDD Gate Compliance

| Gate | Commit | Notes |
|------|--------|-------|
| RED | `8c97e81` test(02-03): add failing tests for ground.medevac agent | 23 tests in test_medevac.py, all skipped via importorskip until medevac.py exists. |
| HOOK | `a4082f3` feat(02-03): add ActionFleetAgent._on_transition subclass hook (D-46) | Additive base-class change. Existing 47 action-fleet tests stay green. |
| GREEN | `18a48f9` feat(02-03): MedevacAgent with capacity rejection (SCN-07, D-46) | All 23 medevac tests pass; full wildfire unit suite 228/228 green. |

## Self-Check: PASSED

- File `demos/wildfire/fleet/medevac.py`: FOUND
- File `tests/wildfire/unit/test_medevac.py`: FOUND
- File `demos/wildfire/fleet/_action.py` (modified): FOUND
- Commit `8c97e81` (test): FOUND
- Commit `a4082f3` (hook): FOUND
- Commit `18a48f9` (feat): FOUND
- Tests: 23/23 medevac, 228/228 wildfire unit suite green
