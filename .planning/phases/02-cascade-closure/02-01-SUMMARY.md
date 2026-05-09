---
phase: 02-cascade-closure
plan: 01
subsystem: wildfire/core
tags: [contracts, config, foundation, medevac, action-fleet, dashboard, magnitudes]
requires: [01-detection-foundation/01-01]  # Phase 1 contracts module + config module
provides:
  - "MedevacStatus Pydantic model in demos/wildfire/core/contracts.py"
  - "Per-fleet speed and action duration constants (HELI_*, MEDEVAC_*, FFUNIT_*)"
  - "Dashboard click-spawn magnitudes (SPAWN_MAGNITUDE_SMALL/MEDIUM/LARGE)"
  - "MEDEVAC_COUNT (3), MEDEVAC_CAPACITY_MAX (4), DASHBOARD_PORT (8081)"
affects:
  - "All Wave 2 plans (02-02 ActionFleetAgent base, 02-03 medevac handler, 02-05 dashboard, 02-09 orchestrator) import from these two modules"
tech_stack_added: []  # pure Pydantic + module-level constants; no new deps
patterns:
  - "Verbatim port from km/specs/wildfire/contracts.md keeps the spec the single source of truth"
  - "Module-level constant block per concern, named to surface the consumer (HELI_*, MEDEVAC_*, etc.)"
key_files_created: []  # both files already existed
key_files_modified:
  - "demos/wildfire/core/contracts.py"
  - "demos/wildfire/core/config.py"
  - "tests/wildfire/unit/test_contracts.py"
  - "tests/wildfire/unit/test_config.py"
decisions:
  - "Speed ordering enforced via test, not just convention (test_speed_ordering_invariant)"
  - "MEDEVAC_CAPACITY_MAX added alongside MEDEVAC_COUNT to mirror MedevacStatus.capacity_max default; downstream consumers can import either"
metrics:
  duration_seconds: 183
  tasks_completed: 2
  files_modified: 4
  tests_added: 13  # 6 MedevacStatus + 7 Phase 2 config
  commits: 3
completed_date: "2026-05-09"
---

# Phase 02 Plan 01: Phase 2 contracts + config tunables Summary

Added the `MedevacStatus` Pydantic model and the Phase 2 fleet + dashboard
configuration constants that every subsequent Wave 2 plan imports from. Two
files modified (`demos/wildfire/core/contracts.py`, `demos/wildfire/core/config.py`)
plus their unit-test files. Phase 1 contracts and constants stay byte-for-byte
unchanged; the full 152-test Phase 1 unit suite passes.

## What landed

### MedevacStatus contract (Task 1)

Verbatim port of the `MedevacStatus` block from
`km/specs/wildfire/contracts.md`. Lands alongside `HeliStatus` and
`FFUnitStatus` in the action-fleet status feeds section so all three
share the `ActionState` literal.

```python
class MedevacStatus(BaseModel):
    instance_id: str
    order_id: str | None
    state: ActionState
    coords: Coords
    capacity_used: int           # current persons aboard
    capacity_max: int = 4
    timestamp: float
```

No new imports needed (`BaseModel`, `Coords`, `ActionState` already in scope per D-28).

### Phase 2 config constants (Task 2)

Appended to `demos/wildfire/core/config.py` (no Phase 1 constant edited):

| Constant                     | Value | Purpose                                              |
|------------------------------|-------|------------------------------------------------------|
| `MEDEVAC_COUNT`              | 3     | Orchestrator spawns this many medevac instances     |
| `HELI_SPEED_KM_S`            | 0.6   | Water bomber, fastest fleet                          |
| `HELI_ACTION_DURATION_S`     | 5.0   | On-site water drop                                   |
| `MEDEVAC_SPEED_KM_S`         | 0.3   | Ground vehicle, mid-pace                             |
| `MEDEVAC_ACTION_DURATION_S`  | 6.0   | On-site extraction                                   |
| `MEDEVAC_CAPACITY_MAX`       | 4     | Mirrors MedevacStatus.capacity_max default           |
| `FFUNIT_SPEED_KM_S`          | 0.15  | Ground suppression unit, slowest                     |
| `FFUNIT_ACTION_DURATION_S`   | 8.0   | On-site suppression                                  |
| `SPAWN_MAGNITUDE_SMALL`      | 200.0 | Tier 1 dashboard click magnitude                     |
| `SPAWN_MAGNITUDE_MEDIUM`     | 500.0 | Tier 2 dashboard click magnitude                     |
| `SPAWN_MAGNITUDE_LARGE`      | 800.0 | Tier 3 dashboard click magnitude                     |
| `DASHBOARD_PORT`             | 8081  | D-39, auto-fallback to next free port if occupied   |

**Speed ordering invariant:** `HELI_SPEED_KM_S > MEDEVAC_SPEED_KM_S > FFUNIT_SPEED_KM_S`.
Encoded as a unit test (`test_speed_ordering_invariant`) so accidental tweaks during
later plan tuning produce a red test, not a silently inverted ETA.

**Magnitude band invariant:** All three spawn magnitudes stay inside the
`CellState` `[25, 800]` expected band (matches `FIRE_SIM_AMBIENT_C` and
`FIRE_SIM_MAX_C`). Encoded as `test_magnitudes_within_cellstate_band`.

## Tests added

