# UAV (high-altitude)

**Status:** discussion
**Identity:** `high-alt.uav` (single instance v1)

## Purpose

Wide-area thermal surveillance. Subscribes to the simulated thermal grid, applies a sensor model, and creates a pending detection record in KV when temperature exceeds a threshold within sensor footprint.

## Triggers

- Subscribes (pubsub): `mesh.environment.thermal` (broadcast). Receives every grid update.

## Outputs

- KV write: `wildfire.detection.{detection_id}` with `state=pending`, coords, severity, ts, detector instance ID.

The UAV does NOT publish detection events on a NATS subject. Detections are durable state in KV from the start of their lifecycle, which is what enables drone election and the pending-when-overloaded queue.

## State

- Internal: own position (static for v1), sensor footprint, temperature threshold, recent-detection dedup window.
- Position record (KV): `wildfire.fleet.high-alt.uav.{instance_id}` with `coords`, `state=active`, `last_updated`. Updated every 1Hz heartbeat.

## Lifecycle

- Always-on. Single instance v1; future: 2+ for redundancy or coverage.

## Reliability

- Idempotent emission: detection IDs derived from `(coords_bucket, time_window)` so a re-detection within the dedup window does not create a second pending record.
- KV `create` (put-if-absent) used for the detection write; if a duplicate detection_id collides, the write fails silently and the existing record stands.

## Behaviour notes

- Sensor footprint: circular, radius configurable (e.g. 5km), centered on UAV position.
- Threshold: `temp > 100C` AND inside footprint AND confidence heuristic `(temp - 100) / 700` clipped to `[0, 1]` AND `confidence > 0.5`.
- Dedup: hash `(round(coords.x, -2), round(coords.y, -2), floor(now / 30))` to bucket detections by 100m grid + 30s window. Avoids flooding KV when a hot cell persists across many grid ticks.
- A detection record carries: `state`, `coords`, `severity`, `ts`, `detector_id`. `severity` derived from temperature.

## Open questions

- Sensor footprint static vs. orbiting? V1: static for simplicity.
- Should the UAV also write its own footprint coverage to KV (so dashboard shows the swept area)? Stretch goal; out of v1.
- Single UAV: realistic enough? Story is "high-altitude observer." Could pair with an aerial relay agent later, but v1 stays at one.

## Subject + KV contracts

- Inbound: `mesh.environment.thermal` carries `ThermalGrid`.
- Outbound (KV): `wildfire.detection.{id}` carries the detection record (Pydantic model TBD; either reuse existing `ThermalDetection` with extra `state` field, or define a `DetectionRecord`).
- Position (KV): `wildfire.fleet.high-alt.uav.{instance_id}` carries `FleetMemberState` (TBD model: coords, state, last_updated).

## SDK shape needed

- Declarative subject sub on the decorator (#1) for `mesh.environment.thermal`.
- `mesh.kv.create(key, value)` (#9) for put-if-absent on detection writes.
- `mesh.instance_id` (#8) to populate `detector_id` and key the position record.
- Pydantic model helpers on KV (#9) reduce boilerplate.
