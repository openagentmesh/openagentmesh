# ADR-0027: Object Store workspace lifecycle and scoping

- **Type:** api-design
- **Date:** 2026-04-14
- **Status:** discussion
- **Source:** conversation (cookbook design discussion on iterative painting use case)

## Context

The "creating a painting through incremental improvements" cookbook recipe walks through a multi-agent workflow where agents iteratively refine a shared artifact stored in the Object Store (`mesh-artifacts`). The current `mesh.workspace` API exposes `put`, `get`, `watch`, and `delete`. Three gaps surfaced when trying to write the recipe:

**Versioning.** The recipe naturally produces a sequence of artifact revisions: `v1.png`, `v2.png`, `v3.png`. NATS Object Store has built-in revision tracking — every `put` to the same key increments a revision counter, and the full history is accessible. The SDK currently doesn't expose this. Developers either rely on manual key-per-version naming or lose history entirely.

**Scoping and cleanup.** A multi-step workflow creates multiple objects under a common prefix (e.g., `painting/session-abc123/`). When the workflow ends, these objects should be cleaned up. Nothing in the current API supports scoped or session-based cleanup. Callers must delete each key individually, and only if they remember to.

**Key naming conventions.** The spec is silent on how keys should be structured. The recipes imply hierarchical naming (`{workflow_id}/{artifact_name}`), but there is no SDK-enforced or SDK-encouraged convention. Without guidance, different agents in the same pipeline may use incompatible key structures.

## Options

### Option A: Manual versioning, no session scoping (status quo)

Developers manage versioning by using distinct keys per version and cleanup by calling `mesh.workspace.delete()` for each key. The SDK exposes only primitive operations.

```python
# Producer stores each version under a distinct key
key_v1 = await mesh.workspace.put(f"painting/{session_id}/v1.png", image_bytes)
key_v2 = await mesh.workspace.put(f"painting/{session_id}/v2.png", improved_bytes)

# Cleanup is manual
await mesh.workspace.delete(f"painting/{session_id}/v1.png")
await mesh.workspace.delete(f"painting/{session_id}/v2.png")
```

No new SDK concepts. Works today. Cleanup is error-prone (forgotten deletes accumulate in the Object Store), and there is no way to retrieve revision history without enumerating keys by naming convention.

### Option B: Expose NATS Object Store native revision history

Surface the Object Store's built-in revision tracking. Every `put` to the same key creates a new revision. The SDK exposes `history()` and `get_revision()`:

```python
# Always write to the same key; NATS keeps revisions automatically
await mesh.workspace.put(f"painting/{session_id}/current.png", image_bytes)
await mesh.workspace.put(f"painting/{session_id}/current.png", improved_bytes)

# Retrieve revision history
versions = await mesh.workspace.history(f"painting/{session_id}/current.png")
# [ObjectRevision(seq=1, size=..., modified=...), ObjectRevision(seq=2, ...)]

# Retrieve a specific revision
old_version = await mesh.workspace.get_revision(f"painting/{session_id}/current.png", revision=1)
```

Simpler key structure (no `v1`, `v2` suffix gymnastics). History is native to the store, not reconstructed from naming conventions. Rollback is trivial.

Downside: NATS Object Store revision semantics differ from KV revision semantics. History depth is configurable at bucket creation time; deep histories for large binary objects consume significant storage. The SDK must surface these settings or accept reasonable defaults.

### Option C: Session-scoped workspace with automatic cleanup

Add a context-manager-based workspace session that automatically deletes all objects it creates when the context exits:

```python
async with mesh.workspace.session(f"painting/{session_id}") as ws:
    key = await ws.put("current.png", image_bytes)
    key = await ws.put("current.png", improved_bytes)
    final = await ws.get("current.png")
    # Yields final artifact
# All objects under "painting/{session_id}/" deleted on exit

# Optionally keep artifacts by committing
async with mesh.workspace.session(f"painting/{session_id}") as ws:
    ...
    ws.commit()  # prevents cleanup on exit
```

Combines versioning (Option B's single-key writes) with automated cleanup. The session prefix becomes a natural scoping boundary. Multi-agent workflows that create and discard many intermediate artifacts benefit most.

Downside: introduces a new concept (`session`) and requires the SDK to track which keys were created within the session. Long-running sessions with crash recovery become complex — if the orchestrator crashes before `__aexit__` is called, cleanup never happens.

### Option D: Key naming convention guidance only (no new API)

Document a recommended key naming convention (`{workflow_id}/{step}/{artifact_name}`) without adding versioning or session APIs. Cleanup helpers remain `delete()` by prefix pattern.

```python
# Recommended convention documented, not enforced
key = await mesh.workspace.put(f"wf-{workflow_id}/step-3/output.png", image_bytes)

# Batch delete by prefix (new helper only)
await mesh.workspace.delete_prefix(f"wf-{workflow_id}/")
```

Minimal SDK surface expansion. `delete_prefix` is the only new method. Developers follow the convention or don't — the SDK doesn't enforce it.

## Open Questions

- How important is revision history for Phase 1? The painting recipe works without it (manual versioning is functional, just verbose).
- Should cleanup be the SDK's responsibility (Option C) or the developer's (Options A/B/D)?
- What is the expected retention policy for `mesh-artifacts`? If objects are short-lived by default (TTL set at bucket creation), cleanup becomes less critical.
- Does the session concept belong in Phase 1 or is it a Phase 2 convenience?
