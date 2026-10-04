"""Run with: python3 -B -m unittest discover -s skills/pr-review/scripts -v"""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
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
    def test_repository_urls(self):
        for url in ("git@github.com:me/project.git", "https://github.com/me/project.git", "ssh://git@github.com/me/project.git"):
            self.assertEqual(context.github_repo(url), "me/project")
        self.assertIsNone(context.github_repo("https://example.com/me/project"))

    def test_filters_other_forks(self):
        with patch.object(context, "run", return_value=json.dumps([pr("other"), pr()])):
            result = context.lookup_pr("team/project", "feature", "me/project")
        self.assertEqual(result["pr"]["headRepositoryOwner"]["login"], "me")

    def test_confirmed_absence(self):
        with patch.object(context, "run", return_value="[]"):
            self.assertEqual(context.lookup_pr("team/project", "feature", "me/project")["status"], "absent")

    def test_lookup_failure_is_not_absence(self):
        with patch.object(context, "run", side_effect=context.DiscoveryError("auth failed")):
            with self.assertRaises(context.DiscoveryError):
                context.lookup_pr("team/project", "feature", "me/project")

    def test_ambiguous_prs(self):
        with patch.object(context, "run", return_value=json.dumps([pr(), pr()])):
            self.assertEqual(context.lookup_pr("team/project", "feature", "me/project")["status"], "ambiguous")

    def test_explicit_pr_repository_mismatch(self):
        with patch.object(context, "run", return_value=json.dumps(pr())):
            with self.assertRaises(context.DiscoveryError):
                context.lookup_pr("wrong/project", "feature", "me/project", "1")


