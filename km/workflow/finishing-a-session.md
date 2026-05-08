# Finishing a Parallel Work Session

## Completion checklist

Before merging, verify:

1. All tests pass (`pytest`).
2. Code samples in `docs/` match the implementation.
3. ADR statuses are updated in the worktree's copy of `km/adr/index.md` (e.g., `spec` to `implemented` or `documented`).
4. `CHANGELOG.md` updated: add entries under `[Unreleased]` for user-visible changes. Write for users, not developers.
5. No unrelated changes crept in (`git diff main...HEAD`).

## Optional: visual diff review

If the change is large or touches public API, browse the diff in GitHub's UI before merging:

```bash
gh browse "main...$(git branch --show-current)"
```

This catches whitespace/rename framing the local diff doesn't surface. No PR needed.

## Merge into main

From inside the worktree, push the branch first (so the merge commit references a remote ref):

```bash
git push -u origin feature/<name>
```

Then from the main checkout (not the worktree):

```bash
cd /path/to/main/checkout
git checkout main
git pull --ff-only
git merge --no-ff feature/<name> -m "merge: <short description> (ADR-NNNN)"
git push origin main
```

`--no-ff` keeps the branch shape and individual commits in the history — no squash, no flatten.

## Cleanup

See `km/workflow/after-merge.md`.

## Report to user

Provide:
- The merge commit SHA
- Summary of what was implemented
- Any issues, open questions, or recommendations for follow-up work

## When to use a PR instead

Skip the direct-merge flow and open a PR when:
- CI must gate the merge (status checks are configured and meaningful)
- External contributors are reviewing
- The work anchors a release cut and a PR-as-changelog artifact is wanted

Otherwise, PRs are ceremony without payoff for this solo project.
