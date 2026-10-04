---
name: pr-review
description: Reviews changes for actionable bugs and regressions before merge. Use when asked for a PR review, branch review, or pre-merge check.
---

Review the changes intended for merge. The review is **read-only**: leave the checkout, index, working-tree files, and external state (PR comments, pushes, remote refs) as you found them. Fetching Git objects and refs is the one permitted write. Fixes require a separate request.

## Scope

From the target worktree, run the helper by its absolute path under this skill's base directory, not the target repository's (`--help` lists `--base`, `--pr`, `--repo`, `--head-remote`):

```bash
python3 <skill-dir>/scripts/pr-context.py
```

Only these establish the base, in order: **user-specified base → open PR's target → unambiguous, history-corroborated local parent evidence → ask the user**. A tracking upstream, nearest merge-base, conventional branch name, or `HEAD~1` is not parent evidence.

On every run, check `pr_lookup` and `errors` whatever the comparison status. A `failed` lookup is an error to report under **Limits**, not an absent PR; for `ambiguous`, ask which PR is meant and rerun with `--pr`. Confirm `target_repository` and `head_repository` name the repositories you mean to review; correct them with `--repo` or `--head-remote`.

The default reviews committed local `HEAD`; `--pr` reviews the published PR head. Include uncommitted changes only on request, reported separately. When `base_selection.freshness` says the base is local-only, check it against its remote before relying on it.

When `comparison.status` is `ready`, use its emitted commands throughout. For any other status, read [SCOPE.md](SCOPE.md) under that status first.

## Review

Read the full diff. Read surrounding code at `head_sha` (`git show <head_sha>:<path>`, `git grep <pattern> <head_sha>`); the working tree may hold another branch or uncommitted edits. Trace changed behavior through callers, dependencies, and tests until each suspected issue is confirmed or ruled out, judging against the repository's conventions and agent instructions.

Prioritize correctness, regressions, security, data loss, concurrency, and compatibility. A missing test is a finding when it leaves a concrete changed behavior unprotected. Run checks only when they are read-only; record the rest as unverified.

The review is done when every file in `--name-status` is either reviewed or listed as excluded with a reason.

## Report

Open with a scope header:

- **Base and head**: refs and SHAs.
- **Base selection**: the source and its evidence; flag a custom comparison when the base differs from the PR target.
- **Exclusions**: skipped files and uncommitted changes, with reasons.
- **Limits**: PR lookup errors, unverified behavior, unrun checks, and reduced context such as a PR-diff fallback.

Then list **actionable** findings introduced by the changes, ordered by severity:

- `critical`: data loss, security exposure, or a broken primary path in normal use.
- `high`: wrong behavior or a regression on a common path.
- `medium`: wrong behavior under an edge case or uncommon configuration.
- `low`: a minor defect with limited impact or an easy workaround.

For each finding give:

- **Severity and short title.**
- **File and line**, pointing to the smallest relevant changed range.
- **Trigger and impact**: the conditions under which it occurs and what breaks.
- **Suggested fix**, briefly, when useful.

List uncertain concerns after the findings, each with the evidence that would settle it. With no actionable findings, say so; the header's limits keep that from claiming the code is proven correct.
