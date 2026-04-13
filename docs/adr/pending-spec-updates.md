# Pending Spec Updates

Generated: 2026-04-11
Updated: 2026-04-13 (applied 3/7 prior, 1 new, 5 remaining)

## From ADR-0005: Streaming wire protocol

**File:** km/agentmesh-spec.md
**Section:** (new section) Streaming Protocol
**Change type:** addition
**Description:** Add streaming subject convention (`mesh.stream.{request_id}`), new headers (`X-Mesh-Stream`, `X-Mesh-Stream-Seq`, `X-Mesh-Stream-End`), `mesh.stream()` async generator API, and capability enforcement rules.
**Proposed text:**
> ### Streaming Subject Convention
> ```
> mesh.stream.{request_id}    # per-request streaming subject
> ```
> Request header: `X-Mesh-Stream: true`
> Response headers: `X-Mesh-Stream-Seq: N` (0-indexed), `X-Mesh-Stream-End: true|false`

---

## From ADR-0010: Pull object store into Phase 1

**File:** km/agentmesh-spec.md
**Section:** Development Phases
**Change type:** modification
**Description:** Move Object Store from Phase 2+ to Phase 1. Update Phase 1 scope to include `mesh-artifacts` (Object Store bucket) and `mesh-context` (KV context bucket).

---

## From ADR-0010: Pull object store into Phase 1

**File:** km/ideas.md
**Section:** Shared memory/context
**Change type:** resolution
**Description:** Mark as resolved — Object Store (`mesh-artifacts`) and shared context KV (`mesh-context`) are now in Phase 1. Remove or annotate the open question.

---

## From ADR-0005: Streaming wire protocol

**File:** km/ideas.md
**Section:** NATS-JetStream KV/ObjectStore Setup
**Change type:** resolution
**Description:** The streaming protocol design (ADR-0005) partially addresses this. The setup procedure for JetStream primitives is now implicit in the embedded server startup. Can be marked as partially resolved.

---

## From ADR-0016: Disconnect advisories for instant failure detection

**File:** km/agentmesh-spec.md
**Section:** §4.7 Registration and Deregistration — "On crash (ungraceful termination)"
**Change type:** modification
**Description:** Replace the heartbeat-only crash detection with a hybrid approach: NATS disconnect advisories as primary (sub-second for crashes, 10-20s for network partitions), heartbeats as secondary (zombie detection only). Add `mesh.death.{channel}.{name}` to subject naming convention (§4.1). Reference the new `km/agentmesh-liveness-and-failure.md` spec for full details.
**Proposed text:**
> **On crash (ungraceful termination):**
>
> The mesh uses a hybrid detection strategy. See `km/agentmesh-liveness-and-failure.md` for the full specification.
>
> 1. **Primary: NATS disconnect advisories** (`$SYS.ACCOUNT.*.DISCONNECT`) — the NATS server emits an advisory when any client's TCP connection drops. The mesh health monitor subscribes to these advisories and immediately deregisters the dead agent from the catalog and registry KV. Detection latency: sub-second for process crashes, 10-20 seconds for network partitions (with tuned `ping_interval`).
> 2. **Secondary: Heartbeat timeout** — if no heartbeat is received within 3× the declared `heartbeat_interval_ms`, the health monitor marks the agent as unhealthy. This catches zombie agents (process alive but unresponsive) that maintain their TCP connection.
>
> On any detection, a death notice is published to `mesh.death.{channel}.{name}` for orchestrators, monitoring, and auto-scaling subscribers.
