# Narrator (LLM peer)

**Status:** discussion
**Identity:** `narrator` (single instance)

## Purpose

Human-readable scenario narration. Every 5 minutes, summarize what happened across all incidents in a paragraph (max 1000 chars). Useful as the demo's "story so far" voiceover when recording, and for live demo runs that exceed the canonical 90-second video.

## Triggers

- Internal timer (5 min).

## Outputs

- Pubsub: `mesh.swarm.narrative` carries `Narrative`.

## State

- Internal: rolling 5-min event window cache.
- KV (read): incident summaries from `wildfire.incident.*`.
- Pubsub (subscribe, light): `mesh.briefing.>`, `mesh.swarm.stats` (counts only).

## Lifecycle

- Always-on. Single instance.

## Reliability

- Lower-priority output. If the LLM fails, log and skip the period; do not retry into the next window.

## Behaviour notes

- LLM choice: Haiku (cheap, narrative quality is enough at this length).
- Prompt sources: incident summaries from KV + counters from the previous narrate window. No raw text from external agents.
- Output: a string up to 1000 chars + `incident_ids_referenced` list.

## Open questions

- Should the narrator output be voiced (TTS) for the recorded video? Stretch goal.
- Manual on-demand summary via `mesh.call("narrator", NarrateRequest)`? Out of v1.

## Subject + KV contracts

- Outbound: `mesh.swarm.narrative` carries `Narrative`.
- Inbound: `mesh.briefing.>`, `mesh.swarm.stats`, KV reads on `wildfire.incident.*`.

## SDK shape needed

- `mesh.publish(subject, model)` (#2).
- Multi-subject sub on the decorator (#1).
- `mesh.kv.list(prefix)` (#9) for incident reads.
