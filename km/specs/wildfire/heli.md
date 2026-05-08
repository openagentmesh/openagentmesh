# Heli (low-altitude water-bomber)

**Status:** discussion
**Identity:** `low-alt.heli` (default 1-2 instances)

## Purpose

Aerial fire suppression by water drop. Receives dispatch orders from the operator (firefighter CLI), flies to coords, drops water, reports outcome. Operates at low altitude (below canopy line) when dropping; transits at higher altitude.

## Triggers

- Invocable: `mesh.call("low-alt.heli", DispatchOrder)`. Queue-grouped across heli instances; first available wins.

## Outputs

- Returns `DispatchAck` synchronously: `accepted`, `instance_id`, `eta_seconds`, optional `reason` if rejected.
- KV write: own fleet state at `wildfire.fleet.low-alt.heli.{instance_id}` for position + state.
- Pubsub: `mesh.action.heli.{instance_id}.status` (or similar) with `HeliStatus` updates: `dispatched`, `transit`, `dropping`, `returning`, `available`.

## State

- Internal: position, busy/free, current dispatch order, water tank level.
- KV (own): position record with same shape as drone, ground vehicle, etc.

## Lifecycle

- Always-on. 1-2 instances default. Independent processes.

## Reliability

- Standard `@mesh.agent` Responder pattern (queue-group dispatch). Compiles on current SDK with no source changes.
- Position record + status events give the dashboard the trail.
- Killed during a drop: status feed gaps, KV record stops updating. Watchdog/heartbeat outside scope v1.

## Behaviour notes

- Default count: 1 (with a stretch to 2 if recording shows obvious wait time in viewers' patience).
- Capacity: 1 water drop per round trip; must return to base to refill (simulated `await asyncio.sleep(refill_time)`).
- Decision logic: when receiving dispatch, check tank, distance, current state; reject (return ack with `accepted=False`, reason) if tank empty or unavailable. Otherwise accept, transit, drop, return.
- Effectiveness: writing back to fire-sim is out of scope v1 (water drop reduces fire intensity in the world). v1 reports the drop event for visualization; fire-sim cools the cell on its own schedule.

## Open questions

- Should heli effectiveness affect fire-sim (close the loop)? Stretch: heli publishes a `mesh.fire.suppress` event with coords; fire-sim subscribes and reduces local temperature. Compelling for the demo's recursive feel. Decision: yes if cheap, no if it pulls in fire-sim coupling.
- Single base location or multiple? Single for v1.
- Should the operator be able to address a specific heli (`mesh.call("low-alt.heli.{id}", ...)`)? Per-instance addressing is desideratum #6. Defer; v1 uses queue group.

## Subject + KV contracts

- Inbound: `mesh.call("low-alt.heli", DispatchOrder)` -> auto-mapped to `mesh.agent.low-alt.heli` per ADR-0049.
- KV (own): `wildfire.fleet.low-alt.heli.{instance_id}`.
- Outbound pubsub: `mesh.action.heli.{instance_id}.status`.

## SDK shape needed

- Plain `@mesh.agent` Responder dispatch surface: **compiles on current SDK.**
- Status pubsub: `mesh.publish(subject, model)` (#2).
- Position KV: the standard `mesh.kv.put()` works today.
- Position broadcast as a publisher source on the same agent: would benefit from #1 but optional in v1 (heartbeat loop in `__main__` works).
