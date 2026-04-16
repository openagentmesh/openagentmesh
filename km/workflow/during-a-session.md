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
