# ADR-0023: Single `@mesh.agent` decorator with type taxonomy

- **Type:** api-design
- **Date:** 2026-04-14
- **Status:** superseded by ADR-0031
- **Source:** conversation (design discussion on agent vs tool distinction and decorator naming)

## Context

As the SDK design matured, a question arose: should the library distinguish between LLM-powered autonomous agents and deterministic functions registered on the mesh? Libraries like FastMCP use `@mcp.tool()` as their registration primitive. Should OAM introduce `@mesh.tool`, `@mesh.skill`, or similar alternatives to `@mesh.agent`?

The discussion explored the full naming space — nouns (`tool`, `skill`, `service`, `endpoint`, `capability`, `node`, `action`, `unit`) and verbs (`expose`, `provide`, `offer`, `serve`, `wire`, `enable`, `use`) — against several evaluation axes: ecosystem familiarity, OAM differentiation, whether the noun works for all participant types (req/reply, streaming, pub/sub), and whether it gives a natural noun for the discovery surface.

The critical constraint that emerged: the API must read as coherent English across both the provider and consumer surfaces. The consumer surface uses `mesh.call()`, `mesh.stream()`, and `mesh.subscribe()`. Testing each noun candidate against these verbs revealed that only "agent" (and "service") pair naturally with all three: "call an agent," "stream from an agent," "subscribe to an agent." Nouns like "skill," "tool," and "capability" don't receive messages — you exercise, use, or invoke them, which creates linguistic tension with a message-passing API.

Additionally, the question of pub/sub participation: the spec already defines `type: "publisher"` and `type: "subscriber"` as future values for `x-agentmesh.type`. Introducing a separate `@mesh.tool` decorator alongside `@mesh.agent` would eventually require `@mesh.publisher`, `@mesh.subscriber`, and `@mesh.mcp_bridge` — a proliferating API surface. A single decorator with a `type` parameter scales cleanly to any number of participation profiles.

## Decision

`@mesh.agent` is the single registration decorator. No `@mesh.tool`, `@mesh.skill`, or other variants are introduced.

The decorator accepts a `type` parameter that describes the agent's behavior profile. The SDK sets different defaults based on type. The handler's shape can be used to infer `type` when not explicitly specified.

**Type taxonomy:**


| `type` value        | Behavior                          | Handler shape            | Default `capabilities.streaming` | Default SLA                  |
| ------------------- | --------------------------------- | ------------------------ | -------------------------------- | ---------------------------- |
| `"agent"` (default) | LLM-powered, autonomous reasoning | yields chunks            | `true`                           | `expected_latency_ms: 30000` |
| `"tool"`            | Deterministic or fast function    | returns value            | `false`                          | `expected_latency_ms: 1000`  |
| `"publisher"`       | Emits events, not invocable       | yields, no request param | n/a                              | n/a                          |
| `"subscriber"`      | Consumes events, not invocable    | future                   | n/a                              | n/a                          |


**Type inference from handler signature:**

The SDK infers `type` at registration time when not explicitly provided:

- Has a request parameter + returns value → inferred `"tool"`
- Has a request parameter + yields → inferred `"agent"` (streaming)
- No request parameter + yields → inferred `"publisher"`

Explicit `type` always overrides inference. Inference is a convenience, not a contract.

**Registration examples:**

```python
# Explicitly typed as tool — returns, fast, idempotent
@mesh.agent(name="extract-entities", channel="nlp", type="tool", description="...")
async def extract_entities(req: ExtractInput) -> ExtractOutput:
    return ExtractOutput(entities=run_ner(req.text))

# Default type — yields, streaming, LLM-powered
@mesh.agent(name="summarizer", channel="nlp", description="...")
async def summarize(req: SummarizeInput) -> SummarizeChunk:
    async for token in call_llm_stream(req.text):
        yield SummarizeChunk(delta=token)

# Publisher — yields events, no request parameter
@mesh.agent(name="price-feed", channel="finance", type="publisher", description="...")
async def monitor_prices() -> PriceEvent:
    while True:
        price = await fetch_price()
        yield PriceEvent(symbol="AAPL", price=price)
        await asyncio.sleep(1)
```

**The autonomy spectrum rationale:**

