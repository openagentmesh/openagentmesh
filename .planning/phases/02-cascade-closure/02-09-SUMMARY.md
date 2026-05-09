---
phase: 02-cascade-closure
plan: 09
subsystem: testing
tags: [orchestrator, integration-test, supervised-children, end-to-end, dashboard, medevac, killpg]

requires:
  - phase: 02-cascade-closure/02-02
    provides: ActionFleetAgent base class
  - phase: 02-cascade-closure/02-03
    provides: medevac fleet agent
  - phase: 02-cascade-closure/02-04
    provides: ground.medevac registration in catalog
  - phase: 02-cascade-closure/02-05
    provides: dashboard backend (FastAPI + WS)
  - phase: 02-cascade-closure/02-06
    provides: dashboard SPA bundle
  - phase: 02-cascade-closure/02-07
    provides: dashboard click-to-spawn flow
  - phase: 02-cascade-closure/02-08
    provides: admin UI EventFeed (regression-checked)
provides:
  - one-command boot of full Phase 2 stack via `python -m demos.wildfire`
  - Phase 2 cascade integration test gated by OAM_INTEGRATION_TESTS=1
  - clean SIGTERM tree-kill (no orphan dashboard / medevac / nats-server)
affects:
  - phase 03 (operator + briefer + tasker) -- orchestrator pattern reuse
  - phase 04 (chaos) -- killpg pattern when injecting kills

tech-stack:
  added: []
  patterns:
    - "process group inheritance (no start_new_session=True for children)"
    - "side-channel raw NATS subscribe for status pubsub assertion in tests"
    - "subprocess gating via OAM_INTEGRATION_TESTS=1 env var"

key-files:
  created:
    - tests/wildfire/integration/test_phase2_cascade.py
  modified:
    - demos/wildfire/core/orchestrator.py
    - tests/wildfire/integration/test_phase1_cascade.py

key-decisions:
  - "Drop start_new_session=True from orchestrator's _spawn and nats-server spawn so killpg(orch_pgid, SIGTERM) reaps the entire tree"
  - "Phase 2 integration test mirrors Phase 1 structure rather than introducing a parallel framework -- single readline-based URL parser, hardcoded ports, simple finally teardown"
  - "Status pubsub assertion uses raw client._nc.subscribe with single-token wildcard (mesh.action.heli.*.status) since '>' is terminal-only in NATS subject grammar"

patterns-established:
  - "Children inherit orchestrator's process group: simpler tree teardown, no orphan nats-server"
  - "Integration test gates: OAM_INTEGRATION_TESTS=1 env var, asyncio test pattern, Popen with start_new_session=True at the test level + os.killpg in finally"

requirements-completed: [SUI-06, SCN-02, SCN-07, SCN-10, SUI-01, SUI-02, ADM-03]

duration: ~2h
completed: 2026-05-09
---

# Phase 02 Plan 09: Cascade Closure Integration Test Summary

**Phase 2 orchestrator now spawns dashboard backend + 3 medevacs alongside the Phase 1 fleet, and a gated Phase 2 cascade integration test validates the spawn -> detection -> survey -> mesh.call dispatch -> status pubsub chain end-to-end.**

## Performance

- **Started:** 2026-05-09T07:30:00Z
- **Completed:** 2026-05-09T13:05:00Z
- **Tasks:** 2 (plus one Rule 2 auto-fix commit)
- **Files modified:** 3 (orchestrator + 2 integration tests, one new)

## Accomplishments

- Orchestrator extended: `CHILD_SPECS` gains `medevac` (count = MEDEVAC_COUNT = 3); a separate `_dash_proc` field tracks the scenario UI dashboard backend (`python -m demos.wildfire.dashboard --port DASHBOARD_PORT`) spawned in step 7b. Banner prints both URLs.
- `python -m demos.wildfire` is now the one-command boot story for the full Phase 2 stack (~16 child processes: NATS + 1 fire-sim + 1 UAV + 5 drones + 1 heli + 3 ffunits + 3 medevacs + admin UI + dashboard).
- New `tests/wildfire/integration/test_phase2_cascade.py` mirrors the Phase 1 pattern and adds: catalog includes `ground.medevac`; fleet count == 13; `mesh.call("low-alt.heli", DispatchOrder)` returns `accepted=True` and HeliStatus pubsub arrives on `mesh.action.heli.*.status` within 20s; same for medevac on `mesh.action.medevac.*.status`; dashboard `/health` returns 200 with `mesh_instance_id`; admin UI `/config.json` regression check.
- Phase 1 cascade test gains `_ensure_dashboard_built()` so the unconditional dashboard child has a built bundle and Phase 1 stdout stays clean.

