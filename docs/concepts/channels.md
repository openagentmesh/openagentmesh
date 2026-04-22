# Channels

Channels are a naming convention, not an API field. An agent's `name` is a dotted identifier whose leading segments form its channel (ADR-0049).

## Usage

```python
spec = AgentSpec(
    name="finance.risk.scorer",
    description="Scores credit risk from a company profile.",
)

@mesh.agent(spec)
async def score(req: ScoreInput) -> ScoreOutput:
    ...
```

The agent's invocation subject is `mesh.agent.finance.risk.scorer`. The leading `finance.risk` is its channel; the trailing `scorer` is the leaf name. No second field on `AgentSpec` carries this information, the dotted name *is* the identifier.

## Discovery by Channel

```python
# All agents under finance.risk (exact tier and any sub-tier)
agents = await mesh.catalog(channel="finance.risk")

# All agents under finance (wider: includes finance.risk.* and finance.compliance.*)
agents = await mesh.catalog(channel="finance")
```

`mesh.catalog(channel=X)` is a prefix filter: an entry matches when its name equals `X` or starts with `X + "."`. Pass no `channel` argument to list everything.

## Invocation by Channel

`mesh.call`, `mesh.stream`, and `mesh.send` always take the full dotted name:

```python
await mesh.call("finance.risk.scorer", ScoreInput(profile="..."))
```

There is no separate `channel=` parameter. The name carries everything.

## Design Principles

- Channels represent **domains or teams**, not technical categories.
- They map directly to NATS subject hierarchy, enabling wildcard subscriptions.
- Channels are **optional**: agents without dots in their name register at the root.
- Keep hierarchies shallow (2 to 3 levels max).

## Examples

| Name | Channel | Purpose |
|------|---------|---------|
| `echo` | *(root)* | Simple utility |
| `nlp.summarizer` | `nlp` | Natural language processing |
| `finance.risk.scorer` | `finance.risk` | Financial risk assessment |
| `finance.compliance.checker` | `finance.compliance` | Compliance checking |
| `data.ingest.uploader` | `data.ingest` | Data ingestion pipeline |

## Wildcard Subscriptions

NATS subject wildcards apply to channel hierarchies:

- `mesh.agent.finance.*` matches agents one level deep under `finance` (e.g. `finance.a`, but not `finance.risk.scorer`).
- `mesh.agent.finance.>` matches all agents at any depth under `finance`.

The SDK exposes this as `subscribe(channel=X)`, which subscribes to `mesh.agent.{X}.>`:

```python
async for event in mesh.subscribe(channel="finance"):
    process(event)
```

`mesh.catalog(channel=X)` is a different operation. It filters the SDK-side catalog index by name prefix; it does not subscribe to NATS subjects.

## Root-Level Agents

Agents without a channel register at the root and are invoked by name alone:

```python
@mesh.agent(AgentSpec(name="echo", description="Echoes a message back."))
async def echo(req: EchoInput) -> EchoOutput:
    ...
```

Subject: `mesh.agent.echo` (no channel segment).

## Name Validation

A name is a non-empty sequence of dot-separated segments, each matching `[a-zA-Z0-9_-]+`. Leading dots, trailing dots, and consecutive dots are rejected at registration time.
