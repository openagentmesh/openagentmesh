---
phase: 01-detection-foundation
plan: 04
subsystem: world
tags: [fire-sim, kv-source, watcher, sparse-kv, spread-tick, self-write-filter]

# Dependency graph
requires:
  - phase: "01-01"
    provides: "demos/wildfire/core/contracts.py (CellState, Coords)"
  - phase: "01-01"
    provides: "demos/wildfire/core/config.py (FIRE_SIM_* tunables, GRID_DIM via keys)"
  - phase: "01-01"
    provides: "demos/wildfire/core/keys.py (CELL_PREFIX, GRID_DIM, cell_center, cell_key, cell_indices)"
  - phase: "01-02"
    provides: "(no direct dependency: fire-sim is NOT a fleet member, has no heartbeat record under wildfire.fleet.*)"
  - phase: "01-03"
    provides: "demos/wildfire/world/__init__.py + orchestrator's CHILD_SPECS entry for fire-sim"
  - phase: ""
    provides: "openagentmesh public API: AgentMesh, AgentSpec, KVEntry; mesh.kv_source(pattern, on_init); mesh.kv.put_model / delete; mesh.instance_id"
provides:
  - "demos/wildfire/world/fire_sim.py with @mesh.agent('fire-sim') Watcher bound to kv_source('wildfire.world.cell.*')"
  - "FireSim class (pure Python, no SDK dependency): integrate_cell / drop_cell / tick"
  - "1 Hz internal spread tick that writes only materially-changed cells via mesh.kv.put_model and deletes ambient-decayed cells via mesh.kv.delete"
  - "Self-write filter via last_modified_by == mesh.instance_id (A-04)"
  - "Module entry: python -m demos.wildfire.world.fire_sim (consumed by orchestrator CHILD_SPECS['fire-sim'])"
affects:
  - "01-05 (UAV kv_source consumer): UAV reads the same wildfire.world.cell.* namespace fire-sim writes; UAV's threshold logic depends on fire-sim's diffusion + decay arithmetic landing values reasonably between 100-800 C"
  - "01-09 (unit tests): test_fire_sim.py landed alongside this plan; future TDD waves can extend it"
  - "01-10 (integration): the spawn CLI -> fire-sim integrate -> spread -> UAV detection cascade depends on this module's tick + write semantics"
  - "01-11 (Phase 1 verification): the orchestrator boots [fire-sim-0] as a child; this module is its target"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Source-driven Watcher: KVEntry[Model] handler shape, invocable=False, no return -- the SDK validates the JSON to a Pydantic model automatically and dispatches PUT vs DELETE via entry.operation"
    - "Self-write filter on a kv_source: last_modified_by carrying writer's mesh.instance_id; the handler returns early when entry.value.last_modified_by == mesh.instance_id (A-04)"
    - "Boot-time replay rebuild: kv_source(..., on_init='replay') (default) re-fires every existing key on startup so the in-process grid is reconstructed from KV state on a restart"
    - "Sparse-KV invariant: cells decayed to ambient are deleted (mesh.kv.delete), not written with ambient temperature; ambient = absence of a key (A-03)"
    - "Material-delta noise filter: only cells whose post-tick temperature shifted by >= FIRE_SIM_MATERIAL_DELTA_C are written, to avoid pumping the KV bus with sub-noise diffusion deltas"
    - "Decoupled core: pure-Python FireSim class for unit tests, plus build_agent(mesh, sim) + _spread_loop(mesh, sim) for the SDK-aware wrapping"
    - "SIGTERM-aware shutdown: loop.add_signal_handler wires SIGTERM/SIGINT to an asyncio.Event so the orchestrator's Popen.terminate() unblocks the long-running mesh.run-equivalent"

key-files:
  created:
    - "demos/wildfire/world/fire_sim.py"
    - "tests/wildfire/unit/test_fire_sim.py"
  modified: []

