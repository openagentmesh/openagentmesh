# Tasker (LLM peer)

**Status:** discussion
**Identity:** `tasker` (single instance v1)

## Purpose

Translate firefighter operator natural language into a typed `TaskCommand` the operator (or `--auto-accept` CLI) can execute. The Tasker is request/reply only; it never publishes commands itself.

## Triggers

- Invocable: `mesh.call("tasker", TaskTranslateRequest)`.

## Outputs

- Returns `TaskCommand` synchronously.

## State

- Internal: prompt template, LLM client, structured output schema.
- KV (read): incident state from `wildfire.incident.*` to inform the LLM about open situations.
- Catalog: read on each request to discover available action fleets and their contracts.

## Lifecycle

- Always-on. Single instance v1.

## Reliability

- Pydantic validation on the LLM's structured output is the safety net. Hallucinated `target_fleet="hovercraft"` fails validation; the agent raises a typed error returned to the caller.
- LLM rate limit / timeout: surface as `MeshError` with a recoverable code; CLI prints and re-prompts.

## Behaviour notes

- Prompt sources: only structured data. Open incidents (KV), available action fleets (`mesh.catalog()`), `operator_id`, the operator's `text`. Never raw text from any other agent.
- Default LLM: Sonnet with `tool_choice` forcing the structured output schema.
- Latency target: <2s p95.
- `target_fleet` is constrained to the action-fleet set: `heli`, `ffunit`, `medevac`. The CLI maps these to the channel-prefixed agent name (`low-alt.heli`, `ground.ffunit`, `ground.medevac`).

## Open questions

- Should the Tasker stream tokens for visible reasoning? Defer; translation is short.
- Catalog freshness: per-request fetch is simpler than subscribing to catalog changes. Lean per-request.
- Should the Tasker be queue-grouped (multiple instances) for redundancy? V1: no, single instance.

## Subject + KV contracts

- Inbound: `mesh.call("tasker", TaskTranslateRequest)` -> auto-mapped to `mesh.agent.tasker`.
- Outbound: synchronous `TaskCommand` reply.

## SDK shape needed

- Plain `@mesh.agent` Responder. **Compiles on current SDK without changes.**
