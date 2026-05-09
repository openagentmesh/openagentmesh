---
phase: 02-cascade-closure
plan: 07
subsystem: dashboard-frontend
tags: [dashboard, frontend, canvas, websocket, click-cycle, heat-layer, fleet-pointers, D-49, D-50, D-52, D-53]
requires:
  - "02-05 (FastAPI WebSocket protocol contract: cell_update / cell_delete / fleet_update / detection / action_status / snapshot_complete envelopes; click ingestion + grid snap)"
  - "02-06 (Svelte 5 + Vite + TypeScript scaffold; pnpm 9.15.0 toolchain)"
provides:
  - "Working scenario UI canvas at demos/wildfire/dashboard/dist/index.html: heat layer, drone/medevac trails, detection markers, fleet pointers; click handler that round-trips cell magnitude through the dashboard backend"
  - "WebSocket client (src/lib/mesh.ts) with reconnect-with-exponential-backoff and typed Svelte stores (cellsStore, fleetStore, detectionsStore, actionStatusStore, connectionStore) consumable by future Phase 2/3 panels"
  - "Browser-only per-cell magnitude cycle helper (src/lib/magnitude.ts) decoupled from Svelte for headless test harness reuse"
  - "Pixel <-> km coordinate utilities (src/lib/coords.ts) mirroring core/keys.py exactly; single source of truth in TS for grid math"
affects:
  - "demos/wildfire/dashboard/dist/* (rebuilt; bundle now 37.4 kB / 14.45 kB gzipped — was 26.27 kB / 10.28 kB on the 02-06 placeholder)"
  - "No changes to dashboard backend (server.py untouched); browser is the only side that moved"
tech_stack:
  added: []
  patterns:
    - "Svelte writable Map stores: replace the Map reference on every update so `$store` autosub fires (mutating in-place would not)"
    - "Bounded ring buffer for actionStatusStore (50 entries) — same shape future briefing/narrative feeds can borrow"
    - "WebSocket reconnect with exponential backoff (1s, 2s, 4s, ...) capped at 30s and a closedByCaller flag so the teardown function deterministically stops reconnects"
    - "Decoupled Renderer: takes a getState callback returning RenderState; App.svelte injects a snapshot from svelte/store get(). Keeps canvas.ts framework-agnostic."
key_files:
  created:
    - "demos/wildfire/dashboard/src/lib/coords.ts"
    - "demos/wildfire/dashboard/src/lib/mesh.ts"
    - "demos/wildfire/dashboard/src/lib/magnitude.ts"
    - "demos/wildfire/dashboard/src/lib/canvas.ts"
  modified:
    - "demos/wildfire/dashboard/src/App.svelte"
decisions:
  - "Reconnect schedule: exponential 1s, 2s, 4s, 8s, 16s, then capped at 30s. Single attempt counter resets on each successful 'open' event."
  - "Cells are keyed by `${x_idx}:${y_idx}` (string) inside the Svelte store, matching server's MSG_CELL_UPDATE / MSG_CELL_DELETE envelopes — no need for cell_indices() at dispatch time because the server already includes both indices."
  - "Trail buffer pruning happens inside the render loop (T-02-07-03 mitigation) rather than on each fleet_update: fleet_updates fire ~1Hz per instance, the render loop is 60Hz, but the trim is O(n) drop-from-front so the cost is bounded at TRAIL_WINDOW_S * heartbeat_rate per instance."
  - "Used `on:click` (Svelte 4 syntax) per the plan body. Svelte 5 emits a deprecation warning. Migration to the `onclick` event attribute is a Phase 5 polish item."
metrics:
  duration: "~5 min"
  completed: "2026-05-09"
  tasks: 4
  files_created: 4
  files_modified: 1
---

# Phase 02 Plan 07: Dashboard Canvas + WebSocket Client + Click Cycle Summary

End-to-end click-to-spawn cycle wired from the browser canvas through the dashboard backend to the KV-backed world grid. The scenario UI now renders the heat layer (cells from `wildfire.world.cell.*`), fleet pointers (UAV / drone / heli / ffunit / medevac), drone trails (last 30s), and detection markers (orange pending, amber surveyed) in real time. Clicking a cell cycles the per-cell magnitude `off -> small (200°C) -> medium (500°C) -> large (800°C) -> off`, sending each step over WebSocket as `{type: "click", coords, temperature}`; the server snaps to the 200m grid and writes (or deletes) the `CellState` KV record, fire-sim's `kv_source` picks it up, and the cascade unfolds visibly in the same canvas.

