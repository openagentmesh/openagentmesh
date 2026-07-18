# H2 2026 roadmap — cron executor state

Machine-maintained by the "OAM H2 roadmap executor" routine. Humans may edit (e.g. to
answer a "Needs Luca" item); the executor re-verifies everything against the repo anyway.

## Current stage

Stage 3 — Production trust (shaping pass done run 4; prioritized plan in
km/notes/2026-07-17-stage3-plan.md awaiting sign-off, item 10; executing the
plan's default order meanwhile).
ADR-0038 auth: COMPLETE (run 5, merged 9502f52).
ADR-0016+0040 liveness pair: COMPLETE (run 6) — health monitor, death
notices, caller fast-fail, docs — merged to main af5a96a (--no-ff), CI
success on branch tip e3733e6 (run 35). **Both Stage 3 exit criteria are
now met**: secured-mesh cookbook (run 5) and the chaos kill-mid-request
test (tests/test_liveness.py::test_call_fast_fails_when_agent_dies_mid_request,
passing — caller gets agent_died in ~1s against a 30s timeout).
ADR-0048 observability v1: COMPLETE (run 7) — merged to main 3e5e486.
ADR-0055 lifecycle gates: COMPLETE (run 8) — merged to main b7e4093.
ADR-0056 admin UI: IN PROGRESS (started run 9) — wave 1 of 5 merged to
main 7b48e99 (websocket listener on dev meshes, `oam ui` static server +
config.json, ADR amended against the shipped repo). Build waves tracked in
km/notes/2026-07-18-adr0056-ui-plan.md; next run continues with wave 2
(ui/ frontend scaffold; the browser client is `@openagentmesh/sdk` via
workspace link — see the plan note and the 2026-07-18 ADR amendment).
Stage 2 remains open only on Needs-Luca items (demo, docs URL, draft review,
publishing). Stage 1 open only on npm publish. Stage 0 open only on its
Needs-Luca items (wildfire merge, worktrees, v0.3.0).

## Stage checklist

- [ ] Stage 0 — Consolidate (blocked on Needs-Luca items below; everything else done)
- [ ] Stage 1 — Interop (core done: MCP bridge, to_agent_card, docs; npm publish blocked)
- [ ] Stage 2 — Launch (drafts + README fold done; demo/URL/publishing need Luca)
- [ ] Stage 3 — Production trust
- [ ] Stage 4 — Frontier

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
5. **ADR-0056 admin UI** — IN PROGRESS (run 9). Wave 1/5 merged to main
   7b48e99; ADR index at `test`. Waves in km/notes/2026-07-18-adr0056-ui-plan.md.
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
   - Remaining: waves 2–5 (frontend scaffold + registry screen, sandbox,
     event feed + liveness dots, packaging/e2e/docs).

## Run log

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
