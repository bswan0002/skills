#!/usr/bin/env python3
"""Discover a published GitHub PR for read-only review. Requires authenticated gh."""

import argparse
import json
import shlex
import subprocess
import sys
from urllib.parse import urlsplit


class DiscoveryError(Exception):
    pass


def run(*args):
    result = subprocess.run(args, text=True, capture_output=True)
    if result.returncode:
        raise DiscoveryError(f"{shlex.join(args)}: {result.stderr.strip() or 'command failed'}")
    return result.stdout.strip()


PR_FIELDS = "number,url,state,baseRefName,baseRefOid,headRefName,headRefOid,headRepository,headRepositoryOwner"


def pr_head_repository(pr):
    owner = (pr.get("headRepositoryOwner") or {}).get("login")
    name = (pr.get("headRepository") or {}).get("name")
    return f"{owner}/{name}" if owner and name else None


def target_repository(pr):
    url = urlsplit(pr["url"])
    if url.hostname != "github.com":
        raise DiscoveryError("Only github.com PRs are supported")
    return "/".join(url.path.strip("/").split("/")[:2])


def discover_pr(requested=None, repo=None):
    """Let gh resolve the association; verify uniqueness among open matches."""
    if requested:
        args = ["gh", "pr", "view", requested, "--json", PR_FIELDS]
        if repo:
            args += ["--repo", repo]
        pr = json.loads(run(*args))
        target = target_repository(pr)
        if repo and target.casefold() != repo.casefold():
            raise DiscoveryError("PR URL and target repository disagree; pass --repo for the URL's repository")
        return {"status": "found", "repository": target, "pr": pr}
    if repo:
        return {"status": "needs_pr", "reason": "An explicit target repository requires --pr"}
    candidate = json.loads(run("gh", "pr", "status", "--json", PR_FIELDS))["currentBranch"]
    if not candidate:
        return {"status": "needs_pr", "reason": "gh could not identify a PR; specify --pr"}
    target = target_repository(candidate)
    head_repo = pr_head_repository(candidate)
    if not head_repo:
        raise DiscoveryError("Cannot verify candidate's head repository; specify --pr")
    prs = json.loads(run("gh", "pr", "list", "--repo", target, "--state", "open", "--head", candidate["headRefName"], "--limit", "1000", "--json", PR_FIELDS))
    if len(prs) >= 1000:
        raise DiscoveryError("PR lookup may be truncated; inspect an explicit PR instead")
    matches = []
    for pr in prs:
        identity = pr_head_repository(pr)
        if not identity:
            raise DiscoveryError("PR lookup returned unverifiable head repository identity")
        if pr["headRefName"] == candidate["headRefName"] and identity.casefold() == head_repo.casefold():
            matches.append(pr)
    if len(matches) > 1:
        return {"status": "ambiguous", "repository": target, "prs": matches}
    if not matches:
        return {"status": "needs_pr", "repository": target, "reason": "No verified open match; specify --pr"}
    return {"status": "found", "repository": target, "pr": matches[0]}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", help="PR number or URL; otherwise discover the current branch's PR")
    parser.add_argument("--repo", help="Target owner/name, used with --pr")
    args = parser.parse_args()
    try:
        result = discover_pr(args.pr, args.repo)
        if result["status"] == "found":
            result["diff_command"] = shlex.join(["gh", "pr", "diff", result["pr"]["url"]])
    except (DiscoveryError, OSError, ValueError, KeyError) as exc:
        result = {"status": "failed", "reason": str(exc)}
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "found" else 1


if __name__ == "__main__":
    sys.exit(main())
