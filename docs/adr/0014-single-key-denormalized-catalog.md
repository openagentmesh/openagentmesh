# ADR-0014: Single-key denormalized catalog pattern

- **Type:** architecture
- **Date:** 2026-04-04
- **Status:** accepted
- **Source:** .specstory/history/2026-04-04_09-50-29Z.md

## Context

The catalog needs to serve LLM-based agent selection efficiently. The question was whether to store one KV key per agent (normalized) or a single key containing all entries (denormalized).

## Decision

Use a single KV key (`catalog` in the `mesh-catalog` bucket) containing a JSON array of all lightweight catalog entries. This gives O(1) catalog reads: one KV get returns the entire agent list, ideal for stuffing into LLM context (~20-30 tokens per agent).

Updates use CAS (Compare-And-Swap): read the current value + revision, modify the array, write back only if the revision hasn't changed. On conflict, retry the read-modify-write loop. Brief staleness (milliseconds) is acceptable; `mesh.contract()` reads per-agent full contracts and is the authoritative source.

## Alternatives Considered

- **One KV key per agent.** Requires listing/enumerating all keys for catalog reads, which is O(n) and inefficient for the primary use case (LLM planning needs the full list at once).

## Risks and Implications

- CAS contention under high concurrent registration. In practice, registration is infrequent compared to reads, so this is acceptable. Retries converge quickly.
- The catalog JSON array grows linearly. At ~500 agents the payload is still small (~15KB). Beyond that, the two-step discovery pattern (catalog for selection, contract for detail) remains correct.
- Single point of write contention. If this becomes a bottleneck, the catalog could be sharded by channel. Not needed for Phase 1 targets.
