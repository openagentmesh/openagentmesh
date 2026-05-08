# ADR-0060: KV ergonomics — `list`, `try_cas`, `create`, model helpers

- **Type:** api-design
- **Date:** 2026-05-08
- **Status:** spec
- **Source:** wildfire demo shaping (sdk-desiderata.md #9). KV is the demo's coordination backbone; current `mesh.kv` API gaps force boilerplate around election, snapshot reads, and Pydantic round-tripping.
- **Amends:** ADR-0025 (public API for shared context KV).
- **Related:** ADR-0014 (CAS on catalog updates — internal pattern), ADR-0021 (consolidated bucket spec), ADR-0052 (KV-watch sources).

## Context

ADR-0025 exposes a `KVStore` on `mesh.kv` for the `mesh-context` bucket with: `put`, `get`, `cas` (context manager, single attempt), `update` (auto-retry CAS), `watch`, `delete`. Pattern wildcards on `watch` already work via NATS subject conventions (verified by probe).

Wildfire shaping surfaced four ergonomic gaps that recur across most KV-using agents:

1. **One-shot snapshot read of all entries under a prefix.** Drones need to read all peer position records (`wildfire.fleet.low-alt.drone.*`) once when running election logic. Today: use `watch(pattern)` with manual draining, awkward.

2. **Non-raising CAS.** Election semantics: "if I'm the closest free drone, claim this detection; if someone else got there first, do nothing." That's CAS-failure-as-data, not as exception. Current `cas` raises `KeyWrongLastSequenceError` on conflict; user code wraps in try/except. A boolean-returning variant matches the intent directly.

3. **Put-if-absent.** UAVs creating new detection records must fail if the key already exists (race protection between sensor windows). Current `put` overwrites silently.

4. **Pydantic helpers.** Demo serializes Pydantic to JSON and back on every read/write. Wrappers cut boilerplate and concentrate the JSON convention in one place.

## Decision

Extend `KVStore` with the following methods. None alter existing methods; this is purely additive.

### `list(prefix: str) -> list[KVEntry]`

```python
async def list(self, prefix: str) -> list[KVEntry]: ...
```

Returns a snapshot of all current entries whose keys match the given prefix or wildcard pattern. Implementation uses the underlying NATS `KeyValue.watch(prefix)` with init-done detection: collects entries until the historical replay completes, returns the list, closes the watch.

`KVEntry` shape matches the source-side definition (ADR-0052):

```python
class KVEntry(Generic[T]):
    key: str
    value: T            # bytes by default; typed via list_models
    revision: int
    operation: Literal["PUT", "DELETE"]
    timestamp: float
```

Pattern wildcards (`*`, `>`) are accepted. For "list everything in the bucket", pass `>`.

```python
peers = await mesh.kv.list("wildfire.fleet.low-alt.drone.*")
free_peers = [e for e in peers if json.loads(e.value)["state"] == "free"]
```

### `try_cas(key: str) -> TryCASContext`

```python
def try_cas(self, key: str) -> TryCASContext: ...
```

Async context manager mirroring `cas(key)` but with a `committed` boolean attribute set on `__aexit__`. On CAS conflict, no exception is raised; `committed` stays `False`.

```python
async with mesh.kv.try_cas(detection_key) as entry:
    record = json.loads(entry.value)
    if record["state"] != "pending":
        return  # someone already claimed it
    record["state"] = f"assigned:{mesh.instance_id}"
    entry.value = json.dumps(record)

if entry.committed:
    # I claimed it
    await self.survey(...)
```

Implementation: the underlying CAS attempt catches `KeyWrongLastSequenceError`, sets `committed = False`, and swallows the exception. Any other exception (network, serialization) propagates as before.

If the user does not modify `entry.value` inside the block, no write is attempted, and `committed` is `True` (consistent semantics: "no change desired" succeeds vacuously). Distinguish "I lost the race" (committed=False after attempting a change) from "I chose not to write" (committed=True with no value mutation): inspect `entry.attempted_write` if needed.

### `create(key: str, value: BaseModel | bytes | str) -> int`

```python
async def create(self, key: str, value: BaseModel | bytes | str) -> int: ...
```

Put-if-absent. Returns the new revision number on success. Raises `KVKeyExists` (new exception in the OAM error taxonomy per ADR-0057) if the key already exists.

Maps to NATS KV's native `create` operation, which uses CAS internally with `revision=0`.

```python
try:
    rev = await mesh.kv.create(
        f"wildfire.detection.{detection_id}",
        DetectionRecord(state="pending", coords=coords, ...),
    )
except KVKeyExists:
    pass  # detection already created by an earlier sensor window or peer UAV
```

### Pydantic model helpers

```python
async def put_model(self, key: str, model: BaseModel) -> int: ...
async def get_model(self, key: str, model_cls: type[T]) -> T: ...
def cas_model(self, key: str, model_cls: type[T]) -> CASModelContext[T]: ...
def try_cas_model(self, key: str, model_cls: type[T]) -> TryCASModelContext[T]: ...
async def list_models(self, prefix: str, model_cls: type[T]) -> list[KVEntry[T]]: ...
```

These wrap the bytes-shaped methods with `model.model_dump_json()` on write and `model_cls.model_validate_json(...)` on read. Behavior is otherwise identical.

```python
async with mesh.kv.try_cas_model("wildfire.detection.abc", DetectionRecord) as entry:
    if entry.value.state != "pending":
        return
    entry.value.state = f"assigned:{mesh.instance_id}"
```

`entry.value` is the validated Pydantic model. Mutations on the model during the block are picked up; on `__aexit__`, the SDK serializes via `model_dump_json` and CAS-writes.

### Code sample (DX contract — drone election)

```python
@mesh.agent(
    AgentSpec(name="low-alt.drone", description="Survey drone, KV-elected"),
    sources=[mesh.kv_source("wildfire.detection.*")],
)
async def drone(entry: KVEntry[DetectionRecord]) -> None:
    if entry.operation != "PUT" or entry.value.state != "pending":
        return

    peers = await mesh.kv.list_models(
        "wildfire.fleet.low-alt.drone.*",
        FleetMemberState,
    )
    free_others = [
        p for p in peers
        if p.value.state == "free" and p.key != my_position_key
    ]
    if any(distance(p.value.coords, entry.value.coords) < my_distance for p in free_others):
        return

    async with mesh.kv.try_cas_model(entry.key, DetectionRecord) as cas_entry:
        if cas_entry.value.state != "pending":
            return
        cas_entry.value.state = f"assigned:{mesh.instance_id}"

    if cas_entry.committed:
        await self.survey(cas_entry.value)
```

## Consequences

- `KVStore` grows five new methods (counting model variants as wrappers). Implementation surface modest; each wraps existing primitives.
- New exception `KVKeyExists` added to the error taxonomy (ADR-0057). Imported from `openagentmesh._errors`.
- `KVEntry` becomes a public class (already needed by ADR-0052 sources).
- Documentation: extend the `mesh-context` API page with the new methods + a "KV-driven coordination" cookbook recipe (probably the wildfire drone election as the example).
- ADR-0042 watcher pattern's legacy form continues to work; sources + try_cas is the new canonical for election workflows.

## Alternatives Considered

**Add fewer methods, document patterns.** Rejected: every demo and any non-trivial KV-using user would re-write the same try/except wrappers and prefix-scan loops. Concentrating these in the SDK pays for itself after one or two users.

**Use a transaction abstraction (`async with mesh.kv.transaction() as tx: ...`).** Rejected: NATS KV does not support multi-key transactions. A "transaction" abstraction would either be a lie (single-key under the hood) or require an external coordinator. Out of scope.

**Generic typed KV: `kv = mesh.kv[DetectionRecord]("wildfire.detection")`.** Rejected for v1: too much abstraction for the value (a typed namespace handle would cover prefix + model in one object, but it complicates the simple case where keys span multiple types). Revisit if patterns demand it.

**Make `cas` non-raising by default and add `cas_strict` for raising.** Rejected: the existing `cas` is in the public API at v0.2.x; changing its semantics is a breaking change. Adding `try_cas` as a sibling preserves compatibility.
