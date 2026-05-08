# Dashboard (web UI)

**Status:** discussion

## Purpose

Single-page web UI rendering the live state of the mesh. Read-only consumer of mesh subjects (no write surface in v1, except the chaos button). The dashboard is what makes the demo legible to a non-technical viewer.

## Stack

- FastAPI backend that connects to the mesh as a NATS subscriber-only client.
- WebSocket from backend to browser for live updates.
- Frontend: minimal HTMX or vanilla JS with a 2D map renderer. **No React.**
- See ADR-0056 for the OAM Admin UI; this dashboard is scenario-specific, not the admin UI.

## Inputs (mesh subjects subscribed)

- `mesh.environment.thermal` (heat map render).
- `mesh.detection.thermal` (UAV detection markers).
- `mesh.survey.>` (drone survey results, photo metadata).
- `mesh.briefing.>` (briefing feed).
- `mesh.medevac.>.status` (medevac trails on map).
- `mesh.swarm.stats` (counter strip).
- `mesh.swarm.narrative` (paragraph feed).
- `mesh.fire.>.intent` (firefighter command audit log).

## Views

- **Map (primary).** 2D top-down. Layers: heat map (thermal grid), fire spread, UAV positions + sweep paths, drone positions + trails, medevac routes, incident markers.
- **Incident list.** From KV reads, with state transitions. Click to focus map.
- **Briefing feed.** Chronological, with severity badges.
- **Narrative feed.** Paragraph blocks every 5 min.
- **Counter strip.** Horizontal: drones active, incidents open, persons recovered, fires detected.

## Interactions

- **Kill-an-agent button.** Publishes a chaos event (`mesh.chaos.kill {target_id}`) that targeted agents subscribe to and self-terminate. Demonstrates fault tolerance live.
- **Click incident -> focus map.** Pure UI, no mesh round-trip.
- Optional v2: "spawn a hotspot" button that posts to fire-sim. Out of scope v1.

## Lifecycle

- Independent process: `uv run python -m demos.wildfire.dashboard`. Default port `8080`.
- Connects to the same NATS as the fleets. No KV writes in v1.

## Reliability

- Pure consumer. If the dashboard dies the simulation continues; restart and it picks up the live state on reconnect.
- Buffer size for feeds: capped (e.g. last 100 briefings) to prevent memory growth.

## Behaviour notes

- Map renderer: cheapest viable. Either canvas + plain coords-to-pixels, or a tiny Leaflet stub with a synthetic tile (since coords are simulated). Lean canvas; no map provider, no auth.
- Heat map: render thermal grid as semi-transparent colored quads keyed to temperature.
- Drone trails: limited to last 30s positions to avoid clutter.
- Status updates pushed via WebSocket from the FastAPI backend, which translates mesh messages into JSON events the frontend consumes.

## Open questions

- Does the dashboard validate Pydantic models, or does it consume raw JSON dicts? Raw JSON simpler for the JS frontend; the FastAPI backend can validate at ingress for safety.
- Authentication / sharing: out of scope v1 (laptop only). Public hosted variant per ADR-0054 will need auth (gated on ADR-0038).
- What does the dashboard show before any events arrive? Empty state with explanatory copy ("Waiting for fire-sim to start...").

## Subject contracts

Read-only consumer of all subjects in the ADR-0054 frozen subject map. Renders the chaos publish path once defined.

## SDK shape needed

- A NATS subscriber-only client that connects to the same mesh URL but registers no agents. Today's `AgentMesh()` works as a subscriber if you do not register handlers; document the pattern.
- Multi-subject subscription is the primary need: today's `mesh.subscribe(subject="...")` is single-subject. The dashboard wires N background tasks, one per subject pattern. Acceptable; no SDK change strictly required, but a `subscribes=[...]` glob would be cleaner (SDK desideratum #1).
