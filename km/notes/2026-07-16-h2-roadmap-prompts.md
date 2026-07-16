# H2 2026 roadmap: staged execution prompts for Fable 5

Companion to the visual roadmap artifact (2026-07-16 maintainer review). Five stages, run
one per session (or a few sessions each), in order. Each prompt is self-contained and
copy-pasteable into a fresh Claude Code session on this repo.

**Design notes (from the Fable 5 prompting guide):**

- Prompts state intent and exit criteria, not step-by-step procedures. CLAUDE.md already
  carries the workflow rules (worktrees, ADR claims, changelog, no co-author); the prompts
  do not repeat them.
- Every prompt opens with "verify state first". The repo will drift between stages, and
  later stages must trust the repo over this file.
- Learnings loop: every stage reads `km/notes/roadmap-learnings.md` on entry (creates it if
  missing) and appends dated lessons on exit. That file, not this one, carries what was
  discovered during execution. If a lesson invalidates a later prompt here, the stage
  updates this file too and says so.
- Stages 0–2 are concrete (the work is known). Stages 3–4 are looser by design: they start
  with a shaping pass and may re-scope.

**Verification snippet embedded in each prompt** (per the guide, this nearly eliminates
fabricated progress claims): "Before reporting progress, audit each claim against a tool
result from this session. If something is not yet verified, say so explicitly."

---

## Stage 0 — Consolidate (target: late July)

```text
I maintain OpenAgentMesh, a solo open-source project. The H2 2026 roadmap (see
km/notes/2026-07-16-h2-roadmap-prompts.md for the full picture) starts by stopping the
rot: unmerged work is aging and no quality gate runs on push. This stage makes main the
single healthy trunk so every later stage builds on a verified baseline.

First, read km/notes/roadmap-learnings.md if it exists (create it if missing) and verify
current repo state before acting: branches, worktrees, test counts, lint status. The facts
below are from 2026-07-16 and may have drifted; trust the repo over this prompt.

Scope, in dependency order:
1. Merge feature/wildfire-demo into main (it held ~50 commits and the full wildfire test
   suite). Resolve conflicts favoring main for SDK code, the branch for demo code. Full
   suite must pass post-merge.
2. Remove the stale .claude/worktrees/agent-* worktrees and their branches (they were 15,
   all locked; verify none has unique unmerged work before deleting — if one does, flag it
   and skip it).
3. Add a CI workflow: pytest, ruff check, ty check, and sdk-ts vitest on push and PR.
4. Drive ruff findings (44) and ty diagnostics (67) to zero. Prefer real fixes;
   per-file ignores only where a demo legitimately needs looseness.
5. Fix the sdk-ts race: tests/call.test.ts "stamps X-Mesh-Request-Id" fails in full runs
   with "No agent serving 'echo.headers'" but passes alone — the sim agent's subscription
   isn't flushed before the call. Fix the helper, not the test timeout.
6. Small known gaps: add src/openagentmesh/py.typed; map pydantic ValidationError to a
   validation_error envelope code if that gap still exists (check first — the May audit
   was partially stale); add executable cookbook tests for multi-module.md and
   parallel-rag-indexing.md.
7. Release v0.3.0 via the existing /release flow (the Unreleased changelog is large).

Not in scope: refactoring _mesh.py or _context.py, new features, docs restructuring.

Exit criteria: CI green on main; wildfire demo importable/runnable from main; zero ruff/ty
findings; TS suite passes 5 consecutive full runs; v0.3.0 tagged and published.

Before reporting progress, audit each claim against a tool result from this session. If
something is not yet verified, say so explicitly. Pause only for destructive or
irreversible actions, real scope changes, or input only I can provide.

On exit: append dated lessons to km/notes/roadmap-learnings.md (merge surprises, CI
gotchas, anything that changes Stage 1's assumptions), and update the ADR index for
anything this stage moved.
```

## Stage 1 — Interop (target: August)

