---
phase: 01-detection-foundation
plan: 01
subsystem: foundation
tags: [pydantic, contracts, kv, wildfire-demo, python, packaging]

# Dependency graph
requires: []
provides:
  - Importable demos package skeleton (demos / demos.wildfire / demos.wildfire.core)
  - Phase 1 frozen contracts module (Coords, CellState, DetectionRecord, SurveyResult, FleetMemberState, DispatchOrder, DispatchAck, HeliStatus, FFUnitStatus + DetectionState/ActionState/FleetMemberState_StateLit Literal aliases)
  - Canonical cell-index encoding + KV namespace helpers (cell_indices, cell_key, cell_center, fleet_key, detection_key + WILDFIRE/CELL/DETECTION/FLEET prefix constants and CELL_SIZE_KM/GRID_DIM)
  - Phase 1 hardcoded configuration constants (HQ, fleet sizes, heartbeat cadence, fire-sim/UAV/drone tunables)
  - Pytest plumbing for the gitignored demos/ package (tests/wildfire/conftest.py)
affects:
  - 01-02-PLAN (orchestrator) — imports core/config, core/keys
  - 01-03-PLAN (spawn CLI) — imports cell_key, cell_center, Coords, CellState
  - 01-04-PLAN (fire-sim) — imports CellState, CELL_PREFIX, FIRE_SIM_*
  - 01-05-PLAN (UAV) — imports CellState, DetectionRecord, UAV_*, detection_key
  - 01-06-PLAN (drone fleet) — imports DetectionRecord, SurveyResult, FleetMemberState, fleet_key, DRONE_*
  - 01-07-PLAN (heli fleet) — imports DispatchOrder/Ack, HeliStatus, FleetMemberState, fleet_key
  - 01-08-PLAN (ffunit fleet) — imports DispatchOrder/Ack, FFUnitStatus, FleetMemberState, fleet_key
  - 01-09-PLAN (unit tests), 01-10-PLAN (integration test) — imports across the board
  - 01-11-PLAN (admin UI integration) — imports FLEET_PREFIX

# Tech tracking
tech-stack:
  added: []  # No new dependencies; pydantic v2 already in pyproject.toml
  patterns:
    - "Single canonical helper for cell-index encoding (one-file change for grid resolution tweaks)"
    - "Single canonical config module for tunables (no magic numbers in agent modules)"
    - "Path-importable demos/ sibling to src/ (gitignored from wheel via D-02; kept editable)"
    - "tests/wildfire/conftest.py inserts worktree root on sys.path so the gitignored demos/ resolves under pytest"

key-files:
  created:
    - demos/__init__.py
    - demos/wildfire/__init__.py
    - demos/wildfire/core/__init__.py
    - demos/wildfire/core/contracts.py
    - demos/wildfire/core/keys.py
    - demos/wildfire/core/config.py
    - tests/wildfire/conftest.py
    - tests/wildfire/unit/test_contracts.py
    - tests/wildfire/unit/test_keys.py
    - tests/wildfire/unit/test_config.py
  modified: []

key-decisions:
  - "Docstring rephrased to avoid bare 'ThermalGrid'/'FireSpawn'/'FireSuppress' strings so the plan's grep-no-match acceptance gate passes (the dropped contracts are mentioned via 'three pubsub-era world-state contracts' instead)"
  - "Added tests/wildfire/conftest.py to insert the worktree root onto sys.path; alternative (pyproject.toml pythonpath) was rejected as a broader change with no functional benefit"
  - "Wrote per-task unit tests for keys (12) and config (6) in addition to the contracts TDD cycle so downstream regressions to grid encoding or canonical tunables are caught immediately"

patterns-established:
  - "Pure-helper module: keys.py imports only from contracts.py (no SDK imports, no I/O)"
  - "Module docstring cites canonical sources (km/specs + 01-CONTEXT.md amendments) so future maintainers know where to update first"

requirements-completed: [SCN-01, SCN-03, SCN-04, SCN-05, SCN-06, SCN-13]  # foundation requirements; later plans exercise the actual scenario flow

