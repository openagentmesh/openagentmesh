# Observability

The mesh observes itself. Every agent host publishes structured log events
to plain NATS subjects that any subscriber can tail — a CLI, a monitoring
agent, a dashboard — with zero external infrastructure. What gets published
is controlled at runtime through a KV bucket: flip one agent to `debug`,
watch the output, flip it back. No restart, no redeploy.

## Log events

The SDK instruments the agent lifecycle and invocation path automatically.
Handler code needs no changes.

| Event | Level | When |
|-------|-------|------|
| `agent_registered` | info | Agent starts and registers |
| `agent_deregistered` | info | Agent shuts down gracefully |
| `agent_activated` | info | [Lifecycle gate](lifecycle.md) opened; agent came online |
| `agent_deactivated` | info | Lifecycle gate closed; agent drained and went offline |
| `request_received` | debug | Incoming invocation |
| `request_completed` | debug | Invocation completed (carries `duration_ms`) |
| `request_failed` | warn | Invocation raised an error (carries the error `code`) |
| `validation_error` | warn | Input failed Pydantic validation |
| `usage_reported` | info | Handler reported LLM usage via [`report_usage()`](usage.md) (carries the usage fields) |

Events are published on `mesh.logs.{name}` — a sibling root to
`mesh.errors.{name}` and `mesh.death.{name}`, so wildcards aggregate
naturally:

```
mesh.logs.>          # all logs, all agents
mesh.logs.nlp.>      # all logs from the nlp channel
mesh.logs.nlp.summarizer
```

Each event is a JSON `LogEvent`:

```json
{
  "timestamp": "2026-07-18T14:30:00.123456+00:00",
  "level": "warn",
  "agent": "nlp.summarizer",
  "event": "request_failed",
  "request_id": "abc123",
  "message": "boom",
  "data": {"code": "handler_error"}
}
```

Log subjects are ephemeral plain NATS subjects — no JetStream, no storage,
no retention configuration. If nobody is listening, events vanish. That is
the deliberate trade-off for a zero-cost live-monitoring layer; historical
retention belongs to the future OTel export story.

## Controlling levels at runtime

A `mesh-observability` KV bucket holds the configuration. Two tiers:

| Key | Scope |
|-----|-------|
| `global` | Mesh-wide default |
| `{name}` | Per-agent override (wins over global) |

Levels: `debug`, `info`, `warn`, `error`, `off`. The default is `info` —
which means **zero per-request publishes in steady state** (the per-request
events are `debug`), while failures stay visible (`warn`).

Hosts watch the bucket and apply changes within a moment of the write:

```bash
oam observe set nlp.summarizer --log-level debug   # one noisy agent
oam observe set --global --log-level warn          # quiet the whole mesh
oam observe config                                 # see what's in effect
```

Or from code:

```python
await mesh.observe.set("nlp.summarizer", log_level="debug")
await mesh.observe.set_global(log_level="warn")

config = await mesh.observe.get("nlp.summarizer")
# ObserveConfig(log_level="debug", source="agent")
```

`source` tells you which tier supplied the effective value: `agent`,
`global`, or `default`.

## Consuming logs

Tail from the CLI:

```bash
oam observe logs                     # everything
oam observe logs nlp.summarizer      # one agent
oam observe logs --level warn        # warn and above
```

Or subscribe in code — `mesh.observe.logs()` yields typed `LogEvent`
objects as they arrive:

```python
async with AgentMesh() as mesh:
    async for event in mesh.observe.logs(level="warn"):
        alert(f"{event.agent}: {event.event} — {event.message}")
```

See the [Observing the Mesh](../cookbook/observing-the-mesh.md) recipe for a
worked debugging session.

## Secured meshes

On a mesh secured with `oam auth init` ([Securing the Mesh](security.md)),
workers publish and read everything under their existing grants; the
**observer** role can tail `mesh.logs.>` and read the config bucket, but
only workers can change levels. Credentials minted before this feature
degrade gracefully — hosts fall back to default levels and keep serving.

## What this layer is not

- **Not tracing.** Span events and cross-agent trace context are a planned
  increment (ADR-0048 defers them until the OTel trace-context decision).
- **Not metrics.** Request counters are specified to ride on heartbeats,
  which arrive with the liveness heartbeat layer (ADR-0016 follow-up).
- **Not history.** Nothing is stored. For replay and dashboards over time,
  export to an external backend once the OTel layer lands.
