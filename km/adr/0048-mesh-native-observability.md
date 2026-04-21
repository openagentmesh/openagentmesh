# ADR-0048: Mesh-native observability

**Status:** discussion

## Context

The mesh already has lifecycle primitives: heartbeats on `mesh.health.{channel}.{name}` and death notices on `mesh.death.{channel}.{name}`. The spec (section 8) outlines OTel integration for Phase 2+, covering trace context propagation and export to external backends.

There is a valuable middle ground between "no observability" and "full OTel export": **the mesh observes itself**. Structured logs and traces published to NATS subjects, consumable by any subscriber (a monitoring agent, a CLI tail command, a dashboard), with zero external infrastructure. NATS server logs are useful for infrastructure diagnostics, but the mesh's own subject hierarchy is the richer primitive: it carries envelope metadata, agent identity, and request context that server logs do not.

The ideas.md "Embedded Observability" sketch proposed auto-instrumented LTM on mesh subjects. This ADR shapes that idea into a concrete design.

## Decision

### Subject hierarchy

Observability subjects are siblings to the existing `.events` subject:

```
mesh.agent.{channel}.{name}.logs      # structured log events
mesh.agent.{channel}.{name}.traces    # OTel-formatted span events
```

NATS wildcards give natural aggregation:

```
mesh.agent.>.logs       # all logs, all agents
mesh.agent.nlp.>.logs   # all logs from the nlp channel
mesh.agent.>.traces     # all traces, all agents
```

These are plain NATS subjects (not JetStream streams). Events are ephemeral: if no subscriber is listening, they are lost. This is a deliberate trade-off: zero storage cost, zero retention configuration, suitable for live monitoring. Historical replay is deferred to the OTel export story, where external backends (Jaeger, Loki) handle retention.

### No separate metrics subject

Metrics (request count, error count, average latency) are folded into the existing heartbeat on `mesh.health.{channel}.{name}` rather than a separate subject. The heartbeat is already periodic and already consumed by health monitors. Adding counters to it gives dashboards both liveness and stats in one stream.

```json
{
  "status": "healthy",
  "uptime_s": 3600,
  "requests_total": 1234,
  "errors_total": 12,
  "avg_latency_ms": 45
}
```

### What the SDK auto-publishes

The SDK instruments the agent lifecycle and invocation path. No agent code changes needed.

**Logs (level-gated):**

| Event | Level | When |
|-------|-------|------|
| `agent_registered` | info | Agent starts and registers |
| `agent_deregistered` | info | Agent shuts down gracefully |
| `request_received` | debug | Incoming invocation |
| `request_completed` | debug | Invocation completed |
| `request_failed` | warn | Invocation raised an exception |
| `validation_error` | warn | Input failed Pydantic validation |

**Traces (OTel span format):**

One span per invocation handling (start to response). One span per outgoing `mesh.call()` / `mesh.stream()`. Parent-child linking via trace context headers (see open question 1).

### Observability control plane via KV

A `mesh-observability` KV bucket controls what gets published. Two tiers of keys:

| Key | Scope | Purpose |
|-----|-------|---------|
| `global` | Mesh-wide | Default settings for all agents |
| `{channel}.{name}` | Per-agent | Override for a specific agent |

Per-agent config takes precedence over global. Value schema:

```json
{
  "log_level": "info",
  "traces": false
}
```

`log_level` values: `debug`, `info`, `warn`, `error`, `off`. Default: `info`.
`traces` values: `true`, `false`. Default: `false`.

Agents watch their own key and the global key via KV Watch. When config changes, the agent adjusts what it publishes within seconds, no restart needed.

Setting config:

- **CLI at startup:** `oam mesh up --log-level debug --traces`
- **CLI at runtime:** `oam observe set nlp.summarizer --log-level debug --traces`
- **SDK at startup:** `AgentMesh(observe={"log_level": "debug", "traces": True})`
- **SDK at runtime:** `await mesh.observe.set("nlp.summarizer", log_level="debug", traces=True)`

### NATS system event bridging

The `oam mesh up` process subscribes to relevant `$SYS.>` advisories and re-publishes them on OAM subjects:

```
mesh.system.slow_consumer      # agent can't keep up with message rate
mesh.system.auth_failure       # authentication rejected
```

Connect/disconnect events are not bridged because the mesh already tracks agent lifecycle through registration, deregistration, and death notices.

This makes `mesh.>` the single subscription namespace for full mesh observability. Requires system account access on the NATS server, which ties into ADR-0038 (auth).

### CLI surface

```bash
# Tail logs
oam observe logs                          # all agents
oam observe logs nlp.summarizer           # specific agent
oam observe logs --level error            # filter by level

# Tail traces
oam observe traces                        # all agents
oam observe traces nlp.summarizer         # specific agent

# View/change config
oam observe config                        # show all
oam observe config nlp.summarizer         # show specific agent
oam observe set nlp.summarizer --log-level debug --traces
oam observe set --global --log-level warn --no-traces
```

