# AgentMesh: Liveness Checks and Client Failure Modes

**Version:** 0.1 — Draft Specification  
**Date:** April 2026  
**Status:** Pre-implementation design document  
**Related:** §4.7 of agentmesh-spec.md (Registration and Deregistration)

---

## 1. Problem Statement

The current spec (§4.7) relies solely on heartbeat-based crash detection: if no heartbeat arrives within 3× the declared interval (default 30s), a health monitor marks the agent as unhealthy. This creates a 30-second window where the catalog advertises a dead agent, causing callers to timeout on invocations that can never succeed.

For agentic applications this is particularly damaging:

- **Orchestration stalls.** An orchestrator dispatching work across agents waits 30s before suspecting a downstream agent is dead, then must timeout, detect failure, and reassign — total recovery time can exceed a minute.
- **Catalog staleness.** LLM-based tool selection trusts the catalog. A stale entry wastes an LLM call cycle (select tool → call → timeout → retry with different tool).
- **Cascade risk.** Multiple agents depending on a dead agent all timeout simultaneously, creating a thundering-herd retry pattern.

---

## 2. Failure Modes

An agent can leave the mesh in four distinct ways. Each has different detection characteristics and appropriate responses.

| Mode | Cause | Detection | Latency | Example |
|------|-------|-----------|---------|---------|
| **Graceful shutdown** | `mesh.stop()` called | Agent deregisters itself (KV delete + catalog CAS) | Instant | Deployment rollout, scaling down |
| **Process crash** | Unhandled exception, OOM kill, SIGKILL | NATS TCP disconnect → server advisory | Sub-second | Bug in handler, container killed |
| **Network partition** | Network failure between agent and NATS | NATS TCP timeout → server advisory (after TCP keepalive timeout) | Seconds (TCP keepalive dependent) | Cloud AZ failure, DNS issue |
| **Zombie** | Process alive but unresponsive (deadlock, infinite loop, blocked on external call) | Heartbeat timeout only | 3× heartbeat interval (default 30s) | LLM API hang, database lock |

Key insight: heartbeats only catch zombies. The other three failure modes have faster detection paths available.

---

## 3. Detection Mechanisms

### 3.1 NATS Disconnect Advisories (Primary)

NATS server emits system events when clients disconnect:

```
$SYS.ACCOUNT.{account}.DISCONNECT
```

The advisory payload includes:

```json
{
  "server": { "name": "nats-1", "host": "0.0.0.0", "id": "..." },
  "client": {
    "start": "2026-04-13T10:00:00Z",
    "stop": "2026-04-13T10:05:32Z",
    "host": "192.168.1.10",
    "id": 42,
    "acc": "default",
    "name": "mesh.agent.nlp.summarizer",
    "lang": "python",
    "ver": "2.9.0"
  },
  "sent": { "msgs": 1523, "bytes": 204800 },
  "received": { "msgs": 1200, "bytes": 102400 },
  "reason": "Client Closed" | "Stale Connection" | "Authentication Timeout" | "Slow Consumer"
}
```

**`reason` field** distinguishes failure modes:

| Reason | Meaning | Mesh response |
|--------|---------|---------------|
| `Client Closed` | Clean TCP close (graceful or process exit) | Deregister if agent didn't self-deregister |
| `Stale Connection` | TCP keepalive/ping failure (network partition or crash without close) | Deregister immediately |
| `Slow Consumer` | Agent couldn't keep up with message rate | Deregister + emit warning on `mesh.errors.{name}` |
| `Authentication Timeout` | Credential issue | Deregister + log security event |

**Detection latency:** Near-instant for process crash (TCP FIN/RST). Seconds for network partition (depends on NATS `ping_interval` and `max_outstanding_pings`, defaults: 2min ping, 2 outstanding = ~4min worst case — should be tuned lower for mesh use).

### 3.2 Heartbeats (Secondary — Zombie Detection)

Heartbeats remain the only mechanism to detect a zombie agent — process alive, TCP connection open, but not actually processing work.

```
mesh.health.{channel}.{name}
```

Heartbeat payload:

```json
{
  "status": "healthy",
  "timestamp": "ISO8601",
  "uptime_ms": 3600000,
  "in_flight": 3,
  "processed": 15230
}
```

The `in_flight` and `processed` counters enable smarter health assessment:
- `in_flight` stuck at N with `processed` not incrementing = likely zombie
- `in_flight` at 0 with `processed` incrementing = healthy idle agent

### 3.3 Invocation-Level Failure Detection (Caller-Side)

Callers detect agent failure through:
- **NATS `no responders`** status — immediate signal that no subscriber exists on the subject (agent never registered or already deregistered). This is a NATS-native feature when using request/reply.
- **Timeout** — agent exists but didn't respond in time.

The SDK should distinguish these in the error returned to callers:

