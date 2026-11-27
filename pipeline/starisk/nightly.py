"""One unattended run: queue → smoke → crawl → derive → gate → commit → PR.

The box owns the timing, the residential IP and the notification channel. This
module owns the decisions, so they can be read and tested in one place instead of
inside a shell script:

1. Read the request queue (Turso) into `sources.json`.
2. Check that Coursera still parses and that the deployed data is still served.
3. Discover the next programs, rebuild the program index, expand the crawl list
   from them, then crawl, localise logos and copy the data into the site.
4. Gate the result. A run that lost scores, grew errors or touched code does not
   become a commit — it becomes a notification.
5. Publish: a new branch for this run, one commit, a plain push, one pull request.

Publishing is a **create**. The branch is named after the run, so the ref does not
 exist on the remote yet, which is the one push git cannot reject — no rebase, no
force, no lease, and no dependency on what happened to last night's branch.

The run never touches `main`; publishing is still a human merge. Merge the PR any
way you like, including squash, and delete the branch afterwards: nothing depends
on it.

    python -m starisk.nightly --dry-run     # config, connectivity, smoke; no writes
    python -m starisk.nightly --limit 100
    python -m starisk.nightly --no-push     # rehearsal: commit on the branch, stop

Exit codes are the interface to the timer and the health check:

    0   ok, committed             20  gate refused             50  smoke failed
    10  nothing changed           30  partial (rate limited)   60  missing config
    15  cooldown, no requests      40  git trouble              70  unexpected failure
"""

from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
import subprocess
import sys
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import crawl, demand, expand, groupings, logo_hires, logos, smoke
from .paths import LOG_DIR

REPO = Path(__file__).resolve().parents[2]
LAST_RUN = LOG_DIR / "last-run.json"
LOCK = LOG_DIR / "nightly.lock"

BRANCH_PREFIX = "data/crawl-"
BASE = "develop"
# Courses read per run. Paired with discovery: 20 programs a night is ~100 new member
# courses, so 100 keeps the never-read queue flat rather than growing without bound.
DEFAULT_LIMIT = 100

OK = 0
NOTHING = 10
# A rate-limited run buys one night of silence: the host asked for it, and
# hammering a 403 is how a soft limit becomes a ban.
COOLDOWN = 15
GATE = 20
PARTIAL = 30
GIT = 40
SMOKE = 50
CONFIG = 60
FAILED = 70

STATUS = {
    OK: "ok",
    NOTHING: "nothing",
    COOLDOWN: "cooldown",
    GATE: "refused",
    PARTIAL: "partial",
    GIT: "git",
    SMOKE: "smoke",
    CONFIG: "config",
    FAILED: "failed",
}

# What a data commit is allowed to contain. Anything else means the run changed
# code, which it must never do.
DATA_PATHS = (
    "pipeline/data/scores.json",
    "pipeline/data/groupings.json",
    "pipeline/data/programs.json",
    "pipeline/data/sources.json",
    "pipeline/data/retired.json",
    "pipeline/data/stats.json",
    "pipeline/data/requests.json",
    "web/src/data/scores.json",
    "web/src/data/groupings.json",
    "web/src/data/requests.json",
    "web/src/data/stats.json",
    "web/src/data/logo-sizes.json",
)
DATA_PREFIXES = ("web/public/logos/",)

# Guards against a quietly broken adapter publishing itself. Retired courses are
# not errors (they never reach `summarize`), so these only count real breakage.
MAX_SCORED_DROP = 5
MAX_NEW_ERRORS = 2
# A few bad courses are weather, not a broken adapter. Refusing a whole night (and
# with it the clone) over 3/100 is how a backlog stops advancing.
MAX_ERROR_SHARE = 0.2


class GitError(RuntimeError):
    pass


# --- pure decisions -------------------------------------------------------


def allowed(path: str) -> bool:
    return path in DATA_PATHS or path.startswith(DATA_PREFIXES)


def diff_summary(before: dict, after: dict) -> dict:
    """What changed between two `scores.json` snapshots, plus the corpus counts."""
    return {
        **crawl.summarize(after),
        "scored_before": crawl.summarize(before)["scored"],
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "updated": sorted(
            key for key in set(after) & set(before) if after[key] != before[key]
        ),
    }


