"""Bring the container's working copy up to date before the nightly runs.

The clone lives in a volume owned by the container: nothing on the host is
checked out, switched or committed.

This is a separate process on purpose. `starisk.nightly` imports its modules when
it starts, so switching branches inside that process would change files that are
already loaded — a run would keep executing the code from the previous checkout.
Doing it here means the process that follows imports what was just fetched.

    cd pipeline && python -m starisk.checkout

Exit codes: 0 ready, 40 git trouble (conflict, dirty tree, missing remote).
"""

from __future__ import annotations

import sys

from .nightly import BASE, BRANCH, GitError, git, tracked_changes

GIT_PROBLEM = 40


def ensure() -> None:
    """Switch to the bot branch and rebase it onto current `develop`."""
    if tracked_changes():
        raise GitError("the working copy has uncommitted changes")

    git("fetch", "origin", BASE)
    # Keep the remote-tracking ref current so --force-with-lease compares against
    # what is really on the remote, not a ref from days ago.
    git("fetch", "origin", f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}", check=False)

    if git("rev-parse", "--verify", "--quiet", BRANCH, check=False).returncode == 0:
        git("switch", BRANCH)
    elif git("rev-parse", "--verify", "--quiet", f"origin/{BRANCH}", check=False).returncode == 0:
        # The branch exists upstream but not here (a fresh clone): continue it
        # rather than discarding the runs it already holds.
        git("switch", "--no-track", "-c", BRANCH, f"origin/{BRANCH}")
    else:
        # --no-track: the upstream is data/crawl, not develop, so `git status`
        # does not claim to be ahead of the release branch.
        git("switch", "--no-track", "-c", BRANCH, f"origin/{BASE}")

    rebased = git("rebase", f"origin/{BASE}", check=False)
    if rebased.returncode != 0:
        git("rebase", "--abort", check=False)
        raise GitError(f"rebase of {BRANCH} onto origin/{BASE} conflicted")


def main() -> int:
    try:
        ensure()
    except GitError as error:
        print(f"[checkout] {error}", file=sys.stderr)
        return GIT_PROBLEM
    print(f"[checkout] {BRANCH} ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