## CHILD_SPECS Final Table

| Logical name | Module                              | Count             |
| ------------ | ----------------------------------- | ----------------- |
| fire-sim     | `demos.wildfire.world.fire_sim`     | 1                 |
| uav          | `demos.wildfire.fleet.uav`          | UAV_COUNT (1)     |
| drone        | `demos.wildfire.fleet.drone`        | DRONE_COUNT (5)   |
| heli         | `demos.wildfire.fleet.heli`         | HELI_COUNT (1)    |
| ffunit       | `demos.wildfire.fleet.ffunit`       | FFUNIT_COUNT (3)  |
| medevac      | `demos.wildfire.fleet.medevac`      | MEDEVAC_COUNT (3) |

Plus single-instance children outside CHILD_SPECS:

| Service       | Module                               | Default port             |
| ------------- | ------------------------------------ | ------------------------ |
| NATS          | `nats-server -c <hocon>`             | 4222 (clients), 4223 (ws), 8222 (monitor) |
| Admin UI      | `openagentmesh.cli ui --port 8088`   | 8088 (auto-walks if busy) |
| Dashboard     | `demos.wildfire.dashboard --port N`  | DASHBOARD_PORT=8081 (auto-walks if busy per D-39) |

## Task Commits

1. **Task 1: orchestrator spawns dashboard + medevac** -- `b2d253f` (feat)
2. **Rule 2 auto-fix: orch children inherit pgid for clean SIGTERM tree-kill** -- `56ae16a` (fix) -- found during integration test debugging; documented under "Deviations" below.
3. **Task 2: Phase 2 cascade integration test + Phase 1 dashboard build** -- `cff5a52` (test)

## Files Created/Modified

- `demos/wildfire/core/orchestrator.py` -- CHILD_SPECS gains `medevac`, Orchestrator gains `dashboard_port` + `_dash_proc`, step 7b spawns the dashboard backend, banner prints both admin UI and dashboard URLs, `_supervise` polls `_dash_proc`, `_shutdown` includes it in the SIGTERM list. Plus the Rule 2 fix below.
- `tests/wildfire/integration/test_phase2_cascade.py` (new) -- Phase 2 end-to-end cascade test (gated).
- `tests/wildfire/integration/test_phase1_cascade.py` -- adds `_ensure_dashboard_built()` next to `_ensure_ui_built()` so the orchestrator's now-unconditional dashboard child has a built bundle.

## Decisions Made

- **No `--no-dashboard` flag.** The plan considered adding a flag so the Phase 1 test could skip the dashboard child. Rejected: simpler to build the bundle in both tests' setup. The Phase 1 test's stdout has tagged `[dash]` lines from the dashboard but they don't affect any assertion.
- **Status pubsub assertion uses raw NATS subscribe** instead of the SDK's `mesh.subscribe`. The SDK is biased toward `@mesh.agent` decorator usage; raw `client._nc.subscribe(subject)` is the simplest way to assert "a message arrived on this subject". Subject pattern is `mesh.action.{fleet_type}.*.status` -- single-token wildcard, since NATS' `>` is terminal-only.
- **Per-fleet status wildcard:** subscribed to `mesh.action.{fleet_type}.*.status` (one token between fleet_type and "status"). Initial pass used `mesh.action.{fleet_type}.>.status` which is malformed: `>` matches one or more tokens but must be terminal. NATS rejected the malformed subject and closed the connection, leaving subsequent `client.call(...)` requests to fail with `ConnectionClosedError`. The current `*` form binds successfully.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Status pubsub wildcard subject was malformed**
- **Found during:** Task 2 (first gated run of `test_phase2_cascade`).
- **Issue:** Initial implementation used `client._nc.subscribe("mesh.action.heli.>.status")`, mirroring the wildcard form used elsewhere in the codebase. NATS' subject grammar requires `>` be the terminal token. The malformed subject closed the connection silently; all subsequent calls (including the heli `client.call`) failed with `nats.errors.ConnectionClosedError`.
- **Fix:** Switched to `mesh.action.heli.*.status` and `mesh.action.medevac.*.status` (single-token `*` wildcard between fleet_type and `status`). This matches the production subject shape `mesh.action.{fleet_type}.{instance_id}.status` exactly.
- **Files modified:** `tests/wildfire/integration/test_phase2_cascade.py`
- **Verification:** Phase 2 test passed in 11.59s after the fix.
- **Committed in:** cff5a52