@dataclass
class Decision:
    code: int
    reason: str

    @property
    def commit(self) -> bool:
        return self.code in (OK, PARTIAL)


def decide(
    changed_paths: list[str],
    summary: dict,
    before: dict,
    adapter_ok: bool = True,
) -> Decision:
    if not adapter_ok:
        return Decision(SMOKE, "the live adapter check failed")

    stray = [path for path in changed_paths if not allowed(path)]
    if stray:
        return Decision(GATE, f"unexpected files changed: {', '.join(stray[:5])}")
    if not changed_paths:
        return Decision(NOTHING, "nothing changed")

    if summary["removed"]:
        return Decision(GATE, f"{len(summary['removed'])} record(s) disappeared")
    drop = before["scored"] - summary["scored"]
    if drop > MAX_SCORED_DROP:
        return Decision(GATE, f"scored courses dropped by {drop}")
    errors = summary["errors"] - before["errors"]
    batch = len(summary["added"]) + len(summary["updated"])
    tolerance = max(MAX_NEW_ERRORS, math.ceil(batch * MAX_ERROR_SHARE))
    if errors > tolerance:
        return Decision(GATE, f"{errors} of {batch} fetched records have errors")
    if summary["rate_limited"]:
        return Decision(PARTIAL, "Coursera rate-limited the crawl")
    if errors:
        return Decision(PARTIAL, f"committed with {errors} record(s) with errors")
    return Decision(OK, "committed")


def _courses(count: int) -> str:
    return f"{count} course" if count == 1 else f"{count} courses"


def commit_message(summary: dict) -> str:
    added, updated = len(summary["added"]), len(summary["updated"])
    if added and updated:
        return f"data(crawl): add {_courses(added)}, rescore {updated}"
    if added:
        return f"data(crawl): add {_courses(added)}"
    if updated:
        return f"data(crawl): rescore {_courses(updated)}"
    return "data(crawl): refresh course data"


def commit_body(summary: dict, decision: Decision) -> str:
    lines = []
    if decision.code == PARTIAL:
        lines.append(f"- Partial run: {decision.reason}")
    delta = summary["scored"] - summary["scored_before"]
    lines.append(f"- {summary['scored']} scored ({delta:+d}), {len(summary['updated'])} rescored")
    lines.append(f"- {summary['errors']} record(s) with errors")
    return "\n".join(lines)


def pr_body(summary: dict, decision: Decision, day: str) -> str:
    lines = [
        f"Nightly crawl, {day}.",
        "",
        f"- {decision.reason}",
        f"- {summary['scored']} scored, {len(summary['added'])} added, "
        f"{len(summary['updated'])} rescored",
        f"- {summary['errors']} record(s) with errors",
        "",
        "Merging this lands the data on `develop`; production still moves with the",
        "`develop → main` release merge.",
    ]
    return "\n".join(lines)


def summary_line(summary: dict, decision: Decision) -> str:
    return (
        f"{decision.reason}: +{len(summary['added'])} added, "
        f"{len(summary['updated'])} rescored, {summary['scored']} scored, "
        f"{summary['errors']} with errors"
    )


# --- git ------------------------------------------------------------------


def git(*args: str, check: bool = True, env: dict | None = None) -> subprocess.CompletedProcess:
    completed = subprocess.run(
        ("git", *args), cwd=REPO, text=True, capture_output=True, env=env
    )
    if check and completed.returncode != 0:
        raise GitError(completed.stderr.strip() or f"git {args[0]} failed")
    return completed


def _paths(output: str) -> list[str]:
    paths = []
    for line in output.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip('"'))
    return [path for path in paths if path]


def changed() -> list[str]:
    """Tracked and untracked paths git would commit; ignored files stay invisible."""
    return _paths(git("status", "--porcelain", "--untracked-files=all").stdout)


def tracked_changes() -> list[str]:
    """Modified tracked files only. Stray untracked files are not a reason to stop."""
    return _paths(git("status", "--porcelain", "--untracked-files=no").stdout)


