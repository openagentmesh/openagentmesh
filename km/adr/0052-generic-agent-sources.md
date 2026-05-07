# ADR-0052: Generic agent sources (decorator extension)

- **Type:** api-design
- **Date:** 2026-04-27
- **Status:** spec
- **Amends:** ADR-0030 (relaxes single-argument decorator), ADR-0042 (subsumes watcher pattern as a special case)
- **Source:** conversation (Discord bridge design surfaced the need for a generic trigger surface)

## Context

The `@mesh.agent` decorator (ADR-0030) currently registers an agent that is invoked via `mesh.call()`. Watcher agents (ADR-0042) are a special handler shape that subscribes to KV changes inside the handler body. Both treat "what triggers this agent" as either implicit (RPC arrival) or hand-rolled inside the function (KV watch loops).

When integrating external systems (chat bridges, webhooks, cron, file watchers, queue consumers), every integration today must either:

1. Run a separate listen loop outside any agent definition and call `mesh.call()` from inside it, or
2. Hide the trigger inside the watcher's handler body, with no declarative description of what fires the agent.

Both paths scatter trigger logic across user code. The mesh has no first-class concept of "this agent is also fired by X." The catalog cannot describe trigger surfaces. Multi-platform agents (same persona on Discord and Slack) require duplicate plumbing.

The Discord bridge design (ADR-0053) crystallised the gap. The cleanest API for a Discord-driven persona is:

```python
@mesh.agent(
    AgentSpec(name="sales-coach", description="..."),
    sources=[discord.channel(SALES, filter=startswith("/coach "))],
)
async def coach(text: str) -> str:
    return await llm(text)
```

The agent's contract stays domain-shaped (`text -> str`), reusable from `mesh.call()` anywhere. The Discord coupling lives on the decorator as a trigger source, not in the agent body. Adding Slack later is one more entry in the `sources` list.

This shape generalises beyond chat. Any subject-driven trigger fits the same Protocol: cron emitters, webhook receivers, KV change watchers, queue consumers.

## Decision

Add `sources` as a second keyword argument on the `@mesh.agent` decorator. Sources are runtime trigger bindings, distinct from the agent's contract.

```python
@mesh.agent(spec: AgentSpec, *, sources: list[Source] = []) -> Callable
```

`AgentSpec` remains the contract. `sources` is local wiring and is NOT part of `AgentSpec` or the catalog projection. Other mesh participants do not see an agent's sources; they only see what `AgentSpec` exposes (name, description, schemas, capabilities).

### `Source` Protocol

A source is a pure data object describing a subject subscription plus optional transforms.

```python
from typing import Protocol, Callable, Any
from openagentmesh import AgentMesh

class Source(Protocol):
    """A trigger surface for an agent.

    A source binds an agent to a NATS subject. When a message arrives on the
    inbound subject, the source's input_transform produces the agent's input.
    The agent runs. If output_transform is set and the agent returned a value,
    the result is published to the outbound subject.
    """
    inbound_subject: str
    outbound_subject: str | None
    input_transform: Callable[[Any], Any] | None
    output_transform: Callable[[Any, Any], Any] | None  # (return_value, inbound_msg) -> outbound_msg
    filter: Callable[[Any], bool] | None
    queue_group: str | None
```

A source need not implement all fields. Concrete cases:

- **Trigger-only source** (cron, file watcher): `outbound_subject=None`, return value ignored.
- **Request/reply source** (chat bridge): both subjects set, transforms convert between wire format and domain format.
- **Pure subscription** (ADR-0042 watcher): inbound_subject only, no transforms, void return.

### Code sample (the DX contract)

```python
from openagentmesh import AgentMesh, AgentSpec
from openagentmesh.integrations.chat.discord import DiscordBridge

mesh = AgentMesh()
discord = DiscordBridge(mesh, channels=[SALES_CHANNEL_ID, PM_CHANNEL_ID])

# Domain-shaped agent, reusable from mesh.call() anywhere.
@mesh.agent(
    AgentSpec(name="sales-coach", description="Sales coaching assistant"),
    sources=[discord.channel(SALES_CHANNEL_ID, filter=lambda m: m.text.startswith("/coach "))],
)
async def coach(text: str) -> str:
    return await llm.complete(f"Sales coach answering: {text}")

# Watcher pattern (ADR-0042) re-expressed as a source:
@mesh.agent(
    AgentSpec(name="extract", description="Extracts entities from raw documents"),
    sources=[mesh.kv_source("pipeline.*.raw")],
)
async def extract(value: bytes) -> None:
    doc = Document.model_validate_json(value)
    extracted = do_extraction(doc)
    await mesh.kv.put(f"pipeline.{doc.id}.extracted", extracted.model_dump_json())

async with mesh, discord:
    await asyncio.Future()  # run forever
```

### Lifecycle

- At decorator time, sources are stored on the registered agent's runtime metadata (NOT in `AgentSpec`).
- On `mesh.__aenter__`, after the agent's primary subscription (the `mesh.call()` subject) is established, the SDK iterates through each source and creates an additional subscription on the source's `inbound_subject`.
- Each source subscription uses the source's `queue_group` if set, else falls back to a default per source.
- On message receipt: source `filter` runs first (drop if False), then `input_transform` runs to produce the agent's input, then the agent handler runs. If the handler returned a non-None value and `output_transform` is set, the transformed result is published to `outbound_subject`.
- On `mesh.__aexit__`, source subscriptions are torn down before the primary subscription.

