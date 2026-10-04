"""Run with: python3 -B -m unittest discover -s skills/pr-review/scripts -v"""

import io
import importlib.util
import json
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("pr_context", Path(__file__).with_name("pr-context.py"))
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


def pr(owner="me", state="OPEN"):
    return {"number": 1, "url": "https://github.com/team/project/pull/1", "state": state,
            "baseRefName": "main", "baseRefOid": "old-base", "headRefName": "feature",
            "headRefOid": "published-head", "headRepository": {"name": "project"},
            "headRepositoryOwner": {"login": owner}}


class LookupTests(unittest.TestCase):
    def lookup(self, candidate=None, prs=(), requested=None, repo=None):
        def fake_run(*args):
            if args[1:3] == ("pr", "status"):
                return json.dumps({"currentBranch": candidate})
            if args[1:3] == ("pr", "list"):
                self.assertIn(candidate["headRefName"], args)
                self.assertIn("team/project", args)
                self.assertIn("open", args)
                return json.dumps(prs)
            if args[1:3] == ("pr", "view"):
                return json.dumps(candidate)
            raise AssertionError(args)
        with patch.object(context, "run", side_effect=fake_run) as run:
            result = context.discover_pr(requested, repo)
        return result, run

    def test_filters_other_forks_repositories_and_branches(self):
        other_repo = pr()
        other_repo["headRepository"]["name"] = "different"
        other_branch = pr()
        other_branch["headRefName"] = "different"
        result, run = self.lookup(pr(), [pr("other"), other_repo, other_branch, pr()])
        self.assertEqual(result["pr"]["headRepositoryOwner"]["login"], "me")
        self.assertEqual(result["repository"], "team/project")
        self.assertEqual(run.call_count, 2)

    def test_case_insensitive_repository_identity(self):
        result, _ = self.lookup(pr("ME"), [pr("me")])
        self.assertEqual(result["status"], "found")

    def test_null_candidate_requires_input_not_claimed_absence(self):
        result, run = self.lookup()
        self.assertEqual(result["status"], "needs_pr")
        self.assertEqual(run.call_count, 1)

    def test_no_open_match_requires_input(self):
        result, _ = self.lookup(pr(state="MERGED"))
        self.assertEqual(result["status"], "needs_pr")

    def test_historical_candidate_can_discover_open_match(self):
        result, _ = self.lookup(pr(state="MERGED"), [pr()])
        self.assertEqual(result["pr"]["state"], "OPEN")

    def test_lookup_failure_is_not_absence(self):
        with patch.object(context, "run", side_effect=context.DiscoveryError("auth failed")):
            with self.assertRaises(context.DiscoveryError):
                context.discover_pr()

    def test_ambiguous_bases(self):
        release = pr()
        release.update(number=2, baseRefName="release")
        result, _ = self.lookup(pr(), [pr(), release])
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(len(result["prs"]), 2)

    def test_truncation_blocks(self):
        with self.assertRaises(context.DiscoveryError):
            self.lookup(pr(), [pr()] * 1000)

    def test_missing_head_identity_blocks(self):
        deleted = pr()
        deleted["headRepository"] = None
        with self.assertRaises(context.DiscoveryError):
            self.lookup(deleted)
        with self.assertRaises(context.DiscoveryError):
            self.lookup(pr(), [deleted])

    def test_explicit_repo_requires_pr(self):
        with patch.object(context, "run") as run:
            result = context.discover_pr(repo="team/project")
        self.assertEqual(result["status"], "needs_pr")
        run.assert_not_called()

    def test_explicit_pr_repository_mismatch(self):
        with self.assertRaises(context.DiscoveryError):
            self.lookup(pr(), requested="1", repo="wrong/project")

    def test_explicit_url_uses_its_repository_without_local_repo_lookup(self):
        result, run = self.lookup(pr(state="MERGED"), requested=pr()["url"])
        self.assertEqual(result["repository"], "team/project")
        self.assertEqual(result["pr"]["state"], "MERGED")
        run.assert_called_once_with("gh", "pr", "view", pr()["url"], "--json", context.PR_FIELDS)

    def test_explicit_number_passes_repo(self):
        result, run = self.lookup(pr(), requested="1", repo="team/project")
        self.assertEqual(result["status"], "found")
        self.assertIn("--repo", run.call_args.args)

    def test_other_host_blocks_before_cloud_api_or_fetch_guidance(self):
        enterprise = pr()
        enterprise["url"] = "https://github.example.com/team/project/pull/1"
        for requested in (None, enterprise["url"]):
            with self.subTest(requested=requested):
                with self.assertRaises(context.DiscoveryError):
                    self.lookup(enterprise, requested=requested)



class MainTests(unittest.TestCase):
    def invoke(self, args=(), result=None, error=None):
        stdout = io.StringIO()
        with patch("sys.argv", ["pr-context.py", *args]), redirect_stdout(stdout):
            with patch.object(context, "discover_pr", return_value=result, side_effect=error) as discover:
                code = context.main()
        return code, json.loads(stdout.getvalue()), discover

    def test_found_emits_one_published_pr_diff_command(self):
        code, result, discover = self.invoke(result={
            "status": "found", "repository": "team/project", "pr": pr(),
        })
        self.assertEqual(code, 0)
        self.assertEqual(result["diff_command"], "gh pr diff https://github.com/team/project/pull/1")
        self.assertNotIn("comparison", result)
        self.assertNotIn("local_head", result)
        discover.assert_called_once_with(None, None)

    def test_explicit_selection_passed_through(self):
        _, _, discover = self.invoke(
            ("--pr", "1", "--repo", "team/project"),
            result={"status": "found", "repository": "team/project", "pr": pr()},
        )
        discover.assert_called_once_with("1", "team/project")

    def test_missing_or_ambiguous_pr_has_no_diff_command(self):
        for status in ("needs_pr", "ambiguous"):
            with self.subTest(status=status):
                code, result, _ = self.invoke(result={"status": status})
                self.assertEqual(code, 1)
                self.assertNotIn("diff_command", result)

    def test_errors_are_reported_not_absence(self):
        for error in (context.DiscoveryError("auth failed"), FileNotFoundError("gh missing")):
            with self.subTest(error=error):
                code, result, _ = self.invoke(error=error)
                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["reason"], str(error))

    def test_list_failure_does_not_use_status_candidate(self):
        stdout = io.StringIO()
        with patch("sys.argv", ["pr-context.py"]), redirect_stdout(stdout):
            with patch.object(context, "run", side_effect=[
                json.dumps({"currentBranch": pr()}), context.DiscoveryError("list failed"),
            ]):
                code = context.main()
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "failed")

    def test_explicit_closed_pr_uses_same_diff_path(self):
        code, result, _ = self.invoke(
            ("--pr", "1"),
            result={"status": "found", "repository": "team/project", "pr": pr(state="MERGED")},
        )
        self.assertEqual(code, 0)
        self.assertEqual(result["diff_command"], "gh pr diff https://github.com/team/project/pull/1")

    def test_removed_local_comparison_flags_are_rejected(self):
        for flag in ("--base", "--head-remote"):
            with self.subTest(flag=flag):
                with patch("sys.argv", ["pr-context.py", flag, "main"]), redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        context.main()
                self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
