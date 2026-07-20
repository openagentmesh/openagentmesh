# ADR-0023: LLM cost model and usage attribution

- **Type:** architecture
- **Date:** 2026-04-14
- **Status:** spec
- **Source:** conversation (discussion on who pays for LLM tokens in the mesh)

## Context

The spec defines how agents register, discover, and invoke each other, but is silent on a fundamental question: who calls the LLM, and who pays for the tokens?

In a mesh interaction, LLM tokens are consumed at up to three sites:

1. **The orchestrating LLM (consumer side).** A consumer discovers agents via `mesh.discover()`, converts them to tool definitions (`.to_anthropic_tool()`), and feeds them to their own LLM. That LLM decides which agent to invoke. The consumer pays for the decision-making tokens.
2. **The agent's internal LLM (provider side).** When `mesh.call("summarizer", payload)` reaches the handler, that handler might call Claude, GPT, or any model internally. The provider deployed the agent, the provider's API key is in the handler, the provider pays.
3. **Mesh-spawned agents (operator side, Tier 3+).** For `type: llm` agents, the spawner control plane holds the API keys and creates agent processes. The mesh operator pays.

The primary use case for OAM is **within-company orchestration** — agents built and operated by teams inside the same organization. In this context, inter-party billing and chargeback are not concerns. All costs flow to the same organization.

What *is* needed: visibility into where tokens are being consumed, so teams can attribute costs to specific agents and workflows.

## Decision

**AgentMesh is transport. It does not call LLMs, manage API keys, or bill for inference.** Each agent provider owns the cost of their handler's execution, just as each microservice owner is responsible for their compute bill. The mesh provides **usage attribution primitives** — not billing.

### Convention 1: `X-Mesh-Usage` response header

Agents optionally self-report token usage in the response header. The mesh propagates the header; it does not generate or validate it. The header value is a JSON object:

```
X-Mesh-Usage: {"input_tokens": 1500, "output_tokens": 300, "model": "claude-sonnet-4-20250514"}
```

Fields (all optional):


| Field                | Type     | Description                             |
| -------------------- | -------- | --------------------------------------- |
| `input_tokens`       | `int`    | Tokens consumed in the LLM input/prompt |
| `output_tokens`      | `int`    | Tokens generated in the LLM output      |
| `total_tokens`       | `int`    | Sum, if provider reports it separately  |
| `model`              | `string` | Model identifier used for this call     |
| `estimated_cost_usd` | `float`  | Agent-computed cost estimate (advisory) |


Non-LLM agents (deterministic functions, database lookups) omit the header entirely.

### Convention 2: Usage as OTel span attributes (Phase 2)

When the OTel middleware is active, usage data from `X-Mesh-Usage` is recorded as span attributes on the agent's invocation span:

- `mesh.usage.input_tokens`
- `mesh.usage.output_tokens`
- `mesh.usage.model`
- `mesh.usage.estimated_cost_usd`

This connects per-call usage to the distributed trace. A multi-agent workflow produces a trace where each span carries its own cost, enabling full cost attribution for any request path.

### Convention 3: SDK helper for usage reporting

The SDK provides a lightweight helper so agent authors don't construct the header manually:

```python
from openagentmesh import AgentMesh, Usage

@mesh.agent(name="summarizer", channel="nlp")
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    result = await call_llm(req.text)
    return SummarizeOutput(
        summary=result.text,
        usage=Usage(
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model="claude-sonnet-4-20250514",
        ),
    )
```

The `Usage` object is not part of the output schema — the SDK intercepts it and moves it to the `X-Mesh-Usage` header before serializing the response. The caller never sees it in the JSON body.

### What we explicitly do NOT build

- **Metering/billing service.** No running totals, no budgets, no invoicing. External monitoring tools (Datadog, Grafana, custom dashboards) aggregate usage from traces and headers.
- **Credential passthrough (BYOK).** No `X-Mesh-Credentials` header for consumers to send their own API keys. This is a security and trust model concern that belongs to specific agent implementations, not the protocol.
- **Mandatory cost reporting.** Usage reporting is opt-in. Agents that don't report usage are not second-class citizens.

## Alternatives Considered

- **Built-in metering in KV.** Maintaining per-agent usage counters in NATS KV. Rejected: this duplicates what OTel and monitoring systems already do, adds write load to KV on every call, and creates a maintenance surface inside the mesh that doesn't belong there.
- **Cost field in the contract.** An `estimated_cost_per_call` in `x-agentmesh.sla`. Considered and deferred: per-call cost depends on input size, model, and pricing changes. A static field would be misleading. The per-response `X-Mesh-Usage` header reports actual usage, which is more useful.
- **Mandatory usage reporting.** Requiring all agents to report usage. Rejected: many agents are deterministic functions with zero LLM cost. Mandating the header adds friction for no value.

## Risks and Implications

- Usage data is agent-reported and unverified. A malicious or buggy agent could report incorrect values. This is acceptable for the within-company use case. Cross-org cost attribution (if ever needed) would require a trusted metering layer, which is out of scope.
- The `Usage` return-value convention requires SDK support for intercepting the object before serialization. This is a small addition to the decorator machinery.
- External monitoring integration (OTel → dashboards) is the user's responsibility. The mesh provides the data; visualization is out of scope.

## Amendment (2026-07-20, implementation)

Shaped against the shipped repo before implementation. Four corrections:

1. **The return-value convention (Convention 3 as originally written) cannot work
   under Pydantic v2.** `SummarizeOutput(summary=..., usage=Usage(...))` requires the
   output model to *declare* a `usage` field — which then appears in the contract's
   output schema, contradicting "the `Usage` object is not part of the output schema"
   (and an undeclared field is a `ValidationError` at construction). Replaced with a
   context-local reporting call, usable from any point inside the handler and
   requiring no output-model changes:

   ```python
   from openagentmesh import AgentMesh, Usage, report_usage

   mesh = AgentMesh()

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

   `report_usage()` outside a request context raises `RuntimeError` (silent data
   loss would be worse). Multiple calls within one request **accumulate**: token
   and cost fields sum, `model` keeps the last reported value — a handler making
   three LLM calls reports each one as it happens. Usage capture applies to the
   invocable shapes (Responder, Streamer); Publisher/Source handlers have no
   request to attribute usage to.

2. **Attribution rides ADR-0048 observability, which did not exist when this ADR
   was written.** Alongside the `X-Mesh-Usage` reply header, the host publishes a
   `usage_reported` log event on `mesh.logs.{name}` at `info` level carrying the
   usage payload (plus `request_id`). This is the aggregation path — tail
   `mesh.observe.logs()` (or `oam observe logs`) and sum. The zero-publishes-at-
   default-level property of ADR-0048 is preserved in spirit: only agents whose
   handlers actually call `report_usage()` emit the event, and reporting is the
   agent author's explicit opt-in. No new subjects or role-template changes:
   usage rides reply headers and the existing `mesh.logs.>` grants.

3. **Streaming agents stamp usage on the stream-end frame** — usage is only known
   once the generator finishes, and the end frame is the one message every
   consumer reads to completion.

4. **Deferred, recorded here so the docs don't promise them:** a caller-side
   accessor (e.g. `call()` returning usage alongside the payload — aggregate via
   the observe event or read the raw header until a real need appears); OTel span
   attributes (Convention 2, still Phase 2 — no OTel middleware exists);
   sdk-ts write-side parity (TS agents are read-mostly today; the header format
   is language-neutral JSON either way).