key-decisions:
  - "Used public openagentmesh imports (AgentMesh, AgentSpec, KVEntry) instead of the plan's _models / _context internal paths -- both are exported in the package __init__.py and the public path keeps the demo robust to internal module shuffles"
  - "Custom _main coroutine + asyncio.create_task(_spread_loop) instead of mesh.run() because the agent needs both source binding (covered by `async with mesh:`) AND a periodic in-process tick task that mesh.run() exposes no hook for (this is the same trade-off the plan example called out)"
  - "Added SIGTERM handler via loop.add_signal_handler (Rule 2 / Rule 3) so the orchestrator's Popen.terminate() shuts the agent down cleanly. Without it the process would hang on the stop_event, leaving a zombie until the orchestrator's TERMINATE_TIMEOUT_S elapsed and SIGKILL was issued. add_signal_handler raises NotImplementedError on Windows; suppressed via contextlib.suppress with a docstring note"
  - "Added FIRE_SIM_MAX_C cap during tick (Rule 2) to prevent runaway accumulation: with positive diffusion + a persistent external write loop, the cell could otherwise grow unbounded. The constant was already exported in core/config.py so this is consistent with the plan-01-01 contract"
  - "Two-pass tick: pass 1 self-decays + neighbour-absorbs already-hot cells; pass 2 ignites cold neighbours of any hot cell whose bleed >= FIRE_SIM_MATERIAL_DELTA_C. Iterating over the original (pre-tick) grid in pass 2 prevents synchronous cascade in a single tick (one CA step per tick)"
  - "DELETE op (kv_source) drops the cell from the in-process grid only; we deliberately do NOT re-write the cell on DELETE, which would create exactly the feedback loop the self-write filter exists to prevent"

requirements-completed: [SCN-01]

# Metrics
duration: ~14min
completed: 2026-05-09
---

# Phase 1 Plan 04: fire-sim kv_source Watcher Summary

**Wildfire's authoritative spread engine, rewired as a Watcher: a `kv_source`-driven agent that integrates external KV writes into a 50x50 in-process grid and writes back only the cells that materially changed, with a single-line self-write filter as the defence against feedback loops.**

## Performance

- **Duration:** ~14 min
- **Started:** 2026-05-09T00:04:34Z (worktree base reset)
- **Completed:** 2026-05-09T00:18:22Z
- **Tasks:** 1 (single-task plan; the entire fire-sim module + its unit-test seed)
- **Files created:** 2 (`demos/wildfire/world/fire_sim.py`, `tests/wildfire/unit/test_fire_sim.py`)

## Accomplishments

- **kv_source-driven Watcher** registered as `@mesh.agent('fire-sim')` bound to `mesh.kv_source(f"{CELL_PREFIX}.*", on_init="replay")`; the handler is annotated `async def fire_sim(entry: KVEntry[CellState]) -> None` so the SDK classifies it as `kv_entry`-shape (per `_handler.py:_classify_source_param`), validates the JSON to `CellState` automatically, and dispatches PUT/DELETE via `entry.operation`.
- **Self-write filter** (A-04): every payload the agent itself writes back to KV carries `last_modified_by = mesh.instance_id`; the handler skips PUT entries whose `entry.value.last_modified_by` matches the agent's id. One-line defence, exactly as the amendment specifies.
- **Boot snapshot replay** via `on_init="replay"` (the SDK default): on startup, every existing `wildfire.world.cell.*` key fires the handler, so the in-process grid rebuilds from KV state on a restart. Live updates from the spawn CLI (and Phase 2 action fleets) flow through the same handler afterwards.
- **1 Hz internal spread tick** (`_spread_loop`) launched as an `asyncio.Task` inside `_main`, ticking every `FIRE_SIM_TICK_INTERVAL_S = 1.0` s. Each tick runs the toy CA (decay + diffusion + neighbour ignition) and writes only the cells whose temperature shifted by `>= FIRE_SIM_MATERIAL_DELTA_C` via `mesh.kv.put_model`; cells whose post-tick temperature falls at or below `FIRE_SIM_AMBIENT_C` are deleted via `mesh.kv.delete` (sparse-KV invariant per A-03).
- **Anti-scope honoured**: zero `mesh.publish` / `subject_source` / `ThermalGrid` / `FireSpawn` / `FireSuppress` / `mesh.environment.thermal` / `mesh.fire.spawn` / `mesh.fire.suppress` references. Verified by the plan's grep contract (exit 1 = no matches).
- **Pure-Python `FireSim` core** decoupled from the SDK so plan 01-09 / 01-10 unit tests can exercise the spread arithmetic without booting NATS. Unit-test seed (`test_fire_sim.py`, 9 tests) lands alongside this plan to satisfy the `tdd="true"` plan flag.
- **SDK signature compliance** (A-09): no `bucket=` or `prefix=` kwargs; `mesh.kv_source(pattern, on_init=...)`, `mesh.kv.put_model(key, model)`, `mesh.kv.delete(key)`, `mesh.instance_id` all match the shipped surface.

