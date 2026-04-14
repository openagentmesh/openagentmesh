# ADR-0021: Consolidate JetStream bucket specification

- **Type:** architecture
- **Date:** 2026-04-13
- **Status:** accepted
- **Source:** .specstory/history/2026-04-13_21-50-40Z.md

## Context

Bucket names were established across ADR-0013 (hyphenated naming) and ADR-0010 (object store in Phase 1), but no single document specified the complete bucket inventory with type (KV vs Object Store), purpose, key patterns, TTL, history depth, or replica settings. The `agentmesh up` CLI command needs an authoritative spec to pre-create these buckets.

## Decision

Publish an authoritative bucket specification covering all four JetStream buckets:

| Bucket | Type | Purpose | Key Pattern |
|--------|------|---------|-------------|
| `mesh-catalog` | KV | Single-key lightweight catalog index | `catalog` (single key) |
| `mesh-registry` | KV | Per-agent full contract storage | `{channel}.{name}` or `{name}` |
| `mesh-context` | KV | Shared context data between agents | Application-defined |
| `mesh-artifacts` | Object Store | Binary artifact storage between agents | Application-defined |

Open questions deferred to implementation:
- TTL for `mesh-context` entries (session-scoped? explicit expiry?)
- Max object size for `mesh-artifacts`
- Replica count (1 for dev/local, configurable for production)
- History depth for `mesh-registry` (1 is sufficient; higher enables contract version auditing)

## Risks and Implications

- TTL and size limits for `mesh-context` and `mesh-artifacts` must be resolved before `agentmesh up` implementation. Leaving them open risks inconsistent defaults across deployments.
- The `mesh-catalog` bucket uses a single key with CAS updates (per ADR-0014). All other buckets use per-entity keys.
- `mesh-artifacts` as Object Store means it has different API semantics than the KV buckets. SDK must handle both store types in lifecycle management.
