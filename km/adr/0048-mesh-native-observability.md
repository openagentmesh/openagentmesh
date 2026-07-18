# ADR-0048: Mesh-native observability

**Status:** documented (v1: structured logs + KV level control + `oam observe logs`; traces, heartbeat metrics, and `$SYS` bridging deferred — see Amendment)

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

## Amendment (2026-07-18): v1 scope, subject correction, stale-context fixes

Shaped discussion → spec for Stage 3 execution (see
`km/notes/2026-07-17-stage3-plan.md`). The original text above is kept for the
full design; this amendment corrects what drifted and pins the v1 slice.

### Stale context corrected

The Context section claims heartbeats on `mesh.health.{channel}.{name}` and
death notices already exist. Reality after ADR-0016/0040 (2026-07-18): death
notices exist on `mesh.death.{name}`; **the heartbeat layer was explicitly
deferred** in ADR-0016's v1 amendment — no `mesh.health.*` publishing exists
anywhere in `src/`. Consequences for this ADR:

- **"Metrics folded into the heartbeat" is deferred with the heartbeat layer.**
  There is no heartbeat to fold counters into. When the heartbeat increment
  lands (ADR-0016 follow-up), it should carry the counters exactly as
  specified above; v1 of this ADR ships no metrics.
- Agent lifecycle detection (registration, death) is already observable via
  the catalog, `mesh.death.>`, and `mesh.errors.>`; v1 logs complement those
  rather than duplicating them.

### Subject correction: `mesh.logs.{name}`, not `mesh.agent.{name}.logs`

The original design hangs logs off the agent subject
(`mesh.agent.{channel}.{name}.logs`) and claims wildcard aggregation via
`mesh.agent.>.logs`. **That wildcard is invalid NATS** — `>` matches only at
the end of a subject — so the one thing the sibling placement was chosen for
(easy aggregation) does not actually work; `mesh.agent.*.*.logs` would pin
agent names to exactly two tokens, which ADR-0049's dotted names do not
guarantee.

v1 therefore uses a dedicated root, matching the `mesh.errors.{name}` and
`mesh.death.{name}` precedent:

```
mesh.logs.{name}          # e.g. mesh.logs.nlp.summarizer

mesh.logs.>               # all logs, all agents
mesh.logs.nlp.>           # all logs from the nlp channel
```

Ephemeral plain NATS subjects, as originally decided (no JetStream, no
retention).

### v1 scope

**In:** structured, level-gated lifecycle/invocation logs auto-published by
the SDK; the `mesh-observability` KV control plane (log level only); the
`mesh.observe` SDK namespace (`logs()`, `get()`, `set()`, `set_global()`);
`oam observe logs|config|set` CLI. The six log events in the table above ship
as specified, on `mesh.logs.{name}`.

**Deferred, with reasons:**

- **Traces** — depend on the trace-context decision (open question 1), which
  is a partial Phase 2 OTel pull-forward; nothing in v1 needs it. The
  `.traces` subject, span publishing, `oam observe traces`, and the `traces`
  config key all move to a v2 increment. Leaning (a) (standard `traceparent`
  header) stands.
- **Metrics in heartbeats** — blocked on the heartbeat layer ADR-0016
  deferred (see above).
- **`$SYS` bridging (`mesh.system.*`)** — the `oam mesh up` monitor process
  from ADR-0016 is the natural host and now exists, but bridging adds new
  wire surface + role-template churn for advisories nobody consumes yet.
  Revisit with the heartbeat increment.
- **Custom logging from handlers** (open question 2) — needs either context
  injection (its own ADR) or an ADR-0026 mesh reference; not required for
  the production-debugging story v1 targets. Leaning: the Python `logging`
  bridge, so agent code stays framework-free.
- **`AgentMesh(observe=...)` constructor param** — dropped, not deferred.
  Two control planes (constructor + KV) would race each other and make
  `oam observe set` lie about effective config. The KV bucket is the single
  source of truth; `oam mesh up --log-level debug` just seeds the global key.

### v1 decisions

- **Config schema (v1):** `{"log_level": "debug"|"info"|"warn"|"error"|"off"}`.
  Default `info`. Per-agent key (the dotted name, e.g. `nlp.summarizer`)
  overrides `global`. The `traces` key returns with the traces increment.
- **Log event schema (open question 3 resolved):** a formal Pydantic model
  `LogEvent` in the SDK — `timestamp`, `level`, `agent`, `event`,
  `request_id`, `message`, `data` (freeform dict, `{}` default). Typed
  models keep the CLI/SDK consumers honest; freeform `data` keeps the SDK
  out of the business of versioning per-event payloads.
- **Performance (open question 4 resolved for v1):** hosts cache effective
  config in-process and update it via KV watch; the per-request cost when a
  level is gated off is a dict lookup and an integer compare, no publish.
  At the default `info` level the per-request events (`request_received`,
  `request_completed`) are `debug` and not published at all — the default
  steady-state overhead is zero publishes per request. `request_failed` and
  `validation_error` are `warn` and always visible by default, which is the
  right bias for production debugging.
- **Role templates ship in the same change** (lesson from ADR-0016/0038:
  new wire surfaces break freshly-minted creds unless ROLE_TEMPLATES moves
  with them): `$KV.mesh-observability.>` joins the shared bucket list;
  workers already cover `mesh.logs.>` via `mesh.>`; observer gains
  `mesh.logs.>` sub; invoker is unchanged (tailing logs is observer work).
  Stale credentials must degrade gracefully (warning, not crash), matching
  the mesh-instances precedent.

### Code sample (v1)

```python
from openagentmesh import AgentMesh, AgentSpec
from pydantic import BaseModel


class SummarizeInput(BaseModel):
    text: str

class SummarizeOutput(BaseModel):
    summary: str


# SDK auto-instruments lifecycle and invocations. No handler changes.
mesh = AgentMesh()

@mesh.agent(AgentSpec(
    name="nlp.summarizer",
    description="Summarizes text",
))
async def summarize(req: SummarizeInput) -> SummarizeOutput:
    # At log_level "debug" the SDK publishes to mesh.logs.nlp.summarizer:
    #   {"level": "debug", "event": "request_received", "request_id": "..."}
    #   ... handler runs ...
    #   {"level": "debug", "event": "request_completed", "data": {"duration_ms": 45}}
    # A handler exception publishes {"level": "warn", "event": "request_failed"}.
    return SummarizeOutput(summary=req.text[:60])


# --- Consuming logs (any process on the mesh) ---

async with AgentMesh() as tap:
    async for event in tap.observe.logs():                  # all agents
        print(f"[{event.level}] {event.agent}: {event.event}")

    async for event in tap.observe.logs("nlp.summarizer"):  # one agent
        print(f"[{event.level}] {event.event} {event.data}")

    async for event in tap.observe.logs(level="warn"):      # warn and above
        ...

# --- Runtime config (no restart) ---

    await tap.observe.set("nlp.summarizer", log_level="debug")
    await tap.observe.set_global(log_level="warn")

    config = await tap.observe.get("nlp.summarizer")
    # ObserveConfig(log_level="debug", source="agent")
    config = await tap.observe.get("nlp.classifier")
    # ObserveConfig(log_level="warn", source="global")
```

```bash
oam observe logs                       # tail all agents' logs
oam observe logs nlp.summarizer        # tail one agent
oam observe logs --level warn          # filter by minimum level
oam observe config                     # show global + per-agent overrides
oam observe set nlp.summarizer --log-level debug
oam observe set --global --log-level warn
```