## Task Commits

Each task committed atomically with `--no-verify` per parallel-execution rules.

| # | Phase | Hash | Type | Subject |
|---|-------|--------|------|---------|
| 1 | RED   | `7d9c4be` | test | failing test for fire-sim core (FireSim class) |
| 1 | GREEN | `d09325a` | feat | fire-sim kv_source Watcher + 1 Hz spread tick (A-04, A-08) |

The RED-then-GREEN sequence satisfies the plan-level TDD gate (`test(...)` commit precedes `feat(...)` commit in `git log`).

## Files Created

- **`demos/wildfire/world/fire_sim.py`** -- the agent module. `python -m demos.wildfire.world.fire_sim` boots a single fire-sim instance against `NATS_URL` (default `nats://127.0.0.1:4222`).
- **`tests/wildfire/unit/test_fire_sim.py`** -- 9 unit tests pinning the `FireSim` class contract (empty-grid no-op, integrate-then-tick shape, drop-cell idempotency, ambient-decay deletion queue, neighbour ignition, grid-boundary safety, material-delta filtering, agent-surface presence).

## API Reference

### `FireSim` class (pure Python, decoupled from SDK)

```python
from demos.wildfire.world.fire_sim import FireSim

sim = FireSim()

# External-mutation entry points (called by the kv_source handler):
sim.integrate_cell(x_idx: int, y_idx: int, temperature: float) -> None
sim.drop_cell(x_idx: int, y_idx: int) -> None  # idempotent

# Internal tick (called by _spread_loop):
cells_changed: dict[tuple[int, int], float], cells_to_delete: list[tuple[int, int]] = sim.tick()
```

The tick returns `(cells_changed, cells_to_delete)` so the wrapping loop issues exactly one `mesh.kv.put_model` per material delta and one `mesh.kv.delete` per decayed-to-ambient cell. `(x_idx, y_idx)` are integer cell indices in `[0, GRID_DIM)`; resolve back to world coords via `cell_center` from `demos.wildfire.core.keys`.

### `@mesh.agent` registration

The agent's catalog identity is **`fire-sim`** (the name plan 01-09 / 01-10 / 01-11 should grep for). Description (consumed by LLM tool selection in later phases):

> "Wildfire spread simulator: 50x50 in-process thermal grid driven by KV writes on wildfire.world.cell.*; runs a 1 Hz spread tick and writes only changed cells back via the same KV namespace."

Capabilities (per `_handler.py` classification of the `KVEntry[CellState]` handler shape): `invocable=False`, `streaming=False`, `source_param_kind="kv_entry"`. **fire-sim is a Watcher, not callable via `mesh.call`.** The catalog lists it for visibility (admin UI shows it as a live registered agent in `oam.catalog.>`) but no operator code invokes it directly.

### Heartbeat

