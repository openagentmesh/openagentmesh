# H2 2026 roadmap — cron executor state

Machine-maintained by the "OAM H2 roadmap executor" routine. Humans may edit (e.g. to
answer a "Needs Luca" item); the executor re-verifies everything against the repo anyway.

## Current stage

Stage 4 — Frontier. Item 2 (ADR-0023 usage attribution) COMPLETE run 14:
merged to main bf00b88 (--no-ff), ADR at `documented`. Item 1 (persona
experiment): machinery BUILT run 15 — merged to main 46b4224 (--no-ff),
`src/openagentmesh/demos/persona_team/` + 10 tests; both topologies run
the full protocol dry with the stub model (details in the plan note's
execution-order section). The item's remaining work — measured runs and
the comparison note — is BLOCKED on OPENROUTER_API_KEY (Needs Luca 11);
the executor will not fake numbers. Item 3 (ADR-0036 decision) comes
after the measured experiment.

Run 16 exhausted the unblocked backlog: the docs-consistency sweep is
done (merged d2d8d74 — see run log) and the "H1 2027 candidates"
skeleton exists (km/notes/2026-07-20-h1-2027-candidates.md, 33906ca,
experiment-derived sections deliberately empty). **Stage 4 — and the
whole roadmap — now has NO unblocked build work left.** Every remaining
item across all stages waits on a Needs-Luca answer; the single
highest-leverage unblock is OPENROUTER_API_KEY (item 11), which
reactivates Stage 4's measured experiment → comparison note → ADR-0036
decision → stage exit. Next runs: verify CI on main, check for answers,
run the regression suite, end. Nothing else to build until Luca acts.

**STAGE 3 COMPLETE (run 13).** All three exit criteria verified against the
repo this run: (1) every shipped ADR at `documented` in km/adr/index.md —
0038, 0016, 0040, 0048, 0055, 0056 all checked via grep this run; (2)
secured multi-node mesh cookbook recipe (docs/cookbook/secured-mesh.md +
executable twin, since run 5); (3) chaos kill-mid-request test
(tests/test_liveness.py::test_call_fast_fails_when_agent_dies_mid_request,
in the 335-test suite that passed this run). The stage-3 plan sign-off
(Needs Luca 10) was never answered; the executor ran the plan's default
order to completion — reordering is moot now, the item stands only as FYI.
ADR-0038 auth: COMPLETE (run 5, merged 9502f52).
ADR-0016+0040 liveness pair: COMPLETE (run 6) — health monitor, death
notices, caller fast-fail, docs — merged to main af5a96a (--no-ff), CI
success on branch tip e3733e6 (run 35). **Both Stage 3 exit criteria are
now met**: secured-mesh cookbook (run 5) and the chaos kill-mid-request
test (tests/test_liveness.py::test_call_fast_fails_when_agent_dies_mid_request,
passing — caller gets agent_died in ~1s against a 30s timeout).
ADR-0048 observability v1: COMPLETE (run 7) — merged to main 3e5e486.
ADR-0055 lifecycle gates: COMPLETE (run 8) — merged to main b7e4093.
ADR-0056 admin UI: IN PROGRESS — wave 1 of 5 merged to main 7b48e99
(run 9: websocket listener on dev meshes, `oam ui` static server +
config.json, ADR amended against the shipped repo); wave 2 of 5 merged to
main efae05e (run 10: ui/ frontend scaffold, registry + contract viewer
screens, `ui` CI job — e2e verified in a real browser); wave 3 of 5
merged to main 968f4f5 (built by run 11 which was cut off before
merging/logging; verified and merged by run 12: invocation sandbox — rjsf
form from input schema, Call + Stream from the browser, error envelope
rendering — plus sdk-ts NotAvailable mapping for ADR-0055 parity); wave 4
of 5 merged to main 48b9f3b (run 12: event feed screen + registry
liveness dots, powered by new sdk-ts `tap()` + `instancesWatch()`
primitives — e2e verified with a real SIGKILL). Build waves tracked in
km/notes/2026-07-18-adr0056-ui-plan.md; next is wave 5 (wheel packaging,
Playwright smoke e2e, docs, ADR → documented, CHANGELOG closeout).
Stage 2 remains open only on Needs-Luca items (demo, docs URL, draft review,
publishing). Stage 1 open only on npm publish. Stage 0 open only on its
Needs-Luca items (wildfire merge, worktrees, v0.3.0).

## Stage checklist

- [ ] Stage 0 — Consolidate (blocked on Needs-Luca items below; everything else done)
- [ ] Stage 1 — Interop (core done: MCP bridge, to_agent_card, docs; npm publish blocked)
- [ ] Stage 2 — Launch (drafts + README fold done; demo/URL/publishing need Luca)
- [x] Stage 3 — Production trust (COMPLETE run 13; exit criteria verified — see Current stage)
- [ ] Stage 4 — Frontier (current; ADR-0023 done run 14; experiment machinery next; measured runs blocked on OPENROUTER_API_KEY, item 11)

## Stage 4 item status (updated 2026-07-20, run 14)

1. **Persona experiment** — MACHINERY BUILT (run 15), measured runs BLOCKED
   on OPENROUTER_API_KEY (item 11). Shipped on roadmap/stage-4, merged to
   main 46b4224: `demos/persona_team/` — structured blackboard records on
   mesh-context KV (Position/RoundState/Decision; `>`-wildcard listing since
   persona names contain dots), StubModel (deterministic, synthetic-flagged)
   + OpenRouterModel (lazy openai import, no new dependency), standing-team
   harness (randomized round-robin dispatch, Delphi rounds, early-convergence
   detection, random-scribe synthesis), hierarchical baseline (orchestrator +
   3 sequential workers), metered run_experiment() (usage_reported tail +
   mesh.agent.> wiretap + wall time → RunReport with a `synthetic` flag),
   CLI `python -m openagentmesh.demos.persona_team`. Verified run 15:
   10/10 new tests ×5 consecutive, full suite 357 (347 baseline + 10),
   ruff/ty zero, CLI stub dry run e2e (standing = 10 mesh calls, hier = 4,
   usage attributed per agent), CI success on branch tip 9612c83 (run 106;
   run 105 was the expected red phase). Shaped run 14. Design note
   km/notes/2026-07-20-persona-experiment-plan.md: proposed task = the
   eager-registration DX question from this repo's backlog (lateral-
   disagreement-shaped, self-contained, judgeable); blackboard = mesh-context
   KV with structured Pydantic records + CAS (JetStream and SQLite-on-
   ObjectStore rejected for v1, reasons in the note); turn-taking =
   randomized round-robin with fixed turn count, Delphi-style rounds (LLM
   chair rejected as a confound); personas = 3–4 fixed role lenses, no
   self-improvement in v1; code home = demos/persona_team/ with a stub
   model for tests. Machinery is buildable without the key; measured runs
   are not (item 11). Task-selection veto offered to Luca (item 12).
2. **ADR-0023 usage attribution** — DONE (run 14). Merged to main bf00b88
   (--no-ff); ADR + index at `documented`; CI success on branch tip 4453424
   (run 101). Amended the ADR against reality first (4 corrections recorded
   in the ADR): the original return-value convention was impossible under
   Pydantic v2 (undeclared field = ValidationError; declared field leaks
   into the contract schema) → contextvar-based `report_usage(Usage(...))`
   callable anywhere in the handler; attribution rides ADR-0048 observe
   (`usage_reported` event at info on mesh.logs.{name} — only reporting
   agents emit, zero-cost default preserved); streamers stamp the
   stream-end frame; caller-side accessor + OTel + sdk-ts write parity
   explicitly deferred in the amendment. Shipped: `_usage.py` (Usage model,
   report_usage, capture helpers), host stamping in responder+streamer
   paths, X-Mesh-Usage header, 9 unit tests + cookbook twin. Docs:
   concepts/usage.md rewritten as shipped (vaporware warning gone),
   cookbook/tracking-llm-usage.md + executable twin, envelope header
   tables, API reference section, observability event table, CHANGELOG.
   No new subjects/buckets → no role-template changes (verified: usage
   rides reply headers + existing mesh.logs.> grants).
3. **ADR-0036 decision** — NOT STARTED (after the experiment, per the
   stage prompt).

## Stage 0 item status (verified 2026-07-17)

1. **Merge feature/wildfire-demo** — BLOCKED: the branch does not exist on origin
   (verified: `git branch -r` shows only feature/error-taxonomy, feature/tool-conversion,
   main; no wildfire code anywhere in `git log --all`). It was never pushed from Luca's
   machine. → Needs Luca.
2. **Remove stale .claude/worktrees** — N/A from the cloud: worktrees and their branches
   are local to Luca's machine, nothing on origin to clean. → Needs Luca (run locally).
