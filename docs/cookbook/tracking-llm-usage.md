# Tracking LLM Usage

Your mesh runs a dozen LLM-backed agents and the monthly bill doubled — which
agent did it? This recipe wires per-request usage reporting into a handler and
builds a small cost monitor that attributes tokens to agents as requests flow.
The machinery is explained in [Usage Attribution](../concepts/usage.md).

## Report usage from the handler

Wherever the handler calls an LLM, report what the provider charged for.
`report_usage()` works from any point inside the handler; the mesh does the
rest:

```python
from pydantic import BaseModel

from openagentmesh import AgentMesh, AgentSpec, Usage, report_usage


class Question(BaseModel):
    text: str


class Answer(BaseModel):
    text: str


mesh = AgentMesh()


@mesh.agent(AgentSpec(
    name="support.answerer",
    description="Answers support questions with an LLM. "
                "Input: question text. Not for order lookups.",
))
async def answerer(req: Question) -> Answer:
    completion = await llm_complete(req.text)  # your LLM client here
    report_usage(Usage(
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
        model=completion.model,
    ))
    return Answer(text=completion.text)
```

A handler that makes several LLM calls just reports each one as it happens —
the mesh sums token and cost fields into one record per request.

## Aggregate cost per agent

Every reporting request emits a `usage_reported`
[observe event](../concepts/observability.md) on `mesh.logs.{name}`. A cost
monitor is a subscriber that keeps totals:

```python
from collections import Counter

from openagentmesh import AgentMesh


async def cost_monitor(mesh: AgentMesh):
    """Attribute tokens to agents as requests flow."""
    totals: Counter[str] = Counter()
    async for event in mesh.observe.logs():
        if event.event != "usage_reported":
            continue
        tokens = event.data.get("input_tokens", 0) + event.data.get("output_tokens", 0)
        totals[event.agent] += tokens
        print(f"{event.agent}: +{tokens} tokens "
              f"({event.data.get('model', '?')}), {totals[event.agent]} total")
```

The same stream from a terminal:

```bash
oam observe logs
```

## Read usage off the wire

Clients in any language can skip the SDK entirely: the reply message carries
the merged usage in the `X-Mesh-Usage` header (for streams, it rides the
stream-end frame):

```
X-Mesh-Usage: {"input_tokens": 1500, "output_tokens": 300, "model": "claude-sonnet-4-20250514"}
```

## Notes

- Reporting is opt-in. Deterministic agents skip it and emit nothing.
- The mesh propagates what agents report; it does not validate the numbers or
  keep running totals — aggregation belongs to your monitor.
- `estimated_cost_usd` is available for agents that price their own calls;
  like every `Usage` field, it accumulates across reports within a request.
