# Firefighter unit (ground)

**Status:** discussion
**Identity:** `ground.ffunit` (default 3 instances)

## Purpose

Ground intervention. Receives dispatch from the operator, drives to coords, suppresses the fire on-site (simulated as time-on-target reducing the fire), reports back. Distinct from the **operator CLI**, which is the human-driven dispatcher (see `firefighter.md`).

## Triggers

- Invocable: `mesh.call("ground.ffunit", DispatchOrder)`. Queue-grouped; first available wins.

## Outputs

- Returns `DispatchAck` synchronously.
- KV write: own fleet state at `wildfire.fleet.ground.ffunit.{instance_id}`.
- Pubsub: `mesh.action.ffunit.{instance_id}.status` with `FFUnitStatus` updates: `dispatched`, `en_route`, `on_site`, `suppressing`, `returning`, `available`.

## State

- Internal: position, busy/free, current order, water/foam reserves (simulated).
- KV (own): position record; same shape as other fleets.

## Lifecycle

- Always-on. 3 instances default. Independent processes.

## Reliability

- Standard Responder pattern via queue group. Works today.
- Status feed lets the scenario UI render trails on the map.

## Behaviour notes

- Travel speed: ground vehicles are slow; tune so a typical mission lasts 30-60s on the simulated map.
- On-site suppression: simulated `await asyncio.sleep(suppression_time)` proportional to fire severity. Optional fire-sim feedback (publishes `mesh.fire.suppress` like the heli) — shared decision with heli.
- Reserves: bounded; ffunit must return to refill before next dispatch. Reject dispatch if depleted.

## Open questions

- Same fire-sim feedback decision as heli: close the loop or not? Both fleets should make the same call.
- Per-unit specialization (foam unit vs. water unit vs. medic-equipped)? Out of v1; one ffunit type only.
- Coordination with medevac: when ffunit finds people on-site, should it auto-publish a medevac request, or always defer to the operator? v1: defer to operator. The ffunit's status update mentions `persons_at_risk`; the briefing surfaces it; the operator dispatches medevac.

## Subject + KV contracts

- Inbound: `mesh.call("ground.ffunit", DispatchOrder)` -> auto-mapped per ADR-0049.
- KV (own): `wildfire.fleet.ground.ffunit.{instance_id}`.
- Outbound pubsub: `mesh.action.ffunit.{instance_id}.status`.

## SDK shape needed

- Plain `@mesh.agent` Responder: **compiles on current SDK.**
- Status pubsub: #2.
- Same desiderata profile as heli.
