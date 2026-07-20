# AgentMesh

The central class. Manages NATS connection, agent subscriptions, and lifecycle.

## Construction

```python
from openagentmesh import AgentMesh

# Connect to an existing NATS server
mesh = AgentMesh("nats://localhost:4222")

# Connect using default localhost URL
mesh = AgentMesh()
```

### `AgentMesh(url, *, creds=None, tls_cert=None, tls_key=None, tls_ca=None)`

Connect to a running NATS server. Defaults to `nats://localhost:4222` when no URL is provided.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `str` | `"nats://localhost:4222"` | NATS connection URL |
| `creds` | `str \| None` | `None` | Path to a NATS `.creds` file. When omitted, resolves from `OAM_CREDS`, then the `creds` field of `.oam-url`; otherwise connects open. See [Securing the Mesh](../concepts/security.md). |
| `tls_cert` | `str \| None` | `None` | Client certificate for mTLS |
| `tls_key` | `str \| None` | `None` | Client key for mTLS |
| `tls_ca` | `str \| None` | `None` | CA bundle used to verify the server |

Connecting without valid credentials to a server that requires them raises `ConnectionDenied` (code `connection_denied`).

### `AgentMesh.local()`

Async context manager that starts an embedded NATS subprocess with JetStream and pre-created KV buckets. For tests and quick demos only. The NATS process stops when the context exits.

```python
async with AgentMesh.local() as mesh:
    # embedded NATS starts, KV buckets created
    result = await mesh.call("echo", {"message": "hello"})
    # NATS stops when context exits
```

### `mesh.instance_id`

A read-only attribute holding a stable per-process identifier (UUID4 hex). Each `AgentMesh()` instance generates its own at construction; it does not change for the lifetime of the instance.

```python
mesh = AgentMesh()
print(mesh.instance_id)
# => "e7b3a91d4f8c2d6a8b5e9c1f0d3a7b2e"
```

The SDK auto-stamps `X-Mesh-Instance-Id: {mesh.instance_id}` on every outbound NATS message (call, send, stream, agent replies, publisher emissions). Receivers can read the header to attribute messages to a specific replica when multiple instances of the same agent name are deployed.

User-supplied headers (where the API accepts them) take priority: the SDK only sets a default when the header is not already present.