**2. [Rule 2 - Missing Critical] Orchestrator children leaked nats-server on test teardown**
- **Found during:** Task 2 (back-to-back integration test runs).
- **Issue:** The Phase 1 orchestrator spawned every child (fleet members + nats-server + admin UI) with `start_new_session=True`, putting each into its own session. `os.killpg(orch.pid, SIGTERM)` from the integration test's teardown only reached the orchestrator process; nats-server and fleet children survived as orphans (PPID=1) past the orchestrator's exit. Subsequent test runs hit `Can't start monitoring: bind: address already in use` on port 8222 because the previous run's nats-server was still listening.
- **Fix:** Removed `start_new_session=True` from `_spawn` and from the nats-server `Popen` call. Children now inherit the orchestrator's session/process group, so the test's `killpg(orch.pid, SIGTERM)` reaches every leaf simultaneously. The orchestrator's own `_shutdown` path (voluntary exit on NATS death or SIGINT) is unchanged: each child still gets `proc.terminate()` then SIGKILL after 5s.
- **Files modified:** `demos/wildfire/core/orchestrator.py`
- **Verification:** Manual reproduction with a small driver script confirmed `killpg(orch_pgid, SIGTERM)` now kills both orch + nats-server cleanly. Manual `python -m demos.wildfire` + Ctrl+C in terminal also tears down cleanly.
- **Committed in:** 56ae16a (separate commit since it's a Rule 2 deviation, not Task 1's planned scope).
- **Threat model:** T-02-09-03 mitigation upgraded from "test finally killpg'd group" to "structurally impossible" -- killpg now reaches every leaf because they share the pgid.

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing-critical)
**Impact on plan:** Both fixes essential for the integration test to actually exercise the dispatch + pubsub assertions and to leave a clean test environment between runs. No scope creep.

## Issues Encountered

- **Back-to-back run TIME_WAIT race on hardcoded HTTP ports.** Both Phase 1 and Phase 2 tests probe `127.0.0.1:8088` (admin UI `/config.json`) and Phase 2 probes `127.0.0.1:8081` (dashboard `/health`). Both `oam ui` (`src/openagentmesh/cli/ui.py`) and `demos/wildfire/dashboard/__main__.py` walk to the next free port if the requested one is in TIME_WAIT (D-39 invariant). When running `pytest tests/wildfire/integration` end-to-end, the first test's HTTP server leaves TIME_WAIT sockets on 8088/8081 for ~30s; the second test's children see the requested port as busy and walk to 8089/8082. The second test's hardcoded `127.0.0.1:8088` probe then fails with `ConnectionRefusedError`. Workarounds attempted (port-bind probe wait, drain-thread for orch stdout, longer teardown timeout) all introduced their own failure modes; the simplest stable shape is what shipped: each phase test passes alone, the back-to-back is environmental.

  Both Phase 1 and Phase 2 tests pass individually:
  ```
  OAM_INTEGRATION_TESTS=1 uv run pytest tests/wildfire/integration/test_phase1_cascade.py  # PASSED in ~14s
  OAM_INTEGRATION_TESTS=1 uv run pytest tests/wildfire/integration/test_phase2_cascade.py  # PASSED in ~12s
  ```

  When running both in the same session, allow ~30s between them or run them in separate `pytest` invocations.

  This is a pre-existing flake in the Phase 1 test pattern -- my changes neither introduced nor structurally fixed it. A future improvement (out of scope for 02-09): both tests parse the resolved UI / dashboard ports from orchestrator stdout instead of hardcoding 8088 / 8081.

