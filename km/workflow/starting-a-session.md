# Starting a Parallel Work Session

## Prerequisites

- One or more ADRs at `spec` status with code samples in the ADR body.
- You (or the user) have decided these ADRs are ready for the test-implement-document cycle.

## Steps

### 1. Read the ADR index

On `main`, read `km/adr/index.md`. Check the **Branch** column for your target ADRs.

- If the Branch column is empty: proceed to claim.
- If a branch is listed: check whether it's still active (open PR, worktree exists, or recent commits). If active, flag the overlap to the user and ask how to proceed. If merged or abandoned, clear the old branch name before reclaiming.

### 2. Claim the ADRs

Add your branch name to the Branch column for each target ADR. Use a descriptive slug, not ADR numbers:

```markdown
| ADR-0024 | Streamer or responder handler contract | spec | feature/handler-types |
```

Multiple related ADRs can share the same branch name.

Commit to `main`:

```
claim: ADRs 0023b, 0024 for feature/handler-types
```

### 3. Create the worktree

```bash
git worktree add .worktrees/<name> -b feature/<name>
cd .worktrees/<name>
```

### 4. Install dependencies and verify baseline

```bash
uv sync
pytest
```

If tests fail, report the failures before starting work. Do not proceed with a broken baseline without the user's explicit approval.

### 5. Start the TDD cycle

Extract the ADR code samples into failing tests under `tests/`. Follow the DDD pipeline: test (red), implement (green), refactor, finalize docs.
