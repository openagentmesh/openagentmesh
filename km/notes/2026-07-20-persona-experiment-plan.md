# Stage 4 persona experiment — shaping note

Date: 2026-07-20 (roadmap executor, run 14)
Status: shaping. Extends km/notes/2026-05-25-persona-team-on-oam.md per the Stage 4
prompt; the brainstorm's own recommendation stands — coordination protocol and
blackboard first, on one non-trivial task, before any persona/self-improvement layer.

## What gets measured

One task, two topologies, same model and prompt budget:

- **Baseline: hierarchical spawn.** One orchestrator agent decomposes the task,
  spawns/calls worker roles sequentially or in parallel, holds all context, merges.
  This is the Claude-Code-subagents shape, expressed as mesh calls.
- **Treatment: standing team.** N peer agents (no orchestrator) coordinate through a
  shared blackboard with a bounded turn-taking mechanism, then converge on a joint
  answer.

Metrics per run (three runs per topology minimum, since LLM variance is real):
result quality (rubric scored, see below), token cost (input/output per agent and
total — **ADR-0023 usage attribution, now implemented, is the meter**: every
agent handler reports usage, the harness tails `usage_reported` events and sums),
wall time, and message count on the mesh (a `tap()` recording gives the full
transcript for free).

## Task selection (proposal, recorded for Luca)

Criteria from the brainstorm: the task must reward *lateral disagreement* —
design debate, review, planning — not mechanical decomposition.

**Proposed task:** produce a reviewed design decision on a real, open question from
this repo's own backlog: *"Should OAM adopt an eager-registration mode?"*
(the run-2 DX question: `@mesh.agent` on a connected mesh registers lazily; a
gateway sees nothing until the host flushes). It is genuinely contested (DX vs.
protocol simplicity vs. backwards compat), self-contained (the ADR corpus is the
context), has a verifiable deliverable (an ADR-style recommendation with
alternatives and risks), and needs no external tools — pure deliberation, which is
exactly the surface the topologies differ on.

Quality rubric (blind-scored per run by an LLM judge with the criteria, plus a
human pass from Luca if he wants): coverage of real trade-offs (does it find the
wire-level facts?), concreteness of the recommendation, identified risks that the
ADR corpus confirms, internal consistency. Negative result is a success per the
stage prompt.

**Needs Luca (non-blocking):** veto/replace the task if a better lateral-disagreement
task exists from his real work. Default proceeds.

## Design decisions (to build next run)

1. **Blackboard: KV bucket (`mesh-context`), not JetStream.** Rationale: the
   deliberation state is "current position per participant + shared decision log",
   a read-modify-write surface, not an append-only firehose; KV watch gives every
   peer live updates (the reactive-pipeline recipe pattern); CAS via
   `mesh.kv.cas()` already exists for contention. JetStream adds retention/consumer
   machinery the experiment doesn't need. The brainstorm's SQLite-on-ObjectStore
   escalation is explicitly out of scope for v1. Record structure (structured, not
   freeform, per the brainstorm): `debate.{task_id}.position.{persona}` (Pydantic:
   claim, rationale, revision), `debate.{task_id}.round` (chair state), settled
   decision under `debate.{task_id}.decision`.
2. **Turn-taking: randomized round-robin with fixed turn count** (the brainstorm's
   option 2). A rotating LLM chair adds a persona-shaped confound to a protocol
   experiment; fixed turns bound cost deterministically (storms and stalls are
   impossible by construction). Delphi-style rounds: independent position →
   read peers' positions from the blackboard → revise → converge (fixed R rounds,
   default 3, convergence check = positions stop changing materially).
3. **Personas: role lenses, not self-improvement.** 3–4 fixed role prompts
   (e.g. DX advocate, protocol conservative, operations/risk) — the de Bono idea
   trimmed to what the task needs. No prompt mutation in v1.
4. **LLM access:** OpenRouter via the `openai` client (`anthropic/*` slugs), per
   the stage prompt. Blocked on OPENROUTER_API_KEY (Needs Luca 11) for measured
   runs; everything up to the API call is buildable and testable with a stub model
   (deterministic canned responses exercise the machinery; they produce NO
   reportable experiment numbers).
5. **Where the code lives:** `demos/persona_team/` (demos are the established home
   for LLM-coupled code; tests stub the LLM). Not SDK surface — the experiment is
   a consumer of shipped primitives (KV, call, tap, usage). If the machinery
   proves out, an ADR shapes any SDK-worthy residue afterwards.

## Execution order (next runs)

1. Build blackboard records + round-robin harness + hierarchical baseline harness
   with a stubbed model; tests prove both topologies run the full protocol dry.
2. When OPENROUTER_API_KEY lands: real runs (3× per topology), collect usage/tap
   recordings, write the dated comparison note with real numbers.
3. Then ADR-0036 decision (build/defer/reject) from what the experiment showed.
