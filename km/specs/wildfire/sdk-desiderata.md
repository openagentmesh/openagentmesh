# SDK desiderata surfaced by the wildfire demo

**Status:** discussion

This file collects API gaps and feature requests that bubbled up while shaping the demo. Each item:
- Names a concrete need with the agents / surfaces that depend on it.
- Stops short of a specific design decision; the design lives in the relevant ADR.
- Tracks the candidate ADR (existing or proposed) that would close the gap.

Sequencing is not implied by ID. Ranking and decisions happen during the discussion that this file is meant to feed.

## #1. Declarative subject + KV-watch sources on `@mesh.agent`

**Need.** An agent should be able to declare "I am triggered by messages on subject X" or "I am triggered by KV changes under pattern P" without writing a subscribe loop in the handler body or a separate asyncio task.

**Used by.** UAV (1 KV write source for detections is implicit), drone (KV-watch on `wildfire.detection.*`), heli/ffunit/medevac (KV-watch on own position broadcast or queue-group call), briefer (KV-watch on `wildfire.detection.*` + pubsub on `mesh.survey.>`), narrator (multi-subject), stats ticker (multi-subject).

**Why now.** Without it, half the fleet types are scripts using the mesh as transport, not registered agents. Catalog has no entry; admin UI registry shows nothing for them.

**Candidate ADR.** ADR-0052 (generic agent sources). Sources cover both NATS subjects and KV patterns. The wildfire build should validate the source Protocol against both kinds.

## #2. Public `mesh.publish(subject, model)` on arbitrary subjects

**Need.** Any agent or non-agent code should be able to publish a Pydantic model to an arbitrary NATS subject without reaching into `mesh._nc.publish`.

**Used by.** Fire-sim (`mesh.environment.thermal`), drone (`mesh.survey.{drone_id}` for visibility), heli/ffunit/medevac (status feeds if pubsub-based), scenario UI (fire spawn, chaos kill), stats ticker (`mesh.swarm.stats`), narrator (`mesh.swarm.narrative`).

**Why now.** Without a public method, every emitter either:
- Uses the Publisher pattern (yields events) and accepts emission on `mesh.agent.{name}.events`, which collides with the demo's flat subject conventions.
- Reaches into `mesh._nc.publish(...)` and serialises by hand, scattering private-API access.