### Code sample

```python
from openagentmesh import AgentMesh, AgentSpec
from pydantic import BaseModel


class SummarizeInput(BaseModel):
    text: str

class SummarizeOutput(BaseModel):
    summary: str


# SDK auto-instruments lifecycle and invocations.
# No code changes needed in the handler.
mesh = AgentMesh()

@mesh.agent(AgentSpec(
    name="summarizer",
    channel="nlp",
    description="Summarizes text",
))
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    # SDK auto-publishes to mesh.agent.nlp.summarizer.logs:
    #   {"level": "debug", "event": "request_received", "request_id": "..."}
    # SDK auto-publishes to mesh.agent.nlp.summarizer.traces:
    #   span start (OTel format)
    result = await some_llm(req.text)
    return SummarizeOutput(summary=result)
    # SDK auto-publishes log: request_completed, duration_ms: 45
    # SDK auto-publishes trace: span end


# --- Consuming observability data ---

async for event in mesh.observe.logs():
    print(f"[{event.level}] {event.agent}: {event.message}")

async for event in mesh.observe.logs("nlp.summarizer"):
    print(f"[{event.level}] {event.message}")

async for span in mesh.observe.traces():
    print(f"{span.agent}: {span.operation} ({span.duration_ms}ms)")


# --- Runtime config ---

await mesh.observe.set("nlp.summarizer", log_level="debug", traces=True)
await mesh.observe.set_global(log_level="warn", traces=False)

config = await mesh.observe.get("nlp.summarizer")
# ObserveConfig(log_level="debug", traces=True, source="agent")

config = await mesh.observe.get("nlp.classifier")
# ObserveConfig(log_level="warn", traces=False, source="global")
```

## Open questions

### 1. Trace context propagation

OTel spans need trace context to link parent and child spans across agents. The spec reserves `traceparent` / `tracestate` headers for Phase 2 OTel integration. Options:

- **(a) Pull `traceparent` into the envelope now.** Small change, means trace data is immediately OTel-compatible when export lands. Partial Phase 2 pull-forward.
- **(b) Use `X-Mesh-Request-Id` as correlation ID.** Simpler, but means traces are flat (no parent-child hierarchy) until OTel export adds real trace context.
- **(c) Mesh-specific `X-Mesh-Trace-Parent` header.** Carries trace_id + span_id, converts to standard `traceparent` later.

Leaning (a): just use the standard header. No reason to invent a custom one if we're already using OTel span format.

### 2. Custom logging from handlers

The SDK auto-publishes lifecycle events. Should agent authors be able to publish custom log entries to the same subject? Options:

- **Context injection:** `async def handle(req, ctx): ctx.log.info("custom")` (new handler shape concept, needs its own ADR).
- **Mesh instance:** `mesh.log.info("custom")` (works if handler has mesh reference per ADR-0026).
- **Python logging bridge:** Agent uses `logging.getLogger("openagentmesh.nlp.summarizer")`, SDK intercepts and publishes to NATS.

### 3. Log event schema

Proposed structure (not final):

```json
{
  "timestamp": "2026-04-21T14:30:00.123Z",
  "level": "info",
  "agent": "nlp.summarizer",
  "event": "request_completed",
  "request_id": "abc123",
  "message": "Request completed in 45ms",
  "duration_ms": 45,
  "metadata": {}
}
```

Should this be a formal Pydantic model in the SDK? Should `metadata` be typed or freeform?

### 4. Performance at high throughput

Publishing a log event per invocation adds serialization and network overhead. At thousands of requests/second, this matters. The KV-based level control mitigates it (set to `error` or `off` for hot agents), but the overhead of checking the KV-cached config on every request is non-zero. Need to verify this is negligible in practice.

### 5. System event bridging scope

Which `$SYS.>` subjects are worth bridging? Slow consumer and auth failure are clear. Others (JetStream advisories, server health) may be too low-level for mesh consumers. Need to enumerate and decide.

## Consequences

- Agents become observable with zero external tooling. A `oam observe logs` command or a monitoring agent subscription gives live visibility into the mesh.
- The KV control plane enables production debugging workflows: flip one agent to debug, watch the output, flip back. No restart, no redeploy.
- Ephemeral subjects mean no storage burden but also no historical replay. Acceptable for this layer; historical analysis is the OTel export story.
- The `mesh.observe` SDK namespace and `oam observe` CLI namespace are new API surfaces that need to stay stable.
- Heartbeat stats give dashboards a lightweight metrics story without a separate metrics pipeline.
- Adding `traceparent` to the envelope (if open question 1 resolves to option a) is a partial pull-forward of Phase 2 OTel work, but makes the trace data immediately portable.
