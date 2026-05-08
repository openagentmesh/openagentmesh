# UAV (high-altitude)

**Status:** discussion

## Purpose

Wide-area thermal sweep. Subscribes to the simulated thermal grid, applies a sensor model, and emits typed detections when temperature exceeds a threshold within sensor range.

## Triggers

- Subscribes: `mesh.environment.thermal` (broadcast). Every UAV instance receives every grid update; the sensor model decides whether the cell is in range.

## Outputs

- Publishes: `ThermalDetection` to `mesh.detection.thermal` (broadcast). One message per detection (multiple per grid update possible).

## State

- Internal: own position (static for v1, configurable per instance), sensor footprint, detection threshold.
- KV: none in v1. Position could move to KV later for visualization.

## Lifecycle

- Always-on. Independent process. Crash means that UAV stops sweeping; other UAVs continue. No shared state.

## Reliability

- Idempotent emission: a re-emitted detection from the same UAV with overlapping coords should not break the cascade. The drone fleet's queue group naturally deduplicates dispatch; the briefer correlates by incident, not by detection event.

## Behaviour notes

- Count: 3-5 instances. Each UAV is its own process with its own static position.
- Sensor footprint: circular, radius configurable (e.g. 2km).
- Threshold: hot cell if `temp > 100C` AND inside footprint AND `confidence > 0.5` (heuristic of `(temp - 100) / 700`, capped).
- Multiple UAVs can detect the same cell. That is intended; redundancy is part of the story.

## Open questions

- Does the UAV publish one detection per hot cell per tick, or aggregate hot cells into a single message? Per cell is simpler; aggregation reduces message volume but loses per-cell confidence.
- Should each UAV register with the catalog (so `mesh.catalog()` shows fleet membership)? Yes for the dashboard story, but only if the agent abstraction holds (depends on SDK desideratum #1).
- Does the UAV need any invocation surface (e.g. `mesh.call("uav.high-alt.{id}", "sweep_now")`)? Out of scope for v1.

## Subject contracts

See ADR-0054. Inbound: `ThermalGrid`. Outbound: `ThermalDetection`.

## SDK shape needed

Declarative subject subscription (SDK desideratum #1) + public `mesh.publish(subject, model)` (#2). Without these the UAV is not a `@mesh.agent`; it is a script using the mesh as transport.
