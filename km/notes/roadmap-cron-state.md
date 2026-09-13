# H2 2026 roadmap — cron executor state

Machine-maintained by the "OAM H2 roadmap executor" routine. Humans may edit (e.g. to
answer a "Needs Luca" item); the executor re-verifies everything against the repo anyway.

## Current stage

**Run 155 (2026-08-24) unblocked and completed Stage 0 item 1 — the wildfire
merge.** `feature/wildfire-demo` appeared on origin (Luca pushed it; Needs Luca
item 1 is answered, see the run log for what could and could not be established
about when). 113 commits merged onto a main seven weeks ahead of the branch
point, reconciled, and merged to main f639f8c (--no-ff). Details in the Stage 0
item status below and in ADR-0054's 2026-08-24 amendment.

Stage 4 — Frontier remains the current stage for new work. Item 2 (ADR-0023
usage attribution) COMPLETE run 14: merged to main bf00b88 (--no-ff), ADR at
`documented`. Item 1 (persona experiment): machinery BUILT run 15 — merged to
main 46b4224 (--no-ff), `src/openagentmesh/demos/persona_team/` + 10 tests; both
topologies run the full protocol dry with the stub model. The item's remaining
work — measured runs and the comparison note — is BLOCKED on OPENROUTER_API_KEY
(Needs Luca 11); the executor will not fake numbers. Item 3 (ADR-0036 decision)
comes after the measured experiment.

Every remaining item across all five stages still waits on a Needs-Luca answer.
The single highest-leverage unblock is OPENROUTER_API_KEY (item 11), which now
reactivates **two** things at once: Stage 4's measured experiment → comparison
note → ADR-0036 decision → stage exit, and Stage 2's demo recording, whose code
blocker just disappeared (`demos/wildfire/DEMO_SCRIPT.md` is on main).

**STAGE 3 COMPLETE (run 13).** All three exit criteria verified against the
repo that run: (1) every shipped ADR at `documented` in km/adr/index.md —
0038, 0016, 0040, 0048, 0055, 0056; (2) secured multi-node mesh cookbook recipe
(docs/cookbook/secured-mesh.md + executable twin, since run 5); (3) chaos
kill-mid-request test
(tests/test_liveness.py::test_call_fast_fails_when_agent_dies_mid_request).
The stage-3 plan sign-off (Needs Luca 10) was never answered; the executor ran
the plan's default order to completion — the item stands only as FYI.
ADR-0038 auth: COMPLETE (run 5, merged 9502f52). ADR-0016+0040 liveness pair:
COMPLETE (run 6, merged af5a96a). ADR-0048 observability v1: COMPLETE (run 7,
merged 3e5e486). ADR-0055 lifecycle gates: COMPLETE (run 8, merged b7e4093).
ADR-0056 admin UI: COMPLETE across five waves (runs 9–13), ADR at `documented`.

Stage 2 remains open on Needs-Luca items (demo recording, docs URL, draft
review, publishing). Stage 1 open only on npm publish. Stage 0 open only on
items 2 and 7 (worktree cleanup, v0.3.0 release) — both Luca's.

## Stage checklist

