---
phase: 01-detection-foundation
plan: 07
subsystem: agents
tags: [heli, ffunit, action-fleet, responder, boot-only, heartbeat, D-08]

# Dependency graph
requires:
  - phase: 01-detection-foundation
    plan: 01
    provides: "demos/wildfire/core/{contracts.py,config.py,keys.py} (DispatchOrder, DispatchAck, HQ, HELI_COUNT, FFUNIT_COUNT, fleet_key)"
  - phase: 01-detection-foundation
    plan: 02
    provides: "demos/wildfire/core/heartbeat.py (heartbeat_loop coroutine)"
  - phase: 01-detection-foundation
    plan: 05
    provides: "demos/wildfire/fleet/__init__.py (fleet subpackage namespace), uav.py reference shape"
provides:
  - "demos/wildfire/fleet/heli.py (low-alt.heli Responder; boot + register + heartbeat only this phase, stub DispatchOrder -> DispatchAck handler for catalog correctness)"
  - "demos/wildfire/fleet/ffunit.py (ground.ffunit Responder; same shape as heli, 3 instances per orchestrator)"
  - "Module entry points: python -m demos.wildfire.fleet.heli, python -m demos.wildfire.fleet.ffunit"
affects:
  - 01-08 (orchestrator: spawns 1 heli + 3 ffunit subprocesses; HELI_COUNT, FFUNIT_COUNT consumed from core/config.py)
  - 01-09 (unit tests: this plan added test_heli.py and test_ffunit.py contributing to 01-09's coverage)
  - 01-10 (integration test: asserts heli + ffunit rows visible in admin UI registry; their heartbeat keys appear under wildfire.fleet.low-alt.heli.* and wildfire.fleet.ground.ffunit.*)
  - "Phase 2 dispatch wiring: replaces the stub bodies with real travel + suppression + DispatchAck logic; queue group already correct (q.low-alt.heli, q.ground.ffunit) via SDK auto-binding"

# Tech tracking
tech-stack:
  added: []  # No new deps; pure reuse of heartbeat_loop + AgentSpec + DispatchOrder/DispatchAck from prior plans
  patterns:
    - "Responder-with-stub-body pattern: register the handler so the catalog records the contract correctly even before the handler body is operational. Phase 2 wiring replaces only the body."
    - "Per-channel agent identity (one catalog entry per channel-prefixed name) with per-instance heartbeat keys (one liveness row per process). Queue group is auto-derived from the catalog name (q.{name}) so multi-instance fleets share the queue without explicit configuration."

key-files:
  created:
    - "demos/wildfire/fleet/heli.py"
    - "demos/wildfire/fleet/ffunit.py"
    - "tests/wildfire/unit/test_heli.py"
    - "tests/wildfire/unit/test_ffunit.py"
  modified: []

key-decisions:
  - "Phase 1 heli + ffunit are boot + register + heartbeat ONLY (D-08). The DispatchOrder -> DispatchAck handler is registered (so the catalog records the contract correctly for the Phase 3 admin UI invocation sandbox) but is never called this phase. No throwaway test caller this phase per D-08."
  - "Stub handler returns DispatchAck(accepted=False, reason='phase 1 stub: ...') rather than raising. A structured rejection means a rogue Phase 2 caller surfaces a loud, typed failure instead of a silent success or an unstructured exception."
  - "Two near-identical modules rather than one parameterised module (per the plan objective). Splitting keeps each fleet grep-able by name (low-alt.heli vs ground.ffunit), gives each its own catalog identity, and matches the future trajectory where Phase 2 will diverge the bodies (heli has water tank + return-to-base; ffunit has reserves + on-site suppression)."
  - "Both modules mirror the uav.py module shape from plan 01-05 (build_agent + async _main + __main__ guard with KeyboardInterrupt suppress). Pattern is now stable for any future fleet-member module."

patterns-established:
  - "Responder agent + heartbeat fleet-member: import HQ, DispatchOrder, DispatchAck, heartbeat_loop; @mesh.agent(AgentSpec(name=...)) async def handler; async with mesh: + asyncio.create_task(heartbeat_loop(...)); cancel + suppress on shutdown. Heli and ffunit are the canonical examples; medevac (Phase 3) will follow the same shape."

requirements-completed: [SCN-05, SCN-06, SCN-13]

# Metrics
duration: 3min
completed: 2026-05-09
---

# Phase 1 Plan 07: heli + ffunit Responder agents (boot + heartbeat) Summary

**Two action-fleet Responder agents (low-alt.heli and ground.ffunit) registered with stub DispatchOrder -> DispatchAck handlers for catalog correctness, plus 1 Hz heartbeat to wildfire.fleet.{zone}.{type}.{instance_id}. Per D-08, the handlers are never called this phase; Phase 2 wires the dispatch path.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-09T00:25:32Z
- **Completed:** 2026-05-09T00:28:29Z
- **Tasks:** 2 (both TDD: heli RED -> GREEN, ffunit RED -> GREEN)
- **Files created:** 4 (2 agent modules, 2 unit test files)
- **Tests added:** 32 (16 per agent: module shape + source-text invariants + stub handler shape + parametrised forbidden-pattern checks)
- **Total wildfire unit tests:** 100 passing (no regressions)

## Accomplishments

- `low-alt.heli` agent registered as a Responder via `AgentSpec(name="low-alt.heli", ...)`, with stub handler `async def heli(order: DispatchOrder) -> DispatchAck`. Phase 1 instance count is 1 (HELI_COUNT).
- `ground.ffunit` agent registered as a Responder via `AgentSpec(name="ground.ffunit", ...)`, same shape. Phase 1 instance count is 3 (FFUNIT_COUNT); the three instances share queue group `q.ground.ffunit` automatically per `src/openagentmesh/_mesh.py:_subscribe_agent`.
- Both modules use the shared `heartbeat_loop(mesh, zone=..., fleet_type=..., get_state=lambda: "free", get_coords=lambda: HQ, get_assignment=lambda: None)` coroutine. Each instance writes its own `wildfire.fleet.{zone}.{type}.{instance_id}` record at 1 Hz.
- Stub handlers return `DispatchAck(accepted=False, instance_id=mesh.instance_id, eta_seconds=None, reason="phase 1 stub: ...")` for catalog-shape correctness. Per D-08 these handlers are never invoked in Phase 1; the bodies will be replaced in Phase 2 when the operator -> tasker -> dispatch path lands.
- Module entry points: `python -m demos.wildfire.fleet.heli` and `python -m demos.wildfire.fleet.ffunit` connect to `NATS_URL` (default `nats://127.0.0.1:4222`), register, start the heartbeat task, and block until SIGINT.
- New unit test files: `tests/wildfire/unit/test_heli.py` and `tests/wildfire/unit/test_ffunit.py` (16 tests each, parametrised forbidden-pattern + stub-shape + module-shape coverage).

## Verification

All plan-level verification commands pass:

1. `uv run python -c "from demos.wildfire.fleet.heli import build_agent; from demos.wildfire.fleet.ffunit import build_agent as fb; print('ok')"` -> `ok`.
2. `grep -E "FireSpawn|ThermalGrid|FireSuppress|mesh.environment.thermal" demos/wildfire/fleet/{heli,ffunit}.py` -> no matches (A-07 / A-08 dropped pubsub artefacts).
3. `uv run ruff check demos/wildfire/fleet/heli.py demos/wildfire/fleet/ffunit.py` -> `All checks passed!`.
4. `uv run pytest tests/wildfire/unit/` -> 100 passed.

Per-module:

- `grep -c "low-alt.heli" demos/wildfire/fleet/heli.py` -> 6 (catalog name plus docstrings).
- `grep -c "ground.ffunit" demos/wildfire/fleet/ffunit.py` -> 7 (catalog name plus docstrings).
- `grep -E "subject_source|kv_source|mesh\.publish" demos/wildfire/fleet/{heli,ffunit}.py` -> no matches (Phase 1 = boot + heartbeat only per D-08).

## Notes for downstream consumers

- **Instance counts in admin UI come from the count of distinct `wildfire.fleet.{zone}.{type}.*` keys with fresh `last_updated` (D-10), NOT from the catalog (which dedups by name).** Three ffunit processes register one catalog entry (`ground.ffunit`) but write three heartbeat keys (`wildfire.fleet.ground.ffunit.{id_a}`, `..{id_b}`, `..{id_c}`). The admin UI registry derives the live-instance count from the heartbeat namespace.
- **No smoke-test caller is shipped this phase (D-08).** Phase 1 demonstrates that heli + ffunit boot, register, and heartbeat. The dispatch round-trip (`mesh.call("low-alt.heli", DispatchOrder)`) is exercised in Phase 2 when the operator + tasker peers land. Adding a throwaway test caller now would have to be removed two phases later when the real caller arrives.
- **Stubs are loud, not silent.** If something does invoke the Phase 1 heli or ffunit handler before Phase 2 wiring, the caller receives `DispatchAck(accepted=False, reason="phase 1 stub: ...")` instead of an empty success. Easy to spot in logs.
- **Queue group is automatic.** The orchestrator (plan 01-08) spawns FFUNIT_COUNT=3 ffunit subprocesses; all three share queue group `q.ground.ffunit` without any explicit configuration. Phase 2 dispatch will naturally hit the first available instance.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed literal `mesh.publish` token from heli.py docstring**
- **Found during:** Task 1 (heli) GREEN verification.
- **Issue:** The plan's parametrised invariant test asserts no occurrence of the literal string `"mesh.publish"` anywhere in the agent module (matching the uav.py convention from plan 01-05). My initial docstring contained `"no mesh.publish of HeliStatus this phase"` as natural prose, which tripped the grep-style invariant.
- **Fix:** Rephrased the docstring bullet to "No outbound pubsub (no HeliStatus emission this phase)" -- preserves the meaning, kills the literal-string match.
- **Files modified:** `demos/wildfire/fleet/heli.py` (1-line docstring edit before the GREEN commit landed).
- **Commit:** Folded into the GREEN commit (no separate commit was needed since the RED -> GREEN cycle was still running on this task).

The same rephrasing was applied preemptively to `ffunit.py`, so Task 2 went RED -> GREEN cleanly without a fix step.

### Authentication gates

None.

### Architectural changes (Rule 4)

None.

## Threat Flags

None. Plan 01-07's threat register accepts both T-01-07-01 (catalog publishes input/output schemas for unimplemented handlers) and T-01-07-02 (DoS on stub handler). Both still match the implemented behavior:

- The `DispatchOrder` and `DispatchAck` schemas in the catalog are real (no aspirational fields); only the body is stubbed.
- The stub returns synchronously with no I/O or compute, so Phase-2-and-later callers cannot exhaust resources by hammering it before the real body lands.

No new threat surface beyond what the plan already enumerated.

## Self-Check: PASSED

- File `demos/wildfire/fleet/heli.py`: FOUND
- File `demos/wildfire/fleet/ffunit.py`: FOUND
- File `tests/wildfire/unit/test_heli.py`: FOUND
- File `tests/wildfire/unit/test_ffunit.py`: FOUND
- Commit hashes (per-task RED + GREEN) verified in `git log` below.
