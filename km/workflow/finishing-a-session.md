# Finishing a Parallel Work Session

## Completion checklist

Before pushing, verify:

1. All tests pass (`pytest`).
2. Code samples in `docs/` match the implementation.
3. ADR statuses are updated in the worktree's copy of `km/adr/index.md` (e.g., `spec` to `implemented` or `documented`).
4. No unrelated changes crept in.

## Push and open PR

```bash
git push -u origin feature/<name>
```

Open a draft PR using `gh`:

```bash
gh pr create --draft --title "<short description>" --body "Implements ADR-0024, ADR-0023b.

## Summary
- <what was built>
- <key decisions made during implementation>

## ADRs
- ADR-0024: <status change>
- ADR-0023b: <status change>

## Notes
- <any overlap discovered, out-of-scope recommendations, or open questions>
"
```

## Report to user

Provide:
- PR URL
- Summary of what was implemented
- Any issues, open questions, or recommendations for follow-up work
