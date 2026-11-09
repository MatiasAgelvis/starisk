"""Turn the landing page's course requests into crawl work.

The site writes a missed course to Turso (`course_requests`) when a visitor asks
for it. This is the other end of that wire:

    cd pipeline
    python -m starisk.demand --env-file .env.dev --dry-run
    python -m starisk.demand --env-file .env.prod --write

It reads the inbox, checks that each course still resolves, and appends it to
`data/sources.json` — the same file `pipeline:add` writes, so the next crawl
picks it up. Program requests seed `data/programs.json`, fetch the program page
and add the courses it contains.

Turso is only the inbox. The durable ask list is `data/requests.json`, which this
script owns and `scripts/sync-data.mjs` copies into the site. A request gets an
`added_at` timestamp when it becomes crawl work; everything after that — score,
title, completion — is derived from `scores.json` / `groupings.json`.

Name-only requests cannot become a slug without a Coursera search, so they are
reported and left alone. Writes are opt-in: without `--write` nothing on disk
changes.

No third-party dependency: Turso's HTTP API is JSON, and the queue is small.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .add import merge
from .crawl import SOURCES_PATH, reviews_url, write_atomic
from .expand import instructor_courses
from .fetch import RateLimited, fetch_page
from .groupings import (
    GROUPING_TYPES,
    GROUPINGS_PATH,
    PROGRAMS_PATH,
    build_groupings,
    fetch_missing,
)

ENV_URL = "TURSO_DATABASE_URL"
ENV_TOKEN = "TURSO_AUTH_TOKEN"
PLACEHOLDER = "{SENSITIVE}"
REPO_ROOT = Path(__file__).resolve().parents[2]
REQUESTS_PATH = Path(__file__).resolve().parents[1] / "data" / "requests.json"
DEFAULT_LIMIT = 50
CHECK_DELAY = 0.5
FETCH_DELAY = 1.5

# The key prefix is the type the rest of the pipeline understands. The snapshot
# keeps it explicit so the site does not have to re-derive it.
QUEUE_TYPES = {
    "learn": "course",
    "specializations": "specialization",
    "professional-certificates": "professional-certificate",
    "instructor": "instructor",
}


class TursoError(RuntimeError):
    """The queue could not be read or written."""


@dataclass(frozen=True)
class Demand:
    id: int
    key: str
    kind: str
    query: str
    requests: int
    first_seen: str | None = None
    last_seen: str | None = None


@dataclass
class Plan:
    courses: list[Demand] = field(default_factory=list)
    teachers: list[Demand] = field(default_factory=list)
    programs: list[Demand] = field(default_factory=list)
    unresolved: list[Demand] = field(default_factory=list)
    ignored: list[Demand] = field(default_factory=list)


@dataclass
class Outcome:
    added_courses: list[Demand] = field(default_factory=list)
    existing_courses: list[Demand] = field(default_factory=list)
    gone: list[Demand] = field(default_factory=list)
    added_programs: list[Demand] = field(default_factory=list)
    existing_programs: list[Demand] = field(default_factory=list)
    added_teachers: list[Demand] = field(default_factory=list)
    teacher_courses: dict[str, list[str]] = field(default_factory=dict)
    member_courses: list[str] = field(default_factory=list)
    program_keys: list[str] = field(default_factory=list)
    waiting: list[Demand] = field(default_factory=list)
    unresolved: list[Demand] = field(default_factory=list)
    ignored: list[Demand] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    seeds: list[str] = field(default_factory=list)
    groupings: dict = field(default_factory=dict)
    handled: list[str] = field(default_factory=list)


def parse_env(text: str) -> dict[str, str]:
    """`KEY=VALUE` lines, with comments and an optional `export`."""
    values: dict[str, str] = {}

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]

        key, separator, value = line.partition("=")
        if not separator:
            continue

        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")

    return values


def resolve(
    env: dict[str, str],
    file_values: dict[str, str],
    url: str | None = None,
    token: str | None = None,
) -> tuple[str | None, str | None]:
    """CLI flags win, then `--env-file`, then the shell environment.

    The explicit file beating an exported variable is the point: running with
    `--env-file .env.prod` must not quietly use a dev database from the shell.
    """
    return (
        url or file_values.get(ENV_URL) or env.get(ENV_URL),
        token or file_values.get(ENV_TOKEN) or env.get(ENV_TOKEN),
    )


def locate_env(
    value: str,
    cwd: Path | None = None,
    root: Path = REPO_ROOT,
) -> Path | None:
    """Find the file a relative `--env-file` points at.

    The shell's directory first, then the repository root. mise runs this task
    from `pipeline/`, while the real `.env.prod` lives at the top of the repo;
    copying it into `pipeline/` just to make a relative path resolve would be
    the wrong fix.
    """
    path = Path(value).expanduser()
    if path.is_absolute():
        return path if path.is_file() else None

    for base in (Path(cwd or Path.cwd()), root):
        candidate = base / path
        if candidate.is_file():
            return candidate
    return None


def is_placeholder(value: str | None) -> bool:
    """Vercel's Sensitive variables come back as `{SENSITIVE}` from a pull."""
    return bool(value) and value.strip().upper() == PLACEHOLDER


