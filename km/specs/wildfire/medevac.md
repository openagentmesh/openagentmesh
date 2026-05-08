# Medevac (ground)

**Status:** discussion

## Purpose

People recovery. Two distinct surfaces:
1. Request/reply dispatch endpoint: a firefighter calls `mesh.medevac.dispatch` with a `MedevacDispatch`, the nearest available unit responds with `MedevacAck`.
2. Status broadcast: each active unit emits state transitions (`en_route`, `on_site`, `extracting`, `returning`, `available`).

## Triggers

- **Dispatch (request/reply):** `mesh.medevac.dispatch` queue group. One request -> one unit.
- **Status (publisher):** internal state machine drives emissions.

## Outputs

- **Dispatch:** returns `MedevacAck` (synchronous reply).
- **Status:** publishes `MedevacStatus` to `mesh.medevac.{id}.status`. Frequency: on state transition (event-driven), plus optional heartbeat at lower rate.

## State

- Internal: own ID, position, current state, current incident assignment.
- KV: none in v1. Could write `medevac.{id}.state` to KV for dashboard read.

## Lifecycle

- Always-on. 5-10 instances. Each independent process.

## Reliability

- Dispatch: standard `@mesh.agent` queue group works today (this surface compiles on current SDK).
- Status: needs a way to publish on a custom subject. Today: only via Publisher pattern (publishes to `mesh.agent.{name}.events`, not `mesh.medevac.{id}.status`) or `mesh._nc.publish` (private). Drives SDK desideratum #2.

## Behaviour notes

- Dispatch decision: nearest-available unit wins. Same problem as drones; naive queue-group selection picks an arbitrary subscriber, which then nak's if not nearest-available.
- Travel: simulated by `await asyncio.sleep(distance / speed)`.
- Persons recovered: drawn from `MedevacDispatch.persons_estimated` plus jitter.

## Open questions

- Is the dispatch surface the agent's invocation subject (auto-mapped from name `medevac.dispatch`) or a custom subject `mesh.medevac.dispatch`? ADR-0054 subject map says the latter, but that requires custom subject mapping. The cleaner option is to lean on the auto-mapped subject and update the ADR's subject map. See SDK desideratum #5.
- Status emissions: agent or separate publisher? Cleanest if same agent registers a publisher source bound to a custom subject (depends on SDK desiderata #1, #2).
- How does a medevac unit signal "I am the closest" without a coordinator? Naive: check, then nak. JetStream nak would route the message to another consumer (#4). Alternative: drone-style query/reply where the dispatcher polls candidates first; rejected because it adds a hop.

## Subject contracts

Inbound: `MedevacDispatch`. Outbound: `MedevacAck` (sync reply), `MedevacStatus` (broadcast).

## SDK shape needed

- The dispatch endpoint mostly works today (request/reply queue-group via `@mesh.agent`).
- Custom outbound subject for status (#2 + #5).
- Possibly JetStream nak for nearest-available (#4).
