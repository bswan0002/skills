"""Run with: python3 -B -m unittest discover -s skills/create-or-update-pr/scripts -v"""

import argparse
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("create_pr_context", Path(__file__).with_name("pr-context.py"))
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)

HEAD = "a" * 40
BASE = "b" * 40


def pr(branch, owner="me"):
    return {"number": 1, "url": "https://github.com/me/project/pull/1",
            "title": "Human title", "body": "Human body", "isDraft": True,
            "baseRefName": "parent", "headRefName": branch,
            "headRepositoryOwner": {"login": owner}}


class PublicationRepositoryTests(unittest.TestCase):
    def test_same_repository_with_different_url_syntax(self):
        fetch_url = "git@github.com:me/project.git"
        push_url = "https://github.com/me/project.git"
        with patch.object(context, "run", side_effect=[fetch_url, push_url]) as run, \
                patch.object(context, "gh_json", side_effect=[
                    {"nameWithOwner": "Me/Project"}, {"nameWithOwner": "me/project"}
                ]) as gh_json:
            self.assertEqual(context.publication_repository("fork"), "Me/Project")
        self.assertEqual(run.call_args_list[0].args, ("git", "remote", "get-url", "fork"))
        self.assertEqual(run.call_args_list[1].args,
                         ("git", "remote", "get-url", "--push", "--all", "fork"))
        self.assertEqual([call.args[2] for call in gh_json.call_args_list],
                         [fetch_url, push_url])

    def test_split_repositories_stop_discovery(self):
        with patch.object(context, "run", side_effect=[
                "https://github.com/upstream/project.git", "git@github.com:me/project.git"
        ]), patch.object(context, "gh_json", side_effect=[
                {"nameWithOwner": "upstream/project"}, {"nameWithOwner": "me/project"}
        ]):
            with self.assertRaisesRegex(RuntimeError, "fetches from upstream/project but pushes to me/project"):
                context.publication_repository("origin")

    def test_requires_exactly_one_push_destination(self):
        url = "https://github.com/me/project.git"
        for push_urls in ("", f"{url}\nhttps://github.com/other/project.git", f"{url}\n{url}"):
            with self.subTest(push_urls=push_urls), \
                    patch.object(context, "run", side_effect=[url, push_urls]), \
                    patch.object(context, "gh_json") as gh_json:
                with self.assertRaisesRegex(RuntimeError, "exactly one push destination"):
                    context.publication_repository("origin")
                gh_json.assert_not_called()

    def test_push_url_lookup_failure_is_not_ignored(self):
        with patch.object(context, "run", side_effect=["fetch-url", RuntimeError("push lookup failed")]):
            with self.assertRaisesRegex(RuntimeError, "push lookup failed"):
                context.publication_repository("origin")

    def test_repository_lookup_failures_are_not_ignored(self):
        for responses in ([RuntimeError("fetch identity failed")],
                          [{"nameWithOwner": "me/project"}, RuntimeError("push identity failed")]):
            with self.subTest(responses=responses), \
                    patch.object(context, "run", side_effect=["fetch-url", "push-url"]), \
                    patch.object(context, "gh_json", side_effect=responses):
                with self.assertRaisesRegex(RuntimeError, "identity failed"):
                    context.publication_repository("origin")


