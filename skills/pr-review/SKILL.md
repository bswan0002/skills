---
name: pr-review
description: Review a pull request or the current branch for actionable bugs and regressions. Use when asked for a PR review, branch review, or a check before merging.
---

Review the changes intended for merge. Leave code and working-tree files unchanged; fixes require a separate request.

## Establish the scope

Read the repository's agent instructions. From its worktree, run the helper using its absolute path resolved relative to **this skill**, not the target repository:

```bash
python3 /absolute/path/to/pr-review/scripts/pr-context.py
# Optional: explicit comparison, PR, target repository, or publishing remote
python3 /absolute/path/to/pr-review/scripts/pr-context.py --base parent-branch
python3 /absolute/path/to/pr-review/scripts/pr-context.py --pr 123 --repo owner/repo
```

Requires Python 3.9+, git, and authenticated gh for GitHub discovery. The helper is read-only: it reports status, remotes, PR lookup results, parent evidence, and fixed-commit diff commands. It never fetches or guesses a parent. A nonzero exit means the local comparison is not ready; read the JSON reason.

Choose the base in this order: **user-specified base → open PR's target → unambiguous, history-corroborated local parent evidence → ask**. The helper resolves the first two; evaluate its raw metadata/reflogs for the third and rerun with `--base` only once the parent is established. Creation from `HEAD` needs checkout-history correlation. Conflicting or incomplete evidence requires clarification.

Verify the reported target and head repository identities. `--head-remote` overrides the publishing remote (tracking remote, otherwise origin); `--repo` overrides gh's target repository. A tracking upstream, nearest merge-base, conventional branch name, or `HEAD~1` does not establish the parent.

Surface lookup errors rather than treating them as no PR. Another source may establish scope independently. Explicit bases resolve locally: check remote freshness separately when reviewing against a live remote branch. Disclose a custom comparison if the requested base differs from the PR target.

## Resolve the comparison

If the helper reports missing objects, verify its suggested fetch source, fetch only the required refs, and rerun. Fetching Git objects/refs is allowed; leave the checkout, index, and working-tree files unchanged. Report failures instead of silently using stale refs. If objects remain unavailable, use the GitHub PR diff and disclose limits on surrounding context.

For `incomplete_history`, deepen the comparison histories using the suggested scoped fetch or a command template with a verified source substituted, then rerun. Increase the depth increment if needed. A shallow repository without a merge-base does not establish unrelated histories; if recovery is unavailable, use the PR diff or report the limitation.

The default reviews committed local `HEAD`; `--pr` reviews the published PR head. Closed/merged PRs use the historical PR diff unless a custom base was requested. Keep uncommitted changes separate and include them only when requested.

Use the emitted fixed-SHA commands throughout the review. Three-dot excludes target-only changes. Stop if the comparison cannot be resolved. State base, head, selection evidence, and scope exclusions before presenting findings.

## Review

Read the full diff and relevant surrounding code. Follow changed behavior through callers, dependencies, and tests as needed to establish whether an issue is real. Inspect repository conventions rather than imposing personal preferences.

Prioritize correctness, regressions, security, data loss, concurrency, and compatibility. Flag a missing test when it leaves a concrete changed behavior unprotected, not as generic advice. Run checks only when they will not modify files or external state; otherwise explain what remains unverified.

Report actionable issues introduced by the changes. For each finding, give:

- **Severity and short title** (`critical`, `high`, `medium`, or `low`).
- **File and line**, pointing to the smallest relevant changed range.
- **Trigger and impact:** the conditions under which the problem occurs and what breaks.
- **Suggested fix**, briefly, when useful.

Separate uncertain concerns from confirmed findings and identify the evidence needed to settle them. Skip style nits and generic advice. If no actionable issues are found, say so; include material review limits or unverified behavior without implying the code is proven correct.
