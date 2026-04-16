# Parallel Worktree Workflow Design

**Date:** 2025-04-16
**Status:** Approved

## Problem

OpenAgentMesh development involves multiple ADRs that can be implemented independently. Working on them sequentially is slow. Running multiple Claude Code sessions in parallel requires isolation so they don't conflict on shared files.

## Decision

Use git worktrees with a claim-and-PR workflow. Each implementation session works in an isolated worktree. The ADR index serves as the claim registry. PRs are the merge gate and discussion platform.

## Design

### Isolation Rule

- **Worktrees are the building space.** All code changes (`src/`, `tests/`, `docs/`, `pyproject.toml` dependencies, etc.) happen inside a worktree, never directly on `main`.
- **`main` is the thinking space.** Direct changes on `main` are limited to `km/` (knowledge management: ADRs, specs, notes, brainstorming), `CLAUDE.md`, and project config files.

### Worktree Trigger

A worktree is created when an ADR (or group of related ADRs) reaches `spec` status and is ready for the test-implement-document cycle. Worktrees are an implementation tool, not a design tool. Brainstorming, shaping, and ADR writing happen on `main`.

### Directory Structure

- Worktrees live in `.worktrees/` at the project root, gitignored.
- Branch naming: `feature/<short-name>` where the short name is a descriptive slug (e.g., `feature/handler-types`). Not tied to ADR numbers since a branch can span multiple ADRs.

### ADR Index as Claim Registry

The `km/adr/index.md` table has a **Branch** column:

```markdown
| ADR | Decision | Status | Branch |
|-----|----------|--------|--------|
| ADR-0024 | Streaming or buffered handler contract | discussion | feature/handler-types |
| ADR-0025 | Public API for shared context KV | discussion | |
```

- Empty Branch column = unclaimed.
- Filled = active or historical (status indicates which).
- Multiple ADRs can share a branch for tightly coupled decisions.
- Branch names stay in the index after merge as a historical record.

### Claim Protocol

1. Session reads `km/adr/index.md` on `main`.
2. Verifies target ADRs have no branch listed.
3. Writes branch name into the Branch column for each claimed ADR.
4. Commits to `main` with message like `claim: ADRs 0023b, 0024 for feature/handler-types`.
5. Creates the worktree and starts working.

### Overlap Handling

If a target ADR already has a branch listed:
- Check whether the existing branch is still active (open PR or worktree exists).
- If active: flag the overlap to the user and ask how to proceed.
- If merged/abandoned: clear the old branch name and reclaim.

### Session Lifecycle

**Starting:**
1. Read ADR index, verify unclaimed.
2. Claim ADRs in index, commit to `main`.
3. `git worktree add .worktrees/<name> -b feature/<name>`.
4. `uv sync` + `pytest` baseline.
5. Start TDD cycle from ADR code samples.

**During:**
- All work in the worktree. No commits to `main` except the initial claim.
- Follow DDD pipeline: test, implement, finalize docs.
- Flag overlap if session discovers it needs to touch a claimed ADR.

**Finishing:**
1. All tests pass, docs updated.
2. Push branch to origin.
3. Open draft PR referencing the ADRs.
4. Update ADR statuses (e.g., `spec` to `implemented`).
5. Report PR URL to user.

**After merge:**
- `git worktree remove .worktrees/<name>`, delete remote branch.
- ADR index on `main` retains branch name as historical record, status updated via merged PR.

### PR Workflow

PRs serve as:
- **Atomic merge unit:** feature lands as one coherent unit.
- **Discussion platform:** line-level comments, iteration with cloud Claude.
- **Historical record:** PR description narrates the feature.

Sessions open draft PRs. User promotes to ready and merges on their schedule. No branch protection or approval rules.

## Documentation Structure

- **CLAUDE.md:** Core principles and rules (isolation rule, trigger, claim protocol summary, overlap detection, PR summary).
- **`km/workflow/`:** Detailed step-by-step procedures per lifecycle stage:
  - `starting-a-session.md`
  - `during-a-session.md`
  - `finishing-a-session.md`
  - `after-merge.md`
