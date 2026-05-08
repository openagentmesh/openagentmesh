# UAV (high-altitude)

**Status:** discussion
**Identity:** `high-alt.uav` (single instance v1)

> **Amended 2026-05-09** — kv_source on the world-cell namespace replaces the subject_source on `mesh.environment.thermal`. UAV reacts to per-cell updates as they happen, instead of scanning a 2500-cell snapshot 1×/sec. See ADR-0054 amended subject + KV map and `fire-sim.md` for the world-grid pivot.

## Purpose

Wide-area thermal surveillance. Watches the shared world-cell KV namespace, applies a sensor model, and creates a pending detection record in KV when temperature exceeds a threshold within sensor footprint.

## Triggers

- KV-watch source: `wildfire.world.cell.*`. Fires once per cell update (whether from fire-sim's spread tick or external mutation). UAV evaluates each updated cell against its sensor model.

## Outputs

- KV write: `wildfire.detection.{detection_id}` with `state=pending`, coords, severity, ts, detector instance ID.

The UAV does NOT publish detection events on a NATS subject. Detections are durable state in KV from the start of their lifecycle, which is what enables drone election and the pending-when-overloaded queue.

## State

- Internal: own position (static for v1), sensor footprint, temperature threshold, recent-detection dedup window.
- Position record (KV): `wildfire.fleet.high-alt.uav.{instance_id}` with `coords`, `state=free`, `last_updated`. Updated every 1 Hz heartbeat.

## Lifecycle

- Always-on. Single instance v1; future: 2+ for redundancy or coverage.

## Reliability

- Idempotent emission: detection IDs derived from `(coords_bucket, time_window)` so a re-detection within the dedup window does not create a second pending record.
- KV `create` (put-if-absent) used for the detection write; if a duplicate detection_id collides, the write fails silently and the existing record stands.

## Behaviour notes

- Sensor footprint: circular, radius configurable (e.g. 5 km), centered on UAV position.
- Threshold: `cell.temperature > 100 °C` AND `cell.coords` inside footprint AND confidence heuristic `(temp - 100) / 700` clipped to `[0, 1]` AND `confidence > 0.5`.
- Dedup: hash `(round(coords.x, -2), round(coords.y, -2), floor(now / 30))` to bucket detections by 100 m grid + 30 s window. Avoids flooding KV when a hot cell persists across many spread ticks.
- A detection record carries: `state`, `coords`, `severity`, `ts`, `detector_instance_id`. `severity` derived from temperature.
- Cell-deletion handling: when a `CellState` key is deleted (cell decayed back to ambient or was suppressed), the kv_source callback fires with a delete event. UAV ignores deletes — detection records aren't retracted; the briefer (Phase 3) handles incident-resolution semantics.

## Open questions

- Sensor footprint static vs. orbiting? V1: static for simplicity.
- Should the UAV also write its own footprint coverage to KV (so dashboard shows the swept area)? Stretch goal; out of v1.
- Single UAV: realistic enough? Story is "high-altitude observer." Could pair with an aerial relay agent later, but v1 stays at one.

## Subject + KV contracts

- KV-watch source (inbound): `wildfire.world.cell.*` carries `CellState` (per `km/specs/wildfire/contracts.md`).
- KV writes (outbound): `wildfire.detection.{id}` carries `DetectionRecord`.
- Position (KV): `wildfire.fleet.high-alt.uav.{instance_id}` carries `FleetMemberState`.

## SDK shape needed

- `kv_source(pattern)` (ADR-0052) for the world-cell watch.
- `mesh.kv.create(key, value)` (ADR-0060) for put-if-absent on detection writes.
- `mesh.instance_id` (ADR-0059) to populate `detector_instance_id` and key the position record.
- Pydantic model helpers on KV (ADR-0060) reduce boilerplate.
- All shipped on main as of 2026-05-08.
