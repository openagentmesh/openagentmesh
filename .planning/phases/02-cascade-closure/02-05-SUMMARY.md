---
phase: 02-cascade-closure
plan: 05
subsystem: wildfire-demo
tags: [dashboard, fastapi, websocket, kv-source, click-handler, server-side-snap, uvicorn]
requires:
  - 02-01  # CellState + DASHBOARD_PORT + SPAWN_MAGNITUDE_* live in core/contracts.py + core/config.py
  - 01-02  # mesh-context single-bucket + wildfire.world.cell.* namespace
provides:
  - demos.wildfire.dashboard.server.make_app
  - demos.wildfire.dashboard.server.register_mesh_consumers
  - demos.wildfire.dashboard.server.handle_click
  - demos.wildfire.dashboard.server.MSG_CELL_UPDATE
  - demos.wildfire.dashboard.server.MSG_CELL_DELETE
  - demos.wildfire.dashboard.server.MSG_FLEET_UPDATE
  - demos.wildfire.dashboard.server.MSG_DETECTION
  - demos.wildfire.dashboard.server.MSG_ACTION_STATUS
  - python -m demos.wildfire.dashboard
affects:
  - 02-06  # frontend scaffold consumes the WS message protocol locked here
  - 02-07  # frontend wiring uses MSG_* constants + click frame shape
  - 02-09  # orchestrator extension supervises `python -m demos.wildfire.dashboard`
tech-stack:
  added:
    - fastapi>=0.115.0       # WebSocket + ASGI app
    - uvicorn[standard]>=0.32.0  # ASGI server (programmatic Server.serve)
    - httpx>=0.27.0          # FastAPI TestClient backend (dev group)
  patterns:
    - "kv_source(f'{PREFIX}.>') for two- and three-segment KV namespaces"
    - "subject_source('mesh.action.>') for cross-fleet status pubsub"
    - "Pure-function click handler (handle_click) decoupled from WebSocket loop for testability"
key-files:
  created:
    - demos/wildfire/dashboard/__init__.py
    - demos/wildfire/dashboard/server.py
    - demos/wildfire/dashboard/__main__.py
    - tests/wildfire/unit/test_dashboard_server.py
  modified:
    - pyproject.toml         # wildfire-dashboard optional-deps extra + dev group fastapi/uvicorn/httpx
    - uv.lock                # pinned fastapi/uvicorn/httpx + transitives
decisions:
  - "Click handler is a top-level async function (handle_click), not a method; lets unit tests exercise it without a real WebSocket connection."
  - "Ambient-temperature clicks (temperature == FIRE_SIM_AMBIENT_C) are treated equivalently to temperature=null per D-50; both delete the key."
  - "Out-of-bounds clicks reject with a Pydantic ValidationError and surface as an {type: error, reason: invalid_coords} frame; the WS connection survives (T-02-05-01)."
  - "Mesh consumers register under 'dashboard.*-feed' channel names so the admin UI catalog renders them as observability components, not scenario agents."
  - "DELETE tombstones in the KV history surface as empty-value PUTs in nats-py; tests filter by truthy value rather than relying on operation flags."
metrics:
  duration: 7m 42s
  completed: 2026-05-09
  tasks_completed: 2
  files_changed: 6
---

# Phase 2 Plan 5: Dashboard FastAPI + WebSocket Backend Summary

Wires the scenario UI dashboard backend: a FastAPI app launched via `python -m demos.wildfire.dashboard` that connects to NATS as an `AgentMesh()` client, watches the four namespaces the browser cares about (`wildfire.world.cell.>`, `wildfire.fleet.>`, `wildfire.detection.*`, `mesh.action.>`), and exposes one bidirectional WebSocket endpoint that fans out updates and accepts click writes.

## What Landed

### `demos/wildfire/dashboard/server.py` (~360 LOC)

Three top-level entry points the rest of the demo consumes:

1. **`make_app(mesh: AgentMesh) -> FastAPI`**: builds the FastAPI app. Routes:
   - `GET /health` returns `{status: "ok", mesh_instance_id, connections}`.
   - `WS /ws` accepts a click frame, snaps coords to the 200m grid, writes or deletes the cell key, and fans out cell/fleet/detection/action_status envelopes to every connected socket. Malformed JSON is logged and dropped; unknown `type` values are warned and skipped; `WebSocketDisconnect` is the normal exit path.
   - `GET /` static-mounts `demos/wildfire/dashboard/dist/` if present (no-op if absent — `__main__` guards presence at boot).

