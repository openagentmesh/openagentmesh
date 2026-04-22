# Subject Naming

All message subjects follow a consistent hierarchy. The subject scheme is transport-agnostic; any system that supports hierarchical topic naming and wildcard subscriptions can implement it.

## Subject Map

### NATS Subjects

| Subject | Purpose |
|---------|---------|
| `mesh.agent.{name}` | Invocation (queue group subscription) |
| `mesh.agent.{name}.events` | Pub/sub event emissions from publisher agents |
| `mesh.stream.{request_id}` | Streaming response chunks |
| `mesh.errors.{name}` | Dead-letter subject for handler errors |
| `mesh.results.{request_id}` | Async callback reply subject |

`{name}` is the agent's dotted identifier (ADR-0049). Names with dots embed the channel hierarchy directly (`nlp.summarizer`, `finance.risk.scorer`); root-level agents have no dots (`echo`).

### KV Keys (not NATS subjects)

| Bucket | Key | Purpose |
|--------|-----|---------|
| `mesh-catalog` | `catalog` | Lightweight catalog index (JSON array) |
| `mesh-registry` | `{name}` | Full agent contract |
| `mesh-context` | Agent-defined | Shared state between agents |

## Wildcards

The subject hierarchy enables wildcard subscriptions:

```
mesh.agent.finance.*      # All agents one level deep under finance
mesh.agent.finance.>      # All agents in finance and sub-channels
mesh.errors.>             # All dead-letter errors
```

## Channel Mapping

Channels are the leading dot-segments of a name. They map directly to subject segments:

| Name | Channel | Invocation Subject |
|------|---------|-------------------|
| `echo` | *(root)* | `mesh.agent.echo` |
| `nlp.summarizer` | `nlp` | `mesh.agent.nlp.summarizer` |
| `finance.risk.scorer` | `finance.risk` | `mesh.agent.finance.risk.scorer` |
