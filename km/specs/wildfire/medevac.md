# Medevac (ground)

**Status:** discussion
**Identity:** `ground.medevac` (default 3 instances)

## Purpose

People recovery. Receives dispatch orders from the operator, drives to coords, extracts persons in need, transports to a holding point. Like ffunit and heli, medevac is an action fleet — not an intelligence provider.

## Triggers

- Invocable: `mesh.call("ground.medevac", DispatchOrder)`. Queue-grouped; first available wins.

## Outputs

- Returns `DispatchAck` synchronously.
- KV write: own fleet state at `wildfire.fleet.ground.medevac.{instance_id}`.
- Pubsub: `mesh.action.medevac.{instance_id}.status` with `MedevacStatus`: `dispatched`, `en_route`, `on_site`, `extracting`, `returning`, `available`.

## State

- Internal: position, busy/free, current order, capacity (persons currently transported).
- KV (own): position record matching the standard fleet shape.

## Lifecycle

- Always-on. 3 instances default. Independent processes.

## Reliability

- Standard Responder pattern. Works today.

## Behaviour notes

- Travel speed: ground vehicle, slower than heli, faster than ffunit (reasonable medevac driver).
- Capacity: 4 persons per unit; on full, must return before next dispatch.
- Extraction time: short (`await asyncio.sleep(extraction_time)`).
- Reject dispatch (`accepted=False`) if at capacity or unavailable.

## Open questions

- Should medevac dispatch include `persons_estimated` and the unit decline if it cannot fit them all? v1: yes; reject with `reason="capacity"` and let operator dispatch a second unit.
- Holding point: single base or multiple drop-off locations? Single for v1.
- Coordination with ffunit: same as ffunit doc — operator owns the cross-fleet decision.

## Subject + KV contracts

- Inbound: `mesh.call("ground.medevac", DispatchOrder)` -> auto-mapped per ADR-0049.
- KV (own): `wildfire.fleet.ground.medevac.{instance_id}`.
- Outbound pubsub: `mesh.action.medevac.{instance_id}.status`.

## SDK shape needed

- Plain Responder: **compiles on current SDK.**
- Same profile as heli and ffunit.