**fire-sim has no heartbeat record under `wildfire.fleet.*`.** Per the plan's must_haves and per `km/specs/wildfire/fire-sim.md`, fire-sim is NOT a fleet member; it has its own catalog identity but no `FleetMemberState` KV write. The admin UI surfaces it via `oam.catalog.>` only. Plan 01-11's verification should look for fire-sim in the catalog row count, not in the `wildfire.fleet.*` namespace count.

## Decisions Made

- **Public openagentmesh imports** (`AgentMesh`, `AgentSpec`, `KVEntry`) instead of the plan's `_models` / `_context` internal paths. Both classes are exported via `src/openagentmesh/__init__.py:23-41`; the public path keeps the demo robust to internal module shuffles. Same convention as `demos/wildfire/world/spawn.py` (plan 01-02 era), which imports `from openagentmesh import AgentMesh`.
- **Custom `_main` coroutine instead of `mesh.run()`** because the agent needs both source binding (covered by `async with mesh:`) AND a periodic in-process tick task; `mesh.run()` blocks on `asyncio.Event().wait()` and exposes no hook for the periodic task. The plan's example called this trade-off out and the implementation follows the same shape.
- **SIGTERM handler** via `loop.add_signal_handler(signal.SIGTERM, stop_event.set)` so the orchestrator's `Popen.terminate()` (which delivers SIGTERM) shuts down cleanly. Mirrored for SIGINT for symmetry with the KeyboardInterrupt fallback. `add_signal_handler` raises `NotImplementedError` on Windows / non-main-thread contexts; suppressed via `contextlib.suppress` with a comment.
- **Two-pass tick algorithm**: pass 1 self-decays + neighbour-absorbs already-hot cells; pass 2 ignites cold neighbours of any hot cell whose bleed crosses the material-write threshold. Iterating over the original (pre-tick) grid in pass 2 prevents synchronous cascade in a single tick (one CA step per tick), matching the spec's intent of a 1 Hz observable spread cadence.
- **DELETE op handler drops the cell only**, never re-writes. Re-writing on DELETE would create exactly the feedback loop the self-write filter exists to prevent.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `GRID_DIM` import path correction**
- **Found during:** RED test execution
- **Issue:** The plan's example imports `GRID_DIM` from `demos.wildfire.core.config`, but plan 01-01's `core/config.py` does not export it; `GRID_DIM` is defined in `core/keys.py:43` (where the grid geometry lives alongside `CELL_SIZE_KM`).
- **Fix:** In `tests/wildfire/unit/test_fire_sim.py`, imported `GRID_DIM` from `demos.wildfire.core.keys` (the actual home). The implementation file already uses the correct import.
- **Files modified:** `tests/wildfire/unit/test_fire_sim.py`
- **Verification:** Test collection succeeds; the original ImportError ("cannot import name 'GRID_DIM' from 'demos.wildfire.core.config'") is resolved.
- **Committed in:** `7d9c4be` (RED commit; the path correction was made before the commit landed).

