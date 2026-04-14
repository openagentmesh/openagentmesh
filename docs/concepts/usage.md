# Usage Attribution

AgentMesh is transport — it routes messages between agents but does not call LLMs, manage API keys, or bill for inference. Each agent provider owns the cost of their handler's execution, just as each microservice owner pays for their own compute.

The mesh provides **usage attribution primitives** so teams can track where tokens are consumed and allocate costs to the agents and workflows that generated them.

## Who Pays for What

In a mesh interaction, LLM tokens are consumed at up to three sites:

| Site | Who pays | Example |
|------|----------|---------|
| **Orchestrating LLM** | Consumer | Consumer discovers agents, feeds them to their LLM as tools, LLM decides which to call |
| **Agent's internal LLM** | Provider | The handler calls Claude, GPT, or another model to do its work |
| **Mesh-spawned agents** | Operator | The spawner control plane holds API keys for `type: llm` agents |

For the primary OAM use case — within-company orchestration — all three roles map to the same organization. The value of usage attribution is not billing, but **visibility**: understanding which agents and workflows drive cost.

## Reporting Usage

Agents optionally self-report token usage via the `X-Mesh-Usage` response header:

```
X-Mesh-Usage: {"input_tokens": 1500, "output_tokens": 300, "model": "claude-sonnet-4-20250514"}
```

Available fields (all optional):

| Field | Type | Description |
|-------|------|-------------|
| `input_tokens` | `int` | Tokens in the LLM prompt |
| `output_tokens` | `int` | Tokens in the LLM response |
| `total_tokens` | `int` | Combined total |
| `model` | `string` | Model identifier |
| `estimated_cost_usd` | `float` | Cost estimate (advisory) |

Non-LLM agents omit the header entirely.

### SDK Helper

The SDK provides a `Usage` object so you don't construct the header manually:

```python
from openagentmesh import AgentMesh, Usage
from pydantic import BaseModel

mesh = AgentMesh()

class SummarizeInput(BaseModel):
    text: str

class SummarizeOutput(BaseModel):
    summary: str

@mesh.agent(name="summarizer", channel="nlp", description="Summarizes text.")
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

The `Usage` object is intercepted by the SDK and moved to the `X-Mesh-Usage` response header. It never appears in the JSON body — callers see only the `SummarizeOutput` schema.

## Tracing Cost Across Workflows

When combined with distributed tracing (Phase 2), usage data becomes span attributes:

- `mesh.usage.input_tokens`
- `mesh.usage.output_tokens`
- `mesh.usage.model`
- `mesh.usage.estimated_cost_usd`

A multi-agent workflow that chains three agents produces a trace where each span carries its own usage, giving full cost visibility across the entire request path.

## Design Principles

- **Opt-in.** Usage reporting is not mandatory. Deterministic agents with no LLM cost skip it.
- **Agent-reported.** The mesh propagates usage data but does not generate or validate it.
- **No built-in metering.** The mesh does not maintain running totals or budgets. External monitoring tools (Datadog, Grafana, custom dashboards) aggregate from traces and headers.