def http_base(url: str) -> str:
    """`libsql://db.turso.io` -> the HTTP endpoint the pipeline API lives on."""
    base = url.strip().rstrip("/")
    if base.startswith("libsql://"):
        base = "https://" + base[len("libsql://") :]
    return base


def _arg(value: int | str) -> dict:
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    return {"type": "text", "value": str(value)}


def execute(
    url: str,
    token: str,
    statements: list[tuple[str, list[int | str]]],
    fetch=urllib.request.urlopen,
) -> list[list[list[dict]]]:
    """Run the statements in one round trip and return each statement's rows."""
    payload = {
        "requests": [
            {"type": "execute", "stmt": {"sql": sql, "args": [_arg(arg) for arg in args]}}
            for sql, args in statements
        ]
        + [{"type": "close"}]
    }
    request = urllib.request.Request(
        f"{http_base(url)}/v2/pipeline",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with fetch(request, timeout=30) as response:
            body = json.load(response)
    except Exception as error:  # noqa: BLE001 - surfaced as one readable message
        raise TursoError(f"Turso request failed: {error}") from error

    results = body.get("results") or []
    rows = []
    for index in range(len(statements)):
        result = results[index] if index < len(results) else None
        if not result or result.get("type") != "ok":
            message = (result or {}).get("error", {}).get("message", "unknown error")
            raise TursoError(f"Turso query failed: {message}")
        rows.append(result["response"]["result"].get("rows") or [])
    return rows


def read_requests(url: str, token: str, fetch=urllib.request.urlopen) -> list[Demand]:
    [rows] = execute(
        url,
        token,
        [
            (
                "SELECT id, key, kind, query, requests, first_seen, last_seen"
                " FROM course_requests ORDER BY requests DESC, last_seen DESC",
                [],
            )
        ],
        fetch=fetch,
    )

    demands = []
    for row in rows:
        cells = [cell.get("value") for cell in row]
        demands.append(
            Demand(
                id=int(cells[0]),
                key=str(cells[1]),
                kind=str(cells[2]),
                query=str(cells[3]),
                requests=int(cells[4]),
                first_seen=cells[5],
                last_seen=cells[6],
            )
        )
    return demands


def build_plan(demands: list[Demand], min_requests: int = 1, limit: int = DEFAULT_LIMIT) -> Plan:
    """Classify the queue by the key's prefix, not the stored `kind`: the prefix
    is what the rest of the pipeline understands, and `kind` is only the shape
    the browser validated."""
    plan = Plan()
    seen: set[int] = set()
    actionable = 0

    for demand in demands:
        if demand.requests < min_requests or demand.id in seen:
            continue
        seen.add(demand.id)

        kind, _, slug = demand.key.partition("/")
        if not slug:
            plan.ignored.append(demand)
        elif kind == "name":
            plan.unresolved.append(demand)
        elif kind not in {"learn", *GROUPING_TYPES, "instructor"}:
            plan.ignored.append(demand)
        elif actionable >= limit:
            continue
        elif kind == "learn":
            plan.courses.append(demand)
            actionable += 1
        elif kind == "instructor":
            plan.teachers.append(demand)
            actionable += 1
        else:
            plan.programs.append(demand)
            actionable += 1

    return plan


def probe_course(key: str, fetch=fetch_page) -> bool:
    """True when Coursera still serves the reviews page for this course."""
    try:
        fetch(reviews_url(key))
    except Exception:  # noqa: BLE001 - a 404 is the answer we want to report
        return False
    return True


def handle(
    plan: Plan,
    sources: list[str],
    seeds: list[str],
    *,
    offline: bool = False,
    check=probe_course,
    sleep=time.sleep,
    fetch_programs=fetch_missing,
    fetch_teachers=instructor_courses,
    build=build_groupings,
    delay: float = CHECK_DELAY,
) -> Outcome:
    """Decide what to add. Pure with respect to the data files: nothing is written."""
    outcome = Outcome(sources=list(sources), seeds=list(seeds))

    for demand in plan.courses:
        if demand.key in outcome.sources:
            outcome.existing_courses.append(demand)
            outcome.handled.append(demand.key)
            continue

        if not offline:
            if not check(demand.key):
                outcome.gone.append(demand)
                continue
            sleep(delay)

        added, _, _, outcome.sources = merge([demand.key], outcome.sources)
        if added:
            outcome.added_courses.append(demand)
            outcome.handled.append(demand.key)
        else:
            outcome.ignored.append(demand)

    teachers = {demand.key.split("/", 1)[1]: demand for demand in plan.teachers}
    if teachers:
        fetched = fetch_teachers(list(teachers), delay=FETCH_DELAY, offline=offline)
        for slug, demand in teachers.items():
            courses = fetched.get(slug)
            if courses is None:
                outcome.waiting.append(demand)
                continue

            outcome.added_teachers.append(demand)
            outcome.teacher_courses[slug] = courses
            added, _, _, outcome.sources = merge(courses, outcome.sources)
            outcome.member_courses.extend(added)
            outcome.handled.append(demand.key)

    programs = {demand.key: demand for demand in plan.programs}
    for demand in plan.programs:
        if demand.key in outcome.seeds:
            outcome.existing_programs.append(demand)
        else:
            outcome.seeds.append(demand.key)
            outcome.added_programs.append(demand)

    if programs:
        outcome.program_keys = list(programs)
        if not offline:
            fetch_programs(outcome.program_keys, delay=FETCH_DELAY)

        outcome.groupings = build()
        for key, demand in programs.items():
            grouping = outcome.groupings.get(key) or {}
            courses = grouping.get("courses") or []
            if not courses:
                # The page was not fetched (or lists nothing). Leave it out of
                # the ask list so the next run can try again.
                outcome.waiting.append(demand)
                continue

            added, _, _, outcome.sources = merge(courses, outcome.sources)
            outcome.member_courses.extend(added)
            outcome.handled.append(demand.key)

    outcome.unresolved = plan.unresolved
    outcome.ignored.extend(plan.ignored)
    return outcome


def read_list(path: Path) -> list[str]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def queue_type(key: str) -> str:
    return QUEUE_TYPES.get(key.split("/", 1)[0], "other")


def build_snapshot(
    demands: list[Demand],
    generated_at: str,
    previous: dict | None = None,
    handled: list[str] | None = None,
    stamp: str | None = None,
) -> dict:
    """The repo-owned ask list: requests that became crawl work.

    `added_at` is the only lifecycle fact we store. Completion, score and title
    are joined from `scores.json` / `groupings.json` when the site builds.
    """
    rows: dict[str, dict] = {}
    for row in ((previous or {}).get("rows") or []):
        key = row.get("key")
        if key and row.get("added_at"):
            rows[str(key)] = {
                "key": str(key),
                "type": row.get("type") or queue_type(str(key)),
                "query": row.get("query"),
                "requests": int(row.get("requests") or 0),
                "first_seen": row.get("first_seen"),
                "last_seen": row.get("last_seen"),
                "added_at": row["added_at"],
            }

    touched = set(handled or [])
    added = stamp or generated_at
    for demand in demands:
        old = rows.get(demand.key) or {}
        if demand.key not in touched and not old:
            continue
        rows[demand.key] = {
            "key": demand.key,
            "type": queue_type(demand.key),
            "query": demand.query,
            "requests": demand.requests,
            "first_seen": demand.first_seen or old.get("first_seen"),
            "last_seen": demand.last_seen or old.get("last_seen"),
            "added_at": old.get("added_at") or (added if demand.key in touched else None),
        }

    ordered = sorted(
        rows.values(),
        key=lambda row: (str(row.get("added_at") or ""), str(row.get("key") or "")),
        reverse=True,
    )
    return {"generatedAt": generated_at, "rows": ordered}


def export_requests(
    demands: list[Demand],
    previous: dict | None = None,
    handled: list[str] | None = None,
    path: Path | None = None,
    generated_at: str | None = None,
) -> dict:
    stamp = generated_at or now_iso()
    snapshot = build_snapshot(
        demands,
        stamp,
        previous=previous,
        handled=handled,
        stamp=stamp,
    )
    write_atomic(path or REQUESTS_PATH, snapshot)
    return snapshot


def asks(count: int) -> str:
    return f"{count} ask" if count == 1 else f"{count} asks"


def report(outcome: Outcome, dry_run: bool) -> None:
    for demand in outcome.added_courses:
        print(f"  add      {demand.key:<50} {asks(demand.requests)}")
    for demand in outcome.existing_courses:
        print(f"  exists   {demand.key:<50} {asks(demand.requests)}")
    for demand in outcome.gone:
        print(f"  gone     {demand.key:<50} {asks(demand.requests)}  (Coursera did not serve it)")
    for demand in outcome.added_programs:
        print(f"  program  {demand.key:<50} {asks(demand.requests)}")
    for demand in outcome.existing_programs:
        print(f"  seeded   {demand.key:<50} {asks(demand.requests)}")
    for demand in outcome.added_teachers:
        print(f"  teacher  {demand.key:<50} {asks(demand.requests)}")
    for slug, courses in outcome.teacher_courses.items():
        print(f"  courses  {f'instructor/{slug}':<50} {len(courses)} course(s)")
    for key in outcome.program_keys:
        count = len(((outcome.groupings.get(key) or {}).get("courses")) or [])
        if count:
            print(f"  members  {key:<50} {count} course(s)")
    for demand in outcome.unresolved:
        print(f"  manual   {demand.key:<50} {asks(demand.requests)}  ({demand.query!r})")
    for demand in outcome.waiting:
        reason = (
            "profile not fetched"
            if demand.key.startswith("instructor/")
            else "program page not fetched"
        )
        print(f"  waiting  {demand.key:<50} {asks(demand.requests)}  ({reason})")
    for demand in outcome.ignored:
        print(f"  skip     {demand.key:<50} {asks(demand.requests)}  (not a course key)")

    added = len(outcome.added_courses) + len(outcome.member_courses)
    verb = "would add" if dry_run else "added"
    line = (
        f"{verb}: {added} course(s), {len(outcome.added_programs)} program(s), "
        f"{len(outcome.added_teachers)} teacher(s)"
    )
    if outcome.waiting:
        line += f"; {len(outcome.waiting)} page(s) pending"
    if outcome.unresolved:
        line += f"; {len(outcome.unresolved)} need a human"
    print(f"\n{line}.")
    if dry_run:
        print("dry run: nothing written. re-run with --write to apply.")
    elif outcome.handled:
        print("next: mise run pipeline:crawl")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m starisk.demand",
        description="Turn the Turso request inbox into crawl work and a local ask list.",
    )
    parser.add_argument("--offline", action="store_true", help="skip link checks and program fetches")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        action="store_true",
        help="write sources/programs and data/requests.json",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="report only (the default, stated explicitly)",
    )
    parser.add_argument(
        "--min-requests",
        type=int,
        default=1,
        metavar="N",
        help="ignore courses asked for fewer than N times (default: 1)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        metavar="N",
        help=f"handle at most N requests this run (default: {DEFAULT_LIMIT})",
    )
    parser.add_argument("--env-file", metavar="PATH", help="read TURSO_* from this file")
    parser.add_argument("--url", help="override TURSO_DATABASE_URL")
    parser.add_argument("--token", help="override TURSO_AUTH_TOKEN")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    options = parse_args(argv)

    file_values = {}
    if options.env_file:
        path = locate_env(options.env_file)
        if path is None:
            print(f"env file not found: {options.env_file}", file=sys.stderr)
            return 1
        file_values = parse_env(path.read_text(encoding="utf-8"))

    url, token = resolve(dict(os.environ), file_values, options.url, options.token)
    if not url or not token:
        print(
            f"{ENV_URL} and {ENV_TOKEN} are required "
            "(--env-file, the shell, or --url/--token).",
            file=sys.stderr,
        )
        return 1

    if is_placeholder(url) or is_placeholder(token):
        print(
            "The env file still contains Vercel's {SENSITIVE} placeholder: "
            "Sensitive variables cannot be pulled. Use `turso db show <db> --url` "
            "and `turso db tokens create <db>` for a local file instead.",
            file=sys.stderr,
        )
        return 1

    try:
        demands = read_requests(url, token)
    except TursoError as error:
        print(error, file=sys.stderr)
        return 1

    previous = read_json(REQUESTS_PATH)
    if not isinstance(previous, dict):
        previous = {}
    known = {
        str(row.get("key"))
        for row in (previous.get("rows") or [])
        if row.get("key") and row.get("added_at")
    }
    pending = [demand for demand in demands if demand.key not in known]

    plan = build_plan(pending, options.min_requests, options.limit)
    sources = read_list(SOURCES_PATH)
    seeds = read_list(PROGRAMS_PATH)

    try:
        outcome = handle(plan, sources, seeds, offline=options.offline)
    except RateLimited as error:
        print(f"Coursera rate limited the program fetch: {error}", file=sys.stderr)
        return 1

    report(outcome, dry_run=not options.write)

    if not options.write:
        return 0

    if outcome.sources != sources:
        write_atomic(SOURCES_PATH, outcome.sources)
    if outcome.seeds != seeds:
        write_atomic(PROGRAMS_PATH, outcome.seeds)
    if outcome.groupings:
        write_atomic(GROUPINGS_PATH, outcome.groupings)

    snapshot = export_requests(demands, previous=previous, handled=outcome.handled)
    print(
        f"ask list: {len(snapshot['rows'])} row(s), "
        f"{len(outcome.handled)} request(s) added this run"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