2. **`register_mesh_consumers(mesh, broadcast)`**: four `@mesh.agent` registrations (`dashboard.cell-feed`, `dashboard.fleet-feed`, `dashboard.detection-feed`, `dashboard.action-feed`) whose source bindings translate KV/pubsub events into the WebSocket envelopes:
   - `mesh.kv_source(f"{CELL_PREFIX}.>", on_init="replay")` — two trailing segments demand `.>` (carry-forward of plan 01-10's wildcard segment-count bug).
   - `mesh.kv_source(f"{FLEET_PREFIX}.>", on_init="replay")` — three trailing segments; same `.>` rule.
   - `mesh.kv_source(f"{DETECTION_PREFIX}.*", on_init="replay")` — one trailing segment; `.*` is correct.
   - `mesh.subject_source("mesh.action.>")` — pubsub for HeliStatus/FFUnitStatus/MedevacStatus.

3. **`handle_click(mesh, *, x, y, temperature)`**: pure click write path, decoupled from the WebSocket loop so unit tests exercise it directly. Server-side grid snap (D-52: `cell_indices` + `cell_center` are the only authority for cell-key derivation); ambient or null temperature deletes the key (D-50, sparse-KV invariant); `last_modified_by = mesh.instance_id` so fire-sim's self-write filter does not skip these writes (it only skips its own deltas).

The five `MSG_*` constants are exported as named module attributes so the 02-09 integration test can reference them by name (no magic strings).

### `demos/wildfire/dashboard/__main__.py` (~150 LOC)

`python -m demos.wildfire.dashboard` boot path:

1. `_verify_dist_or_exit()`: fail fast with stderr `"dashboard bundle missing: run pnpm run build in demos/wildfire/dashboard/"` and `sys.exit(2)` if `dist/index.html` is absent (D-36). Runs before any NATS connection attempt.
2. `find_free_port(host, requested, max_walk=100)`: probes `socket.bind()` and walks +1, +2, ... up to +100; raises `RuntimeError` on exhaustion (D-39). Mirrors `src/openagentmesh/_local.py:_free_port`.
3. `AgentMesh(NATS_URL)` (default `nats://127.0.0.1:4222`).
4. `make_app(mesh)` + `register_mesh_consumers(mesh, app.state.broadcast)` + `mesh._subscribe_pending()` so the four source bindings activate against the live mesh.
5. Print `dashboard at http://<host>:<port>` to stdout (D-39).
6. `uvicorn.Server.serve()` with SIGTERM/SIGINT clean-shutdown via `asyncio.Event` and `server.should_exit`. Matches the orchestrator's `Popen.terminate()` flow.

`main(argv)` argparse exposes `--host` (default `127.0.0.1`, T-02-05-03 mitigation) and `--port` (default `DASHBOARD_PORT = 8081`).

### `tests/wildfire/unit/test_dashboard_server.py` (~390 LOC)

17 tests, all green:

- 5 click-handler tests: write CellState, delete on null, delete on ambient, exact grid snap (`(1.234, -2.789) -> cell_center(cell_indices(...))`), delete-of-absent-key is a no-op.
- 1 kv_source replay test: write a CellState, observe a `cell_update` envelope on the broadcaster.
- 5 source-text gates: every `kv_source(...)` pattern ends in `.>` or `.*`; `subject_source("mesh.action.>")` is wired; legacy contract names absent; `bucket=`/`prefix=`/`model=` kwargs absent (A-09); plan-body grep invariants mirrored.
- 2 protocol-constant + /health tests.
- 4 `__main__` tests: `find_free_port` returns requested when free, walks when busy; `main` is callable; source-text gates for `__main__.py`.

### `pyproject.toml`

Added `[project.optional-dependencies] wildfire-dashboard = [fastapi, uvicorn[standard]]` so a downstream packager can opt in. Added the same plus `httpx>=0.27.0` to the `dev` group so `uv run pytest` exercises the FastAPI TestClient without an extra flag.

## WebSocket Message Protocol (Final, locked for plans 02-06 / 02-07 / 02-09)

### Browser -> Server

```json
{
  "type": "click",
  "coords": {"x": <float>, "y": <float>},
  "temperature": <float | null>
}
```

`temperature: null` (or `temperature == FIRE_SIM_AMBIENT_C`, which is `25.0` from `core.config`) maps to a delete. The browser cycles magnitudes locally per D-49; the server treats whatever arrives as authoritative. The server is the only place that translates `(x, y)` to a cell key (D-52).

### Server -> Browser

```json
{"type": "cell_update", "coords": {"x", "y"}, "temperature", "x_idx", "y_idx"}
{"type": "cell_delete", "x_idx", "y_idx"}
{"type": "fleet_update", "instance_id", "zone", "fleet_type", "coords", "state",
 "current_assignment", "last_updated"}
{"type": "detection", "detection_id", "coords", "severity", "state"}
{"type": "action_status", "subject", "payload"}
```

`payload` on `action_status` is the JSON-decoded body of the published model (HeliStatus / FFUnitStatus / MedevacStatus); the browser dispatches by `subject`.

`MSG_SNAPSHOT_COMPLETE = "snapshot_complete"` is exported for plan 02-07's snapshot-drain UX but is not yet emitted by this plan (kv_source `on_init="replay"` semantics deliver replay synchronously before live updates; a marker frame can be added later if the canvas needs an explicit "ready" signal).

## Server-Side Grid Snap Authority

Confirmed: `handle_click` is the ONLY code path that derives cell keys from raw click coords. The browser sends continuous floats (rounded to 4 decimals per D-52); the server projects them onto the 200m grid via `cell_indices(x, y)` -> `cell_center(x_idx, y_idx)` and writes `CellState.coords` as the snapped center. fire-sim and every other writer reads the canonical center from KV; the raw click float never persists.

## Hand-off Notes

### To Plan 02-06 (frontend scaffold)

The five message-type constants are exported from `demos.wildfire.dashboard.server`:

```python
MSG_CELL_UPDATE      = "cell_update"
MSG_CELL_DELETE      = "cell_delete"
MSG_FLEET_UPDATE     = "fleet_update"
MSG_DETECTION        = "detection"
MSG_ACTION_STATUS    = "action_status"
MSG_SNAPSHOT_COMPLETE = "snapshot_complete"
```

The Svelte 5 / TypeScript bundle should mirror these as a discriminated union and dispatch on the `type` tag. The build output goes to `demos/wildfire/dashboard/dist/`; if `dist/index.html` is absent, the backend exits 2 with a clear pnpm hint, so the frontend scaffold MUST include a working `pnpm run build` flow before plan 02-06 can be considered done.

### To Plan 02-07 (frontend wiring)

Click frame shape (the only thing the browser sends):

```ts
interface ClickFrame {
  type: "click";
  coords: { x: number; y: number };  // continuous km coords, rounded to 4 decimals
  temperature: number | null;         // null OR <= FIRE_SIM_AMBIENT_C (25.0) deletes
}
```

The browser's per-cell magnitude cycle (small=200, medium=500, large=800, off=null) is browser-side only. The server is unaware of "the cycle"; it just writes whatever temperature arrives.

### To Plan 02-09 (orchestrator extension)

Entry point:

```bash
python -m demos.wildfire.dashboard --host 127.0.0.1 --port 8081
```

The orchestrator should `Popen` it like the other demo subprocesses. Default port is `DASHBOARD_PORT = 8081` from `core.config`; the boot path auto-walks if busy and prints the resolved URL on stdout (parse it from the child's stdout if you want the actual port; otherwise probe `/health`).

The dashboard backend exits 2 with a stderr message if `dist/index.html` is absent. The orchestrator should treat this as "expected during dev iteration" rather than a crash; the viewer can run `pnpm run build` and the orchestrator will pick up the bundle on next boot.

`SIGTERM` / `SIGINT` shut down cleanly via `server.should_exit = True` plus `asyncio.Event` wakeup.

## Deviations from Plan

**1. [Rule 3 — Blocking] Add `wildfire-dashboard` optional-deps extra + dev group fastapi/uvicorn/httpx**

- **Found during:** Task 1 RED setup.
- **Issue:** Neither `fastapi` nor `uvicorn` was installed in the worktree's `.venv`; the test file's `from fastapi.testclient import TestClient` import would fail at collection.
- **Fix:** Added `[project.optional-dependencies] wildfire-dashboard = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0"]` (also a project-level success criterion) plus `httpx>=0.27.0` (FastAPI TestClient backend) to the `dev` dependency group. Ran `uv sync` to install.
- **Files modified:** `pyproject.toml`, `uv.lock`.
- **Commit:** d224dcc (rolled into the RED commit since the deps gate test collection).

**2. [Rule 1 — Bug] `mesh.kv.list_models` chokes on DELETE tombstones**

- **Found during:** Task 1 GREEN.
- **Issue:** The unit test for `test_click_with_null_temperature_deletes_cell` initially used `mesh.kv.list_models(prefix, CellState)` to assert the cell was gone. nats-py's KV history surfaces a delete tombstone as an entry with empty bytes `b''` and `operation="PUT"`; `model_validate_json(b'')` raised. Confirmed empirically that the SDK's `list_models` is unsafe in the presence of deletes.
- **Fix:** Tests use raw `mesh.kv.list(prefix)` and a local `_live_cell_entries` helper that skips entries with falsy values. The dashboard implementation itself is unaffected (it consumes KV via `kv_source` watchers, which the SDK already handles correctly for DELETE ops). Logged as a follow-up item: the SDK's `list_models` should either skip empty values or surface a separate `list_live_models` variant. Out of scope for this plan; not added to `deferred-items.md` since this plan does not own the SDK surface.
- **Files modified:** `tests/wildfire/unit/test_dashboard_server.py`.
- **Commit:** c901a96 (rolled into the Task 1 GREEN commit).

## Threat Mitigations Applied

Per the plan's `<threat_model>`:

| Threat ID | Mitigation in code |
|-----------|---------------------|
| T-02-05-01 (Tampering: out-of-bounds click coords) | `Coords(x=x, y=y)` Pydantic validation in `handle_click`; `ValidationError` caught in the WS loop and turned into `{type: "error", reason: "invalid_coords"}` without dropping the connection. |
| T-02-05-03 (Information Disclosure: 0.0.0.0 bind) | `--host` default is `127.0.0.1`; help text documents the LAN-binding opt-in. |
| T-02-05-04 (Spoofing: forged instance_id) | Click handler IGNORES any browser-supplied instance_id and always writes `last_modified_by = mesh.instance_id`. |
| T-02-05-05 (Path traversal in static mount) | FastAPI `StaticFiles` rejects `..` traversal by default; relied on. |

T-02-05-02 (DoS via click flood) and T-02-05-06 (rogue mesh client forging CellState) accepted per the threat register; deferred to a future enterprise hardening ADR.

## Self-Check: PASSED

Files exist:
- FOUND: `demos/wildfire/dashboard/__init__.py`
- FOUND: `demos/wildfire/dashboard/server.py`
- FOUND: `demos/wildfire/dashboard/__main__.py`
- FOUND: `tests/wildfire/unit/test_dashboard_server.py`

Commits exist (verified via `git log --oneline`):
- FOUND: d224dcc (RED — failing tests + deps)
- FOUND: c901a96 (Task 1 GREEN — server.py + __init__.py)
- FOUND: a572639 (Task 2 GREEN — __main__.py)

Plan invariants:
- `make_app` count: 1
- `WebSocket` count: 20
- `mesh.kv_source(` count: 3
- `mesh.subject_source(` count: 1
- `mesh.kv.put_model(` count: 1
- `mesh.kv.delete(` count: 1
- `wildfire.world.cell.>` count: 1
- `wildfire.fleet.>` count: 1
- Banned kwargs (`bucket=`/`prefix=`/`model=`): 0
- Legacy contracts (`ThermalGrid`/`FireSpawn`/`FireSuppress`/`mesh.environment.thermal`/`mesh.fire.spawn`/`mesh.fire.suppress`): 0
- `find_free_port` count in `__main__`: 2
- `uvicorn` count in `__main__`: 9
- `DASHBOARD_PORT` count in `__main__`: 5
- `pnpm run build` count in `__main__`: 2

Smoke test:
- `timeout 5 uv run python -m demos.wildfire.dashboard` -> `dashboard bundle missing: run pnpm run build in demos/wildfire/dashboard/` (expected non-zero exit; PASSED).

Test suite:
- `uv run pytest tests/wildfire/unit/test_dashboard_server.py -q`: 17 passed.
- `uv run pytest tests/wildfire/unit -q` (Phase 1 + Phase 2 regression): 169 passed.
