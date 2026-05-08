# During a Parallel Work Session

## Working rules

- All code changes happen in the worktree. No commits to `main` except the initial claim.
- Follow the DDD pipeline: write failing tests from ADR code samples, implement until green, refactor, finalize docs.
- Commits are atomic per logical unit. Not one big commit at the end.

## Overlap detection

If you discover your work needs to touch code or ADRs claimed by another active branch:

1. Stop and check the ADR index to confirm the overlap.
2. Flag the conflict to the user with specifics: which ADR, which files, what the overlap is.
3. Wait for the user's decision before proceeding. Options include:
   - Skip the overlapping work and note it in the PR description.
   - Coordinate with the other session (user mediates).
   - Take over the overlapping ADR (user reassigns the claim).

## Staying focused

Each worktree session should stay within the scope of its claimed ADRs. If you discover adjacent work that would be valuable but is out of scope, note it as a recommendation in the PR description rather than doing it.

## Communication

If the session is long-running or hits a significant decision point, surface it to the user rather than making assumptions. The user may be supervising multiple sessions and needs clear, concise status updates.

## Multi-wave work (optional inner GSD)

If the claimed ADR (or related ADR group) is too large for a single coding session -- multiple waves of work, coupled across components, expected to span days -- inner GSD inside the worktree is available. Bootstrap with `/gsd-new-project` after the worktree's `uv sync`.

When inner GSD is active:

- The **DDD pipeline above applies per phase**, not per ADR. Each phase's plan defines its own failing-test / implementation / docs cycle.
- **Atomic commits** rule still holds: each task in each phase gets its own commit. Phase boundaries are explicit checkpoints with their own resume artifacts.
- The umbrella ADR's status (in `km/adr/index.md`) moves on the OUTER pipeline (`spec` -> `test` -> `implemented` -> `documented`), not per phase. A wave landing green doesn't move the ADR; the ADR moves when the umbrella decision's lifecycle requires it.

`.planning/` is gitignored at the project level, so phase artifacts (PROJECT.md, REQUIREMENTS.md, ROADMAP.md, STATE.md, phase plans) stay in the worktree's local filesystem and never reach main on merge. The shared reference for all worktrees lives at `km/codebase/` and `km/research/` (tracked); the design source for a feature lives at `km/specs/<feature>/` (tracked).

See `CLAUDE.md` "Outer/Inner workflow" sections for the full boundary.
