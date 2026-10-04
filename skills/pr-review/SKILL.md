---
name: pr-review
description: Reviews published GitHub pull requests for actionable bugs and regressions. Use when asked for a PR review or a PR's pre-merge check.
---

Review the **published PR**, not local `HEAD` or uncommitted changes. The review is **read-only**: leave the checkout, index, working-tree files, and external state (PR comments, pushes, remote refs) as you found them. Fetching Git objects and refs is the one permitted write. Fixes require a separate request.

## Scope

From the target worktree, run the helper by its absolute path under this skill's base directory (`--pr <URL>` or `--pr <number> --repo <owner/name>` selects an explicit PR):

```bash
python3 <skill-dir>/scripts/pr-context.py
```

The helper uses `gh pr status` to discover a candidate and `gh pr list` to verify open matches. Check its `status`:

- **`found`**: confirm the intended PR and repository, then run `diff_command` (`gh pr diff <PR-URL>`).
- **`ambiguous`**: ask which listed PR to review and rerun with `--pr`.
- **`needs_pr`**: ask for a PR; unresolved discovery does not prove no PR exists.
- **`failed`**: report the error and stop until it is resolved.

## Review

Read the full PR diff. Read surrounding code at `pr.headRefOid` (`git show <sha>:<path>`, `git grep <pattern> <sha>`), not the working tree. If the commit is missing, fetch `refs/pull/<number>/head` from the target repository without changing the checkout; if unavailable, disclose the missing context. Trace changed behavior through callers, dependencies, and tests until each suspected issue is confirmed or ruled out, judging against the repository's conventions and agent instructions. If the PR changes during review, refresh its metadata and diff before reporting.

Prioritize correctness, regressions, security, data loss, concurrency, and compatibility. A missing test is a finding when it leaves a concrete changed behavior unprotected. Run checks only when they are read-only; record the rest as unverified.

Use `gh pr view <PR-URL> --json files` as the file checklist. The review is done when every changed file is either reviewed or listed as excluded with a reason.

## Report

Open with a scope header:

- **Scope**: PR URL, target branch, and published head SHA; the comparison is GitHub's PR diff.
- **Exclusions**: skipped files with reasons; local-only changes are outside this review.
- **Limits**: missing context, unverified behavior, and unrun checks. Tests run from a different revision are not verification of the PR head.

Then list **actionable** findings introduced by the changes, ordered by severity:

- `critical`: data loss, security exposure, or a broken primary path in normal use.
- `high`: wrong behavior or a regression on a common path.
- `medium`: wrong behavior under an edge case or uncommon configuration.
- `low`: a minor defect with limited impact or an easy workaround.
- `nit`: a non-blocking stylistic inconsistency or readability/presentation issue with no behavioral impact.

For each finding give:

- **Severity and short title.**
- **File and line**, pointing to the smallest relevant changed range.
- **Trigger and impact**: the conditions under which it occurs and what breaks; nits excluded.
- **Suggested fix**, briefly, when useful.

List uncertain concerns after the findings, each with the evidence that would settle it. With no actionable findings, say so; the header's limits keep that from claiming the code is proven correct.
