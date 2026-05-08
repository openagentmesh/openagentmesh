# Scenario UI

**Status:** discussion

> **Amended 2026-05-09** — stack pivots to Svelte 5 + Vite + plain HTML canvas + FastAPI + WebSocket. The "no React / minimal HTMX or vanilla JS" wording is dropped: side panels are stream-driven scrolling lists where reactive primitives are the cleanest fit, and Vite + pnpm tooling already exists in the repo for the admin UI. The dashboard is a real demo app, not a cookbook copy-paste recipe (REC-02 cookbook covers SDK patterns separately). Click → world-state pivot: clicks now write `CellState` records to KV directly via the dashboard backend; no more `mesh.fire.spawn` / `mesh.fire.suppress` pubsub. See ADR-0054 amended subject + KV map and `fire-sim.md` for the pure-KV world grid.

The wildfire demo runs **two web UIs side by side** (see [admin-ui-integration.md](admin-ui-integration.md)):

- **Scenario UI** (this file): renders the world the agents are operating in. Map, fleet positions, incident markers, briefings, narrative. Plus the one write surface viewers care about: clicking a map cell to spawn (or cool) a fire.
- **Admin UI** (ADR-0056): the OAM control plane. Agent registry, contract viewer, invocation sandbox, event feed. Operational observability of the mesh itself.

The split is deliberate. A self-contained dashboard that rendered both world view and observability in one window would invite the question "is the dashboard piloting this?" Splitting them makes the mesh's role undeniable: the admin UI shows the message cascade independently of the scenario UI; both react to the same mesh state.

## Purpose

Render the simulated world. Read-only consumer of mesh state (KV cell + fleet namespaces, status pubsub), plus one user-driven write surface (per-cell click). The scenario UI does not show agent counts, message volumes, contracts, or other mesh-internal state. That belongs to the admin UI.

## Stack

- **FastAPI** backend connected to the mesh as a NATS client (kv_source on world cells + fleet namespace; subject_source on status pubsub; `mesh.kv.put` / `mesh.kv.delete` for click writes).
- **WebSocket** from backend to browser for live updates and click events. Bidirectional fits read + write on one connection. JSON message protocol with a discriminated `{type, ...}` envelope.
- **Frontend: Svelte 5 + Vite + TypeScript + plain HTMLCanvas.** Side panels use Svelte reactive components fed by stores (briefing pane Phase 3, narrative pane Phase 4); the canvas is hand-rolled (heat layer, fleet pointers, drone trails). pnpm + Vite same toolchain as `ui/` (admin UI). Bundle output at `demos/wildfire/dashboard/dist/` (gitignored); FastAPI mounts it as static files. The admin UI uses React + nats.ws (per ADR-0056 amended); the dashboard uses Svelte + FastAPI: two narratives, two stacks, both supported.
- **No design-system dependency.** Tailwind optional; plain CSS works at this scope.

## Inputs (mesh state subscribed)

- `wildfire.world.cell.*` (KV-watch) → heat layer renders. Each cell update (or delete) is a discrete event; backend projects to browser. Sparse: ambient cells have no key.
- `wildfire.fleet.>` (KV-watch) → fleet pointers (UAV, drones, helis, ffunits, medevacs). Per-instance position + state from `FleetMemberState`.
- `wildfire.detection.*` (KV-watch) → detection markers (transient flashes when `state=pending`, persistent when `surveyed`).
- `mesh.action.>.*.status` (subject) → action-fleet status feed (heli / ffunit / medevac transitions).
- `mesh.briefing.>` (subject) → briefing feed (paragraph blocks). Phase 3.
- `mesh.swarm.narrative` (subject) → narrative feed (5-min summaries). Phase 4.
- `mesh.fire.>.intent` (subject) → firefighter command audit ticker (small, optional).

Notably **not** subscribed: `mesh.swarm.stats`. Counter-style aggregates live in the admin UI.

## Outputs (mesh writes from the scenario UI backend)

- KV write: `wildfire.world.cell.<x_idx>.<y_idx>` carrying `CellState(coords, temperature, last_modified_at, last_modified_by)` — on map click. The `last_modified_by` is the dashboard backend's `mesh.instance_id`; fire-sim's self-write filter doesn't trip (fire-sim filters on its own id).
- KV delete: `wildfire.world.cell.<x_idx>.<y_idx>` — on map click into the "off" state of the cycle. Equivalent to suppression. Same path as action-fleet cooling; no separate contract needed.
- Pubsub publish: `mesh.chaos.kill.{instance_id}` — when the user clicks an "X" on a fleet pointer to kill that instance. Phase 4.

The browser does not connect to NATS directly; the FastAPI backend holds the mesh client and the browser sends typed JSON over WebSocket. The mesh API surface stays uniform (KV writes / pubsub) regardless of which UI made the call.

## Views

- **Map (primary, full-width).** 2D top-down canvas. Layers: heat layer (cells from `wildfire.world.cell.*`, semi-transparent quads keyed by temperature), fleet pointers (from `wildfire.fleet.>`), incident markers (from `wildfire.detection.*` and Phase 3 briefings), drone/medevac trails (last 30 s of position history).
- **Briefing feed (right panel).** Chronological, severity badges. Phase 3.
- **Narrative feed (right panel, below briefings).** 5-min paragraph blocks. Phase 4.