The `@mesh.agent` name is intentional. An "agent" on the mesh is any participant that registers a capability — regardless of the autonomy behind it. A deterministic NER function and a multi-step LLM reasoner are both agents: they both subscribe to a NATS subject, respond to requests, and publish contracts. The `type` field carries the behavioral signal for consumers who need it. The decorator name reflects the participation model, not the implementation complexity.

This is analogous to how HTTP services don't distinguish "dumb endpoints" from "smart services" at the protocol level — all are HTTP servers. The protocol is uniform; the intelligence is inside.

### `mesh.subscribe()` as the pub/sub consumer API

Add `mesh.subscribe()` to the consumer surface as the pair for publisher agents:

```python
# Subscribe to a named publisher
async for event in mesh.subscribe("price-feed"):
    print(event.data)

# Subscribe to all publishers in a channel
async for event in mesh.subscribe(channel="finance"):
    print(event.source, event.data)
```

Subscribes to `mesh.agent.{channel}.{name}.events` for named subscriptions, or `mesh.agent.{channel}.>` for channel-scoped subscriptions. Events are typed if the publisher declared an event model in its contract.

The full consumer surface is now:


| Method                                     | Pattern             | When to use                       |
| ------------------------------------------ | ------------------- | --------------------------------- |
| `mesh.call("name", payload)`               | Responder req/reply | Agent/tool has `streaming: false` |
| `mesh.stream("name", payload)`             | Streamer req/reply  | Agent has `streaming: true`       |
| `mesh.send("name", payload, reply_to=...)` | Async callback      | Fire-and-forget with async reply  |
| `mesh.subscribe("name")`                   | Pub/sub             | Publisher agent emitting events   |


### Publisher agents via `yield` with no request parameter

Publisher agents are registered with `@mesh.agent` and declared (or inferred) as `type="publisher"`. The handler is an async generator with no request parameter. Each `yield` publishes to the agent's `.events` subject.

The yield type is declared as the return annotation and validated at registration time. The contract stores the event schema for consumer introspection.

```python
@mesh.agent(name="price-feed", channel="finance", type="publisher", description="...")
async def monitor_prices() -> PriceEvent:
    while True:
        price = await fetch_price()
        yield PriceEvent(symbol="AAPL", price=price)
        await asyncio.sleep(1)
```

Publisher agents are not invocable — `mesh.call()` and `mesh.stream()` against a publisher return a `not_invocable` error. They are discoverable via `mesh.catalog()` and their type is visible in the catalog entry.

## Alternatives Considered

`**@mesh.tool` as a separate decorator.** Strong ecosystem precedent (MCP, OpenAI, Anthropic all call them "tools"). However: doesn't pair naturally with `mesh.call()` as English, breaks down for pub/sub types, would require additional decorators (`@mesh.publisher`, etc.) as the type taxonomy grows, and creates positioning overlap with MCP's "agent-to-tool" model — which is explicitly the adjacent protocol, not OAM's territory.

`**@mesh.skill`.** Good A2A alignment (the contract schema uses `skills[]`). Works as a discovery noun ("browse skills"). But "call a skill" and "stream from a skill" don't read naturally, and "skill" implies capability rather than participant identity.

`**@mesh.tool` + `@mesh.agent` as two parallel decorators.** Would align with the ecosystem's tool/agent distinction, but the boundary is fuzzy in practice (a cached LLM function is both), forces provider self-classification into a binary, and requires the consumer to know which decorator was used to choose the right `mesh.call()` vs `mesh.invoke()` method.

**Class-based registration.** A class with `call()` and `stream()` methods would provide the cleanest dual-mode story and mechanical SDK enforcement. Rejected for v1 because it breaks the function-first DX that is central to OAM's FastAPI-inspired design philosophy.

## Risks and Implications

- The `type` inference from handler signature is a convenience that could surprise developers who write a returning handler and expect `type="agent"` defaults. Documentation must make the inference rules explicit.
- Publisher agents' lifecycle management (when to stop yielding, how to handle backpressure) is not addressed in this ADR. This is a Phase 2 concern.
- `mesh.subscribe()` channel-scoped subscriptions (`mesh.agent.{channel}.>`) need careful documentation — they subscribe to ALL event subjects under that channel, including non-publisher subjects that might exist.
- The `"subscriber"` type value is reserved in the taxonomy but not designed. It is mentioned here to close the namespace and avoid future naming conflicts.

