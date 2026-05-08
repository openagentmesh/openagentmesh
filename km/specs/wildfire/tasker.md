# Tasker (LLM peer)

**Status:** discussion

## Purpose

Translate firefighter natural language into a typed `TaskCommand` the human (or auto-accepting CLI) can execute. The Tasker is request/reply only: it never publishes commands itself.

## Triggers

- Invocable via `mesh.call("tasker", TaskTranslateRequest)`.

## Outputs

- Returns `TaskCommand` synchronously.

## State

- Internal: prompt template, LLM client.
- KV: reads `mesh.catalog()` results to inform the LLM about available fleets and their contracts.

## Lifecycle

- Always-on. Single instance v1 (no queue group) since the workload is light. Could scale to a queue group later.

## Reliability

- Pydantic validation on the LLM's structured output is the safety net. If validation fails (hallucinated `target_fleet="hovercraft"`), the agent raises `InvalidInput` (or a tasker-specific `ValueError`) and the firefighter CLI handles it.
- LLM rate limit: surface as `MeshError` with code `llm_rate_limited` (suggest retry-after).

## Behaviour notes

- Prompt sources: only structured data. Open incidents (KV), fleet capabilities (`mesh.catalog()`), `unit_id`, the firefighter's `text`. Never the raw text from any other agent.
- Default LLM: Sonnet with `tool_choice` forcing the structured output schema.
- Latency target: <2s p95. Otherwise the firefighter CLI feels sluggish.

## Open questions

- Should the Tasker offer a `mesh.stream("tasker", ...)` variant for token streaming so the firefighter sees the rationale build up? Probably overkill for a translation step; defer.
- Fleet capability discovery: should the Tasker subscribe to catalog changes (ADR-0032) so its prompt always reflects current fleet membership, or fetch on each request? Per-request fetch is simpler and the catalog read is cheap. Lean per-request.

## Subject contracts

Inbound: `TaskTranslateRequest`. Outbound: `TaskCommand`.

## SDK shape needed

- Plain `@mesh.agent` Responder. **Compiles on current SDK without changes.**