That's it. No counter strip, no agent list, no message volume, no subject feed. Those are the admin UI's job.

## Interactions

- **Click map cell → cycle through magnitudes.** Per-cell click state in the browser cycles `small (≈200 °C) → medium (≈500 °C) → large (≈800 °C) → off`. Each click sends a `{type: "click", coords, temperature_or_null}` WebSocket message to the backend, which writes (or deletes) the corresponding `CellState` KV record. fire-sim's kv_source picks it up, integrates into the in-process grid, runs subsequent ticks. Magnitude defaults are tunable in `core/config.py` (`SPAWN_MAGNITUDE_SMALL` / `_MEDIUM` / `_LARGE`).
- **Click a fleet pointer → small popover.** Shows the agent's name and ID; offers a "Kill this agent" button. Clicking it publishes `mesh.chaos.kill.{instance_id}`; admin UI's liveness indicator turns red within seconds. Phase 4.
- **Click incident marker → focus map.** Pure UI, no mesh round-trip.

## Lifecycle

- Independent process: `python -m demos.wildfire.dashboard` runs the FastAPI app + uvicorn server programmatically. Default port **8081**, with auto-fallback to the next free port if 8081 is occupied. Always prints the resolved URL on boot. Configurable via `--port` flag.
- Module home: `demos/wildfire/dashboard/`. Internal layout: `__main__.py` (uvicorn entry), `server.py` (FastAPI + mesh client + WebSocket endpoint), `package.json` + `vite.config.ts` + `src/` (Svelte source), `dist/` (build output, gitignored).
- Connects to the same NATS as the fleets and the admin UI (same env-var resolution as the rest of the demo).
- Orchestrator-supervised: `demos/wildfire/__main__.py` boots embedded NATS, fleet processes, dashboard, admin UI in one shot. One-command demo via `python -m demos.wildfire`.
- Build step: `pnpm install && pnpm run build` from `demos/wildfire/dashboard/`. Output at `dist/index.html` etc., gitignored. Backend startup checks for `dist/index.html`; if missing, prints `run pnpm run build in demos/wildfire/dashboard/` and exits non-zero. CI pipeline (Phase 5 / release infra) runs the build at publish time.

## Reliability

- Pure consumer + tiny publisher. If the dashboard dies the simulation continues; restart and it rebuilds the map from current KV state via `kv.list("wildfire.world.cell.>")` + `kv.list("wildfire.fleet.>")`.
- Buffered feeds capped at last 50 briefings / last 10 narratives.

## Behaviour notes

- Map renderer: cheapest viable. Plain HTMLCanvas + 2D context, coords-to-pixels math, no tile provider, no map library.
- Heat layer: `CellState.temperature` → semi-transparent colored quad keyed by temperature. Ambient cells (no KV key) render as background.
- Drone trails: last 30 s of positions kept in browser-side state; older entries dropped.
- Fleet pointers: small icons keyed by fleet type (UAV triangle, drone dot, heli circle-with-rotor, ffunit cross, medevac square).
- Pixel → km mapping: continuous (round to 4 decimals); backend snaps to the 200 m cell grid before writing the `CellState` KV record. Single source of truth for cell snapping (server-side).
- No click rate-limit; trust the viewer (recording cadence is one fire every few seconds anyway).
- Frame rate: 30 fps canvas redraws sufficient for a coarse 2D scene.

## Open questions

- Is the chaos kill button on the scenario UI (in-world) or on the admin UI (control-plane)? Current lean: scenario UI, because killing a unit "in world" is a scenario action; the admin UI then SHOWS the consequence (liveness dot, message feed). Splits the demo nicely.
- Does the scenario UI need an "explainer overlay" for first-time viewers ("click here to spawn a fire; click again to escalate; click again to cool")? Probably yes; small, dismissible.

## Subject + KV contracts

The dashboard backend reads:
- `wildfire.world.cell.*` (KV) — per-cell `CellState` (added in ADR-0054 amendment).
- `wildfire.fleet.>` (KV) — `FleetMemberState`.
- `wildfire.detection.*` (KV) — `DetectionRecord`.
- `mesh.action.>.*.status` — fleet status pubsub.
- `mesh.briefing.>` — Phase 3.
- `mesh.swarm.narrative` — Phase 4.

The dashboard backend writes:
- `wildfire.world.cell.<x_idx>.<y_idx>` (KV) — on click.
- `mesh.chaos.kill.{instance_id}` (subject) — on chaos kill (Phase 4).

## SDK shape needed

- A NATS client that subscribes to multiple KV namespaces and subject patterns. Today's `AgentMesh()` works; the dashboard backend uses kv_source / subject_source declarative bindings as a regular `mesh.agent`-style consumer.
- `mesh.kv.put(key, model)` and `mesh.kv.delete(key)` (ADR-0060) for click writes.
- `mesh.publish(subject, model)` (ADR-0058) for chaos kill events.
- All shipped on main as of 2026-05-08.
