# Standing-team personas on OAM (brainstorm)

Date: 2026-05-25
Status: brainstorm, no commitment. Not an ADR, not scoped to a phase.

## The idea

An interface where a user creates multiple **personas** that interact as if they were
team members, each carrying the self-improving characteristics of a Hermes-class coding
agent. Explicitly **not** a direct Claude Code / Hermes / Codex alternative. The product
wedge is a different topology, not a better single agent.

## Why this is genuinely different

Claude Code / Hermes subagents are a **hierarchical fan-out/fan-in tree**: ephemeral,
no lateral edges, parent holds all context and mediates everything. Subagents never
talk to each other.

This idea is a **standing team**: persistent personas with stable identity, lateral
peer-to-peer communication, and their own evolving state. Different topology, not a
reskin.

## Why OAM is the right substrate

Maps near one-to-one onto what OAM already is:

- A persona = a long-lived `@mesh.agent` with stable identity, a contract describing
  its role, and KV-backed memory.
- Lateral interaction = `call` / `subscribe` between peers, no parent in the loop.
- Discovery = a persona finds teammates at runtime (catalog / contract).
- Multiple instances of one persona = free via queue groups.
- Self-improvement loop lives inside each persona's handler body. OAM neither helps nor
  hinders it, consistent with the no-adapters principle.

Plumbing is largely Phase 1 plus conventions.

## The hard parts (the things that kill multi-agent systems)

The transport is not the risk. These are:

1. **Shared truth.** Tree model: parent owns context. Decoupled peers: who holds
   canonical codebase state, decisions made, conversation so far? Need a blackboard
   (JetStream / KV) and each persona reconstructs relevant context from it. Get it wrong
   and agents drift, duplicate work, overwrite each other.
2. **Turn-taking without an orchestrator.** Pure pub/sub peers either storm (everyone
   replies to everything, cost explodes) or stall (everyone waits). Needs a coordination
   protocol. Decentralized-coordination preference fits the vision but is the single
   riskiest surface. Prototype this first.
3. **Cost and latency.** N persistent LLM personas deliberating >> one agent spawning a
   throwaway subagent. The team model must earn its cost on tasks where lateral
   disagreement helps (design debate, review, planning), not mechanical tasks.
4. **Self-improvement at team scale.** Single-agent self-improvement is the Hermes claim.
   A team that improves collectively (personas updating their own prompts from peer
   feedback and shared learned patterns) is the novel research wedge, and the least
   proven part.

## Recommended order of attack

Prototype the **coordination protocol** and the **shared-context blackboard** first, on a
single non-trivial task, before committing to the persona / self-improvement layer. The
product lives or dies on coordination coherence, not messaging.

## Coordination protocol: brainstorming elements

Candidate building blocks to draw from (not yet a chosen design):

- **Seven thinking hats** (de Bono-style role lenses; classic set is six). Personas adopt
  distinct cognitive stances (facts, emotion, caution, optimism, creativity, process,
  and a seventh) to force diverse framing and avoid groupthink.
- **RACI matrices.** Per task/decision, assign Responsible / Accountable / Consulted /
  Informed across personas. Gives lateral peers a shared, explicit answer to "who owns
  this and who must be looped in" without an orchestrator dictating it.
- **Delphi method.** Structured, rounds-based convergence: personas submit independent
  positions, a summarized aggregate is shared back, they revise, repeat until convergence.
  Reduces dominance/anchoring effects in deliberation.
- **Turn-taking options:**
  - Round-robin **coordination role** (a rotating "chair" persona that grants the floor), or
  - Round-robin **dispatching tool** with a randomized sequence and a fixed number of
    turns (bounds cost, prevents storms and stalls).
- **Structured project / task records.** First-class, structured task and project state
  (not freeform prose) so personas read and update shared work items deterministically.

## Coordination state storage

- Default: plain **KV records** for coordination state.
- When needs exceed what plain KV records can express (relational queries, joins,
  transactional multi-record updates), escalate coordination-related records to a
  **SQLite file on NATS Object Storage**, not just a Markdown list. Each record is
  **locked before update** so there is no concurrency issue. This gives queryable,
  transactional coordination state while staying inside the NATS substrate.

## Open questions

- What is the minimum coordination protocol that beats hierarchical spawning on a real
  task? Pick one task, measure.
- Where does the blackboard boundary sit (KV vs JetStream vs SQLite-on-ObjectStore)?
- How is the locking on the SQLite-on-Object-Storage record actually implemented (KV-based
  lease/lock per record? object revision CAS?) and what is the contention story under N
  personas?
- Does team-level self-improvement need any shared substrate, or is it purely
  per-persona prompt/state mutation?
