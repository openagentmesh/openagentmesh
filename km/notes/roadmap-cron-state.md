# H2 2026 roadmap — cron executor state

Machine-maintained by the "OAM H2 roadmap executor" routine. Humans may edit (e.g. to
answer a "Needs Luca" item); the executor re-verifies everything against the repo anyway.

## Current stage

Stage 3 — Production trust (shaping pass done run 4; prioritized plan in
km/notes/2026-07-17-stage3-plan.md awaiting sign-off, item 10; executing the
plan's default order — ADR-0038 auth first — meanwhile).
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

## Run log

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