### Composition with capabilities

Sources do NOT change capability inference (ADR-0031). Capabilities are still derived from handler shape. An agent with sources is still invocable if its handler has the Responder shape; still streaming if Streamer; etc.

### Catalog visibility

Sources are NOT part of the catalog projection. The catalog describes what an agent does (contract); sources describe how a particular instance is triggered (wiring). Different deployments of the same agent may have different sources. The catalog must remain stable across deployments.

A future ADR may add a separate observability surface that lists trigger sources per running instance, but it would be deployment-state, not contract.

### Subsumption of ADR-0042

The Watcher pattern (`async def f() -> None: ...` with KV watching inside the body) is now expressible as an agent with one source:

```python
# Before (ADR-0042):
@mesh.agent(spec)
async def extract():
    async for value in mesh.kv.watch("pipeline.*.raw"):
        ...

# After (ADR-0052):
@mesh.agent(spec, sources=[mesh.kv_source("pipeline.*.raw")])
async def extract(value: bytes) -> None:
    ...
```

ADR-0042 is amended, not deleted. The Watcher capability combination (`invocable=False, streaming=False`) remains valid; it now corresponds to "an agent registered exclusively via sources, with no `mesh.call()` invocation surface." The handler-body KV watch loop remains supported as a legacy form.

### Relationship to ADR-0030

ADR-0030 established `AgentSpec` as the single decorator argument. This ADR relaxes the principle: `AgentSpec` is the single CONTRACT argument; non-contract WIRING (like sources) may be passed as additional keyword arguments.

Rationale: AgentSpec carries data that flows into the catalog and is visible across the mesh. Sources carry runtime wiring that only matters locally. They have different lifecycles, different audiences, and different serialization concerns (sources contain callables; AgentSpec is pure data). Forcing both into one model creates worse problems than relaxing the single-argument rule.

### Loop prevention

Sources MUST be idempotent under repeated triggering. If an agent's output is published to a subject that loops back into the same source's inbound, the bridge or source implementation is responsible for breaking the cycle (see ADR-0053 for the Discord-specific case).

The SDK does not enforce loop detection at the source layer; this is delegated to the source implementation, which knows the semantics of its trigger surface.

## Consequences

- `@mesh.agent` decorator gains a `sources: list[Source] = []` keyword argument.
- A `Source` Protocol is added to the public API in `openagentmesh.sources`.
- The mesh runtime creates additional subject subscriptions per source on agent registration.
- ADR-0030 is amended: single-argument rule applies to the contract argument only.
- ADR-0042 is amended: watcher pattern is re-expressible via sources, original handler-body form remains supported.
- Documentation: new `docs/concepts/sources.md` page. Cookbook recipe demonstrating sources (likely the Discord bridge, ADR-0053). API reference updated.
- The capability inference rules (ADR-0031) are unchanged. Agents may have sources regardless of capabilities; the source's transforms bridge the wire format to whatever the handler shape requires.
- No catalog schema changes. Sources are runtime metadata, not contract.

## Alternatives Considered

**Add `sources` as a field on `AgentSpec`.** Rejected. AgentSpec is the catalog-published contract; sources are local wiring with callables that cannot be serialized cleanly. Polluting the contract with deployment-specific config breaks the catalog's role as a stable cross-mesh description.

**Stacked decorators (`@discord.channel(SALES)` + `@mesh.agent(spec)`).** Pure sugar, no core changes. Rejected as the primary path because:

- It scales poorly to multiple sources per agent (decorator stacking gets ugly).
- Each integration must invent its own decorator API; no unified Source Protocol.
- The ordering of decorators matters and is non-obvious (which one wraps the other? when does subscription happen?).
- It gives the mesh no first-class view of trigger surfaces.

The stacked-decorator form may still exist as syntactic sugar for single-source cases, but the canonical API is `sources=[...]`.

**FastAPI-style `Depends()` for triggers.** Rejected. FastAPI `Depends()` is request-time dependency INJECTION — it provides values to the handler, it does not trigger the handler. HTTP arrival is the trigger; `Depends()` runs after. Mapping `Depends()` to OAM triggers conflates two orthogonal concerns: when does the handler fire (sources) vs. what does the handler receive (DI). A separate future ADR may introduce FastAPI-style `Depends()` for injecting mesh services (`AgentMesh`, KV buckets, object stores) into the handler body. That is genuinely useful and orthogonal to sources.

**Keep watcher (ADR-0042) as the only subscription primitive.** Rejected. Watcher is hardcoded to KV watching and runs the loop inside the handler body. It does not generalise to chat, webhooks, cron, or any other trigger. Sources externalise the trigger as a declarative object.

**Build the Discord bridge with a `@discord.handler` decorator and skip sources entirely.** Rejected. Solves the immediate Discord need but reintroduces the same gap for the next integration (Slack, Teams, webhooks). Sources are the durable abstraction; per-integration glue decorators are the throwaway.
