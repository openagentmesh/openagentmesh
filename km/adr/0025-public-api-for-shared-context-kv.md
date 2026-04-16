# ADR-0025: Public API for shared context KV (`mesh-context` bucket)

- **Type:** api-design
- **Date:** 2026-04-14
- **Status:** discussion
- **Source:** conversation (cookbook design discussion on dynamic task lists use case)

## Context

ADR-0021 consolidated the JetStream bucket specification into four buckets:

| Bucket | Type | SDK surface |
|--------|------|-------------|
| `mesh-catalog` | KV | Internal — `mesh.catalog()` / `mesh.discover()` |
| `mesh-registry` | KV | Internal — `mesh.contract()` |
| `mesh-artifacts` | Object Store | `mesh.workspace.*` |
| `mesh-context` | KV | **None — not exposed** |

`mesh-context` is designed for structured, shared mutable state between agents: task lists, workflow progress, running totals, coordination signals. The spec (§4.9) describes it as "shared context/memory" for agents to "read and potentially update as the workflow progresses."

Without a public API for `mesh-context`, the "dynamic task lists" cookbook recipe cannot be written. Agents need to:

1. Read the current state of a shared object
2. Modify it
3. Write it back with optimistic concurrency control (CAS) to avoid overwriting another agent's concurrent update

This CAS read-modify-write loop is the core operation. The spec acknowledges it ("agents that need shared mutable state must implement a read-modify-write loop with retry on revision conflict. The SDK provides this as a helper.") but never defines what that helper looks like.

Three questions are bundled here: the accessor name, the typing model, and the CAS abstraction level.

## Options

### Option A: Low-level `mesh.context` accessor with manual CAS

```python
# Basic get/put
raw = await mesh.context.get("project-alpha/tasks")      # returns bytes or None
await mesh.context.put("project-alpha/tasks", json.dumps(tasks).encode())

# CAS variant
raw, revision = await mesh.context.get_with_revision("project-alpha/tasks")
await mesh.context.put_if_revision("project-alpha/tasks", new_value, expected_revision=revision)

# Watch for changes
async for update in mesh.context.watch("project-alpha/tasks"):
    process(update)
```

Exposes the KV primitives directly. The CAS retry loop is the developer's responsibility. Consistent with how `mesh.workspace` works. Maximum flexibility, minimum magic.

### Option B: `mesh.context` with typed get/put and a CAS context manager

```python
# Typed put/get (Pydantic model round-trips automatically)
await mesh.context.put("project-alpha/tasks", task_list)  # TaskList is a BaseModel
task_list = await mesh.context.get("project-alpha/tasks", model=TaskList)

# Context-manager update handles CAS retry loop internally
async with mesh.context.update("project-alpha/tasks", model=TaskList) as state:
    for task in state.tasks:
        if task.status == "pending":
            task.status = "in_progress"
            task.assignee = "researcher"
            break
# Serializes, retries on CAS conflict, commits

# Watch (typed)
async for state in mesh.context.watch("project-alpha/tasks", model=TaskList):
    print(state.pending_count)
```

The `update()` context manager is the killer feature: it reads, yields a mutable object, serializes, and retries on conflict without requiring the developer to manage revisions. This is the highest-leverage abstraction for multi-agent state coordination.

### Option C: Unified `mesh.workspace` API with store-type differentiation

Fold `mesh-context` access into `mesh.workspace`, differentiating KV vs Object Store by the operation used:

```python
# KV-backed (mesh-context) — structured, small, watch-able
await mesh.workspace.set("context/project-alpha/tasks", task_list)
state = await mesh.workspace.get_kv("context/project-alpha/tasks", model=TaskList)

# Object Store-backed (mesh-artifacts) — binary, large
key = await mesh.workspace.put("artifacts/pipeline-123/doc.md", content_bytes)
content = await mesh.workspace.get(key)
```

Fewer namespaces on `mesh`, but the two backends have meaningfully different semantics (max size, content type, watch behavior, CAS vs. revision). Unifying them may create a leaky abstraction.

## Open Questions

- Should `mesh.context` be a separate namespace from `mesh.workspace`, or a sub-accessor on the same object?
- Should the CAS retry loop be automatic (Option B's `update()`) or explicit (Option A)?
- Should typed Pydantic models be first-class (Option B) or opt-in via `model=` parameter?
- Is the `update()` context manager the right CAS abstraction, or does it hide too much?