def commit(paths: list[str], message: str, body: str) -> str:
    git("add", "--", *paths)
    # The author is the bot even when the run is a local rehearsal: the identity
    # belongs to the job, not to whoever happens to own the clone.
    git(
        "-c",
        f"user.name={os.environ.get('GIT_AUTHOR_NAME', 'Starisk Bot')}",
        "-c",
        f"user.email={os.environ.get('GIT_AUTHOR_EMAIL', 'bot@matiasagelvis.com')}",
        "commit",
        "-m",
        message,
        "-m",
        body,
    )
    return git("rev-parse", "--short", "HEAD").stdout.strip()


def push(env: dict, branch: str) -> None:
    """Publish this run's branch as a new ref.

    A create is the one push git cannot reject: the remote has no value for the
    ref, so there is no non-fast-forward to refuse and no lease to keep in sync.
    That is the whole reason the branch is named after the run.

    The credential helper runs inside git with the token in its environment, so
    the token is absent from argv, from `.git/config` and from the reflog.
    """
    helper = (
        '!f() { test "$1" = get && '
        'printf "username=x-access-token\\npassword=%s\\n" "$GITHUB_TOKEN"; }; f'
    )
    git(
        "push",
        "origin",
        f"HEAD:refs/heads/{branch}",
        env={
            **os.environ,
            "GITHUB_TOKEN": env["GITHUB_TOKEN"],
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "credential.helper",
            "GIT_CONFIG_VALUE_0": helper,
            "GIT_TERMINAL_PROMPT": "0",
        },
    )


# --- http -----------------------------------------------------------------


def repo_slug(env: dict) -> str:
    return env.get("GITHUB_REPO", "MatiasAgelvis/starisk")


