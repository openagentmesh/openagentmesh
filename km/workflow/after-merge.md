# After Merge

## Cleanup steps

After the feature branch is merged into `main`:

### 1. Remove the worktree

```bash
git worktree remove .worktrees/<name>
```

### 2. Delete the local branch

```bash
git branch -d feature/<name>
```

(Use `-D` only if the branch isn't fully merged — should not happen with the `--no-ff` flow.)

### 3. Delete the remote branch

```bash
git push origin --delete feature/<name>
```

Or configure GitHub to auto-delete merged branches in repository settings.

### 4. Verify the ADR index

`main` should reflect:
- Branch names retained in the ADR index as historical record.
- ADR statuses updated to `implemented` or `documented`.

If multiple in-progress sessions exist on other worktrees, those sessions should re-read `km/adr/index.md` to pick up status changes (do not merge `main` into a feature branch just to sync the index).

## Pruning stale worktrees

Periodically check for worktrees that no longer have an active branch:

```bash
git worktree list
git worktree prune
```
