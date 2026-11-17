import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from starisk import nightly


def github_stub(pulls, calls):
    def call(env, method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path.startswith("/pulls?"):
            return pulls
        return {}

    return call


class PushTest(unittest.TestCase):
    def test_a_run_publishes_a_new_ref_without_force(self):
        calls = []

        def run(*args, check=True, env=None):
            calls.append(args)
            return mock.Mock(returncode=0, stdout="")

        with mock.patch.object(nightly, "git", run):
            nightly.push({"GITHUB_TOKEN": "t"}, "data/crawl-20261117T0330")

        self.assertEqual(len(calls), 1)
        args = calls[0]
        self.assertEqual(args[:2], ("push", "origin"))
        self.assertIn("HEAD:refs/heads/data/crawl-20261117T0330", args)
        # The whole point: no lease, nothing to keep in sync, nothing to go stale.
        self.assertNotIn("--force-with-lease", args)
        self.assertNotIn("--force", args)


class PullRequestTest(unittest.TestCase):
    def test_the_run_opens_its_own_pull_request(self):
        calls = []

        with mock.patch.object(nightly, "github", github_stub([], calls)):
            nightly.open_pull_request(dict, "data/crawl-20261117T0330", "Nightly crawl", "body")

        method, path, payload = calls[0]
        self.assertEqual((method, path), ("POST", "/pulls"))
        self.assertEqual(payload["head"], "data/crawl-20261117T0330")
        self.assertEqual(payload["base"], "develop")


class CloseSupersededTest(unittest.TestCase):
    def setUp(self):
        self.pulls = [
            {"number": 7, "head": {"ref": "data/crawl-20261116T0330"}},
            {"number": 8, "head": {"ref": "feature/something"}},
            {"number": 9, "head": {"ref": "data/crawl-20261117T0330"}},
        ]

    def test_only_older_nightly_prs_are_retired(self):
        calls = []
        with mock.patch.object(nightly, "github", github_stub(self.pulls, calls)):
            closed = nightly.close_superseded({}, "data/crawl-20261117T0330")

        self.assertEqual(closed, [7])
        touched = [path for _, path, _ in calls]
        self.assertIn("/pulls/7/comments", touched)
        self.assertIn("/pulls/7", touched)
        self.assertIn("/git/refs/heads/data/crawl-20261116T0330", touched)
        self.assertNotIn("/pulls/8", touched)
        self.assertNotIn("/pulls/9", touched)

    def test_a_failure_to_retire_does_not_stop_the_run(self):
        def call(env, method, path, payload=None):
            if method == "GET":
                return self.pulls
            raise RuntimeError("api down")

        with mock.patch.object(nightly, "github", call):
            closed = nightly.close_superseded({}, "data/crawl-20261117T0330")

        self.assertEqual(closed, [])


class CopyStateTest(unittest.TestCase):
    def test_only_published_json_crosses_into_the_checkout(self):
        with tempfile.TemporaryDirectory() as state_dir, tempfile.TemporaryDirectory() as checkout:
            state = Path(state_dir)
            for name in nightly.PUBLISHED:
                (state / name).write_text(json.dumps({"name": name}), encoding="utf-8")
            (state / "page-cache-file").write_text("cache", encoding="utf-8")

            target = Path(checkout) / "data"
            nightly.copy_state(state, target)

            self.assertEqual(
                sorted(path.name for path in target.iterdir()),
                sorted(nightly.PUBLISHED),
            )

    def test_a_missing_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as state_dir, tempfile.TemporaryDirectory() as checkout:
            state = Path(state_dir)
            (state / "scores.json").write_text("{}", encoding="utf-8")

            target = Path(checkout) / "data"
            nightly.copy_state(state, target)

            self.assertEqual([path.name for path in target.iterdir()], ["scores.json"])