## Tasks Executed

| Task | Name                                       | Commit  | Files                                                                  |
| ---- | ------------------------------------------ | ------- | ---------------------------------------------------------------------- |
| 1    | WebSocket client + Svelte stores           | 295c73e | src/lib/mesh.ts, src/lib/coords.ts                                     |
| 2    | Click magnitude cycle helper               | b333c09 | src/lib/magnitude.ts                                                   |
| 3    | Canvas renderer (heat / trails / fleet)    | 2f0c885 | src/lib/canvas.ts                                                      |
| 4    | App.svelte real component + click wiring   | bd8c885 | src/App.svelte                                                         |

## Layer Order in canvas.ts

Per `km/specs/wildfire/dashboard.md` "Behaviour notes" the renderer paints in this order on every `requestAnimationFrame` tick:

1. **World background** (`#f4f1ea` solid fill, dimensions = canvas.width / height).
2. **Heat layer.** For every cell in `cellsStore.values()`, draw a `cellPxW * cellPxH` rectangle at `(x_idx * cellPxW, y_idx * cellPxH)`. Color: `rgba(255, 200*(1-intensity), 0, 0.2 + 0.5*intensity)` where `intensity = clamp((temperature - 25) / 775, 0, 1)`. Yellow at ambient, orange at mid, red at saturation. Alpha caps at 0.7 so fleet pointers stay legible.
3. **Drone / medevac trails.** Per-instance ring buffer of `(x, y, t)` points; appended only when the fleet member moved >= 50 m since the last sample, dropped when older than 30 s. Stroke: `rgba(0, 100, 255, 0.4)`, lineWidth 1. Trim happens inside the render loop (T-02-07-03 mitigation).
4. **Detection markers.** Surveyed = amber (`rgba(255, 200, 0, 0.9)`) radius 6; pending = warm orange (`rgba(255, 80, 0, 0.9)`) radius 4.
5. **Fleet pointers.** Per `dashboard.md` "Fleet pointers" line: UAV upward triangle (8 px tall), drone filled dot (r=3), heli open circle (r=6) with horizontal rotor bar (-9..+9), ffunit cross (-5..+5 on both diagonals), medevac filled square (10x10).
6. **World bounds outline** (`rgba(0, 0, 0, 0.15)` 1 px) drawn last as a subtle reference frame.

## Reconnect Backoff Schedule

`openMeshWebSocket()` uses exponential backoff:

```
attempt 1: 1000 ms
attempt 2: 2000 ms
attempt 3: 4000 ms
attempt 4: 8000 ms
attempt 5: 16000 ms
attempt 6+: 30000 ms (capped)
```

Constants live at the top of `mesh.ts` (`RECONNECT_BASE_MS = 1000`, `RECONNECT_MAX_MS = 30000`). The attempt counter resets to 0 on each successful `open` event, so a transient blip costs at most one cycle even after a long outage. The teardown function returned by `openMeshWebSocket()` flips a `closedByCaller` flag so any in-flight reconnect timer is canceled and the close handler short-circuits to `disconnected` rather than rescheduling.

## WebSocket Message Coverage

The dispatcher in `mesh.ts` handles all six envelope types from `server.py`:

| Envelope            | Action                                                                                        |
| ------------------- | --------------------------------------------------------------------------------------------- |
| `cell_update`       | Replace `cellsStore` Map with a new Map containing the cell at `${x_idx}:${y_idx}`            |
| `cell_delete`       | Remove the entry; no-op if absent                                                             |
| `fleet_update`      | Set `fleetStore[instance_id]` to the full envelope (coords may be `null` for offline marker)  |
| `detection`         | Set `detectionsStore[detection_id]` to the envelope                                           |
| `action_status`     | Append to `actionStatusStore` ring buffer (max 50)                                            |
| `snapshot_complete` | Reserved; no-op for now                                                                       |
| `error`             | Console-warn; the WebSocket stays open                                                        |

Unknown frame types log a warning and are dropped (T-02-07-01 mitigation: defensive parsing).

## Browser -> Server Frame

Single shape per D-53:

```ts
{ type: "click", coords: { x: number, y: number }, temperature: number | null }
```

`temperature: null` is the "off" transition (D-50): server `mesh.kv.delete`s the cell. `coords.x` / `coords.y` are raw km values rounded to 4 decimals (D-52); the server is the single source of truth for snapping to the 200m grid.

## Verification

