# H2 2026 roadmap — cron executor state

Machine-maintained by the "OAM H2 roadmap executor" routine. Humans may edit (e.g. to
answer a "Needs Luca" item); the executor re-verifies everything against the repo anyway.

## Current stage

Stage 0 — Consolidate (in progress; all cloud-doable items done, 3 items blocked on Luca)

## Stage checklist

- [ ] Stage 0 — Consolidate (blocked on Needs-Luca items below; everything else done)
- [ ] Stage 1 — Interop
- [ ] Stage 2 — Launch
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

## Needs Luca

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

## Run log

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
