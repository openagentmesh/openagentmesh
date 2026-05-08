# Drone (low-altitude)

**Status:** discussion

## Purpose

Close-range survey. Reacts to a thermal detection by flying to the location, performing a survey, and emitting a structured `SurveyResult`. The fleet load-balances naturally via NATS queue groups so the same detection is handled by exactly one drone.

## Triggers

- Subscribes: `mesh.detection.thermal` via queue group `drones`. One detection -> one drone.

## Outputs

- Publishes: `SurveyResult` to `mesh.survey.{drone_id}` (broadcast, drone-id-suffixed for routing observability).

## State

- Internal: own ID, position, busy/free, last detection assigned.
- KV: none in v1. Position trail could go to KV for the dashboard.

## Lifecycle

- Always-on. 20-50 instances per scenario. Independent processes. Killing one is part of the chaos story.

## Reliability

- Queue group means a crashed drone after `subscribe` but before `survey` complete leaves NATS to redeliver to a sibling. Whether redelivery happens automatically depends on JetStream consumer settings on the queue group; raw NATS core has no redelivery for unacked queue messages.
- If we want redelivery on crash, we need JetStream-backed subscription, not core NATS pubsub. This is an SDK design call (desideratum #4).

## Behaviour notes

- Selection: nearest-available drone wins. Naive implementation: queue group picks any subscriber, the chosen drone checks distance + availability and either accepts (proceeds with survey) or `nak`s (returns early so the message goes back to the queue). Without JetStream + nak, "let another drone take it" requires re-publishing.
- Survey time: simulated `await asyncio.sleep(distance / speed + survey_duration)`. No real flight.
- Survey output: `SurveyResult` with `persons_detected` (random within bounds), `structures_visible`, etc.

## Open questions

- Does `nak` and "let another drone take it" need JetStream? If yes, this is the second SDK desideratum: queue groups with redelivery semantics, not just core NATS broadcast load-balancing.
- Should drones publish their position periodically (`mesh.drone.{id}.position`)? Useful for the dashboard, opens visualization. Add as a publisher capability on the same agent.
- Per-drone process or pool of drones in one process? ADR-0054 says one process per drone for the topology story; verify scale at 20-50 processes works on a laptop (NATS handles it; OS process count is the concern).

## Subject contracts

Inbound: `ThermalDetection`. Outbound: `SurveyResult`.

## SDK shape needed

- Declarative subject subscription with queue group (SDK desiderata #1, #3).
- Public `mesh.publish(subject, model)` (#2).
- Possibly: JetStream-backed source with ack/nak semantics (#4) if we want crash redelivery.
