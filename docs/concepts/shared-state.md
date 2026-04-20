# Shared State

Agents on the mesh share structured data through the **KV Store** and binary artifacts through the **Workspace**. Both are backed by NATS JetStream and provisioned automatically when the mesh starts.

!!! warning "Not a database"
    KV Store and Workspace are coordination primitives, not long-term storage. They are designed for in-flight state, intermediate artifacts, and session-scoped context. NATS JetStream does not provide the durability guarantees (backup/restore, replication policies, ACID transactions) of a database or cloud object storage. Persist anything that must survive beyond the current workflow to a proper datastore.

## KV Store (`mesh.kv`)

A key-value store for structured data (JSON strings, counters, configuration). Backed by the `mesh-context` JetStream KV bucket.

### Basic operations

```python
# Write
await mesh.kv.put("config/threshold", "0.85")

# Read
value = await mesh.kv.get("config/threshold")  # "0.85"

# Delete
await mesh.kv.delete("config/threshold")
```

Values are strings. For structured data, serialize to JSON:

```python
import json

await mesh.kv.put("plan-001", json.dumps({"status": "active", "tasks": []}))
raw = await mesh.kv.get("plan-001")
plan = json.loads(raw)
```

### Compare-and-swap

When multiple agents update the same key, use CAS to avoid lost writes.

**Single attempt** (for low-contention keys):

```python
async with mesh.kv.cas("config/threshold") as entry:
    current = float(entry.value)
    entry.value = str(current + 0.1)
```

**Automatic retry** (for high-contention keys):

```python
def increment(value: str) -> str:
    return str(int(value) + 1)

await mesh.kv.update("counter", increment)
```

`update()` re-reads the key and calls the function again if another agent modified it between read and write. Safe for concurrent access from any number of agents.

### Watching for changes

```python
async for value in mesh.kv.watch("plan-001"):
    plan = json.loads(value)
    if plan["status"] == "complete":
        break
```

The watcher receives the new value on every update. Useful for dashboards, progress monitors, or agents that react to state changes. See the [Reactive Pipeline](../cookbook/reactive-pipeline.md) recipe for a full example of building an orchestrator-free pipeline with `watch()`.

Wildcard watching matches keys by pattern. Use `.` as the key separator to enable this, since NATS treats `.` as a token delimiter:

```python
# Watch all keys matching "pipeline.*.raw" (any document ID)
async for value in mesh.kv.watch("pipeline.*.raw"):
    doc = json.loads(value)
    print(f"New document: {doc['id']}")
```

Keys with `/` work for `put`/`get`/`delete` but won't match wildcard patterns in `watch()`. Use `.` separators when you plan to watch by pattern.

## Workspace (`mesh.workspace`)

Binary artifact storage for files, images, embeddings, or any payload that doesn't fit in a KV string. Backed by the `mesh-artifacts` JetStream Object Store bucket.

### Basic operations

```python
# Store a file
pdf_bytes = Path("report.pdf").read_bytes()
await mesh.workspace.put("docs/report.pdf", pdf_bytes)

# Retrieve it
data = await mesh.workspace.get("docs/report.pdf")  # bytes

# Strings are auto-encoded to UTF-8
await mesh.workspace.put("notes/summary.txt", "quarterly results look good")

# Delete when done
await mesh.workspace.delete("docs/report.pdf")
```

### Key naming

Keys support `/` separators for logical hierarchy. The mesh does not enforce a naming convention, but a consistent pattern makes cleanup easier:

```
{workflow_id}/{artifact_name}
{workflow_id}/{step}/{artifact_name}
```

### Multi-agent artifact sharing

The workspace is shared across all agents on the mesh. One agent uploads; any other agent reads by key. No shared filesystems, no cloud storage credentials.

```python
# Agent A: produce an artifact
await mesh.workspace.put("pipeline/step-1/output.json", result_bytes)

# Agent B: consume it
data = await mesh.workspace.get("pipeline/step-1/output.json")
```

This pattern is central to the [Parallel RAG Indexing](../cookbook/parallel-rag-indexing.md) recipe, where an orchestrator uploads a document and multiple indexer agents read it concurrently.

## When to use which

| Need | Use | Why |
|------|-----|-----|
| Small structured data (config, plans, counters) | `mesh.kv` | String values, CAS for concurrency, watch for reactivity |
| Binary files (images, PDFs, model weights) | `mesh.workspace` | Handles large payloads, chunked storage |
| Coordination between agents | `mesh.kv` with CAS | Atomic read-modify-write prevents conflicts |
| Sharing intermediate results | `mesh.workspace` | Any agent can read by key, no coupling |