# Metrics
duration: 6min
completed: 2026-05-09
---

# Phase 1 Plan 1: Detection Foundation - Frozen contracts, KV keys, and tunables Summary

**Phase 1 frozen contracts (Coords, CellState, DetectionRecord, SurveyResult, FleetMemberState, DispatchOrder, DispatchAck, HeliStatus, FFUnitStatus) plus canonical cell-index encoding and the demo's Phase 1 tunables landed as the foundation that every other Phase 1 plan imports.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-09T00:02:11Z
- **Completed:** 2026-05-09T00:08:45Z
- **Tasks:** 4 (1 TDD cycle = 2 commits, plus task-1, task-3, task-4 single commits)
- **Files modified:** 10 (all created)

## Accomplishments

- `demos/` package importable as a sibling to `src/` (path-importable from worktree root only; not in the published wheel per D-02)
- `demos/wildfire/core/contracts.py` ships the verbatim Phase 1 inventory from the amended `km/specs/wildfire/contracts.md` (no `ThermalGrid` / `FireSpawn` / `FireSuppress` per A-07)
- `demos/wildfire/core/keys.py` is the single source of truth for the 200 m world-grid encoding (per A-03) and the `wildfire.*` KV namespaces (per A-08): `cell_indices`, `cell_key`, `cell_center`, `fleet_key`, `detection_key` + `WILDFIRE_PREFIX` / `CELL_PREFIX` / `DETECTION_PREFIX` / `FLEET_PREFIX` / `CELL_SIZE_KM` / `GRID_DIM`
- `demos/wildfire/core/config.py` ships the Phase 1 dial: HQ at origin, fleet sizes (1 uav / 5 drones / 1 heli / 3 ffunits), 1 Hz heartbeat with 3 s reader-side staleness cutoff, fire-sim tunables (1 Hz tick, 25 / 800 °C ambient / max, 5 °C material-change threshold, 4 °C/tick decay, 0.10 spread coefficient), UAV sensor model (5 km footprint, 100 °C threshold, 0.5 confidence floor, 100 m × 30 s dedup bucket), drone speed 0.4 km/s + 5 s survey duration
- 26 unit tests pin all of the above so a downstream tweak that breaks the encoding, a contract shape, or a tunable fails fast

## Contract inventory landed

Module: `demos.wildfire.core.contracts`

| Symbol                       | Kind          | Notes                                                   |
| ---------------------------- | ------------- | ------------------------------------------------------- |
| `Coords`                     | BaseModel     | x/y floats with `Field(ge=-5.0, le=5.0)`                |
| `CellState`                  | BaseModel     | KV value at `wildfire.world.cell.<x_idx>.<y_idx>`       |
| `DetectionRecord`            | BaseModel     | KV value at `wildfire.detection.{id}`; state widened to `DetectionState \| str` |
| `SurveyResult`               | BaseModel     | nested under `DetectionRecord.survey`                   |
| `FleetMemberState`           | BaseModel     | KV value at `wildfire.fleet.{zone}.{type}.{id}`         |
| `DispatchOrder`              | BaseModel     | request side of action fleet dispatch                   |
| `DispatchAck`                | BaseModel     | reply side of action fleet dispatch                     |
| `HeliStatus`                 | BaseModel     | heli pubsub status payload                              |
| `FFUnitStatus`               | BaseModel     | ffunit pubsub status payload                            |
| `ActionState`                | Literal alias | `free / dispatched / en_route / on_site / acting / returning` |
| `FleetMemberState_StateLit`  | Literal alias | `free / busy / offline`                                 |
| `DetectionState`             | Literal alias | `pending / assigned / surveyed`                         |

Out of Phase 1 (deliberately excluded; will land alongside owning agents in later phases): `IncidentBriefing`, `IncidentState`, `TaskCommand`, `TaskTranslateRequest`, `Narrative`, `SwarmStats`, `MedevacStatus`, `ChaosKill`, `FirefighterIntent`. Out of the demo entirely (per A-07): `ThermalGrid`, `FireSpawn`, `FireSuppress`.

## Cell-encoding helper signatures

