# Fire simulator

**Status:** discussion
**Identity:** `fire-sim` (single instance)

## Purpose

Drive the cascade. Publish a synthetic thermal grid at 1 Hz on `mesh.environment.thermal`. Models a spreading fire with hotspots so a recorded run is reproducible. Subscribes to `mesh.fire.spawn` so the scenario UI can add hotspots interactively (the demo's authenticity proof).

Optionally subscribes to suppression events from heli / ffunit to close the loop (heli drops water -> local cells cool down).

## Triggers

- Internal timer (1 Hz): publishes the current grid state.
- Subscribes (pubsub): `mesh.fire.spawn` carrying `(coords, magnitude)`. Adds a hotspot.
- Optional subscribes: `mesh.fire.suppress` from heli/ffunit. Reduces local temperature.

## Outputs

- Pubsub: `mesh.environment.thermal` carries `ThermalGrid` (1 Hz).

## State

- Internal: current grid (e.g. 50x50 cells across 10x10 km), hotspot list, spread model parameters, deterministic seed.
- KV: none for v1. Could expose `wildfire.world.snapshot` for the dashboard's "freeze and replay" features later.

## Lifecycle

- Always-on for the duration of a scenario run.

## Reliability

- Deterministic with a `--seed` flag for reproducible recordings.
- No retries. If fire-sim dies the cascade stops, which is itself a useful chaos signal.

## Behaviour notes

- Grid resolution: 50x50 cells, ~200m per cell, 10x10 km area centered at origin.
- Spread model: lightweight cellular automaton with wind direction parameter (configurable, demo default fixed for predictable recording).
- Cell payload: `(Coords, temperature_celsius)`. Background ~25C, hotspots up to 800C, decay rate when not fed.
- Fire spawn from UI: adds a single hot cell at `coords` with magnitude as initial temperature; spread takes over.
- Suppression from action fleets (if loop is closed): caps local temperature growth and accelerates decay near the suppression coords.

## Open questions

- Is fire-sim a `mesh.agent` or a plain script? Lean: registered agent so the catalog reflects it; the publish is a publisher source on the agent (waits on #2). Until then, `mesh.kv.put` for the grid (no — grid is high-volume pubsub, not KV); or `mesh._nc.publish` workaround.
- Close the suppression loop or not? Lean yes if the heli/ffunit publish event lands cheaply. Adds satisfying recursion to the demo (action affects the world, which the agents observe, which drives next decisions).
- Grid emission: full grid every tick, or delta updates? Full grid simpler; volume is bounded (2500 cells * 1 Hz, ~50 KB/s). Lean full.

## Subject + KV contracts

- Outbound pubsub: `mesh.environment.thermal` carries `ThermalGrid` (definition in ADR-0054 frozen contracts).
- Inbound pubsub: `mesh.fire.spawn` carries `FireSpawn { coords, magnitude }` (new contract).
- Optional inbound pubsub: `mesh.fire.suppress` carries `FireSuppress { coords, intensity }` (new contract).

## SDK shape needed

- `mesh.publish(subject, model)` (#2) for grid emission.
- Multi-subject subscription source on the decorator (#1) for spawn + suppress.
- `mesh.instance_id` (#8) for self-tagging (single instance, but consistent with conventions).
