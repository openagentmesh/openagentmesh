# Wildfire demo specs

Detailed per-component specs for the demo defined in [ADR-0054](../../adr/0054-wildfire-incident-response-demo.md).

ADR-0054 is the high-level decision: scenario lock, frozen contracts, frozen subject map, scope fences. This folder is where the per-agent behaviour, the UI surface, and the SDK requirements that bubble up are shaped iteratively. Files here may reach `decided` independently; ADR-0054 stays the umbrella reference.

## Agents

Agents are organized by altitude/zone channel, with action fleets dispatched via queue group and singleton coordinators (briefer, tasker, narrator, ticker) running once per scenario.

**Intelligence + observation:**

- [Fire simulator](fire-sim.md) (`fire-sim`): publishes the thermal grid that drives the cascade.
- [UAV high-altitude](uav.md) (`high-alt.uav`): wide-area thermal surveillance; writes pending detections to KV.
- [Drone low-altitude](drone.md) (`low-alt.drone`): KV-driven election; closest free drone surveys each detection.

**Action fleets** (queue-grouped dispatch from operator):

- [Heli low-altitude water-bomber](heli.md) (`low-alt.heli`): aerial fire suppression by water drop.
- [Ground firefighter unit](ffunit.md) (`ground.ffunit`): on-site fire suppression.
- [Medevac](medevac.md) (`ground.medevac`): people recovery.

**LLM peers + reporting:**

- [Briefer](briefer.md) (`briefer`): correlates detections + surveys into incident briefings.
- [Tasker](tasker.md) (`tasker`): translates operator NL into typed `TaskCommand`.
- [Stats ticker](stats-ticker.md) (`stats-ticker`): aggregate fleet/incident counters every 10s.
- [Narrator](narrator.md) (`narrator`): 5-minute paragraph summaries.

**Human in the loop:**

- [Firefighter operator CLI](firefighter.md): plain caller process, drives dispatch decisions for action fleets.

## UIs

The demo runs two UIs side by side; see [admin-ui-integration.md](admin-ui-integration.md) for why.

- [Scenario UI](dashboard.md): world view (map, fleet pointers, briefings, narrative) plus map-click fire spawn and chaos-kill. Read-mostly mesh consumer.
- [Admin UI integration](admin-ui-integration.md): pairing with ADR-0056 (OAM Admin UI). Captures what the demo needs from the admin UI, what the admin UI gets from the demo, and the build cadence.

## SDK

- [SDK desiderata](sdk-desiderata.md): API gaps surfaced while shaping the demo. Drives ADR amendments / new ADRs.

## Status

Each file carries its own `Status:` line. Pipeline: `discussion` -> `decided` -> `implemented` -> `documented`. A spec at `decided` can be implemented in parallel with others as long as it does not depend on a still-`discussion` desideratum.
