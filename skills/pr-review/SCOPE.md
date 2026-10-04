# Scope recovery

Reached from [SKILL.md](SKILL.md) when `comparison.status` is not `ready`. Every status carries a `reason`; recoverable statuses also carry a `note` and `suggested_fetches` or `command_templates`. That output is the source of truth for recovery commands; this file covers the judgement the helper cannot make.

Recovery ends in the first of these that succeeds:

1. Recover and rerun the helper until it reports `ready`.
2. Fall back to the GitHub PR diff (`gh pr diff`) when a PR exists, recording the reduced context under **Limits**.
3. Stop and report the status, `reason`, and `errors`.

Present findings only on a resolved comparison or a disclosed PR-diff fallback.

## needs_base

No user-specified base and no open PR was found; if the PR lookup failed, a user-specified `--base` still works without gh. Weigh `parent_evidence`:

- **`metadata`**: base names left in branch config by gh or VS Code. Treat as a lead to corroborate against the reflogs.
- **`branch_reflog`**: the oldest entry records the branch's start point (`branch: Created from main`). When it reads `Created from HEAD` (as `git switch -c` writes), find the `head_checkouts` entry `checkout: moving from X to <branch>` with the same timestamp; `X` is the parent.
- Reflogs expire and rebases rewrite them, so missing or conflicting entries leave the parent unestablished.

Rerun with `--base <parent>` once the evidence is unambiguous and corroborated; otherwise ask the user for the base.

## missing_objects

One or both comparison commits are absent locally. Verify the source in `suggested_fetches`, or substitute a verified remote into `command_templates`; fetch only those refs and rerun. Report a failed fetch rather than comparing against stale refs. If the objects stay unavailable, take the PR-diff fallback.

## incomplete_history

A shallow clone hides the merge-base. Run the scoped deepening fetch and rerun, raising the `--deepen` increment while history stays incomplete. A shallow repository without a merge-base has not proven the histories unrelated; if deepening is unavailable, take the PR-diff fallback.

## historical_pr

A closed or merged PR reviewed without `--base`. Review the historical diff from the emitted `gh pr diff` command rather than today's target branch, and read surrounding code at `head_sha` (fetch it first when `suggested_fetches` is present). Pass `--base` only when the user asks for a custom comparison, and flag it in the report.

## no_merge_base

Full history with no common ancestor: the base is wrong or the histories are unrelated. Confirm the base with the user.

## blocked

An explicit PR or base could not be verified, or the live PR target lookup failed. Read `reason` and `errors`, correct the input (for example `--repo` for a PR URL in another repository), and rerun; otherwise stop.