```python
try:
    result = await mesh.call("summarizer", payload, timeout=5.0)
except AgentNotFoundError:
    # No subscribers on subject — agent is gone
    ...
except AgentTimeoutError:
    # Agent exists but didn't respond — may be overloaded or zombie
    ...
```

---

## 4. Death Notices

When an agent leaves the mesh (by any mechanism), a **death notice** is published to allow interested parties to react.

### 4.1 Subject

```
mesh.death.{channel}.{name}    # death notice for a specific agent
mesh.death.>                    # wildcard: all death notices
```

### 4.2 Payload

```json
{
  "agent": "summarizer",
  "channel": "nlp",
  "reason": "disconnect" | "heartbeat_timeout" | "graceful_shutdown",
  "detected_at": "ISO8601",
  "last_heartbeat": "ISO8601",
  "advisory": { }
}
```

### 4.3 Use Cases

- **Orchestrators** subscribe to `mesh.death.>` and reassign in-flight work when a downstream agent dies.
- **Auto-scaling / spawner** (Phase 3) subscribes and respawns agents from their stored contracts.
- **Monitoring / alerting** consumes death notices for dashboards and paging.
- **Circuit breaker** — after N deaths in T seconds, stop routing to that agent type until manual intervention.

---

## 5. SDK Implementation

### 5.1 Mesh-Level Health Monitor

The `AgentMesh` instance subscribes to disconnect advisories and manages deregistration:

```python
class AgentMesh:
    async def _start_health_monitor(self):
        # Primary: NATS disconnect advisories
        await self._nc.subscribe(
            "$SYS.ACCOUNT.*.DISCONNECT",
            cb=self._on_disconnect_advisory
        )
        # Secondary: heartbeat watcher (for zombie detection)
        self._heartbeat_checker = asyncio.create_task(
            self._check_heartbeats()
        )

    async def _on_disconnect_advisory(self, msg):
        advisory = parse_advisory(msg.data)
        agent_name = advisory["client"]["name"]
        if not agent_name.startswith("mesh.agent."):
            return  # not a mesh agent
        
        # Deregister from catalog + registry
        await self._deregister_agent(agent_name)
        
        # Publish death notice
        await self._nc.publish(
            f"mesh.death.{agent_name}",
            death_notice_payload(advisory)
        )
```

### 5.2 NATS Server Configuration for Mesh

Recommended NATS settings for low-latency failure detection:

```
ping_interval: "10s"          # default 2m — too slow for mesh
max_outstanding_pings: 2       # disconnect after 2 missed pings (20s worst case)
```

This brings network partition detection from ~4 minutes to ~20 seconds. Combined with instant process-crash detection via TCP close, the mesh achieves sub-second to 20-second failure detection for all non-zombie cases.

### 5.3 Agent Registration with Disconnect Handling

Agents set their NATS client name to their mesh subject for advisory correlation:

```python
await nats.connect(
    "nats://localhost:4222",
    name=f"mesh.agent.{channel}.{name}",  # enables advisory correlation
    # ...
)
```

---

## 6. Hybrid Detection Summary

```
Agent dies (process crash)
  └─ TCP FIN/RST → NATS server
       └─ $SYS.ACCOUNT.*.DISCONNECT advisory (sub-second)
            └─ Health monitor deregisters agent
                 └─ mesh.death.{name} published

Agent loses network
  └─ TCP keepalive timeout → NATS server
       └─ $SYS.ACCOUNT.*.DISCONNECT advisory (10-20s with tuned config)
            └─ Health monitor deregisters agent
                 └─ mesh.death.{name} published

Agent becomes zombie (alive but unresponsive)
  └─ Heartbeat stops arriving
       └─ 3× heartbeat interval (default 30s)
            └─ Health monitor deregisters agent
                 └─ mesh.death.{name} published

Agent shuts down gracefully
  └─ mesh.stop() called
       └─ Agent self-deregisters (instant)
            └─ mesh.death.{name} published (reason: graceful_shutdown)
```

---

## 7. Open Questions

1. **Advisory permissions.** `$SYS.ACCOUNT.>` requires system-level access on some NATS configurations. Need to verify this works with default NATS security settings and document required permissions for embedded vs. external NATS.

2. **Multi-instance agents.** When one instance of a queue-group agent disconnects, the death notice should only fire if *all* instances are gone. Otherwise it's a scale-down event, not a death. The health monitor needs to track instance count per agent name.

3. **Reconnection grace period.** Network blips cause disconnect + reconnect in rapid succession. A short grace period (e.g., 5s) before deregistration avoids flapping. But this reintroduces latency. Trade-off needs tuning.

4. **Phase placement.** Disconnect advisories and death notices are high-value for Phase 1 (instant catalog accuracy). Zombie detection via heartbeats is also Phase 1. The question is whether the full health monitor service runs in-process (every `AgentMesh` instance monitors) or as a dedicated sidecar.
