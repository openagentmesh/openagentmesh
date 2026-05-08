# Admin UI integration (paired build with ADR-0056)

**Status:** discussion

## Why this file exists

The wildfire demo and the OAM admin UI are paired deliveries. They are designed and built in tandem so the admin UI is shaped by a real-world workload (the demo) instead of a hypothetical one, and so the demo gets a control-plane surface it does not have to invent.

The pairing reverses an earlier decision to defer the admin UI until after the demo. It is the cleaner answer to the same problem: "design the admin UI against real demand, not speculation." Building them together is how that demand actually reaches the admin UI in time to influence it.

## What the demo needs from the admin UI

The wildfire scenario UI is intentionally narrow: world view + minimal write surface. Everything that is mesh-internal observability lives in the admin UI. Concretely the demo expects the admin UI to provide:

1. **Agent registry that scales.** The demo has 30-60 simultaneous agents (3-5 UAVs, 20-50 drones, 5-10 medevacs, plus singletons). The current ADR-0056 spec describes a flat agent table; that will not scale visually for the demo. Needs grouping by channel/fleet (`uav.*`, `drone.*`, `medevac.*`).

2. **Liveness indicators that work.** Killing an agent from the scenario UI must show up in the admin UI within seconds via a status change. ADR-0056 leaves the dot hidden until ADR-0016 (disconnect advisories) is implemented. The demo forces ADR-0016 onto the joint critical path, or the admin UI grows a heartbeat-based stand-in for v1.

3. **Event feed with subject patterns.** ADR-0056 already specifies this. The demo dogfoods it: a viewer can subscribe to `mesh.detection.thermal` and watch the cascade kick off in real time. Subject pattern wildcards (`>`, `mesh.medevac.>.status`, etc.) must work cleanly.

4. **Invocation sandbox that handles the demo agents.** The Tasker (`async def tasker(req: TaskTranslateRequest) -> TaskCommand`) is a perfect schema-driven form target. The demo viewer can type natural language into the admin UI's sandbox and see a typed `TaskCommand` come back without going through the firefighter CLI. That is the protocol-first message in two seconds.

5. **Subject volume / rate hints.** Not in current ADR-0056. The demo will surface this need: watching the cascade is more compelling when you see "1Hz thermal grid, ~5 detections/s, ~2 surveys/s, 1 briefing/30s" as live counters next to the event feed. Probably a sparkline or rate badge per subject pattern.

6. **Subject topology view (stretch).** Not in current ADR-0056. A lightweight diagram showing pub/sub edges between agents would be the highest-impact visual for "this is a mesh, not a chain." Defer to a follow-up if it slows the joint delivery; but flag it now.

## What the admin UI gets from the demo

A real workload at portfolio scale. Instead of designing screens against three toy agents, the admin UI is designed against a system that includes:

- High-cardinality agent populations (50+ drones).
- Heterogeneous capability mix (Responder, Streamer, Publisher, source-driven).
- High-throughput subjects (1Hz environment grids, ~5 Hz detections).
- Live failure modes (chaos kill button, fault tolerance demonstrations).
- LLM-shaped agents (Tasker, Briefer, Narrator) with structured I/O — perfect sandbox material.
- Read-mostly consumer pattern (the scenario UI itself is a NATS subscriber-only client; admin UI must coexist).

The admin UI ships with a recorded demo of itself running against the wildfire scenario. That is the marketing artifact for ADR-0056 just as the scenario video is the marketing artifact for ADR-0054.

## Concrete deltas the demo will likely force on ADR-0056

These are predictions, not commitments. They become amendment proposals once the build hits each one:

| Pred. | Current ADR-0056 | Likely amendment |
|---|---|---|
| Agent list grouping | flat table | groupable by channel; collapsible groups |
| Liveness | hidden until ADR-0016 | force ADR-0016 onto critical path, or add heartbeat stand-in |
| Subject volume | not present | per-subscription rate badge or sparkline |
| Event feed payload | formatted JSON | typed render hint when payload matches a known contract |
| Subject topology | not present | optional D3-style edge graph; backlog |
| Multi-channel aggregate views | not present | "Drones overview", "Medevacs overview" derived screens |

If too many of these stack up, the admin UI becomes "wildfire-specific" — bad. The discipline is to take only the deltas that any non-trivial mesh would want, and reject the ones that are demo-only flavor (e.g. fleet icons on the map are the scenario UI's job, not the admin UI's).

## What the admin UI does NOT do

- Render the scenario world (no map, no fire spread, no fleet positions). That is the scenario UI's job.
- Spawn fires or kill agents from a "demo controls" panel. Those are scenario actions; they live in the scenario UI. The admin UI may grow a generic agent-kill operation later, but it would not be a wildfire-specific surface.
- Show per-incident state (briefings, narratives). Those are domain entities, not mesh entities.

## Build cadence

The demo and admin UI evolve in interleaved waves. A wave is "scenario surface lights up -> admin UI screen needed -> ship admin UI screen -> demo dogfoods it -> feedback informs next wave."

| Wave | Scenario surface | Admin UI screen | Joint outcome |
|---|---|---|---|
| 1 | UAV + drone + console output | Agent registry (flat OK at this scale) | Live agent count visible while running fleets |
| 2 | Add medevac + firefighter CLI + scenario UI map | Event feed working with wildcards | Scenario click triggers cascade; admin UI shows the propagation |
| 3 | Add briefer + tasker LLM peers | Invocation sandbox; agent grouping by channel | Manual Tasker invocation from admin UI sandbox |
| 4 | Add narrator + chaos kill button + map polish | Liveness indicators (heartbeat or ADR-0016) | Chaos demo: kill in scenario UI -> red dot in admin UI |
| 5 | Recording + cookbook docs | Subject volume hints + final polish | Canonical 90-second video + admin UI marketing artifact |

Each wave commits independently. Branch strategy: one feature branch per wave per UI is too granular; lean toward one feature branch shared between scenario UI and admin UI per wave, OR separate branches that explicitly merge into a wave-tagged integration commit.

## Open coordination questions

- Same repo or split? Both stay in `openagentmesh` for now: the admin UI source already lives at `ui/` per ADR-0056, demo lives at `demos/wildfire/`. No separate repo.
- Same release? The admin UI ships as `pip install "openagentmesh[ui]"` per ADR-0056. The demo ships as a path-importable package + cookbook recipe. They release on the same OAM minor version when both are demo-ready.
- Versioning the canonical recording? The video records a specific OAM version (e.g., v0.4.0). The README badge links to that version; the recording is replaceable but not frequently re-recorded.
- Does the admin UI become "the demo's UI" in marketing copy, or stay framed as a standalone product? Stay standalone. The demo reads as "our SDK + our admin UI together"; the admin UI's own page does not depend on the wildfire demo.

## Status of ADR-0056

This file proposes amendments to ADR-0056 but does not change the ADR directly. As predicted deltas crystallize during the build, file specific ADR-0056 amendments (or follow-up ADRs) and update the table above.