def isolate_git_config(test):
    # Global settings such as push.default would otherwise change results.
    env = patch.dict(os.environ, {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"})
    env.start()
    test.addCleanup(env.stop)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        isolate_git_config(self)
        self.temp = tempfile.TemporaryDirectory()
        self.previous = os.getcwd()
        os.chdir(self.temp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        Path("file").write_text("base\n")
        self.git("add", "file")
        self.git("commit", "-m", "base")
        self.base = self.git("rev-parse", "HEAD")
        self.git("switch", "-c", "feature")
        Path("file").write_text("base\nfeature\n")
        self.git("commit", "-am", "feature")
        self.head = self.git("rev-parse", "HEAD")
        self.git("remote", "add", "origin", "git@github.com:me/project.git")
        self.real_run = context.run

    def tearDown(self):
        os.chdir(self.previous)
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()

    def discover(self, prs=None, base=None, requested=None, fail=False, live_base=None, fail_api=False):
        def fake_run(*args):
            if args[0] != "gh":
                return self.real_run(*args)
            if fail:
                raise context.DiscoveryError("network failed")
            if args[1:3] == ("pr", "list"):
                return json.dumps(prs or [])
            if args[1:3] == ("pr", "view"):
                return json.dumps(prs[0])
            if args[1] == "api":
                if fail_api:
                    raise context.DiscoveryError("live base lookup failed")
                return json.dumps({"object": {"sha": live_base or self.base}})
            raise AssertionError(args)
        args = argparse.Namespace(repo="team/project", base=base, pr=requested, head_remote=None)
        with patch.object(context, "run", side_effect=fake_run):
            return context.discover(args)

    def test_explicit_base_works_without_gh(self):
        result = self.discover(base="main", fail=True)
        self.assertEqual(result["comparison"]["status"], "ready")
        self.assertEqual(result["pr_lookup"]["status"], "failed")
        self.assertEqual(result["comparison"]["base_sha"], self.base)

    def test_no_guess_from_tracking_or_nearby_branch(self):
        self.git("branch", "nearby", "HEAD~1")
        self.git("config", "branch.feature.remote", "origin")
        self.git("config", "branch.feature.merge", "refs/heads/feature")
        result = self.discover()
        self.assertEqual(result["comparison"]["status"], "needs_base")
        self.assertIn("branch_reflog", result["parent_evidence"])

    def test_open_pr_uses_live_base_and_local_head(self):
        result = self.discover(prs=[pr()])
        self.assertEqual(result["comparison"]["base_sha"], self.base)
        self.assertEqual(result["comparison"]["head_sha"], self.head)

    def test_explicit_pr_uses_published_head(self):
        data = pr()
        data["headRefOid"] = self.base
        result = self.discover(prs=[data], requested="1")
        self.assertEqual(result["comparison"]["head_sha"], self.base)

    def track_upstream_main(self):
        # Fork workflow: the branch tracks the parent on upstream, publishes to origin.
        self.git("remote", "add", "upstream", "git@github.com:team/project.git")
        self.git("config", "branch.feature.remote", "upstream")
        self.git("config", "branch.feature.merge", "refs/heads/main")

    def assert_publishes_to_fork(self, result, source):
        self.assertEqual(result["head_remote"]["source"], source)
        self.assertEqual(result["head_repository"], "me/project")
        self.assertEqual(result["pr_lookup"]["status"], "found")

    def test_push_remote_beats_tracking_remote(self):
        self.track_upstream_main()
        self.git("config", "branch.feature.pushRemote", "origin")
        self.assert_publishes_to_fork(self.discover(prs=[pr()]), "pushRemote")

    def test_push_default_beats_tracking_remote(self):
        self.track_upstream_main()
        self.git("config", "remote.pushDefault", "origin")
        self.assert_publishes_to_fork(self.discover(prs=[pr()]), "remote.pushDefault")

    def test_tracking_parent_branch_is_not_publishing(self):
        self.track_upstream_main()
        self.assert_publishes_to_fork(self.discover(prs=[pr()]), "origin")

    def test_push_default_current_publishes_to_tracking_remote(self):
        self.track_upstream_main()
        self.git("config", "push.default", "current")
        result = self.discover(prs=[pr("team")])
        self.assertEqual(result["head_remote"], {"name": "upstream", "source": "tracking"})
        self.assertEqual(result["head_repository"], "team/project")
        self.assertEqual(result["pr_lookup"]["status"], "found")

    def test_tracking_same_named_branch_is_publishing(self):
        self.git("remote", "add", "upstream", "git@github.com:team/project.git")
        self.git("config", "branch.feature.remote", "upstream")
        self.git("config", "branch.feature.merge", "refs/heads/feature")
        result = self.discover(prs=[pr()])
        self.assertEqual(result["head_remote"], {"name": "upstream", "source": "tracking"})
        self.assertEqual(result["head_repository"], "team/project")

    def test_push_url_overrides_fetch_url(self):
        self.git("remote", "set-url", "--push", "origin", "git@github.com:pusher/project.git")
        result = self.discover(prs=[pr("pusher")])
        self.assertEqual(result["head_repository"], "pusher/project")
        self.assertEqual(result["pr_lookup"]["status"], "found")

    def test_fork_pr_reports_pr_head_repository(self):
        data = pr("contributor")
        data["headRefOid"] = self.head
        result = self.discover(prs=[data], requested="1")
        self.assertEqual(result["comparison"]["status"], "ready")
        self.assertEqual(result["head_repository"], "contributor/project")
        self.assertEqual(result["local_head_repository"], "me/project")

    def test_historical_fork_pr_reports_pr_head_repository(self):
        result = self.discover(prs=[pr("contributor", state="MERGED")], requested="1")
        self.assertEqual(result["comparison"]["status"], "historical_pr")
        self.assertEqual(result["head_repository"], "contributor/project")

    def test_deleted_fork_pr_head_repository_is_unavailable(self):
        data = pr()
        data["headRepository"] = None
        data["headRefOid"] = self.head
        result = self.discover(prs=[data], requested="1")
        self.assertEqual(result["comparison"]["status"], "ready")
        self.assertIsNone(result["head_repository"])
        self.assertIn("deleted fork", result["head_repository_note"])

    def test_branch_review_keeps_local_head_repository(self):
        result = self.discover(prs=[pr()])
        self.assertEqual(result["head_repository"], "me/project")
        self.assertNotIn("local_head_repository", result)

    def test_historical_pr_does_not_use_live_target(self):
        result = self.discover(prs=[pr(state="MERGED")], requested="1")
        self.assertEqual(result["comparison"]["status"], "historical_pr")
        self.assertEqual(result["comparison"]["head_sha"], "published-head")
        self.assertIn("refs/pull/1/head", result["comparison"]["suggested_fetches"][0])

    def test_historical_pr_with_local_head_needs_no_fetch(self):
        data = pr(state="MERGED")
        data["headRefOid"] = self.head
        result = self.discover(prs=[data], requested="1")["comparison"]
        self.assertEqual(result["head_sha"], self.head)
        self.assertNotIn("suggested_fetches", result)

    def test_explicit_base_overrides_historical_target(self):
        data = pr(state="MERGED")
        data["headRefOid"] = self.head
        result = self.discover(prs=[data], requested="1", base="main")
        self.assertEqual(result["comparison"]["status"], "ready")
        self.assertEqual(result["base_selection"]["source"], "explicit")

    def test_draft_pr_is_still_open(self):
        data = pr()
        data["isDraft"] = True
        data["headRefOid"] = self.head
        self.assertEqual(self.discover(prs=[data], requested="1")["comparison"]["status"], "ready")

    def test_live_lookup_failure_does_not_use_stale_base(self):
        result = self.discover(prs=[pr()], fail_api=True)
        self.assertEqual(result["comparison"]["status"], "blocked")
        self.assertTrue(result["errors"])

    def test_invalid_explicit_base_blocks(self):
        self.assertEqual(self.discover(base="nonexistent")["comparison"]["status"], "blocked")

    def test_fork_pr_fetch_uses_target_pull_ref(self):
        result = self.discover(prs=[pr()], requested="1")
        fetches = result["comparison"]["suggested_fetches"]
        self.assertIn("https://github.com/team/project.git refs/pull/1/head", fetches[1])

    def test_missing_objects_report_fetch_without_mutation(self):
        before = self.git("show-ref")
        result = self.discover(prs=[pr()], live_base="a" * 40)
        self.assertEqual(result["comparison"]["status"], "missing_objects")
        self.assertIn("team/project.git", result["comparison"]["suggested_fetches"][0])
        self.assertNotIn("command_templates", result["comparison"])
        self.assertEqual(self.git("show-ref"), before)

    def test_missing_objects_with_explicit_base_has_template(self):
        data = pr()
        data["headRefOid"] = "b" * 40
        result = self.discover(prs=[data], requested="1", base="main")["comparison"]
        self.assertEqual(result["status"], "missing_objects")
        self.assertEqual(result["command_templates"], [f"git fetch --no-tags '<verified-source>' {'b' * 40}"])
        self.assertTrue(result["reason"])

    def test_linked_worktree(self):
        path = str(Path(self.temp.name) / "linked")
        self.git("worktree", "add", "-b", "linked-branch", path, "HEAD")
        os.chdir(path)
        result = self.discover(base="main")
        self.assertEqual(result["comparison"]["status"], "ready")

    def shallow_clone(self):
        # Diverging tips share the original base only in full history.
        self.git("switch", "main")
        Path("main-file").write_text("main work\n")
        self.git("add", "main-file")
        self.git("commit", "-m", "main work")
        main_tip = self.git("rev-parse", "HEAD")
        source = Path.cwd().as_uri()
        clone = str(Path(self.temp.name) / "shallow-clone")
        self.git("clone", "--depth=1", "--no-single-branch", source, clone)
        os.chdir(clone)
        self.git("switch", "feature")
        return source, main_tip

    def test_shallow_history_recovers_after_scoped_deepening(self):
        source, main_tip = self.shallow_clone()
        self.assertEqual(self.git("rev-parse", "--is-shallow-repository"), "true")
        self.assertEqual(context.commit(main_tip), main_tip)
        self.assertEqual(context.commit(self.head), self.head)
        before = (self.git("show-ref"), self.git("status", "--porcelain"), Path(".git/shallow").read_text())
        result = self.discover(base=main_tip, fail=True)["comparison"]
        self.assertEqual(result["status"], "incomplete_history")
        self.assertIn("--deepen=100", result["command_templates"][0])
        self.assertEqual(before, (self.git("show-ref"), self.git("status", "--porcelain"), Path(".git/shallow").read_text()))
        self.git("fetch", "--no-tags", "--deepen=100", source, main_tip, self.head)
        recovered = self.discover(base=main_tip, fail=True)["comparison"]
        self.assertEqual(recovered["status"], "ready")
        self.assertEqual(recovered["merge_base"], self.base)

    def test_shallow_pr_has_scoped_target_fetch(self):
        _, main_tip = self.shallow_clone()
        self.git("remote", "set-url", "origin", "git@github.com:me/project.git")
        result = self.discover(prs=[pr()], live_base=main_tip)["comparison"]
        self.assertEqual(result["status"], "incomplete_history")
        self.assertNotIn("command_templates", result)
        self.assertIn("--deepen=100 https://github.com/team/project.git refs/heads/main refs/pull/1/head", result["suggested_fetches"][0])

    def test_unrelated_histories_block(self):
        self.git("switch", "--orphan", "unrelated")
        self.git("commit", "--allow-empty", "-m", "unrelated")
        result = self.discover(base="main")["comparison"]
        self.assertEqual(result["status"], "no_merge_base")
        self.assertTrue(result["reason"])


class PushOracleTests(unittest.TestCase):
    """Check publishing-remote inference against real implicit pushes to local bare repositories."""

    def setUp(self):
        isolate_git_config(self)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.previous = os.getcwd()
        self.addCleanup(os.chdir, self.previous)

    def git(self, *args, check=True):
        result = subprocess.run(["git", *args], text=True, capture_output=True)
        if check and result.returncode:
            raise AssertionError(result.stderr)
        return result

    def repo(self, name, tracked="main", config=()):
        root = Path(self.temp.name) / name
        self.bare = {remote: str(root / f"{remote}.git") for remote in ("upstream", "origin")}
        for path in self.bare.values():
            self.git("init", "-q", "--bare", "-b", "main", path)
        work = root / "work"
        self.git("init", "-q", "-b", "main", str(work))
        os.chdir(work)
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.com")
        self.git("commit", "-q", "--allow-empty", "-m", "base")
        for remote, path in self.bare.items():
            self.git("remote", "add", remote, path)
        self.git("push", "-q", "upstream", f"main:{tracked}")
        self.git("fetch", "-q", "upstream")
        self.git("switch", "-q", "-c", "feature", "--track", f"upstream/{tracked}")
        self.git("commit", "-q", "--allow-empty", "-m", "feature")
        for key, value in config:
            self.git("config", key, value)

    def published_to(self):
        """Remotes where an implicit `git push` published `feature` at HEAD."""
        self.git("push", "-q", check=False)
        head = self.git("rev-parse", "HEAD").stdout.strip()
        return {remote for remote, path in self.bare.items()
                if self.git("--git-dir", path, "rev-parse", "--verify", "-q", "refs/heads/feature", check=False).stdout.strip() == head}

    def inferred(self):
        remotes = {name: self.git("remote", "get-url", name).stdout.strip() for name in self.bare}
        return context.publishing_remote("feature", remotes)[0]

    def test_inference_matches_implicit_push(self):
        cases = [
            ("current", "main", [("push.default", "current")]),
            ("pushRemote", "main", [("branch.feature.pushRemote", "origin")]),
            ("pushDefault", "main", [("remote.pushDefault", "origin")]),
            ("same-name tracking", "feature", []),
        ]
        for name, tracked, config in cases:
            with self.subTest(name):
                self.repo(name.replace(" ", "-"), tracked, config)
                inferred = self.inferred()
                self.assertEqual(self.published_to(), {inferred})

    def test_no_implicit_publish_falls_back_to_origin(self):
        # Git refuses (simple) or publishes under the tracked name (upstream):
        # neither publishes `feature`, so the inference falls back to origin.
        for name, config in (("simple", []), ("upstream-mode", [("push.default", "upstream")])):
            with self.subTest(name):
                self.repo(name, "main", config)
                inferred = self.inferred()
                self.assertEqual(self.published_to(), set())
                self.assertEqual(inferred, "origin")


if __name__ == "__main__":
    unittest.main()