- [ ] Stage 0 — Consolidate (item 1 DONE run 155: wildfire merged to main f639f8c; open only on items 2 and 7, both Luca's)
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

## Stage 0 item status (item 1 updated 2026-08-24 run 155; rest verified 2026-07-17)

1. **Merge feature/wildfire-demo** — DONE (run 155, 2026-08-24). The branch turned up
   on origin and was merged to main f639f8c (--no-ff) via roadmap/stage-0. 113 commits,
   80 files, ~16k lines: `demos/wildfire/` (19-process fleet + Svelte scenario dashboard),
   `tests/wildfire/` (336 tests), `docs/cookbook/wildfire-incident.md` + executable twin.
   Conflict policy per the stage prompt — main won for SDK code (its ADR-0056 admin UI
   over the branch's earlier parallel `ui/`, `_local.py`, `cli/ui.py`), the branch won for
   demo code; the branch's two KV-source DELETE fixes in `_mesh.py` were kept (additive,
   test-covered). `.planning/` dropped (gitignored on main). uv.lock regenerated rather
   than hand-merged. Reconciliation needed after the merge: 34 ruff errors and 54 ty
   diagnostics, all fixed (commit e421fd2). ADR-0054 → `documented` with an amendment
   recording what actually shipped. Verified this run: 700 pytest (2 skipped), ruff/ty
   clean, sdk-ts 62/62 ×5, admin UI 30/30, 28/28 wildfire modules importable, wheel builds
   with no demo leakage, live boot reaching a `surveyed` detection in 9s.
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
**Stage 0 exit criteria as of run 155:** CI green on main — MET (run 257 on
f639f8c); wildfire demo importable/runnable from main — MET (28/28 modules
import; live boot drove a detection to `surveyed`); zero ruff/ty findings — MET;
TS suite 5 consecutive full runs — MET (62/62 ×5); v0.3.0 tagged and published —
NOT MET, and not the executor's to do (item 7 / Needs Luca 3). Four of five.

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

1. **Wildfire demo recording** — HALF UNBLOCKED (run 155). The code blocker is gone:
   the demo is on main and boots (`python -m demos.wildfire`), and the recording script
   is at `demos/wildfire/DEMO_SCRIPT.md`. Still blocked on OPENROUTER_API_KEY (the
   briefing / natural-language dispatch / narration beats need it; the detect→claim→survey
   cascade does not) and on screen recording, which is Luca's machine either way. README
   still carries a placeholder comment where the embed goes. → Needs Luca (item 6).
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
1. ~~**Push feature/wildfire-demo to origin.**~~ **ANSWERED — you pushed it, and run 155
   merged it** (main f639f8c). Nothing further needed here. Two follow-ons for you:
   the branch is now fully merged into main, so it joins the deletable-branch question in
   item 4; and the demo recording (Stage 2 item 1) now waits only on your key and your
   screen recorder.
2. **Worktree cleanup is yours to run locally** (cloud checkouts don't see
   .claude/worktrees). Per the stage prompt: check none of the 15 agent-* branches has
   unique unmerged work before deleting.
3. **v0.3.0 release decision**: release now without wildfire (Unreleased changelog is
   already large: instance_id, publish, KV ergonomics, TS SDK, sources, error taxonomy,
   CI/typing), or wait for the wildfire merge? If "release now", say so here and the next
   run will run the /release flow up to the tag push; note the tag push triggers the PyPI
   publish workflow.
4. **OK to delete stale remote branches?** feature/tool-conversion and (since run 155)
   feature/wildfire-demo are now fully merged ancestors of main — verified this run with
   `git merge-base --is-ancestor`. feature/error-taxonomy is 4 commits ahead of main and
   its content landed by other means, so it needs a look before deletion, not a blind
   delete. Deleting remote branches is destructive, so all three are left alone.
6. **OPENROUTER_API_KEY for the demo recording** (Stage 2 item 1). No longer blocked on
   the branch — the demo is on main and boots. The executor still cannot record in the
   cloud (no key, and screen recording belongs on your machine); the script is now at
   `demos/wildfire/DEMO_SCRIPT.md`. Same key as item 11: providing it once covers the
   recording and the Stage 4 experiment.
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

Recent entries only. Runs 1–223 are archived verbatim in
`km/notes/roadmap-cron-runlog-archive.md` (moved by run 232 when this file
passed 400KB; nothing deleted).

### 2026-09-13 ~04:35–05:00 UTC — run 233 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip is run 232's own commit
cc75e11 — zero new commits of any kind since; Needs Luca section
untouched); no OPENROUTER_API_KEY or npm credential in the environment
(env grep matched nothing); remote refs unchanged (same 9 heads, SHAs
listed and checked); origin tags unchanged (8, ending v0.2.0). Zero open
GitHub issues and zero open PRs. CI run 341 SUCCESS on main tip cc75e11
(closes run 232's own-commit verification). Container came up shallow
again — unshallowed before ancestry claims; all 5 roadmap/stage-* tips
plus feature/tool-conversion and feature/wildfire-demo re-proved merged
ancestors of main (feature/error-taxonomy re-measured at exactly 4 ahead,
the known Needs Luca 4 case).

Regression suite green at baseline: **701 passed / 2 skipped** (99s)
first-pass clean (the 1 warning is the known StarletteDeprecationWarning,
cosmetic); nats-server 2.10.24 via go install (copied to ~/.agentmesh/bin
per the standing reminder), nsc via `nsc/v2@v2.11.0` pin, both installed
BEFORE any suite ran (run 232's sequencing slip not repeated — auth tests
all ran first pass). sdk-ts vitest 62/62 (11/11 files) ×5 consecutive —
sixty-first consecutive clean ×5; admin UI 30/30 (5/5 files) after
`pnpm build` in sdk-ts; ruff and ty both clean from repo root.

Advanced: nothing — no unblocked work exists in any stage. Stage 4 remains
current; every open item across stages waits on a Needs-Luca answer.
Highest-leverage unblock is still OPENROUTER_API_KEY (items 6/11). No
notification sent: nothing changed.

Next run: check for Needs-Luca answers and credentials; if none, verify CI
on this run's own commit, regression-check against the 701/62/30 baseline
(nats-server + nsc via go install, copy nats-server to ~/.agentmesh/bin/
AND put GOPATH/bin on PATH before ANY test suite; sdk-ts uses pnpm not
npm; pnpm install + `pnpm build` in sdk-ts before ui vitest; unshallow
before any ancestry claim or push), log, end silently.

### 2026-09-12 ~18:20–18:45 UTC — run 232 (Fable 5, cloud) — idle verification + log archival

Verified this run: no Luca edits (every commit on origin/main since run
226 is an executor run-log commit; run 226's own commit 1eb5731 carries
Luca's committer email but is the executor's log entry, not an answer —
Needs Luca section byte-identical); no OPENROUTER_API_KEY or npm
credential in env (grep matched nothing). Remote refs unchanged (same 9
heads; 8 tags ending v0.2.0); all 5 roadmap/stage-* tips plus
feature/tool-conversion and feature/wildfire-demo re-proved merged
ancestors of main after unshallowing; feature/error-taxonomy exactly 4
ahead (known Needs Luca 4 case). Zero open issues and zero open PRs.
CI run 340 SUCCESS on main tip 1ead029 (closes run 231's own-commit
verification).

Regression suite green at baseline: pytest first pass came back 694/9
because the suite was run before installing nsc (7 "nsc binary not
available" skips — sequencing slip, standing reminder below still holds);
after `go install nsc/v2@v2.11.0` all 7 auth tests pass (3.96s), so the
effective baseline 701 passed / 2 skipped (the 2 intentional
OAM_INTEGRATION_TESTS gates) is met. Sixtieth consecutive clean sdk-ts
vitest ×5 (62/62 each run, after pnpm install). Admin UI 30/30 after
sdk-ts `pnpm build` (first ui attempt failed to collect on the unbuilt
linked dist, as documented). ruff + ty both clean from repo root.

Maintenance this run: run-log entries for runs 1–223 moved verbatim to
`km/notes/roadmap-cron-runlog-archive.md`; this file drops from 7,494 to
~790 lines (423KB → ~45KB). It had outgrown the 256KB tool read limit —
runs could no longer read their own state file in one pass.

Still fully blocked on Needs-Luca across all open stages; highest-leverage
unblock remains OPENROUTER_API_KEY (items 6/11).

Next run: check for Needs-Luca answers and credentials; if none, verify CI
on this run's own commit, regression-check against the 701/62/30 baseline
(nsc + nats-server via go install with GOPATH/bin on PATH BEFORE the
pytest run; pnpm install + `pnpm build` in sdk-ts before ui vitest;
unshallow before any ancestry claim), log, end silently.

### 2026-09-12 ~12:15–12:45 UTC — run 231 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip is run 230's own commit
365f53a; the 18 commits since the container's checkout point 5b309a9 are
all executor-authored run logs plus run 219's kv.list fix — no human
commits); no OPENROUTER_API_KEY or npm credential in the environment (env
grep matched nothing); remote refs unchanged (same 9 heads, SHAs diffed
against run 230's snapshot); origin tags unchanged (8, ending v0.2.0).
Zero open GitHub issues and zero open PRs. CI run 339 SUCCESS on main tip
365f53a (closes run 230's own-commit verification). Container came up
shallow again — unshallowed before ancestry claims (644 commits); all 5
roadmap/stage-* tips plus feature/tool-conversion and
feature/wildfire-demo re-proved merged ancestors of main
(feature/error-taxonomy re-measured at exactly 4 ahead, the known Needs
Luca 4 case).

Regression suite green at baseline: **701 passed / 2 skipped** (97s)
first-pass clean (the 1 warning is the known StarletteDeprecationWarning,
cosmetic); nats-server 2.10.24 via go install (copied to ~/.agentmesh/bin
per the standing reminder), nsc via `nsc/v2@v2.11.0` pin (auth tests all
ran — 701/2). sdk-ts vitest 62/62 (11/11 files) ×5 consecutive —
fifty-ninth consecutive clean ×5; admin UI 30/30 (5/5 files) after
`pnpm build` in sdk-ts; ruff and ty both clean from repo root.

Advanced: nothing — no unblocked work exists in any stage. Stage 4 remains
current; every open item across stages waits on a Needs-Luca answer.
Highest-leverage unblock is still OPENROUTER_API_KEY (items 6/11). No
notification sent: nothing changed.

Next run: check for Needs-Luca answers and credentials; if none, verify CI
on this run's own commit, regression-check against the 701/62/30 baseline
(nats-server + nsc via go install, copy nats-server to ~/.agentmesh/bin/
AND put GOPATH/bin on PATH before ANY test suite; sdk-ts uses pnpm not
npm; pnpm install + `pnpm build` in sdk-ts before ui vitest; unshallow
before any ancestry claim or push), log, end silently.

### 2026-09-12 ~06:15–06:45 UTC — run 230 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip is run 229's own commit
0d6831c; all 17 commits since the previous checkout point 5b309a9 are
executor-authored run logs plus run 219's kv.list fix — no human commits);
no OPENROUTER_API_KEY or npm credential in the environment (env grep
matched nothing); remote refs unchanged (same 9 heads, SHAs listed and
checked); origin tags unchanged (8, ending v0.2.0). Zero open GitHub
issues and zero open PRs. CI run 338 SUCCESS on main tip 0d6831c (closes
run 229's own-commit verification). Container came up shallow again —
unshallowed before ancestry claims; all 5 roadmap/stage-* tips plus
feature/tool-conversion and feature/wildfire-demo re-proved merged
ancestors of main (feature/error-taxonomy re-measured at exactly 4 ahead,
the known Needs Luca 4 case).

Regression suite green at baseline: **701 passed / 2 skipped** (98s)
first-pass clean (the 1 warning is the known StarletteDeprecationWarning,
cosmetic); nats-server 2.10.24 via go install (copied to ~/.agentmesh/bin
per the standing reminder), nsc via `nsc/v2@v2.11.0` pin (auth tests all
ran — 701/2). sdk-ts vitest 62/62 (11/11 files) ×5 consecutive —
fifty-eighth consecutive clean ×5; admin UI 30/30 (5/5 files) after
`pnpm build` in sdk-ts; ruff and ty both clean from repo root.

Advanced: nothing — no unblocked work exists in any stage. Stage 4 remains
current; every open item across stages waits on a Needs-Luca answer.
Highest-leverage unblock is still OPENROUTER_API_KEY (items 6/11). No
notification sent: nothing changed.

Next run: check for Needs-Luca answers and credentials; if none, verify CI
on this run's own commit, regression-check against the 701/62/30 baseline
(nats-server + nsc via go install, copy nats-server to ~/.agentmesh/bin/
AND put GOPATH/bin on PATH before ANY test suite; sdk-ts uses pnpm not
npm; pnpm install + `pnpm build` in sdk-ts before ui vitest; unshallow
before any ancestry claim or push), log, end silently.

### 2026-09-12 ~00:15–00:45 UTC — run 229 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip is run 228's own commit
670d473 — zero new commits of any kind since; all 25 most recent commits
authored by the executor); no OPENROUTER_API_KEY or npm credential in the
environment (env grep matched nothing); remote refs unchanged (same
9 heads, SHAs listed and checked); origin tags unchanged (8, ending
v0.2.0). Zero open GitHub issues and zero open PRs. CI run 337 SUCCESS on
main tip 670d473 (closes run 228's own-commit verification). Container
came up shallow again — unshallowed before ancestry claims; all 5
roadmap/stage-* tips plus feature/tool-conversion and
feature/wildfire-demo re-proved merged ancestors of main
(feature/error-taxonomy re-measured at exactly 4 ahead, the known Needs
Luca 4 case).

Regression suite green at baseline: **701 passed / 2 skipped** (94s)
first-pass clean (the 1 warning is the known StarletteDeprecationWarning,
cosmetic); nats-server 2.10.24 via go install (copied to ~/.agentmesh/bin
per the standing reminder), nsc via `nsc/v2@v2.11.0` pin (auth tests all
ran — 701/2). sdk-ts vitest 62/62 (11/11 files) ×5 consecutive —
fifty-seventh consecutive clean ×5; admin UI 30/30 (5/5 files) after
`pnpm build` in sdk-ts; ruff and ty both clean from repo root.

Advanced: nothing — no unblocked work exists in any stage. Stage 4 remains
current; every open item across stages waits on a Needs-Luca answer.
Highest-leverage unblock is still OPENROUTER_API_KEY (items 6/11). No
notification sent: nothing changed.

Next run: check for Needs-Luca answers and credentials; if none, verify CI
on this run's own commit, regression-check against the 701/62/30 baseline
(nats-server + nsc via go install, copy nats-server to ~/.agentmesh/bin/
AND put GOPATH/bin on PATH before ANY test suite; sdk-ts uses pnpm not
npm; pnpm install + `pnpm build` in sdk-ts before ui vitest; unshallow
before any ancestry claim or push), log, end silently.

### 2026-09-11 ~18:15–18:45 UTC — run 228 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip is run 227's own commit
8e46112 — zero new commits of any kind since; all commits in the last 30
authored by the executor); no OPENROUTER_API_KEY or npm credential in the
environment (env grep matches only proxy-config vars); remote refs
unchanged (same 9 heads); origin tags unchanged (8, ending v0.2.0). Zero
open GitHub issues and zero open PRs. CI run 336 SUCCESS on main tip
8e46112 (closes run 227's own-commit verification). Container came up
shallow again — unshallowed before ancestry claims; all 5 roadmap/stage-*
tips plus feature/tool-conversion and feature/wildfire-demo re-proved
merged ancestors of main (feature/error-taxonomy re-measured at exactly
4 ahead, the known Needs Luca 4 case).

Regression suite green at baseline: **701 passed / 2 skipped** (90s)
first-pass clean (the 1 warning is the known StarletteDeprecationWarning,
cosmetic); nats-server 2.10.24 via go install (copied to ~/.agentmesh/bin
per the standing reminder), nsc via `nsc/v2@v2.11.0` pin (self-reports
0.0.0-dev, known cosmetic; auth tests all ran — 701/2, not 693/9). sdk-ts
vitest 62/62 (11/11 files) ×5 consecutive — fifty-sixth consecutive clean
×5; admin UI 30/30 (5/5 files) after `pnpm build` in sdk-ts; ruff and ty
both clean from repo root.

Advanced: nothing — no unblocked work exists in any stage. Stage 4 remains
current; every open item across stages waits on a Needs-Luca answer.
Highest-leverage unblock is still OPENROUTER_API_KEY (items 6/11). No
notification sent: nothing changed.

Next run: check for Needs-Luca answers and credentials; if none, verify CI
on this run's own commit, regression-check against the 701/62/30 baseline
(nats-server + nsc via go install, copy nats-server to ~/.agentmesh/bin/
AND put GOPATH/bin on PATH before ANY test suite; sdk-ts uses pnpm not
npm; pnpm install + `pnpm build` in sdk-ts before ui vitest; unshallow
before any ancestry claim or push), log, end silently.

### 2026-09-11 ~12:15–12:45 UTC — run 227 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip is run 226's own commit
1eb5731 — zero new commits of any kind since; the single Luca-identity
commit in history remains run 186's own log commit 3b0486c, re-checked,
not an answer); no OPENROUTER_API_KEY or npm credential in the environment
(env grep matches only proxy-config vars); remote refs unchanged (same
9 heads, SHAs diffed against run 226's expectations — all identical);
origin tags unchanged (8, ending v0.2.0). Zero open GitHub issues and
zero open PRs. CI run 335 SUCCESS on main tip 1eb5731 (closes run 226's
own-commit verification). Container came up shallow again — unshallowed
before ancestry claims; all 5 roadmap/stage-* tips plus
feature/tool-conversion and feature/wildfire-demo re-proved merged
ancestors of main (feature/error-taxonomy re-measured at exactly 4 ahead,
the known Needs Luca 4 case).

Regression suite green at baseline: **701 passed / 2 skipped** (98s)
first-pass clean (the 1 warning is the known StarletteDeprecationWarning,
cosmetic); nats-server 2.10.24 via go install (copied to ~/.agentmesh/bin
per the standing reminder), nsc via `nsc/v2@v2.11.0` pin (self-reports
0.0.0-dev, known cosmetic; auth tests all ran). sdk-ts vitest 62/62
(11/11 files) ×5 consecutive — fifty-fifth consecutive clean ×5; admin UI
30/30 (5/5 files) after `pnpm build` in sdk-ts; ruff and ty both clean
from repo root.

Advanced: nothing — no unblocked work exists in any stage. Stage 4 remains
current; every open item across stages waits on a Needs-Luca answer.
Highest-leverage unblock is still OPENROUTER_API_KEY (items 6/11). No
notification sent: nothing changed.

Next run: check for Needs-Luca answers and credentials; if none, verify CI
on this run's own commit, regression-check against the 701/62/30 baseline
(nats-server + nsc via go install, copy nats-server to ~/.agentmesh/bin/
AND put GOPATH/bin on PATH before ANY test suite; pnpm install + `pnpm
build` in sdk-ts before ui vitest; unshallow before any ancestry claim or
push), log, end silently.

### 2026-09-11 ~06:15–06:45 UTC — run 226 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip is still run 225's own
commit ec6da9c — zero new commits of any kind since; Needs Luca section
untouched); no OPENROUTER_API_KEY or npm credential in the environment
(only proxy-config vars match a grep for openrouter/npm); remote refs
unchanged (same 9 heads, same SHAs, full branch list diffed against
expectations). Zero open GitHub issues and zero open PRs. CI run 334
SUCCESS on main tip ec6da9c (closes run 225's own-commit verification).
Container came up shallow again — unshallowed before ancestry claims
(pre-unshallow, merge-base misreported stage-1 as 200 ahead — the run-224
lesson holds); all 5 roadmap/stage-* tips plus feature/tool-conversion and
feature/wildfire-demo re-proved merged ancestors of main
(feature/error-taxonomy stays the known 4-ahead case, Needs Luca 4).

Regression suite green at baseline: **701 passed / 2 skipped** (97s)
first-pass clean; nats-server 2.10.24 via go install, nsc via `nsc/v2@v2.11.0`
pin (built on go1.24.7, self-reports 0.0.0-dev — known cosmetic; auth tests
all ran, no silent skips). sdk-ts vitest 62/62 (11/11 files) ×5 consecutive —
fifty-fourth consecutive clean ×5; admin UI 30/30 (5/5 files) after
`pnpm build` in sdk-ts; ruff and ty both clean from repo root. Setup
reminder re-earned: sdk-ts vitest spawns `~/.agentmesh/bin/nats-server` by
absolute path — copying the go-installed binary there is required, PATH
alone is not enough (first ×5 attempt failed all spawns with ENOENT until
the copy; not a regression).

Advanced: nothing — no unblocked work exists in any stage. Stage 4 remains
current; every open item across stages waits on a Needs-Luca answer.
Highest-leverage unblock is still OPENROUTER_API_KEY (items 6/11). No
notification sent: nothing changed.

Next run: check for Needs-Luca answers and credentials; if none, verify CI
on this run's own commit, regression-check against the 701/62/30 baseline
(nats-server + nsc via go install, copy nats-server to ~/.agentmesh/bin/
AND put GOPATH/bin on PATH before ANY test suite; pnpm install + `pnpm
build` in sdk-ts before ui vitest; unshallow before any ancestry claim or
push), log, end silently.

### 2026-09-11 — run 225 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip is still run 224's own
commit 0bc3943 — zero new commits of any kind since; Needs Luca section
untouched); no OPENROUTER_API_KEY or npm credential in the environment;
remote refs unchanged (same 9 heads, same SHAs — full branch list diffed
against expectations per the run-155 lesson). Zero open GitHub issues and
zero open PRs. CI run 333 SUCCESS on main tip 0bc3943 (closes run 224's
own-commit verification). Container came up shallow again — unshallowed
before ancestry claims; all 5 roadmap/stage-* tips plus
feature/tool-conversion and feature/wildfire-demo re-proved merged
ancestors of main (feature/error-taxonomy stays the known 4-ahead case,
Needs Luca 4).

Regression suite green at baseline: **701 passed / 2 skipped** (101s)
first-pass clean; nats-server 2.10.24 via go install, nsc via
`nsc/v2@latest` (built clean on go1.24.7 without a toolchain switch this
time, self-reports 0.0.0-dev as in run 222 — works fine; auth tests all
ran, no silent skips). sdk-ts vitest 62/62 (11/11 files) ×5 consecutive —
fifty-third consecutive clean ×5; admin UI 30/30 (5/5 files) after
`pnpm build` in sdk-ts; ruff and ty both clean from repo root. Sequencing
rule honored: no test suite started before nats-server was on PATH.

Advanced: nothing — no unblocked work exists in any stage. Stage 4 remains
current; every open item across stages waits on a Needs-Luca answer.
Highest-leverage unblock is still OPENROUTER_API_KEY (items 6/11). No
notification sent: nothing changed.

Next run: check for Needs-Luca answers and credentials; if none, verify CI
on this run's own commit, regression-check against the 701/62/30 baseline
(nsc + nats-server via go install with GOPATH/bin on PATH before ANY test
suite; pnpm install + `pnpm build` in sdk-ts before ui vitest; unshallow
before any ancestry claim or push), log, end silently.

### 2026-09-10 ~12:15–12:40 UTC — run 224 (Fable 5, cloud) — idle verification

Verified this run: no Luca edits (origin/main tip is still run 223's own
commit 4722384 — zero new commits of any kind since; Needs Luca section
untouched; the two state-file commits under Luca's git identity are runs
180/186's own executor log commits, re-checked, not answers); no
OPENROUTER_API_KEY or npm credential in the environment; remote refs
unchanged (same 9 heads). Zero open GitHub issues and zero open PRs. CI
run 332 SUCCESS on main tip 4722384 (closes run 223's own-commit
verification). Container came up shallow again — unshallowed before
ancestry claims; all 5 roadmap/stage-* tips plus feature/tool-conversion
and feature/wildfire-demo re-proved merged ancestors of main
(feature/error-taxonomy stays the known 4-ahead case, Needs Luca 4; a
pre-unshallow check misreported it as 135 ahead — shallow ancestry
results are worthless, unshallow first, always).

Regression suite green at baseline: **701 passed / 2 skipped** (95s)
first-pass clean; nats-server 2.10.24 + nsc v2.11.0 (pinned) via go
install, no proxy retries. sdk-ts vitest 62/62 (11/11 files) ×5
consecutive — fifty-second consecutive clean ×5; admin UI 30/30 (5/5
files) after `pnpm build` in sdk-ts (first ui attempt without the build
failed to collect, as the baseline requires — rebuilt and green); ruff
and ty both clean from repo root.

Advanced: nothing — no unblocked work exists in any stage. Stage 4 remains
current; every open item across stages waits on a Needs-Luca answer.
Highest-leverage unblock is still OPENROUTER_API_KEY (items 6/11). No
notification sent: nothing changed.

Next run: check for Needs-Luca answers and credentials; if none, verify CI
on this run's own commit, regression-check against the 701/62/30 baseline
(nsc + nats-server via go install with GOPATH/bin on PATH before ANY test
suite; pnpm install + `pnpm build` in sdk-ts before ui vitest; unshallow
before any ancestry claim), log, end silently.