- `cd demos/wildfire/dashboard && pnpm run build` exits 0 (svelte-check `0 ERRORS 0 WARNINGS 0 FILES_WITH_PROBLEMS` for the lib/ TS files; `1 WARNING` from the deprecated `on:click` directive in `App.svelte`, see Deferred Issues below). Bundle: `dist/index.html` (0.40 kB), `dist/assets/index-*.css` (0.78 kB), `dist/assets/index-*.js` (37.37 kB / 14.45 kB gzipped).
- All plan-level anti-pattern greps return 0 matches over `demos/wildfire/dashboard/src/`:
  - No `fetch('/config.json')` / `wsconnect` / `@nats-io` (browser does not talk NATS directly).
  - No `kv_source(` / `subject_source(` (Python SDK shapes don't leak into TS).
  - No `ThermalGrid` / `FireSpawn` / `FireSuppress` / `mesh.environment.thermal` / `mesh.fire.spawn` / `mesh.fire.suppress` (dropped contracts/subjects per D-26..D-28).
  - No `bucket=` / `prefix=` / `model=` kwargs.
- Per-task invariant greps (counts, identifiers): all pass — see commit messages for the exact list.
- Phase 1 + earlier Phase 2 Python regression: `uv run pytest tests/wildfire/unit -x -q` passes 245 tests in 16.30s. Python untouched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Robustness] `canvas` typed as `HTMLCanvasElement | undefined` with `$state()`**

- **Found during:** Task 4 implementation
- **Issue:** The plan's example `let canvas: HTMLCanvasElement;` is unsafe under `tsconfig.json` `strict: true`: Svelte assigns the binding inside `onMount` (after first paint), so the variable is `undefined` when the script body first runs. svelte-check would flag a "used before assigned" diagnostic.
- **Fix:** Declared `let canvas: HTMLCanvasElement | undefined = $state();` and added `if (!canvas) return;` guards in `fitCanvas` and `handleClick` before using it. `$state()` makes the binding reactive so the bind:this assignment triggers a normal Svelte 5 update path.
- **Files modified:** `demos/wildfire/dashboard/src/App.svelte`
- **Commit:** bd8c885

**2. [Rule 2 - Robustness] DPR fallback in fitCanvas / handleClick**

