# Briefer (LLM peer)

**Status:** discussion
**Identity:** `briefer` (2 instances in queue group `briefers` for cadence redundancy)

## Purpose

Turn raw event flow into human-readable, schema-validated incident briefings. The briefer watches the KV detection namespace + survey pubsub, correlates events into incidents (heuristic clustering by coords + time), and on a 30s cadence (or threshold) emits `IncidentBriefing`.

## Triggers

- KV-watch source: `wildfire.detection.*` (state transitions + survey results).
- Pubsub source: `mesh.survey.>` (fast-reaction visibility into surveys; same data as KV but pubsub gives the admin UI feed).
- Internal timer: every 30s OR when an incident's event buffer crosses threshold.

## Outputs

- Pubsub: `mesh.briefing.{incident_id}` (broadcast `IncidentBriefing`).
- KV: `wildfire.incident.{incident_id}` (durable incident state, including the latest briefing snapshot).

## State

- KV (shared incident store): `wildfire.incident.{incident_id}` carries `IncidentState` (events list, briefings history, current severity, recommended actions).
- Internal: in-memory cache mirroring KV for fast briefing assembly.

## Lifecycle

- Always-on. 2 instances in queue group `briefers` for the **periodic-tick** semantics: only one instance produces a briefing per tick.
- KV-watch on detections runs on both instances independently (both observe everything).
- The "produce a briefing" trigger is gated by a CAS on `wildfire.incident.{id}.last_briefing_at`. The instance that wins the CAS produces the briefing; the other yields.

## Reliability

- LLM call may fail (timeout, rate limit, malformed structured output). On failure: log, retry once with exponential backoff, then emit a degraded `IncidentBriefing` with `summary="Briefing unavailable, see KV record"`. Pydantic validation guarantees a well-formed payload.
- KV writes use CAS for incident state mutations to handle concurrent updates from both briefer instances.

## Correlation logic

- New detection (KV `state == pending`): create or merge into an incident.
  - Merge if any existing incident has a detection within 500m and 60s.
  - Otherwise create new incident `inc-{shortuuid}`.
- New survey (KV `state == surveyed` OR pubsub `mesh.survey.>`): attach to the relevant incident.
- Incident "open" while it has any active fleet activity (assigned drone, dispatched action fleet) OR pending detections within the cluster window.
- Incident "resolved" when no fleet is active on it AND fire-sim reports temperature back below threshold for the cluster.

## Behaviour notes

- Briefing trigger: `events.count >= 5` OR `now - last_briefing >= 30s`.
- LLM prompt: structured fields only (incident metadata, event list as JSON). No raw text from external sources.
- Output validation: `IncidentBriefing` Pydantic model. `recommended_actions` constrained to literal list.
- LLM choice: Sonnet for briefer (richer reasoning).

## Open questions

- Is the resolution detection logic part of the briefer, or a separate `wildfire.cleaner` agent? Lean: briefer for v1, factor out if it grows.
- Confidence score on briefings: add `confidence: float = 1.0` to the contract for dashboard rendering cues. Decision: yes.
- Stale-assignment cleanup (drone died mid-survey, detection stuck `assigned:`): briefer adopts this as a side responsibility v1, with a watchdog scan every tick. Document as known limitation; factor out later.
- Should the briefer recommend specific instance IDs (`heli.alpha-1`) or just fleet types? Just types. Operator picks; queue-group dispatch handles the actual instance.

## Subject + KV contracts

- KV-watch: `wildfire.detection.*`.
- Pubsub-sub: `mesh.survey.>`.
- KV-write: `wildfire.incident.{id}` (CAS).
- Pubsub-write: `mesh.briefing.{id}`.

## SDK shape needed

- Multi-source declarative subscription on a single agent (#1, multiple sources).
- Queue group on the periodic-tick logic (#3) — actually mediated by KV CAS on `last_briefing_at`, so the queue group itself is on the source decoration only for catalog visibility, not for tick gating.
- KV ergonomics for CAS + list (#9).
- `mesh.publish(subject, model)` for briefing emission (#2).
