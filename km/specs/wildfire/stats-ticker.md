# Stats ticker

**Status:** discussion

## Purpose

Deterministic counters every 10s. Reads incident state from KV, counts active drones / UAVs / medevacs by subscribing to a recent activity window, and emits a `SwarmStats` snapshot. The dashboard renders these as a steady heartbeat.

## Triggers

- Internal timer (10s).

## Outputs

- Publishes `SwarmStats` to `mesh.swarm.stats` (broadcast).

## State

- Internal: rolling window of fleet activity. Built by subscribing to relevant subjects in the background.
- KV: reads `mesh-context` for incident counts.

## Lifecycle

- Always-on. Single instance.

## Reliability

- Trivial. If the ticker dies the dashboard heartbeat stops, which is itself a useful chaos signal.

## Behaviour notes

- Active fleet members: "I have heard from this drone in the last 30s" via passive subscription, NOT by polling each fleet.
- Counts are best-effort, not authoritative. Documented as such on the dashboard.

## Open questions

- Is the ticker an agent or a script? Today's Publisher pattern (`yield` events) covers periodic emit on the agent's auto-mapped subject `mesh.agent.ticker.events`, which mismatches the ADR's frozen `mesh.swarm.stats`. Resolution: SDK desideratum #2 (custom outbound subject) OR change the ADR's subject map to the auto-mapped form. Lean toward #2 since the ADR's flat subject scheme is the more readable convention.

## Subject contracts

Outbound: `SwarmStats`. Inbound subscriptions for state: TBD (could be `mesh.detection.thermal`, `mesh.survey.>`, `mesh.medevac.>.status`).

## SDK shape needed

- Custom-subject publish for periodic emission (#2).
- Multi-subject background subscription (#1) for activity tracking.
