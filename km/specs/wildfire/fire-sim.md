# Fire simulator

**Status:** discussion
**Identity:** `fire-sim` (single instance)

> **Amended 2026-05-09** — pure-KV world grid. Drops 1 Hz pubsub of `ThermalGrid` and the `mesh.fire.spawn` / `mesh.fire.suppress` subscriptions. World state lives as sparse `CellState` records under `wildfire.world.cell.*`; fire-sim consumes external mutations (clicks, action-fleet suppression) via a `kv_source` and writes spread deltas to the same KV namespace. See ADR-0054 amended subject + KV map.

## Purpose

Drive the cascade. Maintain a 50×50 thermal grid in process and project changes to the shared world-state KV namespace. Models a spreading fire so a recorded run is reproducible. Reacts to external cell mutations (scenario UI clicks, action-fleet suppression) via a KV-watch source — the mesh is the input plane.

## Triggers

- Internal timer (1 Hz tick): runs the spread model on the in-process grid; writes only the cells that changed this tick to KV.
- KV-watch source on `wildfire.world.cell.*`: receives external mutations (clicks, suppression). Filters out self-writes (writes whose `last_modified_by == mesh.instance_id`) to avoid feedback loops on its own spread deltas.

## Outputs

- KV writes: `wildfire.world.cell.<x_idx>.<y_idx>` carrying `CellState { coords, temperature, last_modified_at, last_modified_by }`. Cells decaying to ambient are deleted (sparse-KV invariant — ambient cells have no key).

## State

- Internal: in-process 50×50 grid, hotspot list, spread model parameters, deterministic seed.
- KV: world cell records under `wildfire.world.cell.*`. fire-sim is the primary writer (spread deltas) and one of N writers (clicks + action fleets are peers).
- Snapshot resume: on boot, fire-sim replays current state via `mesh.kv.list("wildfire.world.cell.*")` so a restarted process picks up the existing world.

## Lifecycle

- Always-on for the duration of a scenario run.

## Reliability

- Deterministic given a `--seed` flag and the input cell history (Phase 5 reproducibility harness consumes both).
- No retries. If fire-sim dies the spread stops, but the latest world state survives in KV; on restart, the in-process grid is rebuilt from KV.

## Behaviour notes

- Grid resolution: 50×50 cells, 200 m per cell, 10×10 km area centered at origin.
- Spread model: lightweight cellular automaton with wind direction parameter (configurable, demo default fixed for predictable recording).
- Cell payload: `CellState`. Background ~25 °C — represented by **absence of a KV key**, not by a key carrying 25. Hotspots up to 800 °C, decay rate when not fed.
- Cell key encoding: index-based (`<x_idx>.<y_idx>` with `x_idx = floor((x - bounds.min) / cell_size)`). One source of truth for cell snapping; the dashboard backend does the same snap before writing.
- External mutations:
  - Scenario UI map click: writes a `CellState` directly. fire-sim's kv_source picks it up, integrates into the in-process grid, runs subsequent ticks against the new value.
  - Action-fleet suppression (heli water-drop, ffunit suppression): same path — writes a cooler `CellState` (or deletes the key) at the action coords. No separate suppression contract.
- Self-write filter: every cell write carries the writer's `mesh.instance_id` in `last_modified_by`. fire-sim's kv_source callback skips entries whose `last_modified_by == mesh.instance_id`. One-line guard against feedback loops.
- Spread tick output: only cells whose temperature changed materially write to KV. Active fire footprint is typically 10-50 cells; write rate scales with activity, not grid size.

## Open questions

- Is fire-sim a `mesh.agent`? Yes — a kv_source-driven Watcher. The 1 Hz spread tick is implemented as an asyncio loop alongside `mesh.run()`; the SDK has no first-class periodic-task primitive (deliberately — see Phase 2 discussion notes).
- Spread tick interval: 1 Hz default (tunable in `core/config.py: FIRE_SIM_TICK_INTERVAL`). Faster ticks for tighter cascade feel; slower for more readable timeline.
- Material-change threshold: temperature delta below which a cell's spread tick does NOT write to KV (suppress noise). Tunable in `core/config.py`.

## Subject + KV contracts

- KV-watch source (inbound): `wildfire.world.cell.*` carries `CellState`. fire-sim filters self-writes.
- KV writes (outbound): same namespace `wildfire.world.cell.*`. Sparse — only changed cells, only non-ambient cells.
- No pubsub subscriptions. No pubsub publications from fire-sim.

## SDK shape needed

- `kv_source(pattern)` (ADR-0052) for the world-cell watch.
- `mesh.kv.put(key, model)` and `mesh.kv.delete(key)` (ADR-0060) for spread-delta writes and ambient-decay deletions.
- `mesh.kv.list(pattern)` (ADR-0060) for boot-time snapshot replay.
- `mesh.instance_id` (ADR-0059) for the self-write filter and the `last_modified_by` field.
- All shipped on main as of 2026-05-08.