See [ADR-0059](https://github.com/lucasorgiacomo/openagentmesh/blob/main/km/adr/0059-mesh-instance-id.md) for design rationale.

## Lifecycle

Two lifecycle models, one for each [participation pattern](../concepts/participation.md).

### `mesh.run()`

Blocking lifecycle for providers and hybrids. Connects to NATS, subscribes all registered agents, and blocks until interrupted. Similar to `uvicorn.run()`.

```python
mesh.run()
```

This is the standard entry point for any process that registers agents with `@mesh.agent`.

### `async with mesh:`

Scoped lifecycle for consumers. Connects on entry, disconnects on exit. No agent registration; used by scripts, notebooks, and orchestrators that only discover and call agents.

```python
async with mesh:
    result = await mesh.call("echo", {"message": "hello"})
```

Embedding in an existing async application (e.g. FastAPI lifespan):

```python
async def lifespan(app):
    async with mesh:
        yield
```

## Registration

### `@mesh.agent(spec)`

Decorator to register an async function as a mesh agent. Takes a single `AgentSpec` instance.

```python
from openagentmesh import AgentMesh, AgentSpec

mesh = AgentMesh()

spec = AgentSpec(
    name="nlp.summarizer",
    description="Summarizes text to a target length.",
    tags=["text", "summarization"],
)

@mesh.agent(spec)
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    ...
```

Capabilities are inferred from the handler shape at decoration time. `AgentSpec` carries only human-authored metadata; `invocable` and `streaming` are never declared manually.

### `@mesh.agent(spec, *, sources=[...])`

Bind an agent to one or more declarative trigger surfaces (ADR-0052). Sources are runtime wiring; they do not appear in the catalog. The handler's first-parameter type hint determines what the source dispatches:

| Annotation | Receives |
|---|---|
| `bytes` | Raw payload bytes |
| `Model` (Pydantic) | Validated `Model` instance |
| `KVEntry[Model]` | Full KV entry (key, value, revision, operation) with `value` validated to `Model`. Use `KVEntry[bytes]` to skip validation. |
| `MeshMessage[Model]` | Full NATS envelope (subject, headers, payload) with `payload` validated to `Model`. |

When the handler takes `KVEntry` or `MeshMessage`, the agent is **not invocable** via `mesh.call` (the runtime cannot synthesize an envelope from a wire payload). Use plain Pydantic input or no input for invocable shapes.

```python
from openagentmesh import AgentMesh, AgentSpec, KVEntry

mesh = AgentMesh()

@mesh.agent(
    AgentSpec(name="watcher", description="reacts to detection records"),
    sources=[mesh.kv_source("wildfire.detection.*")],
)
async def react(entry: KVEntry[DetectionRecord]) -> None:
    if entry.operation == "PUT" and entry.value.state == "pending":
        ...
```

#### `mesh.subject_source(subject, *, queue_group=None)`

NATS subject source. Wildcards (`*`, `>`) are supported. `queue_group` enables at-most-one-of-N delivery across replicas.

#### `mesh.kv_source(pattern, *, queue_group=None, on_init="replay")`

KV-watch source on the `mesh-context` bucket. `on_init="replay"` (default) fires the handler for every existing entry under the pattern at agent startup, then continues with live updates. `on_init="skip"` waits for the initial snapshot to drain and then triggers only on subsequent changes. `queue_group` is reserved for JetStream-backed consumers (raises `NotImplementedError` in v1).

| Handler shape | `invocable` | `streaming` | Consumer API |
|---------------|-------------|-------------|--------------|
| `async def f(req) -> Out: return ...` | `True` | `False` | `mesh.call()` |
| `async def f(req) -> Chunk: yield ...` | `True` | `True` | `mesh.stream()` |
| `async def f() -> Out: return ...` | `True` | `False` | `mesh.call()` |
| `async def f() -> Event: yield ...` | `False` | `True` | `mesh.subscribe()` |
| `async def f(): ...` | `False` | `False` | (background task) |

### `@mesh.agent(spec, *, active_when=...)`

Gate the agent's subscription on a condition (ADR-0055). The agent stays in the catalog either way; while the condition is false it is unsubscribed and callers get `not_available`. Composes with `sources` — gated sources deliver nothing while the agent is offline. See [Lifecycle Gates](../concepts/lifecycle.md).

```python
@mesh.agent(
    AgentSpec(name="coordinator", description="active-incident work"),
    active_when=mesh.kv_condition("incident.mode", lambda v: v == b'"active"'),
)
async def coordinator(brief: Brief) -> Assignment:
    ...
```

#### `mesh.kv_condition(key, predicate, *, initial=False, drain_timeout=30.0)`

Gate on a `mesh-context` KV key. `predicate` receives the key's raw `bytes` value (`None` when absent or deleted). The current value is read and applied when the mesh starts; `initial` is the fallback state if that read fails. On gate close, in-flight handlers get `drain_timeout` seconds to finish.

#### `mesh.subject_condition(subject, predicate, *, initial=False, drain_timeout=30.0)`

Gate on messages arriving on a plain NATS subject. `predicate` receives each message's payload `bytes`; the agent's state follows the most recent verdict. `initial` is the state before the first message.

## Invocation

Four interaction modes. See [Invocation](../concepts/invocation.md) for patterns and semantics.

### `await mesh.call(name, payload, *, timeout=30.0)`

Synchronous request/reply. Blocks until the agent responds or times out.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent name |
| `payload` | `Any` | `None` | Input payload (dict, Pydantic model, or any JSON-serializable value) |
| `timeout` | `float` | `30.0` | Timeout in seconds |

**Returns:** `dict` with the deserialized response payload.

**Raises:** `NotFound` when nobody serves the agent and it is not in the
catalog (immediate, via NATS no-responders); `NotAvailable` when it is in the
catalog but a [lifecycle gate](../concepts/lifecycle.md) has it offline;
`AgentDied` when the agent leaves the mesh while your request is in flight
(sub-second, via [death notices](../concepts/liveness.md)); `MeshTimeout`
when the deadline expires with the agent still connected.

### `async for chunk in mesh.stream(name, payload, *, timeout=60.0)`

Streaming request. Yields response chunks as dicts. Raises `AgentDied` from
the generator if the agent leaves the mesh mid-stream.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent name |
| `payload` | `Any` | `None` | Input payload (dict, Pydantic model, or any JSON-serializable value) |
| `timeout` | `float` | `60.0` | Total stream timeout in seconds |

**Yields:** `dict` chunks.

### `await mesh.send(name, payload, *, on_reply, on_error, reply_to, timeout)`

Async callback invocation. Three modes: fire-and-forget, managed callback, or manual reply subject.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent name |
| `payload` | `Any` | `None` | Input payload (dict, Pydantic model, or any JSON-serializable value) |
| `on_reply` | `Callable[[dict], Awaitable[None]] \| None` | `None` | Callback for each reply message |
| `on_error` | `Callable[[MeshError], Awaitable[None]] \| None` | `None` | Callback for timeout or error |
| `reply_to` | `str \| None` | `None` | Manual reply subject (mutually exclusive with `on_reply`) |
| `timeout` | `float` | `60.0` | Inactivity timeout (only applies with `on_reply`) |

```python
# Managed callback
await mesh.send("summarizer", payload, on_reply=handle, on_error=on_err, timeout=30.0)

# Fire-and-forget
await mesh.send("summarizer", payload)

# Manual reply subject
await mesh.send("summarizer", payload, reply_to="mesh.results.abc")
```

### `await mesh.publish(subject, payload, *, headers=None)`

Publish a payload to an arbitrary NATS subject without addressing a specific agent. Use for broadcasting events to a flat domain subject (sensors, tickers, scenario commands, status feeds) rather than to an agent's auto-mapped invocation subject.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `subject` | `str` | required | NATS subject (no wildcards) |
| `payload` | `BaseModel \| bytes \| str` | required | Payload to publish |
| `headers` | `dict[str, str] \| None` | `None` | Optional user headers (override SDK defaults) |

The SDK auto-stamps three headers: `X-Mesh-Request-Id` (uuid hex), `X-Mesh-Instance-Id` (this mesh's id, ADR-0059), and `X-Mesh-Content-Type` (`application/json` for `BaseModel`, `application/octet-stream` for `bytes`, `text/plain` for `str`). User-supplied headers take priority.

Wildcards (`*`, `>`) raise `ValueError`. Subscribe-side wildcards are still supported via `mesh.subscribe(subject=...)`.

```python
class Reading(BaseModel):
    sensor_id: str
    value: float

await mesh.publish("sensor.temperature", Reading(sensor_id="s1", value=42.0))
await mesh.publish("logs.audit", "user-x logged in")
await mesh.publish("binary.frames", b"\x00\x01\x02...")
```

See [ADR-0058](https://github.com/lucasorgiacomo/openagentmesh/blob/main/km/adr/0058-public-mesh-publish.md).

## Subscription

### `async for msg in mesh.subscribe(*, agent, channel, subject, timeout)`

Subscribe to events on a subject, agent, or channel. Returns an async generator yielding dicts.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agent` | `str \| None` | `None` | Agent's dotted name (resolves to its event subject) |
| `channel` | `str \| None` | `None` | Channel prefix (subscribes to `mesh.agent.{channel}.>`) |
| `subject` | `str \| None` | `None` | Raw NATS subject |
| `timeout` | `float \| None` | `None` | Inactivity timeout in seconds |

At least one of `agent`, `channel`, or `subject` must be provided. `agent` and `subject` are mutually exclusive.

```python
# Subscribe to an agent's event stream
async for event in mesh.subscribe(agent="price-feed"):
    print(event["symbol"], event["price"])

# Subscribe to all events in a channel
async for event in mesh.subscribe(channel="finance"):
    print(event)

# Subscribe to a raw subject
async for msg in mesh.subscribe(subject="mesh.results.abc123", timeout=30.0):
    print(msg)
    break
```

## Discovery

### `await mesh.catalog(*, channel=None, tags=None, streaming=None, invocable=None)`

Lightweight listing of registered agents. Returns typed `CatalogEntry` objects.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `channel` | `str \| None` | `None` | Filter by name prefix (an entry matches when its name equals `channel` or starts with `channel + "."`) |
| `tags` | `list[str] \| None` | `None` | Filter by tags (all must match) |
| `streaming` | `bool \| None` | `None` | Filter by streaming capability |
| `invocable` | `bool \| None` | `None` | Filter by invocable capability |

**Returns:** `list[CatalogEntry]`

```python
catalog = await mesh.catalog(channel="nlp")

for entry in catalog:
    print(entry.name, "-", entry.description)
    # entry.invocable, entry.streaming, entry.version, entry.tags also available
```

### `await mesh.discover(*, channel=None)`

Full `AgentContract` objects for all matching agents.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `channel` | `str \| None` | `None` | Filter by name prefix (same semantics as `catalog(channel=...)`) |

**Returns:** `list[AgentContract]`

### `await mesh.contract(name)`

Fetch a single agent's full contract. This is the authoritative source.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | `str` | required | Agent's dotted name |

**Returns:** `AgentContract`

```python
contract = await mesh.contract("nlp.summarizer")

contract.name             # "nlp.summarizer"
contract.description      # "Summarizes text..."
contract.input_schema     # JSON Schema dict
contract.output_schema    # JSON Schema dict
contract.invocable        # True
contract.streaming        # False
```

## KV Store

Shared KV store for structured data exchange between agents.

### `await mesh.kv.put(key, value)`

Store a value.

### `await mesh.kv.get(key)`

Retrieve a value by key. Returns `str`.

### `async with mesh.kv.cas(key) as entry`

Single-attempt compare-and-swap. Read `entry.value`, modify it, and the new value is written on exit with CAS semantics. For concurrent access, use `update()` instead.

### `await mesh.kv.update(key, fn)`

CAS update with automatic retry. `fn` receives the current value and returns the new value. On revision conflict, the value is re-read and `fn` is called again.

```python
def increment(value: str) -> str:
    return str(int(value) + 1)

await mesh.kv.update("counter", increment)
```

### `async for value in mesh.kv.watch(key)`

Watch a key for changes. Yields the new value on each update.

### `await mesh.kv.delete(key)`

Delete a key.

### `await mesh.kv.list(prefix)`

One-shot snapshot of all entries under a prefix or wildcard pattern (ADR-0060). NATS subject wildcards (`*`, `>`) are accepted. Returns `list[KVEntry[bytes]]` with `key`, `value`, `revision`, and `operation`.

```python
entries = await mesh.kv.list("wildfire.detection.*")
for e in entries:
    print(e.key, e.revision, len(e.value))
```

### `async with mesh.kv.try_cas(key) as entry`

Non-raising compare-and-swap (ADR-0060). On conflict, `entry.committed` is `False` and no exception is raised. Use for election semantics where losing the race is data, not error.

```python
async with mesh.kv.try_cas("election.key") as entry:
    if entry.value == "pending":
        entry.value = f"assigned:{mesh.instance_id}"

if entry.committed:
    # I won the race
    ...
```

### `await mesh.kv.create(key, value)`

Put-if-absent (ADR-0060). Returns the new revision number on success. Raises `KVKeyExists` if the key already exists. Accepts `BaseModel`, `bytes`, or `str`.

### Pydantic helpers

`mesh.kv.put_model(key, model)`, `mesh.kv.get_model(key, Model)`, `mesh.kv.cas_model(key, Model)`, `mesh.kv.try_cas_model(key, Model)`, `mesh.kv.list_models(prefix, Model)`. Same semantics as the bytes-shaped methods, with serialization to/from `model.model_dump_json()` handled internally.

```python
async with mesh.kv.try_cas_model("wildfire.detection.d1", DetectionRecord) as entry:
    if entry.value.state == "pending":
        entry.value.state = f"assigned:{mesh.instance_id}"
```

## Workspace (Object Store)

Shared binary artifact storage backed by the NATS JetStream Object Store (`mesh-artifacts` bucket). Use for files, images, embeddings, or any binary payload too large for the KV store.

### `await mesh.workspace.put(key, data)`

Store a binary artifact.

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `str` | Artifact key (supports `/` for hierarchy, e.g. `docs/report.pdf`) |
| `data` | `bytes \| str` | Content to store. Strings are UTF-8 encoded. |

### `await mesh.workspace.get(key)`

Retrieve an artifact by key. Returns `bytes`.

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `str` | Artifact key |

**Returns:** `bytes`

### `await mesh.workspace.delete(key)`

Delete an artifact.

| Parameter | Type | Description |
|-----------|------|-------------|
| `key` | `str` | Artifact key |

```python
# Store and retrieve a binary artifact
await mesh.workspace.put("results/output.png", image_bytes)
data = await mesh.workspace.get("results/output.png")
await mesh.workspace.delete("results/output.png")
```

## Observability

Structured log events and runtime level control (ADR-0048). See
[Observability](../concepts/observability.md) for the model.

### `async for event in mesh.observe.logs(agent=None, *, level=None)`

Tail log events as typed `LogEvent` objects. Runs until the caller breaks
out of the loop.

| Parameter | Type | Description |
|-----------|------|-------------|
| `agent` | `str \| None` | Agent name; `None` tails the whole mesh (`mesh.logs.>`) |
| `level` | `str \| None` | Minimum level to yield (`debug`, `info`, `warn`, `error`) |

**Yields:** `LogEvent` — fields `timestamp`, `level`, `agent`, `event`,
`request_id`, `message`, `data`.

### `await mesh.observe.get(agent)`

Effective config for an agent. Returns `ObserveConfig` with `log_level` and
`source` (`"agent"`, `"global"`, or `"default"`).

### `await mesh.observe.set(agent, *, log_level)`

Set the per-agent log level (`debug`, `info`, `warn`, `error`, `off`).
Applies live via KV watch — no restart.

### `await mesh.observe.set_global(*, log_level)`

Set the mesh-wide default level. Per-agent overrides win.

```python
await mesh.observe.set("nlp.summarizer", log_level="debug")
async for event in mesh.observe.logs("nlp.summarizer"):
    print(event.event, event.data)
```

## Usage Attribution

Opt-in LLM usage reporting (ADR-0023). See
[Usage Attribution](../concepts/usage.md) for the model.

### `report_usage(usage)`

Module-level function (`from openagentmesh import report_usage`). Report LLM
usage from inside a handler while a `call()`/`stream()` request is in flight.
May be called multiple times per request: token and cost fields accumulate,
`model` keeps the last reported value. Raises `RuntimeError` outside a
request context.

The host stamps the merged result on the `X-Mesh-Usage` reply header (the
stream-end frame for streamers) and publishes a `usage_reported` observe
event at `info` level.

### `Usage`

Pydantic model carrying self-reported usage. All fields optional:
`input_tokens`, `output_tokens`, `total_tokens` (`int`), `model` (`str`),
`estimated_cost_usd` (`float`).

```python
from openagentmesh import Usage, report_usage

@mesh.agent
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    result = await call_llm(req.text)
    report_usage(Usage(
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        model="claude-sonnet-4-20250514",
    ))
    return SummarizeOutput(summary=result.text)
```
