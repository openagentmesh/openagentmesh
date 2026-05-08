# Fire simulator

**Status:** discussion

## Purpose

Drive the cascade. Publish a synthetic thermal grid at 1 Hz on `mesh.environment.thermal`. Models a spreading fire with adjustable hotspots so a recorded run is reproducible.

## Triggers

- Internal timer (1 Hz). No external trigger.

## Outputs

- Publishes `ThermalGrid` to `mesh.environment.thermal` (broadcast).

## State

- Internal: current grid (numpy or list of `(coords, temp)`), fire spread model, hotspot list.
- KV: none.

## Lifecycle

- Always-on for the duration of a scenario run. Started from the bootstrap orchestrator.

## Reliability

- Deterministic: a seed makes the demo reproducible for the canonical recording.
- No retries; if the process dies the cascade stops, which is the desired chaos signal.

## Behaviour notes

- Grid resolution: TBD (e.g. 50x50 cells across a 10km square, configurable).
- Spread model: TBD (cellular automaton vs. parametric blob). Lean toward cheapest thing that produces a watchable visual.
- Cell payload: `(Coords, temperature_celsius)`. Background ~25 deg C, hotspots up to 800 deg C.

## Open questions

- Should fire-sim be a `mesh.agent`, a Publisher, or a plain asyncio task that calls `mesh.publish` (pending SDK desideratum #2)?
- Is the grid emitted as a single message or chunked? `ThermalGrid` carries a list of cells; for a 50x50 grid that is 2500 entries per second. Probably fine but worth measuring.
- Should the sim accept commands (e.g., `mesh.fire.spawn` to add a hotspot from the dashboard)? Out of scope for v1, but the subject would land cleanly.

## Subject contracts

See ADR-0054 frozen subject map and `ThermalGrid` model.
