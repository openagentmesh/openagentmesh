# ADR-0016: Use NATS disconnect advisories for instant failure detection

- **Type:** architecture
- **Date:** 2026-04-13
- **Status:** spec
- **Source:** .specstory/history/2026-04-13_19-32-21Z.md (discussion), km/agentmesh-liveness-and-failure.md (spec)

## Context

The original spec (§4.7) relies solely on heartbeat-based crash detection with a 3x tolerance window (default 30s). This creates a 30-second window where the catalog advertises a dead agent, causing stale discovery, wasted LLM tool-selection cycles, and orchestration stalls. For agentic applications where agents coordinate workflows, 30-second detection latency is unacceptable.

The question: can we detect agent failure faster than heartbeat polling, without introducing MQTT or external dependencies?

## Decision

Use NATS `$SYS.ACCOUNT.*.DISCONNECT` advisories as the primary failure detection mechanism. These are server-emitted events triggered by TCP disconnect: near-instant for process crashes, seconds for network partitions (with tuned ping settings). Heartbeats become a secondary mechanism reserved for zombie detection (process alive but unresponsive).

A hybrid approach with four failure modes, each with the fastest available detection path:


| Mode              | Detection                                   | Latency           |
| ----------------- | ------------------------------------------- | ----------------- |
| Graceful shutdown | Self-deregistration                         | Instant           |
| Process crash     | Disconnect advisory (TCP FIN/RST)           | Sub-second        |
| Network partition | Disconnect advisory (TCP keepalive timeout) | 10-20s (tuned)    |
| Zombie            | Heartbeat timeout                           | 30s (3x interval) |


Introduce `mesh.death.{channel}.{name}` subject for death notices that any agent can subscribe to, enabling orchestration recovery, auto-scaling triggers, and monitoring.

## Alternatives Considered

- **Heartbeat-only (status quo):** Simple but 30s minimum detection for all failure modes. Too slow for agentic orchestration.
- **MQTT LWT:** Native broker-level last-will-and-testament. Requires MQTT protocol support. LWT pattern is the inspiration, but NATS disconnect advisories achieve the same result without MQTT dependency.
- **JetStream consumer idle heartbeats:** Only applies to JetStream consumers, not general NATS subscribers. Too narrow.

## Risks and Implications

- `$SYS.ACCOUNT.>` may require elevated permissions on hardened NATS configurations. Need to verify and document required permissions.
- Multi-instance agents (queue groups) need instance-count tracking; death notice should only fire when the *last* instance disconnects, not on individual scale-down.
- Network blips cause rapid disconnect/reconnect. A reconnection grace period prevents flapping but reintroduces latency. Tuning needed.
- NATS `ping_interval` should be tuned from default 2m to ~10s for mesh use, documented in recommended server config.

## Amendment (2026-07-18): v1 scope and placement decisions

Shaped for implementation together with ADR-0040 (they share the death-notice
machinery). Decisions that the original text left open:

**Health monitor placement.** The monitor is hosted by whoever owns the mesh
lifecycle, not by every `AgentMesh` instance:

- `AgentMesh.local()` runs the monitor as an in-process task alongside the
  embedded server.
- `oam mesh up` runs the monitor next to the spawned `nats-server` (in-process
  in `--foreground` mode, as a companion background process otherwise; `oam
  mesh down` stops both).
- Secured meshes run `oam mesh monitor` wherever the operator wants, with two
  credentials (see below).

Rationale: `$SYS` access is privileged and should not be handed to every SDK
client; N per-client monitors would also race each other on deregistration.

**`$SYS` access on the open dev path.** A default no-auth `nats-server` puts
all clients in the global account and offers no way to subscribe to `$SYS.>`.
`oam mesh up` and the embedded server therefore now generate a small config:
`APP` and `SYS` accounts, `no_auth_user` mapping anonymous clients to `APP`
(JetStream enabled), `system_account: SYS` with a generated-password monitor
user. Open DX is preserved — `AgentMesh()` with no creds still just works —
while the monitor gets advisories. The config also tunes `ping_interval: 10s`
/ `max_outstanding_pings: 2` per §5.2 of the liveness spec.

**Two connections in the monitor.** Accounts isolate subjects, so one
connection cannot both read `$SYS.>` (SYS account) and write the catalog /
publish death notices (APP account). The monitor holds a SYS connection for
advisories and a plain `AgentMesh` connection for deregistration and death
notices. On a secured mesh (`oam auth init`) these map to a SYS-account user
credential and a worker-role credential.

**Advisory correlation.** Every `AgentMesh` connection sets its NATS client
name to `oam-host-{instance_id}`. A new KV bucket `mesh-instances` maps
`{instance_id}` → the JSON list of agent names that host serves; hosts write
it at registration time and delete it on graceful shutdown. On a DISCONNECT
advisory for `oam-host-X`, the monitor reads `mesh-instances/X`, and for each
agent no *other* live instance serves: removes the catalog entry, deletes the
registry key, and publishes the death notice. Advisories for connections
without an instance key (CLI taps, callers, gracefully-shut-down hosts) are
ignored.

**Death notices.**

- Subject: `mesh.death.{name}` — dotted agent names mean channel wildcards
  compose naturally (`mesh.death.>` for everything, `mesh.death.nlp.>` for a
  channel), matching ADR-0049.
- Payload: `{"agent", "reason": "disconnect" | "graceful_shutdown", "detected_at", "instance_id"}`.
- Multi-instance: the notice fires only when the **last** instance serving an
  agent disconnects; a scale-down of one replica only updates
  `mesh-instances`.
- Graceful shutdown: the SDK publishes the notice itself (reason
  `graceful_shutdown`) during `_shutdown`, before deregistering — the monitor
  is not involved, so graceful notices work even without a monitor running.

**Reconnection grace period: none (v1).** The SDK connects with
`allow_reconnect=False`, so a dropped connection never comes back under the
same client id; deregistering immediately is correct. Revisit if the SDK
ever enables reconnection.

**v1 scope: the advisory path only.** Heartbeats and zombie detection
(`mesh.health.{name}`, the secondary mechanism in the Decision above) are
**deferred**: no heartbeat machinery exists today, so shipping advisories
strictly improves detection for crash, partition, and graceful shutdown —
the three fast paths — while the zombie case keeps its current behavior
(caller timeout). The heartbeat layer remains specified here and becomes a
follow-up increment.

**Caller-side ergonomics** (`no_responders` → `NotFound`, death-notice
fast-fail during in-flight calls) are ADR-0040's territory.

### Code sample

```python
# The mesh lifecycle owner runs the monitor: `oam mesh up` (or AgentMesh.local()).
# Any process can react to agents leaving the mesh:

async with AgentMesh() as mesh:
    async for notice in mesh.subscribe(subject="mesh.death.>"):
        print(f"{notice['agent']} left the mesh: {notice['reason']}")
        # orchestrators reroute, spawners respawn, dashboards alert

# When an agent process is SIGKILLed, its catalog entry disappears and the
# death notice arrives in well under a second — not after a 30s heartbeat
# window. `await mesh.catalog()` no longer lists the dead agent.
```