# Briefer (LLM peer)

**Status:** discussion

## Purpose

Turn raw event flow into human-readable, schema-validated incident briefings. The briefer subscribes to detections and surveys, correlates them into incidents (heuristic clustering by coords + time), and on a 30s cadence (or threshold) emits `IncidentBriefing` per active incident.

## Triggers

- Subscribes: `mesh.detection.thermal` AND `mesh.survey.>`.
- Internal timer: every 30s, or when an incident's event buffer crosses a threshold.

## Outputs

- Publishes: `IncidentBriefing` to `mesh.briefing.{incident_id}` (broadcast).

## State

- KV bucket: `mesh-context` per ADR-0025 (or a dedicated `wildfire-incidents` bucket). Each incident's events accumulate under `incident.{id}.events`.
- Internal: in-memory cache mirroring KV for fast briefing assembly.

## Lifecycle

- Always-on. Two instances in a queue group `briefers` so a crash does not interrupt the briefing cadence. Both instances see all events; the queue group is on a "produce briefing" trigger, not on the event subscriptions, to avoid both instances briefing the same incident simultaneously.

## Reliability

- The LLM call may fail (timeout, rate limit, malformed structured output). On failure: log, retry once with exponential backoff, then publish a degraded `IncidentBriefing` with `summary="Briefing unavailable, see raw events"`. Pydantic validation ensures the published model is always well-formed.
- KV writes are CAS to handle two-briefer concurrent updates.

## Behaviour notes

- Incident correlation: a new detection within 500m and 60s of an existing incident merges into it; otherwise a new incident is created. ID generation: `inc-{shortuuid}`.
- Briefing trigger: `events.count >= 5` OR `now - last_briefing >= 30s`. Whichever first.
- LLM prompt: structured fields only (incident metadata, event list as JSON). No free-text from external sources flows into the prompt.
- Output validation: `IncidentBriefing` Pydantic model. Recommended actions are constrained to the literal list in the contract.

## Open questions

- Two-instance briefer with one queue group: how does only-one-fires-per-tick work? Easiest: both instances run a timer, but the briefing publish is request/reply via a third "briefing-coordinator" subject... too much. Alternative: use a JetStream KV lease (CAS on `incident.{id}.last_briefing_at`) so only one instance wins each tick. This is mesh-native and transferable.
- Should briefings include a confidence / sources score so the dashboard can render them with quality cues? Yes; add `confidence: float = 1.0` to `IncidentBriefing`, defaulting to 1.0.
- LLM choice: Sonnet for now per ADR-0054. Consider Haiku if the structured output stays simple enough. Decision: Sonnet, log token usage, switch later if cost is a problem.

## Subject contracts

Inbound: `ThermalDetection`, `SurveyResult`. Outbound: `IncidentBriefing`.

## SDK shape needed

- Two-subject subscription on a single agent: SDK desideratum #1 with multiple sources.
- KV access (`mesh.kv`): exists today.
- Custom-subject publish (#2).
- LLM provider abstraction: out of scope for the SDK; the demo wires its own `claude-api` client.
