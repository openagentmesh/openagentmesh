# ADR-0032: Catalog change subscription for client-side capability cache

- **Type:** protocol
- **Date:** 2026-04-17
- **Status:** documented

## Context

ADR-0005 introduced client-side pre-flight capability checks: `mesh.call()` and `mesh.stream()` verify the target agent's capabilities before sending the request. For local agents (registered on the same mesh instance), this check uses `self._agents`. For remote agents, a local cache of the catalog is needed.

Without a cache, the SDK would need to fetch the catalog on every invocation (slow) or skip the check entirely for remote agents (falling back to handler-side enforcement, which costs a round trip).

## Decision

The SDK maintains a local catalog cache, populated by a background subscription to catalog changes. The subscription starts on connect and stops on disconnect.

### Behavior

```python
async with AgentMesh.local() as mesh:
    # _catalog_cache is populated automatically from the catalog KV
    # mesh.call() and mesh.stream() check it before sending requests

    # mesh.catalog() reads from the cache (no KV fetch)
    agents = await mesh.catalog()
```

### Implementation

- `__aenter__` starts a background task that watches the `mesh-catalog` KV key.
- Each catalog update (agent register/deregister) replaces the entire cache (the catalog is a single denormalized JSON array).
- `mesh.catalog()` reads from the cache instead of hitting KV on every call.
- `_check_streaming()` and `_check_buffered()` use the cache for remote agents.
- `__aexit__` cancels the background watcher task.

### Language

The spec describes this as a "catalog change subscription," not a "KV watcher." Transport-neutral language; any implementation must provide push-based catalog updates.

## Risks and Implications

- The cache may be momentarily stale (milliseconds). Handler-side enforcement (ADR-0005) covers the gap.
- One additional subscription per mesh instance. Negligible resource cost.
- `mesh.catalog()` becomes eventually consistent rather than point-in-time reads from KV. This matches the catalog's existing consistency model.