def github(env: dict, method: str, path: str, payload: dict | None = None) -> object:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo_slug(env)}{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {env['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "starisk-nightly",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        # GitHub's status alone is useless (422 from which call, why?). The body
        # carries the validation message, so it belongs in the failure.
        detail = error.read().decode("utf-8", "replace").strip()[:300]
        raise GitError(f"GitHub {error.code} on {method} {path}: {detail}") from error
    return json.loads(body) if body else {}


def open_pull_request(env: dict, branch: str, title: str, body: str) -> str | None:
    """One PR per run. The previous one is closed by `close_superseded`."""
    created = github(
        env,
        "POST",
        "/pulls",
        {"title": title, "head": branch, "base": BASE, "body": body},
    )
    return created.get("html_url") if isinstance(created, dict) else None


def close_superseded(env: dict, keep: str) -> list[int]:
    """Close earlier nightly PRs and drop their branches.

    The newest branch carries the whole snapshot — the crawl is cumulative — so an
    older one has nothing it lacks. Best effort: the run has already published, and
    a tidy-up failure must not turn that into a bad night.
    """
    closed: list[int] = []
    pulls = github(env, "GET", "/pulls?state=open&per_page=100")
    if not isinstance(pulls, list):
        return closed

    for pull in pulls:
        head = (pull.get("head") or {}).get("ref") or ""
        if head == keep or not head.startswith(BRANCH_PREFIX):
            continue
        number = pull.get("number")
        try:
            # A conversation comment, so `/issues/`; `/pulls/{n}/comments` is the
            # review-comment endpoint and rejects a bare body with 422.
            github(env, "POST", f"/issues/{number}/comments", {"body": f"Superseded by `{keep}`."})
            github(env, "PATCH", f"/pulls/{number}", {"state": "closed"})
            github(env, "DELETE", f"/git/refs/heads/{head}")
        except Exception as error:  # noqa: BLE001 - tidying must not fail the run
            print(f"[nightly] could not retire {head}: {error}")
            continue
        closed.append(number)
    return closed


def notify(env: dict, title: str, message: str, priority: str = "default") -> None:
    """A failed notification must never fail the run."""
    url = env.get("NTFY_URL")
    if not url:
        return
    headers = {
        "Title": title.encode("ascii", "replace").decode("ascii"),
        "Priority": priority,
        "Content-Type": "text/plain; charset=utf-8",
    }
    if env.get("NTFY_TOKEN"):
        headers["Authorization"] = f"Bearer {env['NTFY_TOKEN']}"
    request = urllib.request.Request(url, data=message.encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15):
            pass
    except Exception as error:  # noqa: BLE001 - notification is best effort
        print(f"notify failed: {error}")


# --- bookkeeping ----------------------------------------------------------


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def missing_config(env: dict, options) -> list[str]:
    # A rehearsal must run with no secrets at all: neither mode below touches
    # Turso or GitHub.
    if options.dry_run or options.no_git:
        return []
    missing = [name for name in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN") if not env.get(name)]
    if not options.no_push and not env.get("GITHUB_TOKEN"):
        missing.append("GITHUB_TOKEN")
    return missing


def apply_env_file(path_value: str, environ: dict | None = None) -> tuple[dict, str | None]:
    """Merge a dotenv file into the environment, for host runs.

    `demand` reads `os.environ` directly, so the values have to land there rather
    than in a local dict. A relative path is looked up the same way `demand` does
    it — the shell's directory, then the repo root — so `--env-file .env.prod`
    works from `pipeline/` without copying the file.

    The container does not need this: compose injects `ops/.env` as the
    environment before the process starts.
    """
    environ = os.environ if environ is None else environ
    path = demand.locate_env(path_value)
    if path is None:
        return dict(environ), f"env file not found: {path_value}"
    environ.update(demand.parse_env(path.read_text(encoding="utf-8")))
    return dict(environ), None


def load_scores(path: Path = crawl.SCORES_PATH) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_last_run(record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LAST_RUN.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def load_last_run(path: Path = LAST_RUN) -> dict | None:
    """The previous run's record, or None when there is nothing usable."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def cooldown_reason(record: dict | None) -> str | None:
    """Why tonight should make no requests, or None.

    A rate-limited run buys exactly one night off. The skipped run writes its own
    record without the flag, so the schedule alternates instead of stopping for
    good — if the host is still refusing, the night after tries again. Offline
    runs are never skipped: they send nothing.
    """
    if not record or not record.get("rateLimited"):
        return None
    return "the previous run was rate-limited; skipping tonight"


@contextmanager
def single_run(path: Path = LOCK):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        yield False
        return
    try:
        yield True
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


# --- the run --------------------------------------------------------------


def finish(
    env: dict,
    started: str,
    code: int,
    reason: str,
    *,
    summary: dict | None = None,
    commit_hash: str | None = None,
    pr_url: str | None = None,
    rate_limited: bool = False,
) -> int:
    record = {
        "started": started,
        "finished": now(),
        "status": STATUS[code],
        "code": code,
        "reason": reason,
        "commit": commit_hash,
        "pullRequest": pr_url,
        "rateLimited": bool(rate_limited),
    }
    if summary:
        record["corpus"] = {
            "scored": summary["scored"],
            "errors": summary["errors"],
            "added": len(summary["added"]),
            "rescored": len(summary["updated"]),
        }
    write_last_run(record)

    if code == NOTHING:
        # Silent by design: the heartbeat file above is the sign of life.
        pass
    elif code in (OK, PARTIAL, COOLDOWN):
        lines = [summary_line(summary, Decision(code, reason)) if summary else reason]
        if pr_url:
            lines.append(pr_url)
        notify(env, "Starisk nightly", "\n".join(lines), "default")
    else:
        notify(env, "Starisk nightly failed", reason, "high")

    print(f"[nightly] {STATUS[code]}: {reason}")
    return code


def dry_run(options) -> int:
    """Config, connectivity and the live checks. No crawl, no writes, no commit."""
    print("[nightly] dry run: no crawl, no commit, no push")
    print(f"[nightly] publishing to a {BRANCH_PREFIX}<stamp> branch off {BASE}")

    reason = cooldown_reason(load_last_run())
    if reason:
        print(f"[nightly] would skip tonight: {reason}")

    scores = load_scores()
    stats = crawl.summarize(scores)
    print(
        f"[nightly] corpus: {stats['records']} records, {stats['scored']} scored, "
        f"{stats['errors']} with errors"
    )

    report = smoke.run()
    for problem in report.adapter + report.site:
        print(f"[nightly]   ! {problem}")
    if not report.adapter and not report.site:
        print("[nightly] smoke: adapter and site look right")
    if not report.ok:
        print("[nightly] would stop: the live adapter check failed")
        return SMOKE

    # Deliberately does not touch last-run.json: a rehearsal must not look like a run.
    if options.offline:
        print("[nightly] would read the queue without link checks, then crawl the cache")
    else:
        print("[nightly] would read the queue, expand the list, then crawl")
    if report.site:
        print("[nightly] would commit and warn about the site")
    else:
        print("[nightly] would gate and commit if anything changed")
    return OK


def run(options) -> int:
    started = now()
    if options.env_file:
        env, error = apply_env_file(options.env_file)
        if error:
            return finish(env, started, CONFIG, error)
    else:
        env = dict(os.environ)

    missing = missing_config(env, options)
    if missing:
        return finish(env, started, CONFIG, f"missing config: {', '.join(missing)}")

    with single_run() as alone:
        if not alone:
            return finish(env, started, FAILED, "another run holds the lock")

        if options.dry_run:
            return dry_run(options)

        # One night of silence after a rate-limited run: hammering a host that
        # just answered 403 is how a soft limit becomes a ban. The skipped run
        # writes its own record without the flag, so the schedule alternates
        # instead of stopping for good. `--offline` sends nothing and is never
        # skipped; `--no-cooldown` is the manual escape hatch.
        if not (options.no_cooldown or options.offline):
            reason = cooldown_reason(load_last_run())
            if reason:
                return finish(env, started, COOLDOWN, reason)

        before = load_scores()
        rate_limited = False
        index_refused = False
        refusal: list[str] = []
        # Files already dirty when we started are not this run's doing: a stray
        # note in a dev clone must not gate the commit.
        baseline = set(changed())

        try:
            queue_code = demand.main(["--write"] + (["--offline"] if options.offline else []))
        except Exception as error:  # noqa: BLE001 - the queue is an input, not a prerequisite
            print(f"[nightly] the queue read failed: {error}")
            queue_code = 1
        if queue_code != 0:
            print("[nightly] crawling the sources we already have")

        report = smoke.run()
        if not report.ok:
            return finish(
                env,
                started,
                SMOKE,
                "; ".join(str(problem) for problem in report.adapter),
            )

        # Offline keeps to the page cache: expansion only fetches, and discovery has
        # no network to walk the sitemap with.
        index_args = (
            ["--fetch", "--write"]
            if options.offline
            else ["--discover", "--fetch", "--write"]
        )
        if options.force_index:
            # Used by hand after reading the refusal: the numbers are legitimately
            # new, so publish them instead of freezing the directory.
            index_args.append("--force")

        # Programs first: --fetch needs the page cache (a fresh clone has none), and
        # the expansion lever below queues the members of the index this writes.
        index_code = groupings.main(index_args, on_refusal=refusal.append)
        if index_code == 2:
            rate_limited = True
            print("[nightly] the program fetch was rate-limited; keeping the current index")
        elif index_code == 1:
            # The rebuild looked stale (fewer programs, or one that lost ratings or
            # courses). Do not publish it, and do not stop the night: the crawl and
            # scores are still useful, and the published index stays what it was.
            index_refused = True
            detail = refusal[0] if refusal else "reason unknown"
            print(f"[nightly] the program index was refused ({detail}); keeping the current one")
        elif index_code != 0:
            return finish(env, started, FAILED, "the program index rebuild failed")

        if options.offline:
            print("[nightly] offline: skipping the source expansion")
        else:
            # Instructor profiles are a catalogue, not a curriculum: one scored
            # course handed over 455 unrelated slugs, most of them other publishers'
            # courses. Programs are the bounded, deliberate lever, so they are what
            # runs unattended; `--instructors` stays available by hand.
            try:
                grown = expand.main(
                    ["--refresh", "--write", "--programs", "--specializations"]
                )
            except Exception as error:  # noqa: BLE001 - discovery is an input, not a prerequisite
                print(f"[nightly] the expansion failed: {error}")
                grown = 1
            if grown != 0:
                print("[nightly] crawling the sources we already have")

        argv = ["--offline"] if options.offline else []
        if options.limit:
            argv += ["--limit", str(options.limit)]
        if crawl.main(argv) != 0:
            return finish(env, started, FAILED, "the crawl exited non-zero")

        for module in (logos, logo_hires):
            if module.main([]) != 0:
                return finish(env, started, FAILED, f"{module.__name__} exited non-zero")

        synced = subprocess.run(("node", "web/scripts/sync-data.mjs"), cwd=REPO)
        if synced.returncode != 0:
            return finish(env, started, FAILED, "copying the data into the site failed")

        after = load_scores()
        new_paths = [path for path in changed() if path not in baseline]
        summary = diff_summary(before, after)
        rate_limited = rate_limited or summary["rate_limited"]
        decision = decide(new_paths, summary, crawl.summarize(before))
        refusal_detail = refusal[0] if refusal else "reason unknown"
        if index_refused and decision.code == OK:
            # Commit the night's data, but say out loud that the index was not
            # refreshed: a silent refusal is how a directory stalls unseen.
            decision = Decision(PARTIAL, f"program index refused: {refusal_detail}")
        elif index_refused and decision.code == NOTHING:
            return finish(
                env,
                started,
                PARTIAL,
                f"program index refused: {refusal_detail}",
            )

        commit_hash = None
        pr_url = None
        if decision.commit and options.no_git:
            # A rehearsal: the pipeline ran for real, but the data stays in the
            # working tree so nothing is pushed from a clone being edited.
            print("[nightly] rehearsal: the data is left uncommitted")
        elif decision.commit:
            branch = f"{BRANCH_PREFIX}{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M')}"
            try:
                git("switch", "-c", branch)
                commit_hash = commit(
                    [path for path in new_paths if allowed(path)],
                    commit_message(summary),
                    commit_body(summary, decision),
                )
            except GitError as error:
                return finish(env, started, GIT, f"commit failed: {error}", summary=summary)
            if not options.no_push:
                try:
                    push(env, branch)
                except (GitError, KeyError) as error:
                    # The crawl's output is already in the state volume, so this is
                    # not a lost night: the next run publishes it. Partial, not git.
                    return finish(
                        env,
                        started,
                        PARTIAL,
                        f"crawl kept, publish pending: {error}",
                        summary=summary,
                        commit_hash=commit_hash,
                        rate_limited=rate_limited,
                    )
                try:
                    pr_url = open_pull_request(
                        env,
                        branch,
                        "Nightly crawl",
                        pr_body(summary, decision, started[:10]),
                    )
                    for number in close_superseded(env, branch):
                        print(f"[nightly] closed #{number}, superseded by {branch}")
                except Exception as error:  # noqa: BLE001 - the push already landed
                    print(f"[nightly] the pull request was not opened: {error}")

        if report.site:
            print("[nightly] the deployed data has a problem:")
            for problem in report.site:
                print(f"[nightly]   ! {problem}")

        return finish(
            env,
            started,
            decision.code,
            decision.reason,
            summary=summary,
            commit_hash=commit_hash,
            pr_url=pr_url,
            rate_limited=rate_limited,
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m starisk.nightly",
        description="One unattended crawl: queue, smoke, crawl, gate, commit, PR.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="check config, connectivity and the live pages; write nothing",
    )
    parser.add_argument(
        "--env-file",
        metavar="PATH",
        help="read the dotenv file instead of exporting it (host runs only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"fetches per run (default {DEFAULT_LIMIT}; 0 means uncapped)",
    )
    parser.add_argument("--no-push", action="store_true", help="commit on the branch, do not push")
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="run on the current checkout without committing or pushing",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="re-parse cached pages instead of making requests",
    )
    parser.add_argument(
        "--no-cooldown",
        action="store_true",
        help="run even if the previous run was rate-limited",
    )
    parser.add_argument(
        "--force-index",
        action="store_true",
        help="publish the program index even if the rebuild looks stale",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
