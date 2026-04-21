# Channels

Channels are hierarchical namespace prefixes that group agents by domain or team.

## Usage

```python
spec = AgentSpec(
    name="scorer",
    channel="finance.risk",
    description="Scores credit risk from a company profile.",
)

@mesh.agent(spec)
async def score(req: ScoreInput) -> ScoreOutput:
    ...
```

This agent's invocation subject becomes `mesh.agent.finance.risk.scorer`.

## Discovery by Channel

```python
# All agents in the finance.risk channel (exact match)
agents = await mesh.catalog(channel="finance.risk")
```

`mesh.catalog()` filters by exact channel match. To discover agents across sub-channels (e.g. all of `finance.*`), use NATS wildcard subscriptions directly or query multiple channels.

## Design Principles

- Channels represent **domains or teams**, not technical categories
- They map directly to NATS subject hierarchy, enabling wildcard subscriptions
- Channels are **optional**; agents without a channel register at the root level
- Keep hierarchies shallow (2-3 levels max)

## Examples

| Channel | Purpose |
|---------|---------|
| `nlp` | Natural language processing agents |
| `finance.risk` | Financial risk assessment |
| `finance.compliance` | Compliance checking |
| `data.ingest` | Data ingestion pipeline |

## Wildcard Subscriptions

NATS subject wildcards apply to channel hierarchies:

- `mesh.agent.finance.*` matches all agents one level deep (`finance.risk.scorer`, `finance.compliance.checker`)
- `mesh.agent.finance.>` matches all agents at any depth under `finance`

These are NATS-native wildcards, not SDK features. The SDK's `mesh.catalog(channel="finance")` filters the catalog index; NATS wildcards apply to direct subject subscriptions.

## Root-Level Agents

Agents without a channel register at the root and are invoked by name alone:

```python
@mesh.agent(AgentSpec(name="echo", description="Echoes a message back."))
async def echo(req: EchoInput) -> EchoOutput:
    ...
```

Subject: `mesh.agent.echo` (no channel segment).
