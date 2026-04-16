# After Merge

## Cleanup steps

After the PR is merged on GitHub:

### 1. Remove the worktree

```bash
git worktree remove .worktrees/<name>
```

### 2. Delete the remote branch

```bash
git push origin --delete feature/<name>
```

Or configure GitHub to auto-delete branches after merge (repository settings, "Automatically delete head branches").

### 3. Pull main

```bash
git checkout main
git pull
```

### 4. Verify the ADR index

After merge, `main` should reflect:
- Branch names in the ADR index as historical record.
- ADR statuses updated (e.g., `implemented`, `documented`).

If the merge introduced status changes that conflict with other in-progress sessions' view of the index, those sessions should pull the latest `main` into their awareness (read the file, not merge main into the feature branch).

## Pruning stale worktrees

Periodically check for worktrees that no longer have an active branch:

```bash
git worktree list
git worktree prune
```
