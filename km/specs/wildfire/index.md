# Wildfire demo specs

Detailed per-component specs for the demo defined in [ADR-0054](../../adr/0054-wildfire-incident-response-demo.md).

ADR-0054 is the high-level decision: scenario lock, frozen contracts, frozen subject map, scope fences. This folder is where the per-agent behaviour, the UI surface, and the SDK requirements that bubble up are shaped iteratively. Files here may reach `decided` independently; ADR-0054 stays the umbrella reference.

## Agents

- [Fire simulator](fire-sim.md): publishes the thermal grid that drives the cascade.
- [UAV (high-altitude)](uav.md): wide-area thermal sweep, emits detections.
- [Drone (low-altitude)](drone.md): close-range survey, queue-grouped fleet.
- [Medevac (ground)](medevac.md): people recovery, queue-grouped fleet, status feed.
- [Firefighter unit](firefighter.md): human-in-the-loop CLI, dispatches medevac.
- [Briefer (LLM)](briefer.md): structured incident briefings from raw events.
- [Tasker (LLM)](tasker.md): NL to typed `TaskCommand`, request/reply.
- [Stats ticker](stats-ticker.md): deterministic 10s counters.
- [Narrator (LLM)](narrator.md): 5-minute paragraph summaries.

## UI

- [Dashboard](dashboard.md): map, feeds, counters, chaos controls.

## SDK

- [SDK desiderata](sdk-desiderata.md): API gaps surfaced while shaping the demo. Drives ADR amendments / new ADRs.

## Status

Each file carries its own `Status:` line. Pipeline: `discussion` -> `decided` -> `implemented` -> `documented`. A spec at `decided` can be implemented in parallel with others as long as it does not depend on a still-`discussion` desideratum.
