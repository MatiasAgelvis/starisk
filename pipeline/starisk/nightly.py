"""One unattended run: queue → smoke → crawl → derive → gate → commit → PR.

The box owns the timing, the residential IP and the notification channel. This
module owns the decisions, so they can be read and tested in one place instead of
inside a shell script:

1. Read the request queue (Turso) into `sources.json`.
2. Check that Coursera still parses and that the deployed data is still served.
3. Crawl, localise logos, rebuild the program index, copy the data into the site.
4. Gate the result. A run that lost scores, grew errors or touched code does not
   become a commit — it becomes a notification.
5. Commit on `data/crawl`, push, and keep one pull request open against `develop`.

The run never touches `main`; publishing is still a human merge.

    python -m starisk.nightly --dry-run     # config, connectivity, smoke; no writes
    python -m starisk.nightly --limit 60
    python -m starisk.nightly --no-push     # rehearsal: commit on the branch, stop

Exit codes are the interface to the timer and the health check:

    0   ok, committed             20  gate refused             50  smoke failed
    10  nothing changed           30  partial (rate limited)   60  missing config
    40  git conflict/divergence   70  unexpected failure
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import crawl, demand, groupings, logo_hires, logos, smoke

REPO = Path(__file__).resolve().parents[2]
LOG_DIR = REPO / "logs"
LAST_RUN = LOG_DIR / "last-run.json"
LOCK = LOG_DIR / "nightly.lock"

BRANCH = "data/crawl"
BASE = "develop"
DEFAULT_LIMIT = 60

OK = 0
NOTHING = 10
GATE = 20
PARTIAL = 30
GIT = 40
SMOKE = 50
CONFIG = 60
FAILED = 70

STATUS = {
    OK: "ok",
    NOTHING: "nothing",
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
    "pipeline/data/requests.json",
    "web/src/data/scores.json",
    "web/src/data/groupings.json",
    "web/src/data/requests.json",
    "web/src/data/logo-sizes.json",
)
DATA_PREFIXES = ("web/public/logos/",)

# Guards against a quietly broken adapter publishing itself.
MAX_SCORED_DROP = 5
MAX_NEW_ERRORS = 2


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
    if errors > MAX_NEW_ERRORS:
        return Decision(GATE, f"{errors} more records with errors")
    if summary["rate_limited"]:
        return Decision(PARTIAL, "Coursera rate-limited the crawl")
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


def changed() -> list[str]:
    """Tracked and untracked paths git would commit; ignored files stay invisible."""
    out = git("status", "--porcelain", "--untracked-files=all").stdout
    paths = []
    for line in out.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path.strip('"'))
    return [path for path in paths if path]


def prepare() -> None:
    """Start the bot branch from current `develop`, without rewriting merged work."""
    if changed():
        raise GitError("working tree is not clean; refusing to start")

    git("fetch", "origin", BASE)
    # Keep the remote-tracking ref current so --force-with-lease compares against
    # what is really on the remote, not a ref from days ago.
    git("fetch", "origin", f"+refs/heads/{BRANCH}:refs/remotes/origin/{BRANCH}", check=False)

    if git("rev-parse", "--verify", "--quiet", BRANCH, check=False).returncode == 0:
        git("switch", BRANCH)
        rebased = git("rebase", f"origin/{BASE}", check=False)
        if rebased.returncode != 0:
            git("rebase", "--abort", check=False)
            raise GitError(f"rebase of {BRANCH} onto origin/{BASE} conflicted")
    else:
        git("switch", "-c", BRANCH, f"origin/{BASE}")


def commit(message: str, body: str) -> str:
    paths = [path for path in changed() if allowed(path)]
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


def push(env: dict) -> None:
    """Push without writing the token anywhere git can keep it.

    The credential helper runs inside git with the token in its environment, so
    the token is absent from argv, from `.git/config` and from the reflog.
    """
    helper = (
        '!f() { test "$1" = get && '
        'printf "username=x-access-token\\npassword=%s\\n" "$GITHUB_TOKEN"; }; f'
    )
    git(
        "push",
        "--force-with-lease",
        "origin",
        f"{BRANCH}:{BRANCH}",
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
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read()
    return json.loads(body) if body else {}


def open_pull_request(env: dict, title: str, body: str) -> str | None:
    """Keep one open PR per merge cycle; reuse it until it is merged."""
    owner = repo_slug(env).split("/")[0]
    open_prs = github(env, "GET", f"/pulls?state=open&head={owner}:{BRANCH}")
    if isinstance(open_prs, list) and open_prs:
        number = open_prs[0]["number"]
        updated = github(env, "PATCH", f"/pulls/{number}", {"title": title, "body": body})
        return updated.get("html_url") if isinstance(updated, dict) else None

    created = github(
        env,
        "POST",
        "/pulls",
        {"title": title, "head": BRANCH, "base": BASE, "body": body},
    )
    return created.get("html_url") if isinstance(created, dict) else None


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
    missing = [name for name in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN") if not env.get(name)]
    if not options.dry_run and not options.no_push and not env.get("GITHUB_TOKEN"):
        missing.append("GITHUB_TOKEN")
    return missing


def load_scores(path: Path = crawl.SCORES_PATH) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_last_run(record: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LAST_RUN.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


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
) -> int:
    record = {
        "started": started,
        "finished": now(),
        "status": STATUS[code],
        "code": code,
        "reason": reason,
        "commit": commit_hash,
        "pullRequest": pr_url,
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
    elif code in (OK, PARTIAL):
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
    print(f"[nightly] branch {BRANCH} → {BASE}, limit {options.limit or 'uncapped'}")

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
    if report.site:
        print("[nightly] would commit and warn about the site")
    else:
        print("[nightly] would crawl, gate and commit if anything changed")
    return OK


def run(options) -> int:
    env = dict(os.environ)
    started = now()

    missing = missing_config(env, options)
    if missing:
        return finish(env, started, CONFIG, f"missing config: {', '.join(missing)}")

    with single_run() as alone:
        if not alone:
            return finish(env, started, FAILED, "another run holds the lock")

        if options.dry_run:
            return dry_run(options)

        try:
            prepare()
        except GitError as error:
            return finish(env, started, GIT, str(error))

        before = load_scores()

        queue_code = demand.main(["--write"] + (["--offline"] if options.offline else []))
        if queue_code != 0:
            print("[nightly] the queue read failed; crawling the sources we already have")

        report = smoke.run()
        if not report.ok:
            return finish(
                env,
                started,
                SMOKE,
                "; ".join(str(problem) for problem in report.adapter),
            )

        argv = ["--offline"] if options.offline else []
        if options.limit:
            argv += ["--limit", str(options.limit)]
        if crawl.main(argv) != 0:
            return finish(env, started, FAILED, "the crawl exited non-zero")

        for module in (logos, logo_hires):
            if module.main([]) != 0:
                return finish(env, started, FAILED, f"{module.__name__} exited non-zero")

        # --fetch first: the index is derived from the page cache, and a fresh
        # clone has none. Without it the rebuild is empty and deletes every
        # program — the exact failure this guard now also refuses.
        if groupings.main(["--fetch", "--write"]) != 0:
            return finish(env, started, FAILED, "the program index rebuild failed")

        synced = subprocess.run(("node", "web/scripts/sync-data.mjs"), cwd=REPO)
        if synced.returncode != 0:
            return finish(env, started, FAILED, "copying the data into the site failed")

        after = load_scores()
        summary = diff_summary(before, after)
        decision = decide(changed(), summary, crawl.summarize(before))

        commit_hash = None
        pr_url = None
        if decision.commit:
            commit_hash = commit(commit_message(summary), commit_body(summary, decision))
            if not options.no_push:
                try:
                    push(env)
                except (GitError, KeyError) as error:
                    return finish(
                        env,
                        started,
                        GIT,
                        f"push failed: {error}",
                        summary=summary,
                        commit_hash=commit_hash,
                    )
                try:
                    pr_url = open_pull_request(
                        env,
                        "Nightly crawl",
                        pr_body(summary, decision, started[:10]),
                    )
                except Exception as error:  # noqa: BLE001 - the push already landed
                    print(f"[nightly] the pull request was not updated: {error}")

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
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"fetches per run (default {DEFAULT_LIMIT}; 0 means uncapped)",
    )
    parser.add_argument("--no-push", action="store_true", help="commit on the branch, do not push")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="re-parse cached pages instead of making requests",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
