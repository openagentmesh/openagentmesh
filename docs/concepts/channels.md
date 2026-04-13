# Channels

Channels are hierarchical namespace prefixes that group agents by domain or team.

## Usage

```python
@mesh.agent(
    name="scorer",
    channel="finance.risk",
    description="Scores credit risk from a company profile.",
)
async def score(req: ScoreInput) -> ScoreOutput:
    ...
```

This agent's invocation subject becomes `mesh.agent.finance.risk.scorer`.

## Discovery by Channel

```python
# All agents in the finance.risk channel
agents = await mesh.catalog(channel="finance.risk")

# All agents under finance (including finance.risk, finance.compliance, etc.)
agents = await mesh.catalog(channel="finance")
```

## Design Principles

- Channels represent **domains or teams**, not technical categories
- They map directly to NATS subject hierarchy, enabling wildcard subscriptions
- Channels are **optional** — agents without a channel register at the root level
- Keep hierarchies shallow (2-3 levels max)

## Examples

| Channel | Purpose |
|---------|---------|
| `nlp` | Natural language processing agents |
| `finance.risk` | Financial risk assessment |
| `finance.compliance` | Compliance checking |
| `data.ingest` | Data ingestion pipeline |

## Root-Level Agents

Agents without a channel register at the root and are invoked by name alone:

```python
@mesh.agent(name="echo", description="Echoes a message back.")
async def echo(req: EchoInput) -> EchoOutput:
    ...
```

Subject: `mesh.agent.echo` (no channel segment).
