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