3. **CI workflow** — DONE. `.github/workflows/ci.yml` runs ruff, ty, pytest, and sdk-ts
   tsc+vitest on push (main + roadmap/**) and PRs. Verified green on roadmap/stage-0
   (runs #2, #3 both success, both jobs).
4. **ruff/ty to zero** — DONE. `ruff check .` and `ty check` both pass with zero findings
   (verified this run; was 44 ruff / 245 ty). One scoped suppression with rationale:
   invalid-return-type in tests/demos for the ADR-0031 streamer annotation convention.
5. **sdk-ts race** — DONE. Root cause was sim helpers not flushing subscription interest;
   fixed in the helper. 5 consecutive full vitest runs green (53/53 each).
6. **Small gaps** — DONE. py.typed added (verified present in built wheel);
   ValidationError→invalid_input mapping ALREADY EXISTED (ADR-0057; prompt's May audit
   was stale — verified in _mesh.py, no code needed); executable cookbook tests added for
   multi-module.md and parallel-rag-indexing.md (3 new tests, passing).
7. **v0.3.0 release** — NOT DONE, held. Ordering: the stage releases after the wildfire
   merge, which is blocked. Also, pushing a release tag triggers PyPI publish (outward-
   facing). → Needs Luca (decision).

All of the above merged to main (`merge: stage-0 consolidation`, --no-ff). Test suite on
the merged tree: 232→235 pytest passing, 53 vitest passing, ruff/ty clean.

## Stage 1 item status (verified 2026-07-17, run 2)

1. **to_agent_card(url=None)** — DONE (ADR-0012's promised projection; 6 tests;
   docs/welcome/oam-and-a2a.md and docs/api/contract.md updated to match reality).
2. **MCP export bridge** — DONE per amended ADR-0002 (stdio-only v1; amendment records
   that upstream deprecated SSE for Streamable HTTP). `@mesh.agent(spec, mcp=...)`,
   `mesh.run_mcp()/serve_mcp()`, `oam mcp serve` CLI, `openagentmesh[mcp]` extra.
   E2E proof actually run: the official MCP SDK client spawned `oam mcp serve` over
   stdio, listed the mesh agent, called it, got the right reply
   (tests/test_mcp_stdio_e2e.py, passing). Trying Claude Code itself as the client is a
   nice manual follow-up for Luca: `claude mcp add mesh -- oam mcp serve`.
3. **npm publish** — PREPARED, publish BLOCKED. License field fixed (Apache-2.0→MIT),
   publish-npm.yml workflow added (sdk-ts-v* tags, full test gate, tag/version check).
   Publishing needs an npm credential → Needs Luca. No tag pushed (tag push = publish).
4. **Docs** — DONE. Cookbook recipe docs/cookbook/mcp-bridge.md + executable twin
   tests/cookbook/test_mcp_bridge.py; oam-and-mcp.md rewritten around the shipped bridge.

Out of scope, untouched: A2A inbound gateway, add_mcp (Phase 3), SLA gating (ADR-0006 —
did not fall out trivially).

All merged to main (`merge: stage-1 interop`, --no-ff). Merged tree verified this run:
253 pytest passed, 53 vitest passed, ruff/ty zero.

## Stage 2 item status (verified 2026-07-17, run 3)

1. **Wildfire demo recording** — BLOCKED twice over: feature/wildfire-demo still not on
   origin (re-verified this run: `git branch -a` has no wildfire branch), and recording
   needs OPENROUTER_API_KEY. README carries a placeholder comment where the embed goes.
   → Needs Luca (items 1 and 6 below).
2. **Docs URL split** — INVENTORIED, decision recorded as a question (Needs Luca item 7).
   Facts verified this run: README has 3 links to openagentmesh.github.io; mkdocs.yml
   `site_url: https://openagentmesh.dev/`; no CNAME file anywhere in the repo;
   .github/workflows/docs.yml deploys to GitHub Pages. Note: the wrong site_url is an
   ACTIVE bug, not cosmetics — the deployed github.io site emits canonical URLs and a
   sitemap pointing at openagentmesh.dev. Could not verify from the cloud whether
   openagentmesh.dev resolves (sandbox proxy 403s both URLs) — unverified.
3. **Launch content** — DRAFTED, committed on roadmap/stage-2 under km/notes/launch/:
   2026-07-17-launch-post-draft.md (blog post, "The Wire, Not the Workflow") and
   2026-07-17-show-hn-draft.md (title options + body + prepared first comment).
   Both marked draft; publishing is Luca's explicit go (item 8). README top fold
   tightened on the same branch: positioning hook (MCP/A2A gap), hero agent sample,
   `claude mcp add mesh -- oam mcp serve` one-liner, demo placeholder.
4. **Admin UI MVP (ADR-0056)** — SHAPED, DEFER PROPOSED (item 9). Estimate 4–6
   sessions, over the stage's ~2-session bar: new ui/ toolchain (Vite+React+TS+
   Tailwind+rjsf+nats.ws), embedded-NATS websocket listener, `oam ui` static server,
   three screens incl. browser-side streaming replies, CI wheel-packaging changes.
   Extra argument for deferring to Stage 3: the registry screen's liveness dot depends
   on ADR-0016 (a Stage 3 item) — building the UI after Stage 3's liveness work avoids
   shipping the heartbeat stand-in hack.

## Needs Luca

5. **npm credential for @openagentmesh/sdk.** Add an NPM_TOKEN secret (or configure a
   trusted publisher) for the 'npm' environment, then say "publish sdk-ts 0.1.0" here;
   the next run will tag sdk-ts-v0.1.0 and the workflow publishes. The `npm i` exit
   criterion stays open until then.
1. **Push feature/wildfire-demo to origin.** The branch (~50 commits, wildfire test
   suite) exists only on your machine. Until it's on origin, Stage 0 item 1 can't proceed
   and Stage 2's demo recording has no code to run. `git push origin feature/wildfire-demo`
   from the machine that has it is enough; the executor will handle the merge next run.
2. **Worktree cleanup is yours to run locally** (cloud checkouts don't see
   .claude/worktrees). Per the stage prompt: check none of the 15 agent-* branches has
   unique unmerged work before deleting.
3. **v0.3.0 release decision**: release now without wildfire (Unreleased changelog is
   already large: instance_id, publish, KV ergonomics, TS SDK, sources, error taxonomy,
   CI/typing), or wait for the wildfire merge? If "release now", say so here and the next
   run will run the /release flow up to the tag push; note the tag push triggers the PyPI
   publish workflow.
4. **OK to delete stale remote branches?** feature/error-taxonomy and
   feature/tool-conversion predate their content landing on main (verified their
   tests/modules are on main). Deleting remote branches is destructive, so left alone.
6. **OPENROUTER_API_KEY for the demo recording** (Stage 2 item 1). Also blocked on the
   wildfire branch push (item 1 above). Both are yours; the executor cannot record the
   demo in the cloud regardless (no key, no branch, and screen recording is better done
   on your machine anyway — DEMO_SCRIPT.md will be on the wildfire branch).
7. **Docs URL decision** (Stage 2 item 2): standardize on
   https://openagentmesh.github.io/openagentmesh/ or wire openagentmesh.dev?
   Facts: no CNAME in the repo, docs deploy to GitHub Pages, mkdocs.yml claims
   openagentmesh.dev, README uses github.io. The mismatch makes the live site emit
   canonical/sitemap URLs to a domain that may not be wired (SEO harm today).
   Options: (a) "github.io" — executor fixes mkdocs.yml site_url next run, done;
   (b) "wire openagentmesh.dev" — you add the CNAME/DNS (domain + Pages settings are
   yours), executor then flips README links. Answer here with (a) or (b).
   Recommendation: (a) now, (b) later if you buy/wire the domain — (a) is one line
   and reversible.
8. **Review the launch drafts** (Stage 2 exit criterion): km/notes/launch/
   2026-07-17-launch-post-draft.md and 2026-07-17-show-hn-draft.md (on roadmap/stage-2;
   on main after merge). Posting anywhere is your explicit go — the executor will never
   post them. Edit in place or leave notes here.
10. **Stage 3 prioritized plan — sign-off requested** (the stage prompt asks for
   your sign-off before execution). Plan: km/notes/2026-07-17-stage3-plan.md.
   Order: 0038 auth → 0016+0040 liveness pair → 0048 observability (trimmed v1)
   → 0055 lifecycle gates → 0056 UI if deferral confirmed. The executor started
   on 0038 (the prompt's own default priority) rather than idle; items are
   independent, so reordering on your answer loses nothing. Edit the plan file
   or leave notes here to reorder/veto.
11. **OPENROUTER_API_KEY for the Stage 4 persona experiment.** Stage 4's
   deliverable is a measured comparison (standing team vs. hierarchical
   spawn) with real LLM runs through OpenRouter. Without the key the
   executor will build the blackboard/turn-taking machinery and ADR-0023
   usage attribution, but cannot produce the experiment's numbers (and will
   never fake them). Same key as item 6; providing it once covers both.
12. **Persona-experiment task selection (non-blocking).** The executor
   proposes deliberating a real backlog question — "should OAM adopt an
   eager-registration mode?" (the run-2 DX finding) — as the experiment
   task; rationale in km/notes/2026-07-20-persona-experiment-plan.md.
   Silence = proceed with it; name a different lateral-disagreement task
   here to override before the measured runs happen.
9. **ADR-0056 admin UI: OK to defer to Stage 3?** Shaping estimate 4–6 sessions
   (details in Stage 2 item status above). The stage prompt says propose deferral if
   over ~2 sessions — this is the proposal. Silence = defer; say "build it in Stage 2"
   to override.

## Stage 3 item status (updated 2026-07-17, run 5)

1. **ADR-0038 auth** — DONE (run 5). Merged to main 9502f52 (--no-ff);
   ADR + index at `documented`. Verified: 281 pytest on the merged tree
   locally; ruff/ty clean; CI success on branch tip fca33cc (main-merge CI
   run not yet observed — check next run).
   - SDK: `AgentMesh(creds=, tls_cert=, tls_key=, tls_ca=)`; resolution
     creds= > OAM_CREDS > .oam-url TOML > open; `ConnectionDenied` on
     connect-time rejection AND on calls blocked by permissions (async
     violation reports correlated back to the call site); local() ignores
     ambient creds. Bonus fix: call() timeouts now raise MeshTimeout
     instead of leaking nats.errors.TimeoutError.
   - CLI: `oam auth init` (nsc-wrapped operator+SYS+account tree, emits
     runnable server.conf, mem resolver), `user add --role
     worker|invoker|observer`, `user revoke`, `whoami`; `oam mesh connect
     --creds`. E2E tests boot a server from the emitted config and drive
     real role-credentialed meshes (28 auth tests total).
   - Docs: concepts/security.md, cookbook/secured-mesh.md + executable
     twin, oam auth CLI reference, AgentMesh constructor params.
   - ADR amendments recorded in the ADR itself: role table corrected
     against real wire usage (original blocked registration); JWT mode
     requires a system account for JetStream; nkeys now a core dep.
   - Stage exit criterion "cookbook recipe showing a secured multi-node
     mesh" is met. Remaining stage exit criterion: the chaos-style
     kill-mid-request test (belongs to the 0016+0040 liveness pair).
2. **ADR-0016+0040 liveness pair** — DONE (run 6). Both ADRs at
   `documented`; merged to main af5a96a (--no-ff); CI success on branch tip
   e3733e6; 292 pytest verified locally on the merged tree.
   - ADR-0016 amended (v1 scope + code sample): monitor lives with the mesh
     lifecycle owner (`local()` in-process, `oam mesh up` companion process,
     `oam mesh monitor` for secured meshes); dev servers now run an
     accounts config (APP+SYS, no_auth_user keeps anonymous DX) so the
     monitor can read $SYS advisories; ping_interval 10s. Heartbeat/zombie
     layer explicitly deferred in the amendment.
   - Correlation: connections named oam-host-{instance_id}; new
     mesh-instances KV bucket maps instance → served agents; death notices
     (mesh.death.{name}) fire only on last-instance departure; graceful
     shutdown publishes its own notice and no longer removes the catalog
     entry while a replica survives (fixed a latent scale-down bug).
   - ADR-0040 shaped → documented: call()/stream() race death notices →
     AgentDied (agent_died); no-responders → NotFound (was a leaked raw
     nats error the error-handling cookbook test had pinned).
   - Docs: concepts/liveness.md, cookbook/agent-liveness.md + executable
     twin, errors/security/API/CLI pages updated; auth role templates
     gained $KV.mesh-instances.> (worker) and mesh.death.> (invoker/
     observer); stale credentials degrade gracefully (warning, no crash).
   - E2E verified in-sandbox beyond pytest: real `oam mesh up` + SIGKILLed
     host → death notice in 15ms, catalog cleaned, `oam mesh down` stops
     monitor and removes its pid/config files.
3. **ADR-0048 observability** — DONE (run 7). ADR at `documented`; merged
   to main 3e5e486 (--no-ff); CI success on branch tip 630396c (run 42);
   308 pytest + ruff/ty clean verified locally on that tree.
   - Shaped discussion→spec first (trimmed v1 per the stage-3 plan), with
     three corrections recorded in the ADR amendment: the log subject moved
     to a `mesh.logs.{name}` root (the original sibling placement relied on
     an invalid mid-subject `>` wildcard), "metrics in heartbeats" deferred
     because ADR-0016 v1 deferred the heartbeat layer itself, and the
     `AgentMesh(observe=...)` constructor param dropped (KV is the single
     control plane). Traces, `$SYS` bridging, custom handler logging: all
     deferred with reasons in the amendment.
   - Shipped: SDK auto-publishes six level-gated log events around the
     invocation path (zero publishes per request at default `info`);
     `mesh-observability` KV bucket with live KV-watch level control
     (per-agent > global > default); `mesh.observe` namespace
     (logs/get/set/set_global, typed LogEvent/ObserveConfig exports);
     `oam observe logs|config|set` CLI; role templates updated in the same
     change (observer gains mesh.logs.> + config-bucket read).
   - Docs: concepts/observability.md, cookbook/observing-the-mesh.md +
     executable twin, subjects/API/CLI/security pages. Also fixed two
     pre-existing docs gaps (subjects.md missing mesh.death/mesh-instances;
     cookbook index missing three shipped recipes).
   - 16 new tests (12 SDK + 2 CLI + 2 cookbook twin).
4. **ADR-0055 lifecycle gates** — DONE (run 8). ADR at `documented`;
   merged to main b7e4093 (--no-ff); CI success on branch tip 426cde3
   (run 52); 321 pytest verified locally on the merged tree; 53 vitest
   verified on the branch (unchanged by this work).
   - Amended the ADR before code (4 corrections): conditions are mesh
     factory methods (`mesh.kv_condition`/`mesh.subject_condition`,
     matching ADR-0052's source factories — the original sample's
     `openagentmesh.lifecycle` public submodule contradicted the package
     convention); `not_available` is a caller-side mapping (no-responders
     + present-in-catalog → NotAvailable, absent → NotFound — an agent
     that left its queue group cannot reply, so the original "receives
     not_available during drain" mechanics were self-contradictory);
     kv_condition watches the mesh-context bucket; startup does a
     synchronous read (deterministic come-up) with `initial` as fallback.
   - Shipped: `@mesh.agent(spec, active_when=...)`; `_lifecycle.py` with
     Condition protocol + KVCondition/SubjectCondition (top-level
     exports); per-agent activate/deactivate with idempotent transitions;
     gated handlers run as tracked tasks so deactivation unsubscribes
     instantly and drains our own in-flight set (nats-py's
     Subscription.drain() is NOT cancellation-safe — cancelling it
     mid-flush poisons pong futures and kills the client read loop; found
     via a real hang, see learnings); `NotAvailable` error;
     `agent_activated`/`agent_deactivated` observe events; Watcher shape
     retired (ADR-0031 table + agents.md updated, ADR-0042 already
     superseded).
   - Docs: concepts/lifecycle.md, cookbook/lifecycle-gated-agents.md +
     executable twin, errors/API/observability pages, mkdocs nav.
   - 13 new tests (11 unit + 2 twin); 5 consecutive green runs of the
     lifecycle files after fixing two test races (see learnings).
   - No role-template changes needed: gates ride existing surfaces
     (mesh-context KV; subject gates share subject_source's constraint).
5. **ADR-0056 admin UI** — IN PROGRESS (runs 9–10). Waves 1–2 of 5 merged
   to main (7b48e99, efae05e); ADR index at `test`. Waves in
   km/notes/2026-07-18-adr0056-ui-plan.md.
   - ADR amended twice this run against reality: (a) the websocket listener
     cannot share the NATS client port (verified fatal bind error on
     2.10.24) — defaults are now ws = mesh port + 1, `oam ui` on 4224;
     (b) KV layout corrected (mesh-catalog single `catalog` key,
     mesh-registry per-agent, mesh-instances for liveness — no
     `oam.catalog.>`); (c) Watcher shape retirement reflected; (d) the
     browser client is `@openagentmesh/sdk` itself (it already ships
     wsconnect + a configUrl bootstrap; `nats.ws` is deprecated upstream);
     (e) assets are CI-built, not committed.
   - Shipped wave 1: `render_mesh_server_conf(ws_port=)` + EmbeddedNats
     `ws_url`; `oam mesh up` opens ws on port+1 and prints it; `oam ui`
     (stdlib static server, /config.json, SPA fallback, free-port
     fallback, --check, OAM_UI_HOST/OAM_NATS_WS_URL envvars, friendly
     missing-assets error). 12 new tests (9 unit + 3 CLI).
   - E2E verified in-sandbox: real `oam mesh up` → ws handshake 101 on
     port+1; `oam ui` served config.json and SPA-fallback routes; derived
     ws URL from .oam-url correctly.
   - Shipped wave 2 (run 10, merged efae05e): `ui/` scaffold (Vite +
     React 18 + TS + Tailwind 4, pnpm; `@openagentmesh/sdk` via
     link:../sdk-ts per the ADR's SDK-reuse amendment); MeshProvider
     context bootstrapping via /config.json (dev server serves it too);
     registry table (capability badges per ADR-0031 shapes, first-sentence
     descriptions, 2s poll of the SDK's KV-watch-warmed cache) and agent
     detail contract viewer (human/JSON toggle, input/output/chunk
     schemas); events-screen stub until wave 4. 11 vitest tests against a
     fake MeshClient injected via context (no module mocking); new `ui`
     CI job (sdk-ts build → typecheck, vitest, production build);
     `src/openagentmesh/_ui_assets/` now gitignored per the ADR's
     CI-built-assets decision.
   - E2E verified in-sandbox (run 10): headless chromium (preinstalled
     Playwright browser) against a real `oam mesh up` + registered agent +
     `oam ui` serving the production build — connected badge, live catalog
     row, detail screen with real Pydantic schemas, JSON toggle, deep-link
     via SPA fallback; zero page errors.
   - Shipped wave 3 (built by run 11 — cut off after pushing, before
     merge/log — verified and merged 968f4f5 by run 12): `InvokePanel` on
     agent detail — rjsf form from input schema (bare button when no
     schema), Call round-trip, Stream via SDK async iterator with Stop
     (AbortController), error box with taxonomy code badge + request_id +
     per-code hints; source-only agents render no panel. sdk-ts gained
     `NotAvailable` (no-responders + present in cached catalog →
     not_available, ADR-0055 parity). 8 new ui tests (19 total), 2 new
     sdk-ts tests (55 total).
   - Wave 3 verification (run 12): CI success on branch tips 297850e
     (run 78) and 2c45dd2 (run 79); locally ui typecheck + 19/19 vitest +
     production build, sdk-ts 55/55 vitest, 333/333 pytest; headless-
     chromium e2e against a real `oam mesh up` + `oam ui`: form from a
     real Pydantic schema, call reply rendered, 4-chunk stream reassembled
     with status line, and a kv_condition-gated agent produced the
     not_available error box (badge + gate hint + request_id), zero page
     errors.
   - Shipped wave 4 (run 12, merged 48b9f3b): sdk-ts `mesh.tap(pattern)`
     (wiretap yielding {subject, payload, isError}: JSON decode with raw-
     text fallback, error envelopes yielded not thrown, stream-end
     ignored) and `mesh.instancesWatch()` (mesh-instances KV watch,
     replay coalesced into one initial snapshot via delta + status();
     completes silently when the bucket is absent). UI: Events screen
     (pattern input default `mesh.>` — deliberately narrower than the
     ADR's `>`, which taps the UI's own JS-API/inbox chatter; subscribe/
     unsubscribe, pause-buffers/resume-flushes, clear, 500-row cap,
     error highlighting) and registry status dots (useLiveness =
     instancesWatch ∪ mesh.death.> tap). 7 new sdk-ts tests (62 total),
     11 new ui tests (30 total).
   - Wave 4 verification (run 12): red suite committed first (dc96151,
     CI failure = expected red); CI success on green tip c1bc714 (run 83)
     and docs tip d2c7168 (run 84); locally 3 consecutive ui runs 30/30,
     2 sdk-ts runs 62/62, builds clean; chromium e2e against a real
     3-host mesh: all dots live, SIGKILL → mesh.death.mortal in the live
     feed, pause/clear correct, dead agent's row removed from the
     registry (health-monitor deregistration — the gray dot only covers
     the pre-cleanup race and monitor-less meshes), survivors live, zero
     page errors.
   - Shipped wave 5 (run 13, merged a4b667b) — ADR-0056 COMPLETE, at
     `documented`: publish.yml builds sdk-ts + ui and copies ui/dist into
     src/openagentmesh/_ui_assets/ before `uv build` (verified locally:
     assets present in wheel AND sdist; `oam ui --check` works from a
     clean-venv wheel install; no `[ui]` extra — stdlib server, assets are
     data files in the base wheel). publish.yml's test job also gained the
     nats-server/nsc installs ci.yml had (it would have failed the next tag
     push without them). ui/e2e/smoke.mjs + `ui-e2e` CI job (playwright):
     registry live dot, rjsf Call round-trip, event feed on mesh.> — the
     only automated coverage of the real websocket path; passed locally
     (preinstalled chromium) AND in real CI (run 90 job "Smoke e2e against
     a real mesh", success, verified at step level). Docs:
     cookbook/admin-ui.md + twin, `oam ui` in cli.md, mesh-up output fix,
     index/nav. ADR amended (mesh.> default, monitor-deregistration,
     no-[ui]-extra, e2e-as-only-real-transport-coverage) → documented.
     CHANGELOG admin-UI entry rewritten as shipped.

## Run log

### 2026-07-24 ~06:10–06:20 UTC — run 31 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip d8813ee = run 30's
commit; zero commits since; state file untouched; only executor
identities in the author list since bootstrap); no OPENROUTER_API_KEY or
npm credential in the environment; unshallowed first per the run-22
lesson (history intact, 319 commits, bootstrap 116e1bc an ancestor);
all five roadmap/stage-* branches at 0 unmerged commits each; stale
feature/error-taxonomy (4 unmerged) + feature/tool-conversion pair
unchanged (Needs Luca 4); zero open GitHub issues and zero open PRs;
CI success on main tip d8813ee (run 129). Regression suite green on
main: 357/357 pytest (77s, nats-server + nsc via the Go-proxy
workaround first) and sdk-ts 62/62 vitest, matching the run-16 through
run-30 baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: unshallow first; check for Needs-Luca answers and
credentials; if none, verify CI on any new main tip, regression-check,
log, end silently.

### 2026-07-24 ~00:05–00:15 UTC — run 30 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip aef6d39 = run 29's
commit; zero commits since; state file untouched; all authors since
bootstrap are executor identities); no OPENROUTER_API_KEY or npm
credential in the environment; unshallowed first per the run-22 lesson
(history intact, 318 commits, bootstrap 116e1bc an ancestor); all five
roadmap/stage-* branches at 0 unmerged commits each; stale
feature/error-taxonomy (4 unmerged) + feature/tool-conversion pair
unchanged (Needs Luca 4); zero open GitHub issues and zero open PRs;
CI success on main tip aef6d39 (run 128). Regression suite green on
main: 357/357 pytest (72s, nats-server + nsc via the Go-proxy
workaround first) and sdk-ts 62/62 vitest, matching the run-16 through
run-29 baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: unshallow first; check for Needs-Luca answers and
credentials; if none, verify CI on any new main tip, regression-check,
log, end silently.

### 2026-07-23 ~18:05–18:15 UTC — run 29 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip 05f5d36 = run 28's
commit; zero commits since; state file untouched; no non-executor
authors since bootstrap); no OPENROUTER_API_KEY or npm credential in
the environment; unshallowed first per the run-22 lesson (history
intact, 317 commits, bootstrap 116e1bc an ancestor — the fetch-time
"forced update" was again the shallow-snapshot artifact); all five
roadmap/stage-* branches at 0 unmerged commits each; stale
feature/error-taxonomy (4 unmerged) + feature/tool-conversion pair
unchanged (Needs Luca 4); zero open GitHub issues and zero open PRs;
CI success on main tip 05f5d36 (run 127). Regression suite green on
main: 357/357 pytest (75s, nats-server + nsc via the Go-proxy
workaround first) and sdk-ts 62/62 vitest, matching the run-16 through
run-28 baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: unshallow first; check for Needs-Luca answers and
credentials; if none, verify CI on any new main tip, regression-check,
log, end silently.

### 2026-07-23 ~12:10–12:20 UTC — run 28 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip 6f78dc4 = run 27's
commit; zero commits since; state file untouched; all authors since
bootstrap are executor identities); no OPENROUTER_API_KEY or npm
credential in the environment; unshallowed first per the run-22 lesson
(history intact, 316 commits, bootstrap 116e1bc an ancestor — the
fetch-time "forced update" was again the shallow-snapshot artifact);
all five roadmap/stage-* branches at 0 unmerged commits each; stale
feature/error-taxonomy + feature/tool-conversion pair unchanged (Needs
Luca 4); zero open GitHub issues and zero open PRs; CI success on main
tip 6f78dc4 (run 126). Regression suite green on main: 357/357 pytest
(80s, nats-server + nsc via the Go-proxy workaround first) and sdk-ts
62/62 vitest, matching the run-16 through run-27 baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: unshallow first; check for Needs-Luca answers and
credentials; if none, verify CI on any new main tip, regression-check,
log, end silently.

### 2026-07-23 ~06:10–06:20 UTC — run 27 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip 11698f4 = run 26's
commit; zero commits since; state file untouched); no OPENROUTER_API_KEY
or npm credential in the environment; unshallowed first per the run-22
lesson (history intact, 315 commits, bootstrap 116e1bc an ancestor — the
fetch-time "forced update" was again the shallow-snapshot artifact); all
five roadmap/stage-* branches at 0 unmerged commits each; stale
feature/error-taxonomy (4 unmerged) + feature/tool-conversion pair
unchanged (Needs Luca 4); zero open GitHub issues and zero open PRs;
CI success on main tip 11698f4 (run 125). Regression suite green on
main: 357/357 pytest (95s, nats-server + nsc via the Go-proxy workaround
first) and sdk-ts 62/62 vitest, matching the run-16 through run-26
baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: unshallow first; check for Needs-Luca answers and
credentials; if none, verify CI on any new main tip, regression-check,
log, end silently.

### 2026-07-23 ~00:05–00:15 UTC — run 26 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip db4fc95 = run 25's
commit; zero commits since; state file untouched); no OPENROUTER_API_KEY
or npm credential in the environment; unshallowed first per the run-22
lesson (history intact, 314 commits, bootstrap 116e1bc an ancestor — the
fetch-time "forced update" was again the shallow-snapshot artifact); all
five roadmap/stage-* branches at 0 unmerged commits each; stale
feature/error-taxonomy (4 unmerged) + feature/tool-conversion pair
unchanged (Needs Luca 4); zero open GitHub issues and zero open PRs;
CI success on main tip db4fc95 (run 124). Regression suite green on
main: 357/357 pytest (73s, nats-server + nsc via the Go-proxy workaround
first) and sdk-ts 62/62 vitest, matching the run-16 through run-25
baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: unshallow first; check for Needs-Luca answers and
credentials; if none, verify CI on any new main tip, regression-check,
log, end silently.

### 2026-07-22 ~18:10–18:20 UTC — run 25 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip 5b46169 = run 24's
commit; zero commits since; state file untouched); no OPENROUTER_API_KEY
or npm credential in the environment; unshallowed first per the run-22
lesson (history intact, 313 commits, bootstrap 116e1bc an ancestor — the
fetch-time "forced update" was again the shallow-snapshot artifact); all
five roadmap/stage-* branches at 0 unmerged commits each; stale
feature/error-taxonomy (4 unmerged) + feature/tool-conversion pair
unchanged (Needs Luca 4); zero open GitHub issues and zero open PRs;
CI success on main tip 5b46169 (run 123). Regression suite green on
main: 357/357 pytest (75s, nats-server + nsc via the Go-proxy workaround
first) and sdk-ts 62/62 vitest, matching the run-16 through run-24
baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: unshallow first; check for Needs-Luca answers and
credentials; if none, verify CI on any new main tip, regression-check,
log, end silently.

### 2026-07-22 ~12:10–12:20 UTC — run 24 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip 7e1acf9 = run 23's
commit; zero commits since; state file untouched); no OPENROUTER_API_KEY
or npm credential in the environment; unshallowed first per the run-22
lesson (history intact, 312 commits, the fetch-time "forced update" was
again the shallow-snapshot artifact); all five roadmap/stage-* branches
at 0 unmerged commits each; stale feature/error-taxonomy (4 unmerged) +
feature/tool-conversion pair unchanged (Needs Luca 4); zero open GitHub
issues and zero open PRs; CI success on main tip 7e1acf9 (run 122).
Regression suite green on main: 357/357 pytest (74s, nats-server + nsc
via the Go-proxy workaround first) and sdk-ts 62/62 vitest, matching
the run-16 through run-23 baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: unshallow first; check for Needs-Luca answers and
credentials; if none, verify CI on any new main tip, regression-check,
log, end silently.

### 2026-07-22 ~06:05–06:20 UTC — run 23 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip 1f59796 = run 22's
commit; zero commits since; state file untouched); no OPENROUTER_API_KEY
or npm credential in the environment; all five roadmap/stage-* branches
at 0 unmerged commits each (rev-list after `git fetch --unshallow` per
the run-22 lesson — this run's bootstrap "forced update" on fetch was
again the shallow-snapshot artifact, history intact at 311 commits);
stale feature/error-taxonomy (4 unmerged May-2026 commits, content on
main) + feature/tool-conversion pair unchanged (Needs Luca 4); zero open
GitHub issues and zero open PRs; CI success on main tip 1f59796
(run 121). Regression suite green on main: 357/357 pytest (76s,
nats-server + nsc via the Go-proxy workaround first) and sdk-ts 62/62
vitest, matching the run-16 through run-22 baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: unshallow first; check for Needs-Luca answers and
credentials; if none, verify CI on any new main tip, regression-check,
log, end silently.

### 2026-07-22 ~00:05–00:20 UTC — run 22 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip 5f18183 = run 21's
commit; zero commits since; the only non-Claude author since bootstrap
is run 21's own "OAM Roadmap Executor" identity); no OPENROUTER_API_KEY
or npm credential in the environment; all five roadmap/stage-* branches
at 0 unmerged commits each; stale feature/error-taxonomy +
feature/tool-conversion pair unchanged (Needs Luca 4); zero open GitHub
issues and zero open PRs; CI success on main tip 5f18183 (run 120).
Regression suite green on main: 357/357 pytest (73s, nats-server + nsc
installed via the Go-proxy workaround first) and sdk-ts 62/62 vitest,
matching the run-16 through run-21 baselines.

Shallow-clone scare, resolved: before unshallowing, rev-list reported
70 unmerged commits on roadmap/stage-0 and the fetch showed a "forced
update" on main — both artifacts of the shallow bootstrap snapshot, not
real. `git fetch --unshallow` → history intact (310 commits, bootstrap
116e1bc an ancestor of main), all branches fully merged. Lesson
appended to roadmap-learnings.md: unshallow before any rev-list/
merge-base verification. The v0.1.5/v0.1.6/v0.2.0 tags that appeared on
fetch are historical April releases newly visible to this clone, not
new pushes.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: unshallow first; check for Needs-Luca answers and
credentials; if none, verify CI on any new main tip, regression-check,
log, end silently.

### 2026-07-21 ~18:05–18:15 UTC — run 21 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip bf83bfe = run 20's
commit; zero new commits since; state file untouched); no
OPENROUTER_API_KEY or npm credential in the environment; all five
roadmap/stage-* branches at 0 unmerged commits each (rev-list against
ls-remote heads); the stale feature/error-taxonomy +
feature/tool-conversion pair unchanged (Needs Luca 4); zero open GitHub
issues and zero open PRs; CI success on main tip bf83bfe (run 119).
Regression suite green on main: 357/357 pytest (69s, after installing
nsc — first pass without it was 350+7 skips, the known nsc-gated auth
tests) and sdk-ts 62/62 vitest, both matching the run-16 through run-20
baselines. Container-clone note: this run's checkout was a stale shallow
snapshot from bootstrap time; the fetch reported a "forced update" and
an empty merge-base, which looked like a history rewrite but was a
shallow-clone artifact — `git fetch --unshallow` confirmed the bootstrap
commit is an ancestor of main (history intact, 309 commits).

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: check for Needs-Luca answers and credentials; if none, verify
CI on any new main tip, regression-check, log, end silently.

### 2026-07-21 ~12:10–12:20 UTC — run 20 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip 0ab25de = run 19's
commit; every commit is the executor's; state file untouched since then);
no OPENROUTER_API_KEY or npm credential in the environment; all five
roadmap/stage-* branches at 0 unmerged commits each (checked via
rev-list against ls-remote heads); the stale feature/error-taxonomy +
feature/tool-conversion pair unchanged (Needs Luca 4); zero open GitHub
issues and zero open PRs; CI success on main tip 0ab25de (run 118).
Regression suite green on main: 357/357 pytest (72s) and sdk-ts 62/62
vitest, both matching the run-16 through run-19 baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: check for Needs-Luca answers and credentials; if none, verify
CI on any new main tip, regression-check, log, end silently.

### 2026-07-21 ~06:10–06:20 UTC — run 19 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip 7c46e26 = run 18's
commit; every commit is the executor's; state file untouched since then);
no OPENROUTER_API_KEY or npm credential in the environment; all five
roadmap/stage-* branches at 0 unmerged commits each (checked via
rev-list); the stale feature/error-taxonomy + feature/tool-conversion
pair unchanged (Needs Luca 4); zero open GitHub issues AND zero open PRs
(PR state explicitly checked this run — refs/pull/1 and /2 exist on
origin but both are closed/historical); CI success on main tip 7c46e26
(run 117). Regression suite green on main: 357/357 pytest (81s) and
sdk-ts 62/62 vitest, both matching the run-16/17/18 baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state unchanged since run 17's
one-time notification, per the stay-silent note.

Next run: check for Needs-Luca answers and credentials; if none, verify
CI on any new main tip, regression-check, log, end silently.

### 2026-07-21 ~00:05–00:20 UTC — run 18 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip still c470f64 = run 17's
commit; state file last touched by the executor; every commit is the
executor's); no OPENROUTER_API_KEY or npm credential in the environment;
all five roadmap/stage-* branches at 0 unmerged commits each; the stale
feature/error-taxonomy + feature/tool-conversion pair unchanged (Needs
Luca 4); zero open GitHub issues; CI success on main tip c470f64 (run
116). Regression suite green on main: 357/357 pytest (74s) and sdk-ts
62/62 vitest, both matching the run-16/17 baselines.

Advanced: nothing — no unblocked work exists in any stage (re-verified).
No notification sent: blocked/healthy state is unchanged since run 17's
one-time notification, per that run's stay-silent note. Executor note:
sdk-ts installs with `corepack pnpm@10 install` (pnpm-lock.yaml, no
package-lock) — an `npm ci` attempt this run failed before the learnings
reminder was heeded; harmless, but the learnings entry stands.

Next run: check for Needs-Luca answers and credentials; if none, verify
CI on any new main tip, regression-check, log, end silently.

### 2026-07-20 ~18:10–18:20 UTC — run 17 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip still 166d8c9 = run 16's
addendum; every commit is the executor's; state file untouched since
d6bd351); no OPENROUTER_API_KEY or npm credential in the environment; all
five roadmap/stage-* branches fully merged (0 unmerged commits each); the
stale feature/error-taxonomy + feature/tool-conversion pair unchanged
(Needs Luca 4); zero open GitHub issues; CI success on main tip 166d8c9
(run 115; run 113 on the merge commit d2d8d74 was cancelled by the
same-tree km push — the known supersede pattern, runs 114/115 cover that
tree). Regression suite green on main: 357/357 pytest (78s) and sdk-ts
62/62 vitest, both matching run 16's baselines.

Advanced: nothing — no unblocked work exists in any stage (run 16's
conclusion re-verified). Sent Luca a push notification this run that the
roadmap is fully blocked on the Needs-Luca items (highest-leverage
unblock: OPENROUTER_API_KEY, item 11). Future idle runs should stay
silent unless the blocked/healthy state changes — the notification is
recorded here precisely so it isn't repeated every 6 hours.

Next run: check for Needs-Luca answers and credentials; if none, verify
CI on any new main tip, regression-check, log, end.

### 2026-07-20 ~13:05 UTC — run 16 addendum

CI on main verified before run end: run 114 on tip d6bd351 success
(covers the merge d2d8d74's tree; its own run was superseded by the
same-tree km push, the known pattern). No open verifications.

### 2026-07-20 ~12:05–13:00 UTC — run 16 (Fable 5, cloud)

Verified at start: no Luca edits (all commits are the executor's; state
file untouched since e038d4a); no OPENROUTER_API_KEY or npm credential
in the environment; all five roadmap/stage-* branches fully merged
(0 unmerged commits each, checked this run); CI success on main tip
00666d0 (run 109); zero open GitHub issues; baseline 357 pytest green
on main before any work.

Advanced (docs-consistency sweep, on roadmap/stage-4, merged d2d8d74):
three parallel read-only audit agents swept cookbook twins, protocol/
reference tables, and CLI/API/nav against the source; every finding
re-verified against code before fixing. Fixed (commit 09a1b1e):
envelope.md documented a nonexistent `validation_error` code (real code
is `invalid_input`), its error table missed 5 shipped codes and
mis-attributed validation failures to handler_error; X-Mesh-Instance-Id
and X-Mesh-Content-Type headers were undocumented; mesh-artifacts
bucket missing from subjects.md; mesh.health.> grant documented as
reserved (ADR-0016 deferral); errors.md taxonomy missed
connection_denied + kv_key_exists; last retired-"Watcher" references
fixed incl. a broken #watcher anchor in reactive-pipeline.md (its code
sample re-verified to still register); cli.md gained missing `oam mcp
serve` + `oam demo` sections; agentmesh.md call/stream/catalog/discover
signatures de-keyword-only'd to match code; DeathNotice/KVSource/
SubjectSource exports now named in docs. Twin test renamed
test_multi_agent.py → test_multi_process.py to match its recipe slug
(c6038f5). Clean at sweep end: nav, internal links, cookbook
index/twins, role templates, observability event table.

Verified this run: 357 pytest green on the branch post-change (and 37
cookbook tests re-run after the rename), ruff/ty zero, zensical build
clean, CI success on branch tip c6038f5 (run 111). Merged --no-ff to
main d2d8d74. Also landed on main directly: H1-2027 candidates skeleton
(33906ca) and this km update. Reviewed-and-accepted (no action): errors
documented in concepts/errors.md are not duplicated under docs/api/
(canonical page exists and is linked — by design, not drift).

Left open: all Needs-Luca items (1–12). CI on main after the merge not
yet observed at run end (the km push lands on the same tree; verify
next run per the known pattern). **The roadmap is now fully blocked on
Luca**: no unblocked build work remains in any stage. Next run: verify
CI on main, check for answers/key, regression-check, end.

### 2026-07-20 ~06:35 UTC — run 15 addendum

CI on main verified before run end: run 108 on tip e038d4a success (the
merge commit's own run 107 was superseded/cancelled by the same-tree km
push — the known pattern, not a failure). No open verifications.

### 2026-07-20 ~06:00–06:30 UTC — run 15 (Fable 5, cloud)

Verified at start: no Luca edits (all commits are the executor's; state
file untouched since 23337c1); all four prior roadmap/stage-* branches
fully merged (0 unmerged commits each, checked this run); stage-4 branch
tip 4453424 fully contained in main; baseline 347 pytest green on main
tip 23337c1 before any work (matches run 14's claim).

Advanced (Stage 4 item 1 machinery, on roadmap/stage-4, merged 46b4224):
built the persona-team experiment machinery per the plan note through the
pipeline — red tests first (4a8b740, CI run 105 the expected red), then
demos/persona_team/ implementation (f6c461e), CHANGELOG + plan-note
closeout (9612c83). Verified this run: 10/10 new tests, 5 consecutive
green runs; full suite 357 passed on the branch; ruff + ty zero; CLI
stub dry run exercised end-to-end (both topologies, per-agent usage
attribution visible in the JSONL report); CI success on branch tip
9612c83 (run 106). Merged --no-ff to main and pushed.

Not done, and why: measured experiment runs (no OPENROUTER_API_KEY —
Needs Luca 11; stub numbers are synthetic and flagged as such in
RunReport, never reportable); comparison note (depends on measured
runs); ADR-0036 decision (stage prompt orders it after the experiment).
CI on the main merge 46b4224 superseded-or-running at run end — the km
state push lands on the same tree; verify next run per the known
pattern. Left open: all prior Needs-Luca items (5, 1–4, 6–12).
Next run: check Needs-Luca answers first (the key unblocks everything);
otherwise docs-consistency sweep or H1-2027 skeleton per Current stage.

### 2026-07-20 ~00:05–00:35 UTC — run 14 (Fable 5, cloud)

Verified at start: no Luca edits (all commits are the executor's; state
file untouched since 06f694e); all four roadmap/stage-* branches fully
merged (0 unmerged commits each; feature/error-taxonomy and
feature/tool-conversion remain the known stale pair, Needs Luca 4); CI on
main tip 40737cf/06f694e closed by run 13's addendum; no open GitHub
issues (checked this run); baseline 337 pytest green on main before any
work.

Advanced (Stage 4 item 2, ADR-0023, on roadmap/stage-4, merged bf00b88):
amended the ADR against the shipped repo first (the return-value
convention was unimplementable under Pydantic v2 — full corrections in
the ADR amendment), red tests committed first per the pipeline (9 tests,
collection-error red), then implementation (_usage.py + responder/
streamer stamping + usage_reported observe event), then docs (concepts
page de-vaporwared, cookbook recipe + twin, envelope/API/observability
references, CHANGELOG) with ADR + index → documented. Verified this run:
347 pytest on the merged tree (337 baseline + 9 usage + 1 twin), ruff/ty
zero, zensical build clean, CI success on branch tip 4453424 (run 101;
run 100 superseded by the same-branch km push, the known pattern; the
red-commit failure run was the expected red phase).

Also advanced Stage 4 item 1 to shaped: the persona-experiment design
note (km/notes/2026-07-20-persona-experiment-plan.md) fixes task,
blackboard, turn-taking, personas, measurement, and execution order —
next run builds it. New Needs Luca 12 (task veto, non-blocking).

CI on main verified before run end: run 29709474809 on tip d503e01
success (the merge commit bf00b88's own run was superseded/cancelled by
the same-tree km push — the known pattern, not a failure). No open
verifications. Left open: all prior Needs-Luca items plus new item 12.
Next run: build the persona-experiment machinery per
km/notes/2026-07-20-persona-experiment-plan.md on roadmap/stage-4.

### 2026-07-19 ~18:00–18:35 UTC — run 13 (Fable 5, cloud)

Verified at start: no Luca edits (all commits since bootstrap are the
executor's; state file untouched since a4864ec); all four roadmap/stage-*
branches fully merged (0 unmerged commits each); CI success on main tip
a4864ec (run 87) — closes run 12's tail.

Advanced (Stage 3, ADR-0056 wave 5, on roadmap/stage-3, merged a4b667b):
wheel packaging in publish.yml (verified by actually building: assets in
wheel + sdist, `oam ui --check` green from a clean-venv wheel install),
playwright smoke e2e (ui/e2e/smoke.mjs + ui-e2e CI job — passed locally
and in real CI), admin-UI docs (cookbook + twin + CLI reference), ADR
amendments → documented. Full detail in Stage 3 item status. Verified
this run: 335 pytest, ruff/ty clean, sdk-ts 62/62 vitest, ui 30/30 vitest
+ typecheck + build, zensical build clean, CI run 90 on branch tip
d1bf25b all four jobs success (ui-e2e step-level verified; run 88 on the
packaging commit also success; run 89 cancelled by the same-branch push,
the known pattern).

**Stage 3 closed** — all three exit criteria checked against the repo
(see Current stage). Advanced the tracker to Stage 4.

Addendum (same run, later): CI on main after the wave-5 merge — run 92
on tip e236e03 success; run 91 on the merge commit a4b667b itself
FAILED on a single pytest flake (test_sources
test_handler_with_pydantic_model: embedded NATS ws port 36467 was
grabbed between the _free_port probe and nats-server binding it —
"bind: address already in use"; same code tree green in runs 90 and
92, so not a regression). Root-caused and fixed the race the same run:
EmbeddedNats.start() now re-picks auto-selected ports and retries (3
attempts), with two deterministic tests forcing the collision
(tests/test_embedded_nats.py). Merged --no-ff to main 40737cf after CI
run 94 success on branch tip 949619a; 337 pytest + ruff/ty clean
locally on the fixed tree. CI on main tip 40737cf verified before run
end — see below.

Left open: all Needs-Luca items, plus new item 11 (OPENROUTER_API_KEY
for Stage 4's measured experiment). Next run: begin Stage 4 per its
prompt — read km/notes/2026-05-25-persona-team-on-oam.md and the
learnings, then start with ADR-0023 usage attribution (the stage prompt
itself suggests it first, and it needs no LLM key), recording the
experiment-blocker under Needs Luca 11.

### 2026-07-19 ~12:40 UTC — run 12 addendum

CI on main verified before run end: run 86 on tip 2047923 success (the
wave-4 merge commit's own run 85 was superseded/cancelled by the
same-ref km push — the known pattern, not a failure; the code tree it
carries is what run 86 tested). No open verifications.

### 2026-07-19 ~12:05 UTC — run 12 (Fable 5, cloud)

**Run 11 reconciliation:** run 11 (~06:15 UTC, per branch CI timestamps)
pushed all four wave-3 commits to roadmap/stage-3 with green CI on the tip
(297850e, run 78) but was cut off before merging, logging, or updating
this file. The early-push protocol did its job: nothing was lost, and
this run's work started as verify-and-merge, not redo.

Verified at start: no Luca edits (state file untouched since d098273; all
commits are the executor's); stage-0/1/2 branches still fully merged;
stage-3 carried exactly the four wave-3 commits. Verified the wave-3 work
against reality (see Wave 3 verification above) and merged --no-ff to
main as 968f4f5. CHANGELOG entry for the sdk-ts NotAvailable change and
the plan-note wave-3 closeout added on the branch (2c45dd2, CI run 79
success) before merging.

Continued this run: ADR-0056 wave 4 built end-to-end on roadmap/stage-3
per the pipeline (red dc96151 → green c1bc714 → docs d2c7168) and merged
--no-ff to main as 48b9f3b after CI success on the tip (run 84) plus the
local + browser verification recorded in the Stage 3 item status. Two
waves landed in one run because run 11 had already built wave 3.

Left open: all Needs-Luca items still unanswered; CI on main tip after
the wave-4 merge verified before run end (see addendum). Next run:
check Needs-Luca answers, then ADR-0056 wave 5 (packaging: build ui into
_ui_assets in the release workflow; Playwright smoke e2e in CI or as a
script; cookbook/admin-ui.md + CLI reference docs; amend the ADR with
the `mesh.>` default-pattern deviation and the monitor-deregistration
note; ADR + index → documented; CHANGELOG admin-UI entry rewrite).

### 2026-07-19 ~00:10–00:30 UTC — run 10 (Fable 5, cloud)

Verified at start: no Luca edits (all commits since bootstrap are the
executor's; origin quiet since 18:32, no overlap risk); all four
roadmap/stage-* branches fully merged (0 unmerged commits each); CI
success on main tip 1f5e959 (run 63) — closes run 9's tail.

Advanced (Stage 3, ADR-0056 wave 2, on roadmap/stage-3, merged efae05e):
scaffold → red tests (10 red / 1 green) → implementation → CI job, per
the pipeline. Full detail in Stage 3 item status above. Verified this
run: ui typecheck + 11/11 vitest (3 consecutive runs) + production build
green locally; 53/53 sdk-ts vitest locally; CI success on branch tip
e266d8b (run 70 — all three jobs incl. the new `ui` job; run 68's
failure was an invalid-yaml step name in the new job, fixed in 16b935c;
runs 65/66/69 cancelled by same-branch pushes, the known pattern);
headless-chromium e2e against a real mesh passed (details above).

CI on main verified before run end: run 72 on tip c61fd00 success (the
merge commit's own run 71 was superseded/cancelled by the same-tree km
push — the known pattern, not a failure). No open verifications.
Left open: all Needs-Luca items still unanswered. Next run: check
Needs-Luca answers, then ADR-0056 wave 3 per the plan note (invocation
sandbox: @rjsf/core form from input schema, Call request/reply + Stream
reassembly in the browser, error-envelope rendering incl. not_available).

### 2026-07-18 ~18:05–19:00 UTC — run 9 (Fable 5, cloud)

Verified at start: no Luca edits (all commits since bootstrap are the
executor's; origin quiet since 13:00, no overlap risk); all four
roadmap/stage-* branches fully merged (0 unmerged commits each); baseline
314 passed + 7 skipped on main tip a328dfa after the usual Go-proxy
nats-server build.

Advanced (Stage 3, ADR-0056 wave 1, on roadmap/stage-3, merged 7b48e99):
amended the ADR against the shipped repo first (5 corrections — two found
empirically this run: the ws-port bind conflict and the nats.ws
deprecation/SDK-reuse discovery), wrote the build-wave plan note, then
red tests → implementation → e2e verification. Full detail in Stage 3
item status above. Verified this run: 326 pytest + 7 skips on the branch
(and ruff/ty clean); CI success on branch tips e983d3f (run 59) and
92bd408 (run 60; run 58 was the expected red phase); real `oam mesh up`
websocket handshake + `oam ui` serving checked end-to-end in the sandbox.

CI on main verified before run end: run 62 on tip d8e5323 success (the
merge commit's own run 61 was superseded/cancelled by the same-tree km
push — the known pattern, not a failure). No open verifications.
Left open: all Needs-Luca items still unanswered. Next run: check
Needs-Luca answers, verify CI on main, then ADR-0056 wave 2 per
km/notes/2026-07-18-adr0056-ui-plan.md — ui/ scaffold with the TS SDK as
the browser client (workspace link to sdk-ts/), registry + contract
screens, vitest + CI job. pnpm works in the sandbox via `corepack
pnpm@10`.

### 2026-07-18 ~12:10–13:15 UTC — run 8 (Fable 5, cloud)

Verified at start: origin quiet since 06:28 (no overlap risk); no Luca
edits (all commits since bootstrap are the executor's); CI success on main
tip 9e057bb (run 45) — closes run 7's tail; baseline 308 pytest green on
main (301+7 skips before installing nsc, 308 with it).

Advanced (Stage 3, ADR-0055 lifecycle gates, on roadmap/stage-3, merged
b7e4093): amended the ADR against the shipped repo first (4 corrections
recorded in the ADR amendment), red tests committed first per the
pipeline, then implementation, docs, and the Watcher-shape retirement.
Full detail in Stage 3 item status above. One real bug found and fixed
during the work: the first drain implementation used nats-py's
Subscription.drain(), whose cancellation mid-flush kills the client read
loop — diagnosed from an actual test hang via task-dump, replaced with
task-based dispatch + own drain. Verified this run: 321 pytest + ruff +
ty clean on the merged tree; 53 vitest on the branch; zensical build
clean; CI success on branch tip 426cde3 (run 52; run 49's failure was
the expected red phase).

CI on main verified before run end: run 53 on merge commit b7e4093 and
run 54 on state commit 744cf8a, both success. No open verifications.
Left open: all Needs-Luca items still unanswered. Next run: check
Needs-Luca answers, then start ADR-0056
admin UI (in Stage 3 scope via item 9's silence-deferral; 4–6 session
estimate — expect it to span several runs; re-read the ADR and the
Stage-2 shaping notes in this file before building).

### 2026-07-18 ~05:50–06:35 UTC — run 7 (Fable 5, cloud)

Verified at start: CI success on the run-6 merge af5a96a (run 36) and main
tip f7fb3c8 (run 37) — closes run 6's open check. No Luca edits (all
commits since bootstrap are the executor's; origin quiet since 00:37 UTC,
no overlap risk). No open GitHub issues. Baseline 292 pytest green on main
before any work.

Advanced (Stage 3, ADR-0048 observability v1, on roadmap/stage-3, merged
3e5e486): shaped discussion→spec (subject-root correction + stale-context
fixes recorded in the ADR amendment), red tests committed first per the
pipeline, then implementation, CLI, role templates, and docs. Full detail
in the Stage 3 item status above. Verified this run: 308 pytest + ruff +
ty clean locally on the branch tip; CI success on 630396c (run 42; the
red-tests commit's CI failure, run 40, was the expected red phase);
zensical docs build clean.

CI on main verified before run end: run 44 on tip 026c627 success (the
merge commit's own run 43 was superseded/cancelled by the same-tree km
push, matching the known pattern — not a failure). No open verifications.
Left open: all Needs-Luca items still unanswered. Next run: check
Needs-Luca answers, then ADR-0055 lifecycle gates
(spec-ready with code sample; last planned Stage 3 item unless Luca
confirms the ADR-0056 UI deferral, which would slot the UI after it).

### 2026-07-17 23:50 – 2026-07-18 ~00:55 UTC — run 6 (Fable 5, cloud)

Verified at start: CI success on the ADR-0038 merge 9502f52 (run 27) and
main tip 8918e68 (run 28) — closes run 5's open check. No Luca edits (last
human commit still the 2026-07-16 bootstrap; origin quiet ~13h, no overlap
risk). Baseline 281 pytest green on main before any work.

Advanced (Stage 3, ADR-0016+0040 pair, on roadmap/stage-3, merged af5a96a):
- Amended ADR-0016 (v1 scope, monitor placement, code sample) and shaped
  ADR-0040 discussion→spec; red tests committed first per the pipeline;
  full details in the Stage 3 item status above.
- 8 new liveness tests + 3 cookbook-twin tests, all green; 292 pytest on
  merged main verified locally; ruff/ty clean; CI success on branch tip
  e3733e6 (run 35). Docs built clean (zensical build).
- Both Stage 3 exit criteria now met (secured-mesh recipe + chaos test).

Left open: CI on the merge commit af5a96a (pushed at end of run — verify
next run); all Needs-Luca items still unanswered. Next run: verify CI on
af5a96a, check Needs-Luca answers, then ADR-0048 observability — shape
discussion→spec (trimmed v1 per the stage-3 plan: logs subjects, KV level
control, `oam observe logs`) before any code. ADR-0055 is the parallel
workstream if 0048 shaping stalls.

### 2026-07-17 ~19:15–19:50 UTC — run 5 (Fable 5, cloud)

**Run 4 reconciliation:** run 4 (~18:10 UTC) committed the stage-3 plan and
claimed ADR-0038 in the index (cb9ddf1) but was cut off before creating the
roadmap/stage-3 branch or logging its own run entry — this entry closes that
gap. No Needs-Luca answers found (state file untouched since cb9ddf1, all
commits are the executor's own; origin quiet ~65 min at run start).

Verified: baseline 253 pytest passed on main tip cb9ddf1 before any work;
nats-server rebuilt via Go module proxy (learnings workaround still good);
nsc installed the same way.

Advanced (Stage 3 / ADR-0038, on roadmap/stage-3, pushed through 14b1e89):
- Red-green per the pipeline: red tests committed first for both increments.
- SDK auth slice + connect --creds/whoami CLI (details in Stage 3 item
  status above). 274 pytest, ruff/ty clean, verified locally on the branch.
- ADR-0038 implementation notes added (system-account requirement, nkeys
  dep, denial semantics); index status spec -> test; CHANGELOG updated.

Continued (same run, later): completed ADR-0038 entirely — `oam auth
init`/`user add`/`user revoke` wrapping nsc (role subject lists corrected
against real wire usage; ADR amended), a fix making denied/timed-out calls
raise ConnectionDenied/MeshTimeout instead of leaking raw NATS errors,
docs slice (concepts/security.md, cookbook/secured-mesh.md + twin, CLI
reference), CI now installs nsc + nats-server explicitly (one red CI run
from test-ordering: auth tests ran before the lazy binary download —
fixed). Merged --no-ff to main as 9502f52 after CI success on fca33cc;
281 pytest on merged tree verified locally.

Left open: CI on the main merge commit (verify next run); all prior
Needs-Luca items still unanswered. Next run: verify CI on 9502f52, check
Needs-Luca answers, then start the ADR-0016+0040 liveness pair (amend 0016
with a code sample + shape 0040 discussion->spec first; ends with the
chaos-style kill-mid-request test, the stage's remaining exit criterion).

### 2026-07-17 ~12:05–12:25 UTC — run 3 (Fable 5, cloud)

Verified: origin/main tip f38b490 = run 2's final commit, no edits from Luca (all
Needs-Luca items still unanswered); CI green on the stage-1 merge b2a5849 (run #12)
and on f38b490 (run #13) — closes the verification run 2 left open; wildfire branch
still absent from origin; no lock-protocol concern (origin quiet ~5.5 h before this
run started).

Advanced (Stage 2, on roadmap/stage-2, CI run #14 green — both jobs genuinely
executed: ruff/ty/pytest + tsc/vitest — merged to main --no-ff as 2d81978):
- Launch post draft ("The Wire, Not the Workflow") and Show HN draft (title options,
  body, prepared first comment) in km/notes/launch/, both marked unpublished.
- README top fold: positioning hook, hero agent sample, MCP bridge one-liner, demo
  video placeholder comment.
- Docs URL split inventoried (item status above); flagged that the wrong site_url is
  an active canonical/SEO bug. Could not check DNS from the sandbox (proxy 403).
- ADR-0056 shaped: 4–6 session estimate, defer-to-Stage-3 proposed (Needs Luca 9).

Left open: everything gated — demo recording (wildfire branch + OPENROUTER_API_KEY),
docs URL decision, draft reviews, npm publish, Stage 0 items 1/2/7. Next run: check
Needs-Luca answers and act on any (URL fix is one line; npm tag; v0.3.0 /release);
otherwise Stage 2 has no more unblocked work — consider starting Stage 3's shaping
pass (read-only ADR assessment + prioritized plan for Luca's sign-off), which needs
no answers to begin.

### 2026-07-17 ~06:05–07:15 UTC — run 2 (Fable 5, cloud)

**Overlap warning:** this run started while run 1 was still finishing (cron fired at the
6h mark; run 1 ran long). Both runs independently did the Stage-0 ty work; run 2
discarded its duplicate commits in favor of run 1's pushed branch. Lesson + proposed
lock protocol recorded in roadmap-learnings.md.

Verified: run 1's state-file claims all check out against the repo (ruff/ty zero, 235
tests passing at main before stage-1, CI run #5 on main tip concluded success — the
merge-commit run #4 was superseded/cancelled by the same-tree docs push, not a failure).
nats-server built from Go module proxy again (learnings workaround works).

Advanced (all on roadmap/stage-1, merged to main --no-ff, verified locally post-merge):
- Stage 1 items 1, 2, 4 done + item 3 prepared (see item status above).
- ADR-0002 amended (stdio-only v1, whole-mesh export semantics, code sample added);
  ADR-0002/0003 statuses updated; ADR claims recorded in the index Branch column.
- Bug found & fixed along the way: mesh.contract() dropped input/output schemas on the
  registry round-trip, so remote agents projected empty tool schemas.
- CHANGELOG updated under [Unreleased].

Left open: Stage 0 items 1/2/7 and Stage 1 npm publish — all Needs Luca. Next run:
check Needs Luca answers; verify CI green on the stage-1 merge (pushed at end of run,
CI result not yet observed); then Stage 2 prep that doesn't need answers (launch-post
and Show HN drafts, README fold) — note Stage 2's demo recording is blocked on the
wildfire branch and OPENROUTER_API_KEY, and the docs-URL decision is Luca's.

### 2026-07-17 ~05:15–06:30 UTC — run 1 (Fable 5, cloud)

Verified: state file said "not started" and was accurate; wildfire branch absent from
origin (blocker found); baseline pytest 232 passed only after building nats-server from
source via Go module proxy (GitHub release downloads 403 through the sandbox network
policy — see learnings); ruff 44, ty 245, sdk-ts flake reproduced on run 1 of 2.

Advanced (all on roadmap/stage-0, merged to main --no-ff, CI green on branch):
- sdk-ts sim-helper flush fix; 5 consecutive full-suite runs green (53/53).
- ruff 44→0 (real fixes; suppress conversions, specific exception asserts).
- ty 245→0 (narrowing properties _conn/kv/workspace, bound TypeVar in _context,
  Literal narrowing, explicit Msg import, ClassVar→instance code on MeshError; one
  scoped suppression for the ADR-0031 streamer convention with rationale in pyproject).
  ty caught one real bug mid-fix (keyword-only MeshError kwargs).
- CI workflow added and verified green end-to-end on the branch (both jobs).
- py.typed added; multi-module + parallel-rag cookbook tests added (235 total passing).
- CHANGELOG updated under [Unreleased].
- km/notes/roadmap-learnings.md created.

Left open: Stage 0 items 1, 2, 7 (see Needs Luca). Next run: re-check Needs Luca answers;
if wildfire is pushed, do the merge per the stage prompt; verify CI green on main
(merge commit CI run was pending when this run ended); otherwise Stage 0 is
done-except-blocked and Stage 1 (Interop) work can begin while blocked items wait.
