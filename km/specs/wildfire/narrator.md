# Narrator (LLM peer)

**Status:** discussion

## Purpose

Human-readable scenario narration. Every 5 minutes, summarize what happened across all incidents in a paragraph (max 1000 chars). Doubles as the demo's "story so far" voiceover when recording.

## Triggers

- Internal timer (5 min).
- Optional: manual trigger via `mesh.call("narrator", NarrateRequest)` for on-demand summaries (out of scope v1).

## Outputs

- Publishes `Narrative` to `mesh.swarm.narrative` (broadcast).

## State

- Internal: rolling 5-min event window.
- KV: reads incident summaries (briefings) from the same bucket the briefer writes to.

## Lifecycle

- Always-on. Single instance.

## Reliability

- Lower-priority output. If the LLM fails, log and skip the period; do not retry into the next window.

## Behaviour notes

- LLM choice: Haiku (cheap, narrative quality is enough at this length).
- Prompt sources: structured incident summaries + counters from the previous narrate window. No raw text from external agents.
- Output: a single string up to 1000 chars, plus the list of incidents referenced for citation.

## Open questions

- Should the narrator also subscribe to detections directly so it can mention "we saw 230 detections in the last 5 min"? Yes, light-touch. Counts only, no raw payload reasoning.
- Should the narrator output be voiced (TTS) for the recorded video? Stretch goal. Not in v1.

## Subject contracts

Inbound subscriptions: TBD (likely `mesh.briefing.>`, `mesh.swarm.stats`). Outbound: `Narrative`.

## SDK shape needed

- Same as stats ticker: custom-subject publish (#2), multi-subject sub (#1).