class DiscoveryTests(unittest.TestCase):
    def discover(self, prs=None, tracking="published-name", tracking_remote="origin",
                 head_branch=None, head_remote=None, base="main", metadata=None,
                 creation="", failed_lookup=None):
        prs = prs or {}
        calls = []

        def fake_run(*args, optional=False):
            calls.append(args)
            if args == ("git", "rev-parse", "--show-toplevel"):
                return "/repo"
            if args == ("git", "branch", "--show-current"):
                return "local-name"
            if args == ("git", "rev-parse", "HEAD"):
                return HEAD
            if args[:3] == ("git", "config", "--get"):
                return {"branch.local-name.remote": tracking_remote,
                        "branch.local-name.merge": f"refs/heads/{tracking}" if tracking else None,
                        "branch.local-name.gh-merge-base": metadata}.get(args[3])
            if args[:3] == ("git", "reflog", "show"):
                return creation
            if args[:3] == ("git", "remote", "get-url"):
                return "https://github.com/me/project.git"
            if args == ("git", "remote"):
                return "origin\nfork"
            if args[:3] == ("gh", "repo", "view"):
                return json.dumps({"nameWithOwner": "me/project",
                                   "defaultBranchRef": {"name": "main"}})
            if args[:3] == ("gh", "pr", "list"):
                branch = args[args.index("--head") + 1]
                if branch == failed_lookup:
                    raise RuntimeError("lookup failed")
                return json.dumps(prs.get(branch, []))
            if args[:3] == ("gh", "pr", "view"):
                return json.dumps(next(p for values in prs.values() for p in values
                                       if str(p["number"]) == args[3]))
            if args[:2] == ("gh", "api"):
                return json.dumps({"object": {"sha": BASE}})
            if args[:2] == ("git", "ls-remote"):
                return f"{HEAD}\t{args[-1]}"
            if args[:2] == ("git", "cat-file"):
                return "" if args[-1].startswith(HEAD) else None
            if args[:3] == ("git", "rev-list", "--count"):
                return "0"
            if args == ("git", "status", "--short"):
                return ""
            if args == ("git", "rev-parse", "--abbrev-ref", "@{upstream}"):
                return f"{tracking_remote}/{tracking}" if tracking else None
            raise AssertionError(args)

        args = argparse.Namespace(repo=None, head_remote=head_remote,
                                  head_branch=head_branch, base=base)
        with patch.object(context, "run", side_effect=fake_run):
            result = context.discover(args)
        return result, calls

    def queried_branches(self, calls):
        return [c[c.index("--head") + 1] for c in calls if c[:3] == ("gh", "pr", "list")]

    def test_invalid_publication_remote_stops_before_pr_lookup(self):
        with patch.object(context, "publication_repository", side_effect=RuntimeError("split remote")), \
                patch.object(context, "open_pr") as open_pr:
            with self.assertRaisesRegex(RuntimeError, "split remote"):
                self.discover()
            open_pr.assert_not_called()

    def test_local_pr_takes_priority(self):
        result, calls = self.discover(prs={"local-name": [pr("local-name")]}, base=None)
        self.assertEqual(self.queried_branches(calls), ["local-name"])
        self.assertIsNone(result["tracking_pr"])
        self.assertEqual(result["open_pr"]["headRefName"], "local-name")
        self.assertEqual(result["base"]["branch"], "parent")

    def test_renamed_branch_requires_confirmation(self):
        candidate = pr("published-name")
        result, calls = self.discover(prs={"published-name": [candidate]})
        self.assertEqual(self.queried_branches(calls), ["local-name", "published-name"])
        self.assertEqual(result["tracking_pr"], candidate)
        self.assertIsNone(result["open_pr"])
        self.assertEqual(result["publication"]["branch"], "local-name")
        self.assertTrue(any("Ask whether" in w for w in result["warnings"]))

    def test_confirmed_tracking_branch_used_for_pr_and_publication(self):
        result, calls = self.discover(prs={"published-name": [pr("published-name")]},
                                      head_branch="published-name", base=None)
        self.assertEqual(self.queried_branches(calls), ["published-name"])
        self.assertEqual(result["head"], "local-name")
        self.assertEqual(result["open_pr"]["headRefName"], "published-name")
        self.assertEqual(result["publication"]["branch"], "published-name")
        self.assertEqual(result["publication"]["local_only_commits"], 0)
        self.assertIn(("git", "ls-remote", "--heads", "origin", "refs/heads/published-name"), calls)
        self.assertEqual(result["base"]["branch"], "parent")
        self.assertIsNone(result["tracking_pr"])

    def test_user_can_confirm_separate_local_publication(self):
        result, calls = self.discover(prs={"published-name": [pr("published-name")]},
                                      head_branch="local-name")
        self.assertEqual(self.queried_branches(calls), ["local-name"])
        self.assertIsNone(result["tracking_pr"])
        self.assertEqual(result["publication"]["branch"], "local-name")

    def test_tracking_main_without_pr_keeps_local_name(self):
        result, calls = self.discover(tracking="main")
        self.assertEqual(self.queried_branches(calls), ["local-name", "main"])
        self.assertIsNone(result["tracking_pr"])
        self.assertEqual(result["publication"]["branch"], "local-name")
        self.assertFalse(any("Ask whether" in w for w in result["warnings"]))

    def test_tracking_parent_with_pr_is_not_automatically_selected(self):
        result, _ = self.discover(tracking="main", prs={"main": [pr("main")]})
        self.assertIsNone(result["open_pr"])
        self.assertEqual(result["publication"]["branch"], "local-name")
        self.assertIsNotNone(result["tracking_pr"])

    def test_other_owner_pr_is_not_a_candidate(self):
        result, _ = self.discover(prs={"published-name": [pr("published-name", "other")]})
        self.assertIsNone(result["tracking_pr"])

    def test_override_remote_does_not_reuse_old_tracking_branch(self):
        result, calls = self.discover(head_remote="fork",
                                      prs={"published-name": [pr("published-name")]})
        self.assertEqual(self.queried_branches(calls), ["local-name"])
        self.assertIsNone(result["tracking_pr"])
        self.assertEqual(result["publication"]["remote"], "fork")

    def test_same_tracking_name_or_no_tracking_needs_no_fallback(self):
        for tracking in ("local-name", None):
            with self.subTest(tracking=tracking):
                _, calls = self.discover(tracking=tracking)
                self.assertEqual(self.queried_branches(calls), ["local-name"])

    def test_tracking_lookup_failure_stops_discovery(self):
        with self.assertRaisesRegex(RuntimeError, "lookup failed"):
            self.discover(failed_lookup="published-name")

    def test_non_main_parent_evidence_still_selects_parent(self):
        creation = f"{HEAD}\trefs/heads/local-name@{{123 +0000}}\tbranch: Created from parent"
        result, _ = self.discover(tracking="main", base=None, metadata="parent", creation=creation)
        self.assertEqual(result["base"]["branch"], "parent")
        self.assertEqual(result["publication"]["branch"], "local-name")

    def test_same_head_and_base_check_uses_publication_branch(self):
        with self.assertRaisesRegex(RuntimeError, "same branch"):
            self.discover(head_branch="published-name", base="published-name")


if __name__ == "__main__":
    unittest.main()
