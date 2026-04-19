# Subject Naming

All NATS subjects follow a consistent hierarchy.

## Subject Map

| Subject | Purpose |
|---------|---------|
| `mesh.agent.{channel}.{name}` | Invocation (queue group subscription) |
| `mesh.agent.{name}` | Invocation for root-level agents (no channel) |
| `mesh.registry.{channel}.{name}` | KV registry key for full contract |
| `mesh.catalog` | KV key for lightweight catalog index |
| `mesh.health.{channel}.{name}` | Heartbeat subject |
| `mesh.agent.{channel}.{name}.events` | Pub/sub event emissions |
| `mesh.errors.{channel}.{name}` | Dead-letter subject |
| `mesh.results.{request_id}` | Async callback reply subject |

## Wildcards

NATS subject hierarchy enables wildcard subscriptions:

```
mesh.agent.finance.*      # All agents in the finance channel
mesh.agent.finance.>      # All agents in finance and sub-channels
mesh.health.>             # All health heartbeats
```

## Channel Mapping

Channels map directly to subject segments:

| Channel | Invocation Subject |
|---------|-------------------|
| (none) | `mesh.agent.echo` |
| `nlp` | `mesh.agent.nlp.summarizer` |
| `finance.risk` | `mesh.agent.finance.risk.scorer` |