```text
I maintain OpenAgentMesh. Strategic context: in 2026 the agent-protocol landscape has
converged on MCP for tools and A2A for cross-org federation. OAM's position is the
internal fabric between them, and its adoption story depends on bridging: a mesh agent
should be callable from any MCP client, and a mesh contract should project to an A2A
agent card. This stage ships that interop story plus the npm release of the TS SDK.

First, read km/notes/roadmap-learnings.md and apply anything relevant. Verify current
state: re-read ADR-0002 (bidirectional MCP bridge), ADR-0003 (mcp export flag),
ADR-0006 (SLA gating), and ADR-0039 in km/adr/, and check what already exists —
to_tool_schema/to_openai_tool/to_anthropic_tool were already implemented as of July;
to_agent_card was not. The ADRs are at 'spec' status and may need amending before
implementation; if the design in an ADR now looks wrong, say so and propose the
amendment before building.

Scope:
1. to_agent_card(url=None) projection on AgentContract, matching what
   docs/welcome/oam-and-a2a.md already promises. Update that page to match reality.
2. MCP export bridge per ADR-0002/0003: agents opted in via a flag are served to MCP
   clients (stdio and/or HTTP — follow the ADR, amend it if the MCP spec moved). An
   end-to-end proof: a real MCP client (e.g. Claude Code) invoking a mesh agent.
3. npm publish for @openagentmesh/sdk: fix the license field (package.json says
   Apache-2.0, the repo is MIT), add a release workflow mirroring the PyPI one, publish
   0.1.0 (or the version main warrants after Stage 0).
4. Docs: an MCP-bridge cookbook recipe with an executable test twin, and an update to
   docs/welcome/oam-and-mcp.md reflecting the shipped bridge.

Not in scope: the A2A gateway (inbound federation) — projection only; SLA gating
(ADR-0006) unless it falls out trivially.

Exit criteria: an MCP client lists and calls a mesh agent in a demo you actually ran;
npm package installable (`npm i @openagentmesh/sdk` works from a clean directory);
docs and ADR index updated; all tests green.

Before reporting progress, audit each claim against a tool result from this session. If
something is not yet verified, say so explicitly. Pause only for destructive actions,
real scope changes, or credentials only I can provide (npm publish token likely needs me).

On exit: append lessons to km/notes/roadmap-learnings.md — especially anything about MCP
spec drift or DX friction that should reshape Stage 2's launch messaging.
```

## Stage 2 — Launch (target: September)

```text
I maintain OpenAgentMesh. It is technically solid and, after Stages 0–1, consolidated and
interoperable — but invisible: no community, no recorded demo, inconsistent docs URLs.
Distribution is the project's #1 risk. This stage is about being seen, and the deliverables
are marketing artifacts grounded in things that actually run.

First, read km/notes/roadmap-learnings.md; it may reshape the messaging (e.g. if the MCP
bridge revealed a sharper hook than the one assumed here). Verify what shipped in Stages
0–1 before writing any copy — every claim in launch content must be demoable.

Scope:
1. Record the wildfire demo (~90s). DEMO_SCRIPT.md exists from the wildfire work; it needs
   OPENROUTER_API_KEY (I'll provide the key; all LLM calls go through OpenRouter). Embed
   the recording in README and docs index.
2. Resolve the docs URL split: README points to openagentmesh.github.io, mkdocs.yml claims
   openagentmesh.dev, no CNAME exists. Ask me whether to wire the custom domain or
   standardize on github.io, then make every reference consistent.
3. Launch content: one blog-style post ("why an agent mesh, why NATS, how it sits between
   MCP and A2A") drawing on km/notes/20260423_competitors.md and the docs comparison
   pages; a Show HN draft; a tightened README top fold with the demo.
4. Optional, capacity permitting: Admin UI MVP per ADR-0056 (registry browser + invocation
   sandbox). Shape first — if it's more than ~2 sessions of work, propose deferring it to
   Stage 3 and say why.

Not in scope: paid promotion, Discord/community setup beyond a link, conference talks.

Exit criteria: demo video embedded and playing; docs URL consistent everywhere; launch
post + Show HN draft reviewed by me; README top fold sells the project in 10 seconds.

Publishing anything externally (posting the HN thread, pushing the domain live, uploading
video to a public host) requires my explicit go — prepare, then stop and show me.

Before reporting progress, audit each claim against a tool result from this session.
On exit: append lessons to km/notes/roadmap-learnings.md, including any launch feedback
worth folding into Stage 3 priorities.
```