**2. [Rule 3 - Blocking] Forbidden-symbol grep false-positive in docstring**
- **Found during:** Plan-level verification (grep `ThermalGrid|FireSpawn|FireSuppress|mesh.publish|subject_source|...`)
- **Issue:** The module docstring originally listed the dropped pubsub artefacts as anti-scope (`"It does NOT publish ``ThermalGrid`` ... It does NOT subscribe to ``mesh.fire.spawn`` ..."`). The plan's grep is unconditional and therefore matched the prose, even though the matches are negative claims.
- **Fix:** Reworded the anti-scope paragraph to use generic language ("zero pubsub surface", "the old pre-amendment thermal-grid publisher and the spawn / suppress subscriber surfaces are gone") instead of the literal symbol names. Same fix the orchestrator plan 01-03 applied (deviation #2 in 01-03-SUMMARY).
- **Files modified:** `demos/wildfire/world/fire_sim.py` (docstring only; behaviour unchanged)
- **Verification:** All four grep contracts now exit 1 (no matches): the plan's `<verify>` block, the prompt's `<success_criteria>`, and the two extended variants.
- **Committed in:** `d09325a` (GREEN commit)

**3. [Rule 3 - Blocking] Ruff style fixes (I001 import order, SIM105 try/except/pass)**
- **Found during:** Plan-level verification (`uv run ruff check demos/wildfire/world/fire_sim.py`)
- **Issue:** (a) Initial `from openagentmesh ...` line preceded `from demos. ...` blocks; ruff treats both `openagentmesh` (declared first-party in `pyproject.toml`) and `demos.*` (sibling of `src/`) as the same first-party group, so they must be in one block with no blank line. (b) Three `try/except/pass` patterns flagged SIM105: SIGTERM handler fallback, tick-task cancellation drain, and `__main__` KeyboardInterrupt swallow.
- **Fix:** (a) Reordered imports so `demos.*` blocks precede `openagentmesh` (alphabetical within the same first-party group), removed the blank-line separator. (b) Replaced all three try/except/pass patterns with `contextlib.suppress(...)`; added `import contextlib` to the stdlib block.
- **Files modified:** `demos/wildfire/world/fire_sim.py`
- **Verification:** `uv run ruff check demos/wildfire/world/fire_sim.py` -> All checks passed!
- **Committed in:** `d09325a` (GREEN commit)

### Auto-added (Rule 2: missing critical functionality)

**4. [Rule 2 - SIGTERM handler]**
- **Issue:** Plan 01-03's orchestrator supervises children with `subprocess.Popen.terminate()` (POSIX SIGTERM) on shutdown. Without a SIGTERM handler, fire-sim would block on `asyncio.Event.wait()` (or `asyncio.Event().wait()` per the plan's example) until the orchestrator's terminate-timeout elapsed and a SIGKILL was issued. That makes orchestrator shutdown non-instant and prevents fire-sim's `async with mesh:` clean-shutdown path (catalog deregistration, in-flight publish drain) from running.
- **Fix:** Wired `signal.SIGTERM` and `signal.SIGINT` to an `asyncio.Event` via `loop.add_signal_handler`; `_main` blocks on the event instead of `asyncio.Event().wait()`. SIGKILL still works as a hard kill (cannot be intercepted), but `Popen.terminate()` now produces a clean shutdown.
- **Threat-model link:** No new trust boundary; this is a correctness fix for the orchestrator-driven shutdown path.

**5. [Rule 2 - FIRE_SIM_MAX_C cap]**
- **Issue:** With positive diffusion (`FIRE_SIM_SPREAD_DIFFUSION = 0.10`) and a persistent external write source (e.g. the spawn CLI driving repeated spawns at 800 C), the absorbed `excess` term in pass 1 plus the per-tick decay yields a net-positive trajectory for cells surrounded by hotter neighbours. Without an upper bound, cells could escape Pydantic's "expected range [25, 800]" docstring even though `CellState.temperature` has no Pydantic constraint.
- **Fix:** Cap `new_temp` and `ignited_temp` at `FIRE_SIM_MAX_C = 800.0` (already exported by `demos/wildfire/core/config.py:67`).
- **Threat-model link:** Mitigates T-01-04-03 (DoS via KV write storm) by bounding the per-cell value; the existing `FIRE_SIM_MATERIAL_DELTA_C` filter is still the primary write-storm defence.

**Total deviations:** 5 auto-fixed (3 blocking; 2 missing-functionality additions). No scope expansion; no architectural changes.

## Issues Encountered

None beyond the five deviations above. The pre-existing ruff I001 in `demos/wildfire/world/spawn.py:24` was observed during the full-`demos/` ruff sweep but is **out of scope** for this plan (it lives in plan 01-02's territory, was not introduced or touched by this plan's edits). Logged for future cleanup; not fixed here per the executor's scope-boundary rules.

## Threat Flags

