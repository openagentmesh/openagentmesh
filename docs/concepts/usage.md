# Usage Attribution

AgentMesh is transport; it routes messages between agents but does not call LLMs, manage API keys, or bill for inference. Each agent provider owns the cost of their handler's execution, just as each microservice owner pays for their own compute.

The mesh provides **usage attribution primitives** so teams can track where tokens are consumed and allocate costs to the agents and workflows that generated them.

## Who Pays for What

In a mesh interaction, LLM tokens are consumed at up to two sites:

| Site | Who pays | Example |
|------|----------|---------|
| **Orchestrating LLM** | Consumer | Consumer discovers agents, feeds them to their LLM as tools, LLM decides which to call |
| **Agent's internal LLM** | Provider | The handler calls Claude, GPT, or another model to do its work |

For the primary OAM use case (within-company orchestration) both roles map to the same organization. The value of usage attribution is not billing, but **visibility**: understanding which agents and workflows drive cost.

## Reporting Usage

Handlers opt in by calling `report_usage()` while handling a request:

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

`Usage` fields — all optional:

| Field                | Type     | Description                             |
| -------------------- | -------- | --------------------------------------- |
| `input_tokens`       | `int`    | Tokens consumed in the LLM input/prompt |
| `output_tokens`      | `int`    | Tokens generated in the LLM output      |
| `total_tokens`       | `int`    | Sum, if the provider reports it separately |
| `model`              | `string` | Model identifier used for this call     |
| `estimated_cost_usd` | `float`  | Agent-computed cost estimate (advisory) |

A handler may call `report_usage()` multiple times per request — a pipeline making three LLM calls reports each one as it happens. Reports **accumulate**: token and cost fields sum, and `model` keeps the last reported value. Calling `report_usage()` outside a request context raises `RuntimeError`; usage reporting applies to the invocable shapes (Responder and Streamer — Publisher and Source handlers have no request to attribute usage to).

## Where the Data Goes

The host propagates each request's merged usage to two places:

**The `X-Mesh-Usage` reply header.** The reply message (for `call()`) or the stream-end frame (for `stream()` — usage is only known once the generator finishes) carries the usage as JSON:

```
X-Mesh-Usage: {"input_tokens": 1500, "output_tokens": 300, "model": "claude-sonnet-4-20250514"}
```

Any client, in any language, can read it off the wire without SDK support.

**A `usage_reported` [observe event](observability.md).** Published on `mesh.logs.{name}` at `info` level with the usage fields in `data` and the `request_id` for correlation. This is the aggregation path:

```python
async for event in mesh.observe.logs():
    if event.event == "usage_reported":
        tokens = event.data.get("input_tokens", 0) + event.data.get("output_tokens", 0)
        print(f"{event.agent}: {tokens} tokens ({event.data.get('model', '?')})")
```

Or from the terminal: `oam observe logs` shows the events as they flow.

## Design Principles

- **Opt-in.** Usage reporting is not mandatory. Deterministic agents with no LLM cost skip it — and emit nothing, so the [zero-publishes-at-default-level](observability.md) property holds for them.
- **Agent-reported.** The mesh propagates usage data but does not generate or validate it.
- **No built-in metering.** The mesh does not maintain running totals or budgets. External monitoring tools aggregate from the observe events and headers.
