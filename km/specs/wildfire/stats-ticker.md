# Stats ticker

**Status:** discussion
**Identity:** `stats-ticker` (single instance)

## Purpose

Deterministic counters every 10s. Reads incident state and fleet position records from KV, computes aggregate stats, emits a `SwarmStats` snapshot for the admin UI's stats display (and for the narrator).

## Triggers

- Internal timer (10s).

## Outputs

- Pubsub: `mesh.swarm.stats` carries `SwarmStats`.

## State

- Internal: nothing persistent.
- KV (read): `wildfire.incident.*` for incident counts, `wildfire.fleet.*` for fleet activity.

## Lifecycle

- Always-on. Single instance.

## Reliability

- Trivial. Counters are best-effort, not authoritative.

## Behaviour notes

- Snapshot composition reads KV every tick rather than maintaining a long-running rolling window.
- `SwarmStats` carries: timestamp, drones_active/total, helis_active/total, ffunits_active/total, medevacs_active/total, incidents_open, incidents_resolved, persons_recovered_total, fires_detected_total.
- "Active" means `state != "free"` in the fleet KV record. "Available total" means count of records.

## Open questions

- Should the ticker be a Publisher (`async def ticker(): yield SwarmStats(...)`) on its auto-mapped subject, or use `mesh.publish(subject, model)` (#2) on the flat `mesh.swarm.stats`? Lean #2 to keep the subject convention demo-flat.
- Cadence configurable (1s for tight feedback, 10s for steady)? CLI flag.

## Subject + KV contracts

- Outbound: `mesh.swarm.stats` carries `SwarmStats`.
- Inbound (KV reads): `wildfire.incident.*`, `wildfire.fleet.*`.

## SDK shape needed

- `mesh.publish(subject, model)` (#2).
- `mesh.kv.list(prefix)` (#9) to read fleet state efficiently. Today's `watch + drain initial` works but is awkward.