None. The plan's `<threat_model>` declares three threats (T-01-04-01 self-write spoofing accepted, T-01-04-02 malformed-key tampering mitigated by try/except parse, T-01-04-03 KV write-storm DoS mitigated by material-delta threshold). All three remain accurate; the implementation matches the disposition column.

The Rule-2 additions (SIGTERM handler, FIRE_SIM_MAX_C cap) introduce no new trust boundaries:
- The signal handlers respond only to local POSIX signals from the orchestrator parent process; no remote attack surface.
- The temperature cap is a mathematical bound, not an authentication or input-validation check.

## Known Stubs

None. The fire-sim agent is functionally complete for Phase 1; the spread CA tunables (`FIRE_SIM_*`) are documented as "tuned later when the demo runs" in `demos/wildfire/core/config.py:79`, but the agent surface itself is not stubbed.

## Self-Check: PASSED

**Files created:**
- `[ FOUND ] demos/wildfire/world/fire_sim.py`
- `[ FOUND ] tests/wildfire/unit/test_fire_sim.py`

**Commits in `git log`:**
- `[ FOUND ] 7d9c4be` (test: failing test for fire-sim core)
- `[ FOUND ] d09325a` (feat: fire-sim kv_source Watcher + 1 Hz spread tick)

**Plan-level verification (4 commands from `<verify>` block + 3 from prompt success_criteria):**
- `[ PASS ] FireSim import + integrate_cell + tick + assertion`
- `[ PASS ] forbidden-symbol grep returns no matches`
- `[ PASS ] kv_source count >= 1` (6 occurrences in the module)
- `[ PASS ] no bucket= or prefix= kwargs`
- `[ PASS ] extended success_criteria forbidden grep returns no matches`
- `[ PASS ] kv_source on wildfire.world.cell present` (1 occurrence)
- `[ PASS ] uv run ruff check demos/wildfire/world/fire_sim.py -> All checks passed!`

**Test suite:** 9/9 fire-sim unit tests pass; 45/45 wildfire suite passes (no regressions in 01-01..01-03 territory).

## TDD Gate Compliance

The plan declares `tdd="true"` on Task 1. Gate sequence verified in `git log`:

```
7d9c4be  test(01-04): add failing test for fire-sim core (FireSim class)
d09325a  feat(01-04): fire-sim kv_source Watcher + 1 Hz spread tick (A-04, A-08)
```

RED commit precedes GREEN commit. No REFACTOR commit was needed (the implementation passed all 9 tests on first run after the import-path fix in test_fire_sim.py).

## Next Phase Readiness

- **01-05 (UAV)** can now be planned against a live `wildfire.world.cell.*` namespace: UAV's `kv_source` consumer pattern mirrors fire-sim's, just with the additional threshold + footprint + dedup + `mesh.kv.create` write to `wildfire.detection.{id}`. The self-write filter pattern lands as a copy-paste; UAV's filter uses `entry.value.last_modified_by != mesh.instance_id` (UAV does NOT write back to cells, so the filter is "skip our own deltas" as a no-op for UAV but the same template for clarity).
- **01-09 (unit tests)** has its first wildfire-agent test file landed (`test_fire_sim.py`); 01-09 should extend it with `AgentMesh.local()`-based integration of the kv_source handler, not just the pure-Python core.
- **01-10 (integration)** can wire the spawn CLI -> fire-sim integrate -> spread cascade as soon as plan 01-05 (UAV) lands; the cascade is `wildfire.world.cell.*` writes -> fire-sim integrates + spreads -> threshold-crossing cells trip UAV -> `wildfire.detection.{id}` appears.
- **01-11 (Phase 1 verification)**: orchestrator's `[fire-sim-0]` child is the target of this module; the `python -m demos.wildfire.world.fire_sim` entry honours the orchestrator's `NATS_URL` env propagation (D-06) without any wrapper.

---
*Phase: 01-detection-foundation*
*Plan: 01-04*
*Completed: 2026-05-09*