## Stage 3 — Production trust (target: October–November)

```text
I maintain OpenAgentMesh. Post-launch, the adoption blockers shift to production
questions: how do I secure the mesh, how does it fail, how do I see inside it. This stage
hardens OAM for real deployments. It is deliberately less prescribed than earlier stages:
launch feedback and learnings may have reordered priorities, so start with a shaping pass.

First, read km/notes/roadmap-learnings.md and any post-launch issues/feedback (GitHub
issues included). Then re-read these ADRs and assess each one's current relevance and
design quality before writing code: ADR-0038 (NATS auth + credentials, spec), ADR-0016
(disconnect advisories, spec), ADR-0040 (death-notice fast failure, discussion), ADR-0048
(mesh-native observability, discussion), ADR-0055 (lifecycle gates active_when, spec).
km/notes/20260418_NATS_security_features.md and km/agentmesh-liveness-and-failure.md hold
the background research.

Produce a short prioritized plan (which ADRs, what order, what's deferred and why), get my
sign-off, then execute ADR by ADR through the standard pipeline: shape/amend the ADR →
failing test from its code sample → implement → document. Discussion-status ADRs need
shaping into spec (with a code sample) before any code.

Default priority if nothing from launch says otherwise: auth first (it gates every serious
deployment), then failure semantics (0016+0040 together — they share the liveness
machinery), then observability, then lifecycle gates.

Exit criteria: each shipped ADR at 'documented' in km/adr/index.md; a cookbook recipe
showing a secured multi-node mesh; a chaos-style test that kills an agent mid-request and
asserts callers fail fast rather than time out.

Before reporting progress, audit each claim against a tool result from this session.
Pause for my sign-off on the prioritized plan, and for anything destructive or
irreversible; otherwise proceed.

On exit: append lessons to km/notes/roadmap-learnings.md and update Stage 4's prompt in
km/notes/2026-07-16-h2-roadmap-prompts.md if the frontier bet should change shape.
```

## Stage 4 — Frontier (target: November–December)

```text
I maintain OpenAgentMesh. With the fabric consolidated, interoperable, launched, and
hardened, this stage spends time on the differentiator no framework offers: standing-team
personas — persistent lateral agents coordinating without an orchestrator. This is
research, not a feature checklist; the deliverable is a measured answer, not shipped code.

First, read km/notes/roadmap-learnings.md and km/notes/2026-05-25-persona-team-on-oam.md
(the design brainstorm: topology, risks, coordination building blocks). The note's own
recommendation stands unless learnings overturned it: prototype the coordination protocol
and shared-context blackboard FIRST, on one non-trivial task, before any persona or
self-improvement layer.

Scope:
1. Pick one non-trivial task suited to lateral disagreement (the note discusses criteria).
   Build the minimal blackboard (KV or JetStream — decide and record why) and one
   turn-taking mechanism (rotating chair or randomized round-robin with fixed turn count).
   Run the same task through a hierarchical spawn baseline and through the standing team.
   Measure: quality of result, token cost, wall time. Write the comparison up as a dated
   km/notes/ entry. Be honest if the topology loses — a negative result redirects the
   project cheaply and is a success for this stage.
2. Usage attribution (ADR-0023, spec): docs/concepts/usage.md already documents the
   design; implement it so the docs stop promising vaporware. This also gives the persona
   experiment its cost measurement for free — consider doing it first.
3. Decide ADR-0036 (orchestration/workflows): after the experiment, recommend build,
   defer, or reject, with rationale, and update the ADR's status accordingly.

LLM access: all calls go through OpenRouter (openai client, anthropic/* slugs); I have no
direct Anthropic key.

Exit criteria: comparison note written with real measured numbers from runs you executed;
usage attribution at 'documented'; ADR-0036 has a decision; roadmap-learnings.md carries
the distilled verdict on the persona wedge.

Before reporting progress, audit each claim against a tool result from this session — the
experiment's numbers especially must come from actual runs, never estimates. Pause for
scope changes and for the task-selection decision if the choice is genuinely ambiguous.

On exit: append final H2 lessons to km/notes/roadmap-learnings.md and draft a short
"H1 2027 candidates" list from what the experiment revealed.
```
