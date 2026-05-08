# SDK desiderata surfaced by the wildfire demo

**Status:** discussion

This file collects API gaps and feature requests that bubbled up while shaping the demo. Each item:
- Names a concrete need with the agents / surfaces that depend on it.
- Stops short of a specific design decision; the design lives in the relevant ADR.
- Tracks the candidate ADR (existing or proposed) that would close the gap.

Sequencing is not implied by ID. Ranking and decisions happen during the discussion that this file is meant to feed.

## #1. Declarative subject subscription on `@mesh.agent`

**Need.** An agent should be able to declare "I am triggered by messages on subject X" without writing a subscribe loop in the handler body or in a separate asyncio task.

**Used by.** UAV (1 subject), drone (1 subject + queue group), briefer (2+ subjects), medevac status emitter (depends on shape), narrator (multi-subject), stats ticker (multi-subject).

**Why now.** Without it, 5 of 9 fleet types are scripts using the mesh as a transport, not registered agents. The catalog has no entry for them. That weakens the protocol-first thesis.

**Candidate ADR.** ADR-0052 (generic agent sources). The current draft proposes `sources=[Source(...)]` on the decorator. The wildfire discussion may amend the shape (e.g. ergonomic helpers like `@mesh.subscribes(subject)`).

## #2. Public `mesh.publish(subject, model)` on arbitrary subjects

**Need.** Any agent or non-agent code should be able to publish a Pydantic model to an arbitrary NATS subject without reaching into `mesh._nc.publish`.

**Used by.** Every fleet that emits a domain event on a subject other than its auto-mapped agent subject. UAV, drone, medevac (status), fire-sim, stats ticker, narrator, briefer.

**Why now.** Without a public method, every fleet either:
- Uses the Publisher pattern (yields events) and accepts emission on `mesh.agent.{name}.events`, which collides with the ADR's frozen flat subjects.
- Reaches into `mesh._nc.publish(...)` and serialises by hand, scattering private-API access across the demo.

**Candidate ADR.** New ADR (or amend ADR-0034). Open shape questions: does `mesh.publish` accept a `BaseModel` and JSON-encode automatically? Does it set the OAM headers (mesh-id, etc.)? Does it accept any hashable payload or strictly Pydantic?

## #3. Queue group on raw subject subscription

**Need.** `mesh.subscribe(subject=...)` (or its declarative equivalent) must accept a `queue_group=` parameter so multiple instances of the same fleet can load-balance on a custom subject.

**Used by.** Drone fleet (`mesh.detection.thermal`, queue group `drones`), briefer (queue group `briefers` for "produce briefing" cadence).

**Why now.** Today's `mesh.subscribe(subject=...)` is broadcast-only. Auto-mapped agent invocation subjects (`mesh.agent.{name}`) get a queue group, but custom subjects do not. The drone fleet's load-balancing story does not work on broadcast.

**Candidate ADR.** Same one as #1 (the source abstraction needs a queue_group field) plus possibly a parameter on `mesh.subscribe` for direct caller use.

## #4. JetStream-backed sources with ack / nak semantics

**Need.** When a queue-group consumer wants to refuse a message ("I am not the nearest drone, give it to a sibling"), there must be a way to negative-ack so NATS redelivers to another consumer in the same queue group. Core NATS pubsub does not redeliver; this requires JetStream consumers.

**Used by.** Drone fleet ("nearest available wins"), medevac dispatch (same), any future "candidate wins" pattern.

**Why now.** Without this, the "nearest available" decision must happen at the publisher (poll candidates, pick winner, publish to one) which adds a round-trip and breaks the protocol-first cleanliness. Or fleets must accept the "any drone" assignment, which loses the realism point of the demo.

**Candidate ADR.** Likely a separate ADR layered on top of #1: the source abstraction must allow JetStream backing as an option, with `ack`/`nak` exposed to handlers. Possibly an ergonomic helper `mesh.contend(...)` for the contend-and-yield pattern.

## #5. Subject-naming clarity for invocable agents

**Need.** ADR-0054 freezes subjects like `mesh.medevac.dispatch` for request/reply, but ADR-0049 (dotted agent names) auto-maps invocable subjects to `mesh.agent.{channel}.{name}`. These conflict on paper.

**Used by.** Medevac dispatch, tasker.

**Why now.** Either the demo uses the auto-mapped subject (and the ADR-0054 subject map gets corrected) or the SDK gains a way to override the agent's invocation subject. The first is simpler; the second is more flexible.

**Candidate ADR.** Likely an ADR-0054 amendment (correct the subject map) rather than an SDK change. If the SDK does support overrides later, it should be explicit and rare; the default should remain the auto-mapped form to keep the protocol predictable.

## #6. Catalog visibility for source-driven agents

**Need.** When an agent is purely source-driven (no invocable, no streaming, no publisher) it still has a contract worth advertising: "I subscribe to X and react." The catalog should reflect this.

**Used by.** Any UAV / drone / briefer that has no `mesh.call` surface but is still an agent.

**Why now.** Today the catalog projection is built from `AgentSpec` + handler shape. Sources are runtime wiring per ADR-0052 and intentionally not part of the catalog. But "reacts to X" is part of the agent's identity for the dashboard and human readers. We need either:
- A trigger-source summary in the catalog projection (deployment-state, but useful), or
- An accepted convention where the agent's `description` covers it ("Wide-area thermal sweep, reacts to mesh.environment.thermal updates").

**Candidate ADR.** Decision deferred. The dashboard's first cut can rely on description text; if the dashboard needs structured trigger info, raise an ADR.

## #7. Process orchestration for multi-fleet demos

**Need.** Running 30-60 processes by hand on a laptop is friction. The demo needs a `bootstrap.py` (or `agentmesh wildfire up`) that starts an embedded NATS, then spawns each fleet's processes in counts configured by a TOML / YAML.

**Used by.** All fleets when running locally.

**Why now.** Without an orchestrator the developer or demo runner types `uv run python -m demos.wildfire.fleets.uav` 30 times.

**Candidate ADR.** Probably no SDK change. The demo owns the orchestrator. If the pattern recurs across demos, raise an ADR for `agentmesh demo run <name>` as a CLI feature.

## Tracking

| ID | One-line | Blocking | Candidate ADR |
|---|---|---|---|
| #1 | Declarative subject sub on decorator | UAV, drone, briefer, etc. | ADR-0052 |
| #2 | Public `mesh.publish(subject, model)` | All emitters | new / amend ADR-0034 |
| #3 | Queue group on subject subscriptions | Drone, briefer | ADR-0052 |
| #4 | JetStream ack / nak for contend-and-yield | Drone, medevac dispatch | new |
| #5 | Subject naming clarity | Medevac, tasker | ADR-0054 amendment |
| #6 | Catalog visibility for source-driven agents | Dashboard | deferred |
| #7 | Demo orchestration | Demo run | demo-local |