`tests/wildfire/unit/test_contracts.py` (6 new):
- `test_medevac_status_importable`
- `test_medevac_status_constructs_with_documented_fields`
- `test_medevac_status_capacity_max_default_four`
- `test_medevac_status_order_id_accepts_none`
- `test_medevac_status_accepts_every_action_state`
- `test_medevac_status_rejects_invalid_state`

`tests/wildfire/unit/test_config.py` (7 new):
- `test_phase2_constants_importable`
- `test_speed_ordering_invariant`
- `test_magnitude_tiers_ordered`
- `test_magnitudes_within_cellstate_band`
- `test_medevac_count_default_three`
- `test_medevac_capacity_max_matches_contract_default`
- `test_action_durations_positive`
- `test_dashboard_port_default`

Plan listed 6 explicit Phase 2 config tests; 8 land here because two extra
positive-value sanity checks (`test_action_durations_positive`,
`test_medevac_capacity_max_matches_contract_default`) were cheap to add and
catch regression classes the explicit list missed (e.g., a future zero
duration silently breaking the ETA formula).

## Verification

- `uv run pytest tests/wildfire/unit/test_contracts.py tests/wildfire/unit/test_config.py -x -q` -> 28 passed
- `uv run pytest tests/wildfire/unit -x -q` (whole Phase 1 + new) -> 152 passed
- `grep -E "ThermalGrid|FireSpawn|FireSuppress|mesh.environment.thermal|mesh.fire.spawn|mesh.fire.suppress" demos/wildfire/core/contracts.py demos/wildfire/core/config.py | grep -v '^#'` -> no matches (A-07/A-08, pure-KV pivot)
- `grep -E "bucket=|prefix=|model=" demos/wildfire/core/contracts.py demos/wildfire/core/config.py | grep -v '^#'` -> no matches (A-09 negative gate)
- `grep -c "class MedevacStatus" demos/wildfire/core/contracts.py` -> 1
- `grep -c "capacity_max: int = 4" demos/wildfire/core/contracts.py` -> 1

Phase 1 contracts (`Coords`, `CellState`, `DetectionRecord`, `SurveyResult`,
`FleetMemberState`, `DispatchOrder`, `DispatchAck`, `HeliStatus`,
`FFUnitStatus`) untouched. Phase 1 config (HQ, fleet sizes, heartbeat,
fire-sim, UAV, drone) untouched.

## Decisions Made

- **Test speed ordering as an invariant, not a comment.** A later plan
  could fiddle with `HELI_SPEED_KM_S` to tune the cascade; if it accidentally
  drops below `MEDEVAC_SPEED_KM_S`, ETA logic in `ActionFleetAgent` (plan 02-02)
  silently produces nonsense. Pinning the inequality in a unit test makes the
  failure loud.
- **Pin `MEDEVAC_CAPACITY_MAX` in config beside `MEDEVAC_COUNT`.** The
  contract defaults `capacity_max` to 4, so the obvious option was "don't
  duplicate". Chose to add the constant anyway because plan 02-03 (medevac
  handler) and plan 02-09 (orchestrator) both need to instantiate
  `MedevacStatus(capacity_used=..., capacity_max=...)` explicitly when
  populating intermediate state. Letting them import the constant keeps a
  single source for the cap.

## Deviations from Plan

### Auto-fixed Issues

None: no Rule 1/2/3 fixes triggered. The plan was a pure additive
"declare types and constants" task.

### Plan deviations (informational)

1. **Two extra config sanity tests added.**
   - The plan listed 6 explicit Phase 2 config tests; the implementation
     added 8. The two extras (`test_action_durations_positive`,
     `test_medevac_capacity_max_matches_contract_default`) are cheap and
     catch regression classes the explicit list missed.
   - Net effect: stricter test coverage, no behavior change.

2. **Module docstrings updated to mention Phase 2.**
   - The plan said "no Phase 1 constant edited" and that holds: only the
     module-level docstrings of `contracts.py` and `config.py` were touched
     to mention the Phase 2 additions and decision sources. No code or
     constant was modified. This keeps "where do these constants come from?"
     answerable without re-reading the plan.

## Commits

| Stage  | Hash    | Message                                              |
|--------|---------|------------------------------------------------------|
| RED    | fb9b085 | test(02-01): add failing tests for MedevacStatus contract |
| GREEN  | 2653785 | feat(02-01): add MedevacStatus contract              |
| Task 2 | 8532b26 | feat(02-01): add Phase 2 fleet + dashboard tunables to config.py |

Task 1 followed strict TDD: RED commit (failing test), GREEN commit
(minimal implementation, all tests pass). Task 2 was pure additive
constants so a single feat commit covers both the implementation and its
tests.

## Self-Check: PASSED

- `demos/wildfire/core/contracts.py` exists, contains `class MedevacStatus`
- `demos/wildfire/core/config.py` exists, contains `MEDEVAC_COUNT`,
  `SPAWN_MAGNITUDE_LARGE`, `DASHBOARD_PORT`
- `tests/wildfire/unit/test_contracts.py` and `test_config.py` exist
- All three commits (`fb9b085`, `2653785`, `8532b26`) present in git log
- Full unit suite (152 tests) passes
- Negative gates (no `bucket=|prefix=|model=`, no `ThermalGrid|FireSpawn|FireSuppress`) clean
