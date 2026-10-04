---
name: pr-review
description: Review a pull request or the current branch for actionable bugs and regressions. Use when asked for a PR review, branch review, or a check before merging.
---

Review the changes intended for merge. Leave code and working-tree files unchanged; fixes require a separate request.

## Establish the scope

Read the repository's agent instructions. Inspect the current branch, remotes, and working-tree status. Keep committed changes separate from uncommitted changes; include the latter only when requested.

Choose the base in this order:

1. **Explicit base:** use the user's requested branch or commit. If it differs from an existing PR's target, state that this is a custom comparison.
2. **Open PR:** use its target branch in its target repository. For the current branch, start with:

   ```bash
   gh pr view --json url,state,baseRefName,baseRefOid,headRefName,headRefOid
   ```

   For a supplied PR URL or number, inspect that PR explicitly. Verify its state and repository/head identity; a closed or merged PR is not an open-PR fallback. An explicitly requested closed or merged PR needs its actual PR diff, not a comparison against today's target branch.
3. **Local parent evidence:** inspect branch-base metadata and the branch creation reflog. Examples of metadata are `branch.<name>.gh-merge-base`, `branch.<name>.vscode-merge-base`, and `branch.<name>.github-pr-base-branch`. Use a parent only when the evidence is unambiguous, the ref resolves, and history corroborates it. A creation entry from `HEAD` needs the corresponding checkout history to identify the branch.
4. **Uncertain:** ask which branch or commit to compare against before reviewing.

Distinguish a confirmed absence of an open PR from failed lookup, missing authentication, or unavailable tooling. Surface lookup failures; use another source only if it independently establishes the scope.

Tracking upstream usually names the published copy of the current branch, not its parent. The nearest merge-base, a conventional branch name such as `main`, and `HEAD~1` are not sufficient evidence of the intended target. Conflicting or missing evidence calls for clarification, not a best guess.

## Resolve the comparison

Verify the base repository rather than assuming `origin` is correct, especially for forks. Resolve the current target commit using that repository. If fetching is needed, fetch only the required branch from the verified remote; fetching Git objects/refs is allowed, but leave the checkout, index, and working-tree files unchanged. Report fetch failures instead of silently treating stale refs as current.

For a local branch review, use the committed local `HEAD`. For an explicit PR review, use the PR's head; local `HEAD` may be ahead, behind, or unrelated. If PR objects cannot be obtained locally, inspect the PR diff through GitHub and disclose any limits on surrounding context.

Resolve base and head to commit IDs and use those fixed IDs throughout the review:

```bash
git diff --stat <base-sha>...<head-sha>
git diff --name-status <base-sha>...<head-sha>
git diff <base-sha>...<head-sha>
```

Three-dot compares the head with its merge-base against the target, excluding target-only changes. If the refs or merge-base cannot be resolved, stop and explain what is missing.

State the base, head, source of the base selection, and any scope exclusions before presenting findings.

## Review

Read the full diff and relevant surrounding code. Follow changed behavior through callers, dependencies, and tests as needed to establish whether an issue is real. Inspect repository conventions rather than imposing personal preferences.

Prioritize correctness, regressions, security, data loss, concurrency, and compatibility. Flag a missing test when it leaves a concrete changed behavior unprotected, not as generic advice. Run checks only when they will not modify files or external state; otherwise explain what remains unverified.

Report actionable issues introduced by the changes. For each finding, give:

- **Severity and short title** (`critical`, `high`, `medium`, or `low`).
- **File and line**, pointing to the smallest relevant changed range.
- **Trigger and impact:** the conditions under which the problem occurs and what breaks.
- **Suggested fix**, briefly, when useful.

Separate uncertain concerns from confirmed findings and identify the evidence needed to settle them. Skip style nits and generic advice. If no actionable issues are found, say so; include material review limits or unverified behavior without implying the code is proven correct.
