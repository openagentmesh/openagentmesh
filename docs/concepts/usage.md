# Usage Attribution

!!! warning "Not yet implemented"
    Usage attribution is designed but not yet implemented in the SDK. This page describes the planned feature.

AgentMesh is transport; it routes messages between agents but does not call LLMs, manage API keys, or bill for inference. Each agent provider owns the cost of their handler's execution, just as each microservice owner pays for their own compute.

The mesh will provide **usage attribution primitives** so teams can track where tokens are consumed and allocate costs to the agents and workflows that generated them.

## Who Pays for What

In a mesh interaction, LLM tokens are consumed at up to two sites:

| Site | Who pays | Example |
|------|----------|---------|
| **Orchestrating LLM** | Consumer | Consumer discovers agents, feeds them to their LLM as tools, LLM decides which to call |
| **Agent's internal LLM** | Provider | The handler calls Claude, GPT, or another model to do its work |

For the primary OAM use case (within-company orchestration) both roles map to the same organization. The value of usage attribution is not billing, but **visibility**: understanding which agents and workflows drive cost.

## Planned: Reporting Usage

Agents will optionally self-report token usage via the `X-Mesh-Usage` response header:

```
X-Mesh-Usage: {"input_tokens": 1500, "output_tokens": 300, "model": "claude-sonnet-4-20250514"}
```

## Design Principles

- **Opt-in.** Usage reporting is not mandatory. Deterministic agents with no LLM cost skip it.
- **Agent-reported.** The mesh propagates usage data but does not generate or validate it.
- **No built-in metering.** The mesh does not maintain running totals or budgets. External monitoring tools aggregate from traces and headers.
