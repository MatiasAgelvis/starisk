import unittest
from unittest import mock

from starisk import checkout
from starisk.nightly import GitError


def stub_git(calls, fail_on=None):
    """Record every call; optionally raise on the command that starts with `fail_on`."""

    def run(*args, check=True, env=None):
        calls.append(args)
        if fail_on and args[: len(fail_on)] == fail_on:
            raise GitError("fatal: unable to access 'https://github.com/…': timed out")
        return mock.Mock(returncode=0, stdout="")

    return run


def ensure_with(calls, changes=None, fail_on=None):
    with (
        mock.patch.object(checkout, "git", stub_git(calls, fail_on)),
        mock.patch.object(checkout, "tracked_changes", return_value=changes or []),
    ):
        checkout.ensure()


class EnsureTest(unittest.TestCase):
    def test_one_fetch_covers_both_refs(self):
        calls = []
        ensure_with(calls)

        fetches = [call for call in calls if call[0] == "fetch"]
        self.assertEqual(fetches, [("fetch", "origin", "--prune")])
        self.assertEqual(calls[0], ("fetch", "origin", "--prune"))

    def test_a_failed_fetch_stops_before_switching(self):
        """A blip here is what used to surface as "(stale info)" at push time."""
        calls = []
        with self.assertRaises(GitError) as caught:
            ensure_with(calls, fail_on=("fetch",))

        self.assertIn("could not fetch from origin", str(caught.exception))
        self.assertEqual([call for call in calls if call[0] != "fetch"], [])

    def test_a_dirty_working_copy_never_fetches(self):
        calls = []
        with self.assertRaises(GitError):
            ensure_with(calls, changes=["pipeline/data/scores.json"])

        self.assertEqual(calls, [])

    def test_the_branch_is_rebased_onto_current_develop(self):
        calls = []
        ensure_with(calls)

        self.assertIn(("rebase", "origin/develop"), calls)
        self.assertLess(
            calls.index(("fetch", "origin", "--prune")),
            calls.index(("rebase", "origin/develop")),
        )

    def test_a_conflicted_rebase_aborts(self):
        calls = []

        def run(*args, check=True, env=None):
            calls.append(args)
            if args[:2] == ("rebase", "--abort"):
                return mock.Mock(returncode=1, stdout="")
            if args[0] == "rebase":
                # `ensure` asks for the result rather than an exception here.
                self.assertFalse(check, "the rebase must be run with check=False")
                return mock.Mock(returncode=1, stdout="")
            return mock.Mock(returncode=0, stdout="")

        with (
            mock.patch.object(checkout, "git", run),
            mock.patch.object(checkout, "tracked_changes", return_value=[]),
            self.assertRaises(GitError) as caught,
        ):
            checkout.ensure()

        self.assertIn("conflicted", str(caught.exception))
        self.assertIn(("rebase", "--abort"), calls)
