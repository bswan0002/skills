#!/usr/bin/env python3
"""Read-only review discovery. Python 3.9+, git, and optionally authenticated gh."""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from urllib.parse import quote


class DiscoveryError(Exception):
    pass


def run(*args):
    result = subprocess.run(args, text=True, capture_output=True, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    if result.returncode:
        raise DiscoveryError(f"{shlex.join(args)}: {result.stderr.strip() or 'command failed'}")
    return result.stdout.strip()


def optional(*args):
    try:
        return run(*args)
    except DiscoveryError:
        return None


def github_repo(url):
    match = re.fullmatch(r"(?:https?://github\.com/|ssh://git@github\.com/|git@github\.com:)([^/]+/[^/]+?)(?:\.git)?/?", url)
    return match.group(1) if match else None


def commit(ref):
    return optional("git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}")


def parent_evidence(branch):
    if not branch:
        return {}
    metadata = {}
    for key in ("gh-merge-base", "vscode-merge-base", "github-pr-base-branch"):
        value = optional("git", "config", "--get", f"branch.{branch}.{key}")
        if value:
            metadata[key] = {"value": value, "local_commit": commit(value)}
    # Raw, timestamped evidence, not an inferred parent. HEAD creation requires
    # checkout correlation; expired/rebased reflogs may not establish a parent.
    return {
        "metadata": metadata,
        "branch_reflog": optional("git", "reflog", "show", "--date=iso-strict", "--format=%H %gD %gs", branch),
        "head_checkouts": optional("git", "reflog", "show", "-n", "100", "--date=iso-strict", "--format=%H %gD %gs", "HEAD"),
    }


PR_FIELDS = "number,url,state,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner"


def lookup_pr(repo, branch, head_repo, requested=None):
    if requested:
        pr = json.loads(run("gh", "pr", "view", requested, "--repo", repo, "--json", PR_FIELDS))
        # A URL must identify a PR in the selected target repository.
        if not pr["url"].lower().startswith(f"https://github.com/{repo}/pull/".lower()):
            raise DiscoveryError("PR URL and target repository disagree; pass --repo for the URL's repository")
        return {"status": "found", "pr": pr}
    if not branch or not head_repo:
        return {"status": "unavailable", "reason": "Cannot verify current branch's GitHub head repository; use --head-remote or --pr"}
    prs = json.loads(run("gh", "pr", "list", "--repo", repo, "--state", "open", "--head", branch, "--limit", "1000", "--json", PR_FIELDS))
    if len(prs) >= 1000:
        raise DiscoveryError("PR lookup may be truncated; inspect an explicit PR instead")
    matches = []
    for pr in prs:
        owner = (pr.get("headRepositoryOwner") or {}).get("login")
        name = (pr.get("headRepository") or {}).get("name")
        if not owner or not name:
            raise DiscoveryError("PR lookup returned unverifiable head repository identity")
        if pr["headRefName"] == branch and f"{owner}/{name}".lower() == head_repo.lower():
            matches.append(pr)
    if len(matches) > 1:
        return {"status": "ambiguous", "prs": matches}
    return {"status": "found", "pr": matches[0]} if matches else {"status": "absent"}


def comparison(base_sha, head_sha):
    missing = [sha for sha in (base_sha, head_sha) if not commit(sha)]
    if missing:
        return {"status": "missing_objects", "commits": missing}
    merge_base = optional("git", "merge-base", base_sha, head_sha)
    if not merge_base:
        return {"status": "no_merge_base"}
    span = f"{base_sha}...{head_sha}"
    return {
        "status": "ready", "base_sha": base_sha, "head_sha": head_sha,
        "merge_base": merge_base,
        "commands": [shlex.join(["git", "diff", *flags, span]) for flags in (["--stat"], ["--name-status"], [])],
    }


def discover(args):
    root = run("git", "rev-parse", "--show-toplevel")
    branch = run("git", "branch", "--show-current")
    head = run("git", "rev-parse", "HEAD")
    remote_names = run("git", "remote").splitlines()
    remotes = {name: run("git", "remote", "get-url", name) for name in remote_names}
    upstream_remote = optional("git", "config", "--get", f"branch.{branch}.remote") if branch else None
    head_remote = args.head_remote or upstream_remote or ("origin" if "origin" in remotes else None)
    if args.head_remote and args.head_remote not in remotes:
        raise DiscoveryError(f"Unknown head remote: {args.head_remote}")
    head_repo = github_repo(remotes.get(head_remote, ""))
    result = {
        "repository_root": root, "branch": branch or None, "local_head": head,
        "working_tree": run("git", "status", "--short"), "remotes": remotes,
        "head_repository": head_repo, "parent_evidence": parent_evidence(branch),
        "errors": [],
    }
    repo = args.repo
    # An explicit local comparison remains usable if gh is unavailable.
    try:
        repo = repo or json.loads(run("gh", "repo", "view", "--json", "nameWithOwner"))["nameWithOwner"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise DiscoveryError("Expected a GitHub repository in owner/name form")
        result["target_repository"] = repo
        result["pr_lookup"] = lookup_pr(repo, branch, head_repo, args.pr)
    except (DiscoveryError, OSError, ValueError, KeyError) as exc:
        result["pr_lookup"] = {"status": "failed", "reason": str(exc)}
        result["errors"].append(str(exc))
    lookup = result["pr_lookup"]
    pr = lookup.get("pr")
    if args.pr and not pr:
        result["comparison"] = {"status": "blocked", "reason": "Explicit PR could not be verified"}
        return result
    if args.pr and pr["state"] != "OPEN" and not args.base:
        result["comparison"] = {
            "status": "historical_pr", "reason": "Use the historical PR diff, not today's target branch",
            "commands": [shlex.join(["gh", "pr", "diff", str(pr["number"]), "--repo", repo])],
        }
        return result
    review_head = pr["headRefOid"] if args.pr else head
    if args.base:
        base_sha = commit(args.base)
        result["base_selection"] = {"source": "explicit", "ref": args.base, "sha": base_sha, "freshness": "local; not checked against remote"}
        result["comparison"] = comparison(base_sha, review_head) if base_sha else {"status": "blocked", "reason": "Explicit base does not resolve locally"}
    elif pr and pr["state"] == "OPEN":
        try:
            # Query the target repository directly; neither origin nor a local
            # tracking ref establishes its current tip. This does not fetch.
            endpoint = f"repos/{repo}/git/ref/heads/{quote(pr['baseRefName'], safe='')}"
            base_sha = json.loads(run("gh", "api", endpoint))["object"]["sha"]
            result["base_selection"] = {"source": "open_pr", "ref": pr["baseRefName"], "sha": base_sha, "repository": repo}
            result["comparison"] = comparison(base_sha, review_head)
            if result["comparison"]["status"] == "missing_objects":
                fetch_refs = [f"refs/heads/{pr['baseRefName']}"]
                if args.pr:
                    fetch_refs.append(f"refs/pull/{pr['number']}/head")
                result["comparison"]["suggested_fetches"] = [
                    shlex.join(["git", "fetch", "--no-tags", f"https://github.com/{repo}.git", ref]) for ref in fetch_refs
                ]
                result["comparison"]["note"] = "Fetch only if allowed, then rerun discovery; no fetch was performed."
        except (DiscoveryError, OSError, ValueError, KeyError) as exc:
            result["errors"].append(str(exc))
            result["comparison"] = {"status": "blocked", "reason": "Could not resolve live PR target"}
    else:
        result["comparison"] = {"status": "needs_base", "reason": "Evaluate parent evidence; rerun with --base only after establishing or asking for the intended base"}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="User-specified or independently verified local ref/commit")
    parser.add_argument("--repo", help="GitHub target repository: owner/name")
    parser.add_argument("--pr", help="Explicit PR number or URL (use --repo for another repository)")
    parser.add_argument("--head-remote", help="Remote identifying the current branch's publishing repository")
    args = parser.parse_args()
    try:
        result = discover(args)
    except (DiscoveryError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"errors": [str(exc)], "comparison": {"status": "blocked"}}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["comparison"]["status"] in ("ready", "historical_pr") else 1


if __name__ == "__main__":
    sys.exit(main())
