# Scenario UI

**Status:** discussion

The wildfire demo runs **two web UIs side by side** (see [admin-ui-integration.md](admin-ui-integration.md)):

- **Scenario UI** (this file): renders the world the agents are operating in. Map, fleet positions, incident markers, briefings, narrative. Plus the one write surface viewers care about: clicking a map cell to spawn a fire.
- **Admin UI** (ADR-0056): the OAM control plane. Agent registry, contract viewer, invocation sandbox, event feed. Operational observability of the mesh itself.

The split is deliberate. A self-contained dashboard that rendered both world view and observability in one window would invite the question "is the dashboard piloting this?" Splitting them makes the mesh's role undeniable: the admin UI shows the message cascade independently of the scenario UI; both react to the same subjects.

## Purpose

Render the simulated world. Read-only consumer of mesh subjects, plus one user-driven write surface (fire spawn). The scenario UI does not show agent counts, message volumes, contracts, or other mesh-internal state. That belongs to the admin UI.

## Stack

- FastAPI backend connected to the mesh as a NATS subscriber-only + minimal-publisher client.
- WebSocket from backend to browser for live updates.
- Frontend: minimal HTMX or vanilla JS with a 2D canvas map. **No React**; the admin UI carries the React stack so the scenario UI stays a featherweight contrast.

## Inputs (mesh subjects subscribed)

- `mesh.environment.thermal` -> heat map render.
- `mesh.detection.thermal` -> UAV detection markers (transient flashes).
- `mesh.survey.>` -> drone survey results, render at coords.
- `mesh.briefing.>` -> briefing feed (paragraph blocks).
- `mesh.medevac.>.status` -> medevac trails on map.
- `mesh.swarm.narrative` -> narrative feed (5-min summaries).
- `mesh.fire.>.intent` -> firefighter command audit log (small ticker, optional).

Notably **not** subscribed: `mesh.swarm.stats`. Counter-style aggregates live in the admin UI.

## Outputs (mesh subjects published)

- `mesh.fire.spawn` (or similar) -> the user clicked a map cell. Carries `(coords, magnitude)`. The fire-sim subscribes and adds a hotspot to its grid.
- `mesh.chaos.kill` (optional) -> the user clicked an "X" on a fleet pointer to kill that instance. Targeted agent subscribes and self-terminates. This is a scenario action, not a control-plane action; it stays in the scenario UI.

These two are the only mesh writes from the scenario UI. The browser does not connect to NATS directly; the FastAPI backend holds the mesh client and the browser POSTs JSON to small endpoints.

## Views

- **Map (primary, full-width).** 2D top-down canvas. Layers: heat map (thermal grid, semi-transparent quads), fire spread, UAV positions + sweep paths, drone positions + trails, medevac routes, incident markers.
- **Briefing feed (right panel).** Chronological, severity badges. The human-readable LLM output is part of the scenario story, not control-plane data.
- **Narrative feed (right panel, below briefings).** 5-min paragraph blocks.

That's it. No counter strip, no agent list, no message volume, no subject feed. Those are the admin UI's job.

## Interactions

- **Click map cell -> spawn fire.** The cell's coords are published as a fire-spawn event. Fire-sim picks it up and adds a hotspot. The cascade reacts. This is the demo's authenticity proof: any viewer can drive the cascade live.
- **Click a fleet pointer -> small popover.** Shows the agent's name and ID; offers a "Kill this agent" button. Clicking it publishes a chaos event; admin UI's liveness indicator turns red within seconds.
- **Click incident marker -> focus map.** Pure UI, no mesh round-trip.

## Lifecycle

- Independent process: `uv run python -m demos.wildfire.scenario_ui`. Default port 8081 (admin UI on 4223 per ADR-0056).
- Connects to the same NATS as the fleets and the admin UI.
- One-command demo startup (`agentmesh wildfire up`) boots embedded NATS, fleets, scenario UI, admin UI in one shot.

## Reliability

- Pure consumer + tiny publisher. If the scenario UI dies the simulation continues; restart and it rebuilds the map from current subscriptions.
- Buffered feeds capped at last 50 briefings / last 10 narratives.

## Behaviour notes

- Map renderer: cheapest viable. Plain canvas + coords-to-pixels math. No tile provider, no map library.
- Heat map: thermal grid as semi-transparent colored quads, temperature -> color.
- Drone trails: limited to last 30s of positions.
- Fleet pointers: small icons keyed by fleet type (UAV triangle, drone dot, medevac square, firefighter cross).
- Map click area uses a coarse cell grid (e.g. 1km cells) so a click maps to one fire-sim cell unambiguously.

## Open questions

- Is the chaos kill button on the scenario UI (in-world) or on the admin UI (control-plane)? Current lean: scenario UI, because killing a unit "in world" is a scenario action; the admin UI then SHOWS the consequence (liveness dot, message feed). Splits the demo nicely.
- Does the scenario UI need an "explainer overlay" for first-time viewers ("click here to spawn a fire")? Probably yes; small, dismissible.
- Frame rate: 30 fps canvas redraws sufficient? Likely yes for a coarse 2D scene.

## Subject contracts

Read-only consumer of all event subjects in the ADR-0054 frozen subject map. Two new outbound subjects (fire-spawn, chaos-kill) need to be added to the ADR-0054 subject map and frozen contracts when they crystallize.

## SDK shape needed

- A NATS subscriber-only client with minimal publisher capability. Today's `AgentMesh()` works as a subscriber + publisher of arbitrary subjects, once SDK desideratum #2 (`mesh.publish(subject, model)`) lands.
- Multi-subject subscription: today's `mesh.subscribe(subject="...")` is single-subject; the scenario UI runs N background tasks. Acceptable; a glob source helper would be cleaner but is not blocking.
