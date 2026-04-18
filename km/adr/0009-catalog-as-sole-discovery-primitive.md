# ADR-0009: Catalog as sole discovery primitive: no separate tags/channels API

- **Type:** api-design
- **Date:** 2026-04-06
- **Status:** documented
- **Source:** .specstory/history/2026-04-06_19-28-01Z.md

## Context

Tags are a first-class filter axis on the catalog. The question was whether to add `mesh.tags()` (and potentially `mesh.channels()`) as separate discovery methods for a "browse → narrow → select" flow.

## Decision

Drop it. The catalog (~20-30 tokens/agent) already fits in LLM context. A separate `mesh.tags()` call pays for a round-trip to derive what's already visible in the catalog response. The LLM can extract tags and channels itself from what's already there.

The catalog is the exploration primitive; no need for another one.

## Alternatives Considered

- **`mesh.tags()` returning `list[str]`.** Trivial to implement (filter on catalog data) but adds an unnecessary API call and LLM round-trip.
- **`mesh.tags()` returning `dict[str, int]` with counts.** Richer but still derivable from catalog.

## Risks and Implications

- At scale (500+ agents), the catalog may no longer fit comfortably in context. At that point, a tag/channel index might be reconsidered. For Phase 1 targets, the catalog is sufficient.
- Keeps the API surface minimal, fewer methods for users to learn.