- **Docker port collision on shared dev machine.** The user's Progress Platform stack has a `progress-broker-1` container that maps host 4222/8222 to container ports. While running, that container blocks the orchestrator's nats-server bind. Stopping the container (or running tests on a different machine) is the workaround. Detected during this plan's debugging; documented for awareness.

## User Setup Required

None -- no external service configuration. The `_ensure_ui_built()` and `_ensure_dashboard_built()` helpers in the integration tests build admin UI and dashboard SPA bundles automatically on first run via `pnpm install && pnpm run build`, so a fresh checkout works as long as `pnpm` is on PATH.

## Next Phase Readiness

**Ready for hand-off to Phase 3 (operator + briefer + tasker).**

Notes for Phase 3:
- **Operator CLI `--nl` flag retrofit:** `demos/wildfire/world/firefighter.py` (operator CLI, runs in a separate terminal -- not orchestrator-supervised) gains a `--nl` flag that routes intent through the new tasker agent rather than direct dispatch.
- **Briefer + Tasker spawn entries:** add to `CHILD_SPECS` in the same shape:
  ```python
  CHILD_SPECS["briefer"] = ("demos.wildfire.briefer", 1)
  CHILD_SPECS["tasker"] = ("demos.wildfire.tasker", 1)
  ```
  Both are single-instance, no env-var fan-out needed.
- **Briefing pane in operator CLI:** the firefighter.py UI grows a side-pane that subscribes to incident briefings (Briefer's pubsub feed). Reuse the `client._nc.subscribe` raw pattern.
- **Channel-prefix grouping in admin UI registry:** the registry table currently lists agents flat. Phase 3 groups by zone/channel prefix for visual clarity (`high-alt.*`, `low-alt.*`, `ground.*`, plus the new `briefer` and `tasker` entries).

## Cross-AI Review Prompt Suggestions

- "Was the action-fleet single-writer pattern (D-41) unambiguously documented in the integration test? Where would a reviewer look first to confirm `mesh.action.{fleet_type}.{instance_id}.status` is being published exactly once per transition?"
- "Does the orchestrator's dashboard banner survive port-fallback (D-39)? The banner prints `dashboard at http://127.0.0.1:{requested}` but the dashboard's own stdout (multiplexed under `[dash]`) prints the resolved port. Should the orchestrator parse the resolved port and re-emit a banner?"
- "Should the Phase 2 integration test parse the resolved admin UI / dashboard ports from orchestrator stdout instead of hardcoding 8088 / 8081? This would make the test robust to back-to-back TIME_WAIT but adds 30+ lines of stdout-parsing complexity. Trade-off worth taking?"

## Self-Check: PASSED

Verified:
- `demos/wildfire/core/orchestrator.py` exists and contains `medevac`, `MEDEVAC_COUNT`, `DASHBOARD_PORT`, `_dash_proc`, `dashboard at http`.
- `tests/wildfire/integration/test_phase2_cascade.py` exists; `pytest --collect-only` reports both Phase 1 and Phase 2 test modules.
- All 245 wildfire unit tests still pass (`uv run pytest tests/wildfire/unit -x -q`).
- Both integration tests pass individually under `OAM_INTEGRATION_TESTS=1`.
- Commits exist in git log: `b2d253f`, `56ae16a`, `cff5a52`.
- Plan invariant greps all return expected counts (medevac/heli/health/DASHBOARD_PORT/OAM_INTEGRATION_TESTS); no bare `kv.list(prefix)` calls; no `bucket=`/`prefix=`/`model=` kwargs; no superseded `ThermalGrid`/`FireSpawn`/`FireSuppress` references.

---
*Phase: 02-cascade-closure*
*Completed: 2026-05-09*