```python
# demos/wildfire/core/keys.py

WILDFIRE_PREFIX = "wildfire"
CELL_PREFIX     = "wildfire.world.cell"
DETECTION_PREFIX = "wildfire.detection"
FLEET_PREFIX    = "wildfire.fleet"
CELL_SIZE_KM    = 0.2
GRID_DIM        = 50

def cell_indices(x: float, y: float) -> tuple[int, int]
    # int((x + 5.0) / 0.2) with edge clamp +5.0 -> 49 (per A-03);
    # defensive negative clamp to 0.

def cell_center(x_idx: int, y_idx: int) -> Coords
    # Inverse: returns the snapped center of cell (x_idx, y_idx).
    # cell_center(25, 25) == Coords(x=0.1, y=0.1).

def cell_key(x: float, y: float) -> str
    # f"{CELL_PREFIX}.{x_idx}.{y_idx}"

def fleet_key(zone: str, fleet_type: str, instance_id: str) -> str
    # f"{FLEET_PREFIX}.{zone}.{fleet_type}.{instance_id}"

def detection_key(detection_id: str) -> str
    # f"{DETECTION_PREFIX}.{detection_id}"
```

## Full list of config constants

Module: `demos.wildfire.core.config` (importable so downstream plans can grep for what's available):

| Name                          | Value           | Source                                          |
| ----------------------------- | --------------- | ----------------------------------------------- |
| `HQ`                          | `Coords(x=0.0, y=0.0)` | D-11                                     |
| `UAV_COUNT`                   | `1`             | D-08                                            |
| `DRONE_COUNT`                 | `5`             | D-08                                            |
| `HELI_COUNT`                  | `1`             | D-08 (can bump to 2)                            |
| `FFUNIT_COUNT`                | `3`             | D-08                                            |
| `HEARTBEAT_INTERVAL_S`        | `1.0`           | D-09                                            |
| `LIVENESS_STALENESS_S`        | `3.0`           | D-10                                            |
| `FIRE_SIM_TICK_INTERVAL_S`    | `1.0`           | km/specs/wildfire/fire-sim.md                   |
| `FIRE_SIM_AMBIENT_C`          | `25.0`          | km/specs/wildfire/fire-sim.md                   |
| `FIRE_SIM_MAX_C`              | `800.0`         | km/specs/wildfire/fire-sim.md                   |
| `FIRE_SIM_MATERIAL_DELTA_C`   | `5.0`           | km/specs/wildfire/fire-sim.md                   |
| `FIRE_SIM_DECAY_PER_TICK_C`   | `4.0`           | km/specs/wildfire/fire-sim.md                   |
| `FIRE_SIM_SPREAD_DIFFUSION`   | `0.10`          | km/specs/wildfire/fire-sim.md                   |
| `UAV_FOOTPRINT_RADIUS_KM`     | `5.0`           | km/specs/wildfire/uav.md                        |
| `UAV_TEMP_THRESHOLD_C`        | `100.0`         | km/specs/wildfire/uav.md                        |
| `UAV_CONFIDENCE_FLOOR`        | `0.5`           | km/specs/wildfire/uav.md                        |
| `UAV_DEDUP_GRID_KM`           | `0.1`           | km/specs/wildfire/uav.md                        |
| `UAV_DEDUP_WINDOW_S`          | `30.0`          | km/specs/wildfire/uav.md                        |
| `DRONE_SPEED_KM_S`            | `0.4`           | km/specs/wildfire/drone.md                      |
| `DRONE_SURVEY_DURATION_S`     | `5.0`           | km/specs/wildfire/drone.md                      |

## Task Commits

Each task was committed atomically:

1. **Task 1: Create demos package skeleton** — `c57baf3` (feat)
2. **Task 2: Phase 1 frozen contracts (TDD RED)** — `d6770b4` (test)
3. **Task 2: Phase 1 frozen contracts (TDD GREEN)** — `5a8513e` (feat)
4. **Task 3: Cell key encoding + KV namespace helpers** — `32042a3` (feat)
5. **Task 4: HQ + fleet sizes + tunables** — `2ec6f16` (feat)

_Note: Task 2 has two commits per the plan's `tdd="true"` directive (RED then GREEN). REFACTOR was unnecessary — the contracts module is a verbatim transcription of the spec, no cleanup needed._

## Files Created/Modified

- `demos/__init__.py` — empty (package marker)
- `demos/wildfire/__init__.py` — empty (package marker)
- `demos/wildfire/core/__init__.py` — empty (package marker)
- `demos/wildfire/core/contracts.py` — Phase 1 frozen Pydantic models + Literal aliases
- `demos/wildfire/core/keys.py` — canonical cell encoding + KV namespace helpers (pure)
- `demos/wildfire/core/config.py` — Phase 1 hardcoded constants (HQ + fleet sizes + tunables)
- `tests/wildfire/conftest.py` — sys.path insertion for the gitignored `demos/` package
- `tests/wildfire/unit/test_contracts.py` — 8 contract behaviour tests
- `tests/wildfire/unit/test_keys.py` — 12 encoding + namespace tests
- `tests/wildfire/unit/test_config.py` — 6 constant-value smoke tests

`pyproject.toml` was deliberately NOT modified (per Task 1 acceptance criterion + D-02): `demos/` stays out of the published wheel.

## Decisions Made

- **Docstring phrasing for the dropped contracts** — the plan's grep gate (`grep -E "ThermalGrid|FireSpawn|FireSuppress" demos/wildfire/core/contracts.py` returns no matches) initially failed because the original docstring named the dropped contracts as historical context. Rephrased to "the three pubsub-era world-state contracts (see the spec file for their names)" to keep the documentation pointer without breaking the gate. The spec file (`km/specs/wildfire/contracts.md`) still names them in its amendment note.
- **Tests/wildfire/conftest.py vs. pyproject.toml pythonpath** — chose the conftest because it scopes the path injection to the wildfire test tree only and avoids touching pyproject (Task 1's "do NOT add demos/ to pyproject.toml" rule was specifically about `[project] packages`, but the conservative choice is fewer pyproject edits).
- **Ruff isort fix on contracts.py** — accepted the `--fix` blank-line removal between docstring + imports (purely cosmetic; tests still green).
- **Per-task unit tests beyond the TDD requirement** — the plan only mandated TDD for Task 2 (contracts). Added unit tests for `keys.py` (Task 3) and `config.py` (Task 4) anyway since they pin the canonical values that downstream plans assume; cheap insurance against silent regressions.

## Deviations from Plan

None of substance — plan executed exactly as written. The two minor adjustments (rephrased docstring, added conftest for pytest path) are documented in **Decisions Made** above; both were within the spirit of the plan rather than departures from it.

## Issues Encountered

- **One pre-existing flaky test** (`tests/test_publish.py::TestPublishValidation::test_wildcard_subject_rejected_star`) failed on `bind: address already in use` during the regression-check run (parallel embedded NATS port collision). Reran in isolation: passed. Out of scope for this plan; not fixed.

## Next Phase Readiness

- All Phase 1 plans (01-02 through 01-11) can now `from demos.wildfire.core import ...` for contracts, key helpers, and tunables
- 26 wildfire-suite tests pass; broader OAM test suite unaffected by these changes
- Plan acceptance gates: all green
  - `uv run python -c "import demos.wildfire.core.contracts, demos.wildfire.core.config, demos.wildfire.core.keys; print('ok')"` → ok (exit 0)
  - `grep -E "ThermalGrid|FireSpawn|FireSuppress" demos/wildfire/core/` → no matches (exit 1)
  - `uv run ruff check demos/wildfire/core/` → All checks passed

## Self-Check

- Files claimed: all 10 verified present (3 `__init__.py`, 3 core modules, 1 conftest, 3 test modules)
- Commits claimed: c57baf3, d6770b4, 5a8513e, 32042a3, 2ec6f16 — all in `git log`
- Verification gates: all 3 green per the run logged above

## Self-Check: PASSED

---
*Phase: 01-detection-foundation*
*Completed: 2026-05-09*
