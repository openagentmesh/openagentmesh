# Subject Naming

All message subjects follow a consistent hierarchy. The subject scheme is transport-agnostic; any system that supports hierarchical topic naming and wildcard subscriptions can implement it.

## Subject Map

### NATS Subjects

| Subject | Purpose |
|---------|---------|
| `mesh.agent.{channel}.{name}` | Invocation (queue group subscription) |
| `mesh.agent.{name}` | Invocation for root-level agents (no channel) |
| `mesh.agent.{channel}.{name}.events` | Pub/sub event emissions from publisher agents |
| `mesh.stream.{request_id}` | Streaming response chunks |
| `mesh.errors.{channel}.{name}` | Dead-letter subject for handler errors |
| `mesh.results.{request_id}` | Async callback reply subject |

### KV Keys (not NATS subjects)

| Bucket | Key | Purpose |
|--------|-----|---------|
| `mesh-catalog` | `catalog` | Lightweight catalog index (JSON array) |
| `mesh-registry` | `{channel}.{name}` or `{name}` | Full agent contract |
| `mesh-context` | Agent-defined | Shared state between agents |

## Wildcards

The subject hierarchy enables wildcard subscriptions:

```
mesh.agent.finance.*      # All agents in the finance channel
mesh.agent.finance.>      # All agents in finance and sub-channels
mesh.errors.>             # All dead-letter errors
```

## Channel Mapping

Channels map directly to subject segments:

| Channel | Invocation Subject |
|---------|-------------------|
| (none) | `mesh.agent.echo` |
| `nlp` | `mesh.agent.nlp.summarizer` |
| `finance.risk` | `mesh.agent.finance.risk.scorer` |