**Candidate ADR.** New ADR (or amend ADR-0034). Open shape questions: does `mesh.publish` accept a `BaseModel` and JSON-encode automatically? Does it set OAM headers (mesh-id, instance-id from #8)? Does it accept a generic payload or strictly Pydantic?

## #3. Queue group on raw subject subscription

**Need.** `mesh.subscribe(subject=...)` (or its declarative equivalent) must accept a `queue_group=` parameter so multiple instances can load-balance on a custom subject.

**Used by.** Briefer (queue group `briefers` for "produce briefing" cadence). Drone selection no longer uses queue groups (KV election supersedes).

**Why now.** Today's `mesh.subscribe(subject=...)` is broadcast-only. The briefer needs at-most-one-of-N semantics for periodic ticks across replicas.

**Candidate ADR.** Same one as #1 (the source abstraction needs a queue_group field) plus possibly a parameter on `mesh.subscribe` for direct caller use.

## #4. JetStream-backed sources with ack / nak semantics

**Status:** **DEFERRED.** The wildfire demo no longer needs this. KV-driven election (drone selection via CAS on a pending detection record) replaces the "queue-group + nearest-wins-via-nak" pattern.

Kept on this list for future reference: any production OAM workload that wants QoS-routed work distribution (priorities, retry-on-rejection) will resurface this need. Probably tracked outside the wildfire demo.

## #5. Subject-naming clarity for invocable agents

**Need.** ADR-0054 originally listed flat subjects (`mesh.medevac.dispatch`) for request/reply, but ADR-0049 auto-maps invocable subjects to `mesh.agent.{dotted-name}`. These conflict.

**Used by.** Heli, ffunit, medevac (all queue-group dispatch fleets), tasker.

**Why now.** With the channel-prefixed naming (`low-alt.heli`, `ground.ffunit`, `ground.medevac`), invocations are `mesh.call("low-alt.heli", DispatchOrder)` and route to `mesh.agent.low-alt.heli` per ADR-0049. The demo accepts this auto-mapping; ADR-0054 subject map is amended accordingly.

**Resolution.** No SDK change. ADR-0054 amendment to align the subject map with ADR-0049's auto-mapping.

## #6. Catalog visibility for source-driven agents (and per-instance presence)

**Need.** When an agent is purely source-driven (no invocable, no streaming, no publisher) it still has a contract worth advertising. Today the catalog projection comes from `AgentSpec` + handler shape; sources are runtime wiring.

Separately, the admin UI wants to show "this agent has 5 active instances." Catalog is at fleet-level identity (one entry per dotted name), so per-instance presence must come from elsewhere (KV record per instance, or NATS connection metadata, or heartbeats).

**Used by.** Admin UI (registry view, instance counts, liveness dots).

**Why now.** Demo will have ~16 fleet processes spread across 5 fleet identities. Without per-instance presence, admin UI cannot show "drone fleet, 5 instances, all live."

**Candidate ADR.** Likely composes with desideratum #8 (`mesh.instance_id`). Options:
- Each instance writes a KV record at `wildfire.fleet.{zone}.{type}.{instance_id}` with a heartbeat timestamp. Admin UI reads these.
- The mesh ships a generic instance-presence convention (e.g. `mesh.presence.{agent}.{instance_id}`) so admin UI works for any deployment, not just wildfire.
- Wait for ADR-0016 (NATS disconnect advisories) to land for liveness; instance discovery via NATS connection metadata.

## #7. Process orchestration for multi-fleet demos

**Need.** Running 16-30 processes by hand on a laptop is friction. Demo needs `agentmesh wildfire up` (or `bootstrap.py`) that starts embedded NATS, then spawns each fleet's processes with configurable counts.

**Used by.** All fleets when running locally.

**Candidate ADR.** Demo-local. If the pattern recurs across demos, raise an ADR for `agentmesh demo run <name>` as a CLI feature.

## #8. `mesh.instance_id`: stable per-process identifier

**Need.** A stable UUID per `AgentMesh()` instance, generated at construction, surfaced as a public attribute. Used to:
- Populate ID fields in outbound contracts (`detector_id`, `drone_id`, `medevac_id`).
- Auto-stamp on outbound messages as a header so admin UI / logging / tracing can group by source.
- Key per-instance KV records (`wildfire.fleet.low-alt.drone.{instance_id}`) for presence and position.

**Why now.** Today every fleet generates its own UUID at startup. The boilerplate is fine but proliferates; SDK affordance is one obvious source. More importantly, OAM has no convention for "which replica handled this?" — adding it once at the SDK level lets the admin UI render replica-aware views without per-demo plumbing.

**Used by.** Every multi-instance fleet, admin UI.

**Candidate ADR.** New ADR. Small scope: add `mesh.instance_id` property, set as a default header on all outbound messages. The header convention becomes part of the protocol.

## #9. KV ergonomics for election + state coordination

**Need.** Several KV operations the demo wants are either missing or inconvenient on the current `mesh.kv` (the public KVStore exposed per ADR-0025 for the `mesh-context` bucket).

**Confirmed working today (verified with a probe):**
- `mesh.kv.watch(pattern)` accepts NATS subject wildcards (`*`, `>`). Snapshot + live updates returned in one stream.
- `mesh.kv.cas(key)` async context manager. Reads value+revision on enter, writes with revision check on exit if value changed.
- `mesh.kv.update(key, fn)` auto-retries on CAS conflict.

**Missing or inconvenient:**

| Sub-need | Why | Demo touchpoint |
|---|---|---|
| `mesh.kv.list(prefix)` one-shot snapshot | Drones need to read all peer position records to compute "am I closest free?" Today requires a `watch` plus draining initial-done. | Drone election |
| `mesh.kv.try_cas(key)` returning success/fail bool | Election semantics: lose-the-race is data, not exception. Today raises `KeyWrongLastSequenceError`; user code must wrap in try/except. | Drone election |
| `mesh.kv.create(key, value)` (put-if-absent) | UAV creates a new detection record; must fail if the key exists (races between UAVs). | UAV detection write |
| Pydantic model helpers (`mesh.kv.put_model`, `cas_model`) | Demo serialises Pydantic to JSON and back on every read/write. Wrapper would cut boilerplate. | All KV-using agents |
| Atomic delete with revision | Cleanup of completed incidents under contention. Lower priority. | Briefer cleanup |

**Why now.** KV is the demo's coordination backbone (drone selection, fleet position, incident state, briefing snapshot). Boilerplate around CAS conflict + serialisation + listing accumulates fast across 5+ fleet types.

**Candidate ADR.** Likely a single small ADR amending ADR-0025 (public KV API) with the missing primitives. Pydantic helpers are a separate, optional ADR.

## Tracking

| ID | One-line | Blocking | Candidate ADR |
|---|---|---|---|
| #1 | Declarative subject + KV sources on decorator | UAV, drone, briefer, ffunit, heli, medevac | ADR-0052 |
| #2 | Public `mesh.publish(subject, model)` | Most emitters | new / amend ADR-0034 |
| #3 | Queue group on subject subscriptions | Briefer | ADR-0052 |
| #4 | JetStream ack / nak | DEFERRED | future |
| #5 | Subject-naming alignment | All call-fleets | ADR-0054 amendment |
| #6 | Per-instance presence + source-driven catalog visibility | Admin UI | composes with #8 |
| #7 | Demo orchestration | Demo runner | demo-local |
| #8 | `mesh.instance_id` stable per-process UUID + auto-header | Multi-instance fleets, admin UI | new |
| #9 | KV ergonomics: list, try_cas, create, model helpers | Drone, UAV, briefer, all KV writers | amend ADR-0025 |