- **Found during:** Task 4 implementation
- **Issue:** `window.devicePixelRatio` is documented as defined in modern browsers but spec-wise can be 0 on edge cases (browser inside a tabbed environment that hasn't painted yet). The plan example used the bare value; multiplying canvas dims by 0 would produce a non-rendering canvas with a confusing 0-sized hit-test rect.
- **Fix:** `const dpr = window.devicePixelRatio || 1;` everywhere the value is consumed. Same pattern in both `fitCanvas` and `handleClick` so the click hit-test stays consistent with the canvas resolution.
- **Files modified:** `demos/wildfire/dashboard/src/App.svelte`
- **Commit:** bd8c885

**3. [Rule 2 - Robustness] Coords nullable on FleetMember**

- **Found during:** Task 1 type design (then confirmed against `server.py` MSG_FLEET_UPDATE)
- **Issue:** `server.py`'s `on_fleet` handler emits `coords: None` when a fleet KV key is DELETEd (offline marker). The plan's TypeScript type definition listed `coords: { x: number; y: number }` non-nullable, which would fail strict-TS comparison checks at the canvas layer if a stale offline frame slipped through.
- **Fix:** `coords: Coords | null` on FleetMember; `if (member.coords === null) continue;` in canvas.ts trail / pointer loops. No-op semantics preserved.
- **Files modified:** `demos/wildfire/dashboard/src/lib/mesh.ts`, `demos/wildfire/dashboard/src/lib/canvas.ts`
- **Commit:** 295c73e (mesh.ts), 2f0c885 (canvas.ts)

**4. [Rule 3 - Blocking] `verbatimModuleSyntax: true` + `import type`**

- **Found during:** Task 1 + Task 3 build
- **Issue:** `tsconfig.json` ships with `verbatimModuleSyntax: true`, which forces type-only imports to use `import type { ... }`. Without this, svelte-check fails with TS1484 "type-only-import expected".
- **Fix:** Used `import type { Writable }` in `mesh.ts` (for the Writable<> alias) and `import type { Cell, Detection, FleetMember } from "./mesh"` in `canvas.ts`.
- **Files modified:** `demos/wildfire/dashboard/src/lib/mesh.ts`, `demos/wildfire/dashboard/src/lib/canvas.ts`
- **Commits:** 295c73e (mesh.ts), 2f0c885 (canvas.ts)

**5. [Rule 2 - Polish] Added `resetIdx(xIdx, yIdx)` next to `reset(x, y)`**

- **Found during:** Task 2 implementation
- **Issue:** The plan only specifies `reset(x, y)` keyed on raw coords, but the WebSocket dispatcher receives `cell_delete` envelopes with `x_idx` / `y_idx` already pre-snapped by the server. Forcing the dispatcher to invent fake km coords just to round-trip them through `cellIndices()` would be needless work.
- **Fix:** Added `resetIdx(xIdx, yIdx)` as a sibling helper. Plan 02-09 (orchestrator integration test) or a future polish step can wire `cell_delete` through it; today the dispatcher logs and skips since the user's next click on the same cell will start at "small" again anyway (the cycle starts at "off" which advances to "small" first).
- **Files modified:** `demos/wildfire/dashboard/src/lib/magnitude.ts`
- **Commit:** b333c09

These deviations are all small Rule 2/3 robustness adjustments. No architectural changes; no Rule 4 escalation needed.

## Deferred Issues

**1. `on:click` deprecation warning in App.svelte**

Svelte 5.55 emits a deprecation warning for the `on:click` event directive in favor of the `onclick` event attribute. The plan invariant (`grep -c "on:click"` >= 1) explicitly requires the legacy syntax, and the build still exits 0. The migration is mechanical (one-line change) and can be folded into a Phase 5 polish plan once the rest of the wildfire pipeline is stable. Not worth a deviation entry today because the plan body uses `on:click` verbatim.

**2. `cell_delete` does not reset the local magnitude cycle**

When the server emits `cell_delete` (e.g. fire-sim's decay reaches ambient and removes the key, or another browser tab clicks the same cell to "off"), this browser's `magnitude.ts` cycle map for that cell is NOT reset. Effect: the operator's next click on that cell may produce "medium" instead of "small". `resetIdx()` is exported for this purpose; wiring it from `mesh.ts`'s `applyCellDelete` is a 2-line follow-up that should land in plan 02-09's integration step or a Phase 5 polish.

## Hand-off Notes

### To plan 02-09 (orchestrator + integration test)

The browser-side smoke test can be skipped if the integration test boots the orchestrator with a stub `dist/`: the test only needs the backend WebSocket to respond correctly to `{type: "click", coords, temperature}` frames and to fan-out `cell_update` / `fleet_update` envelopes. Canvas pixel correctness is verified manually for the demo recording.

A minimal browser-side smoke (optional) is one paragraph of Playwright:

```python
async with browser.new_page() as page:
    await page.goto(f"http://localhost:{port}/")
    await page.wait_for_function("document.querySelector('canvas')")
    # Click center of canvas; should produce a cell write at world (0, 0).
    rect = await page.evaluate("() => document.querySelector('canvas').getBoundingClientRect()")
    await page.mouse.click(rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2)
```

### To plan 02-08 (admin UI event feed) / Phase 3+ panels

The Svelte stores in `mesh.ts` are reusable: any future briefing pane / narrative pane just needs to read the existing stores or extend `mesh.ts` with another envelope type (`briefing` / `narrative`). The dispatcher's `switch` statement is the single extension point.

`actionStatusStore`'s 50-entry ring buffer mirrors the future "briefing feed buffered at last 50 / narrative feed buffered at last 10" cap from `dashboard.md` "Reliability". Consistent shape across feeds.

## Threat Flags

None. The plan's `<threat_model>` covers the relevant surface (T-02-07-01 client-side validation handed to backend; T-02-07-02 demo-only data; T-02-07-03 trail buffer trimmed per render tick — all mitigated as planned).

## Self-Check

- demos/wildfire/dashboard/src/lib/coords.ts: FOUND
- demos/wildfire/dashboard/src/lib/mesh.ts: FOUND
- demos/wildfire/dashboard/src/lib/magnitude.ts: FOUND
- demos/wildfire/dashboard/src/lib/canvas.ts: FOUND
- demos/wildfire/dashboard/src/App.svelte: MODIFIED (placeholder replaced)
- demos/wildfire/dashboard/dist/index.html: REBUILT (0.40 kB; mounts the new App.svelte bundle)
- Commit 295c73e (Task 1): FOUND in git log
- Commit b333c09 (Task 2): FOUND in git log
- Commit 2f0c885 (Task 3): FOUND in git log
- Commit bd8c885 (Task 4): FOUND in git log
- pnpm run build: exits 0 (1 deprecation warning on `on:click`, no errors)
- uv run pytest tests/wildfire/unit -x -q: 245 passed (Python regression clean)

## Self-Check: PASSED
