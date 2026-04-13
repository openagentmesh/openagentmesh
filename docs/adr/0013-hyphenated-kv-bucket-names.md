# ADR-0013: Hyphenated KV bucket names (mesh-catalog not mesh.catalog)

- **Type:** architecture
- **Date:** 2026-04-04
- **Status:** accepted
- **Source:** .specstory/history/2026-04-04_09-50-29Z.md

## Context

Initial design used dots in KV bucket names (`mesh.catalog`, `mesh.registry`). NATS JetStream KV bucket names must match a validation regex that does not allow dots.

## Decision

Use hyphens instead of dots for all KV bucket names:
- `mesh-registry`: per-agent full contracts
- `mesh-catalog`: single key with lightweight catalog array
- `mesh-context`: shared context data
- `mesh-artifacts`: shared object store for binary artifacts

NATS subjects (which do use dots) remain unchanged: `mesh.agent.{channel}.{name}`, `mesh.registry.{channel}.{name}`, etc.

## Risks and Implications

- Naming inconsistency between KV buckets (hyphens) and NATS subjects (dots). Documented in code comments and spec. Developers must not confuse the two namespaces.
