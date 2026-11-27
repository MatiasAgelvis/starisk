"""Derive program membership from cached specialization pages.

A program (specialization or Professional Certificate) is a many-to-many
relationship: a program contains many courses, and a course can sit in several
programs. This module builds the derived index — conceptually the `programs`
table plus the `program_courses` join — from pages that already list their
courses. The `courses` values are foreign keys into `scores.json`.

A program is **not a course**: its page has no written reviews of its own (the
review widget belongs to whichever course is selected), so no score is derived
here. What is stored is the bundle's own aggregate — Coursera's pooled rating and
the population behind it — which is the one number that is the program's own.

No network: it reads the page cache. Program pages are fetched by `expand` (for
specializations) or added explicitly (for Professional Certificates). `--discover`
walks Coursera's specialization sitemap to add the next few program seeds, which
is how the directory grows without an editorial list.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path

from .adapter import (
    extract_aggregate,
    extract_details,
    extract_specialization_courses,
    extract_title,
)
from .cache import CACHE_DIR, load_page, store_page
from .crawl import DATA_DIR, load_retired, write_atomic, write_retired
from .fetch import RateLimited, Retired, fetch_page, jitter
from .sitemap import program_slugs

GROUPINGS_PATH = DATA_DIR / "groupings.json"
PROGRAMS_PATH = DATA_DIR / "programs.json"

# Programs discovered per run. One request each, and each brings a handful of
# courses into the queue, so this is the throttle on corpus growth.
DISCOVER_PER_RUN = 20

# Program pages fetched per run. Discovery adds 20 a night, so a warm cache fetches
# about 20; the cap is a ceiling for the cold case, where a partial fetch must not
# turn into a hundreds-of-requests burst. Published programs are fetched first and
# carried forward when their page is missing, so a budget never costs the index.
FETCH_PER_RUN = 200

# A single program can move between fetches (Coursera edits a bundle or recounts
# its rating). A tenth of the directory moving at once is the stale-cache
# signature the write guard refuses; the floor keeps small indexes from refusing
# on one edit.
MAX_MOVED_SHARE = 0.1
MIN_MOVED = 5

GROUPINGS_PATH = DATA_DIR / "groupings.json"

# Coursera's two program URL types. Both render their course list with the same
# `sdp-course-list-link` hook.
GROUPING_TYPES = ("specializations", "professional-certificates")
_TYPE_LABELS = {
    "specializations": "specialization",
    "professional-certificates": "professional-certificate",
}


def grouping_key(path: Path) -> str | None:
    """`specializations__algorithms.html.gz` -> `specializations/algorithms`."""
    suffix = ".html.gz"
    if not path.name.endswith(suffix):
        return None

    stem = path.name[: -len(suffix)]
    if stem.endswith(".landing"):
        stem = stem[: -len(".landing")]
    if "__" not in stem:
        return None

    kind, slug = stem.split("__", 1)
    if kind not in GROUPING_TYPES or not slug:
        return None
    return f"{kind}/{slug}"


def extract_grouping(html: str, key: str) -> dict | None:
    """One program from its landing page, or None when the page has no courses.

    A program has no written reviews of its own — Coursera renders the review
    widget of whichever course is selected — so this never stores a score. What
    it does store is the page's own aggregate: the pooled rating Coursera shows
    for the bundle, and the population behind it. That is the one number a
    program has that is not derived from its courses.
    """
    kind = key.split("/", 1)[0]
    courses = list(
        dict.fromkeys(f"learn/{slug}" for slug in extract_specialization_courses(html))
    )
    if not courses:
        return None

    title = extract_title(html)
    if not title:
        return None

    grouping = {
        "key": key,
        "type": _TYPE_LABELS[kind],
        "title": title,
        "url": f"https://www.coursera.org/{key}",
        "courses": courses,
    }
    details = extract_details(html)
    provider = details.get("provider")
    if provider:
        grouping["provider"] = provider

    aggregate = extract_aggregate(html)
    if aggregate["rating"] is not None:
        grouping["coursera"] = round(aggregate["rating"], 1)
    if aggregate["ratings_total"]:
        grouping["ratings_total"] = aggregate["ratings_total"]
    if aggregate["counts"]:
        grouping["rating_counts"] = aggregate["counts"]
    return grouping


def cached_grouping_keys(directory: Path = CACHE_DIR) -> list[str]:
    """Program keys whose pages are already in the cache, in filename order."""
    keys = []
    for path in sorted(directory.glob("*.html.gz")):
        key = grouping_key(path)
        if key:
            keys.append(key)
    return list(dict.fromkeys(keys))


def build_groupings(
    directory: Path = CACHE_DIR,
    previous: dict | None = None,
    retired: dict | None = None,
) -> dict[str, dict]:
    """The derived program index, keyed by `type/slug`.

    A specialization that is also a crawl source has a base page plus a
    `.landing` copy; either can carry the course list, so try both.

    `previous` is the published index: a program whose page is not cached keeps
    its published entry instead of vanishing. That is what makes a fetch budget
    free — a cold cache means stale numbers for a night, not a smaller directory
    and not a refused write. A tombstoned key is never carried.
    """
    groupings = {}
    for key in cached_grouping_keys(directory):
        for candidate in (key, f"{key}.landing"):
            html = load_page(candidate, directory)
            if not html:
                continue
            grouping = extract_grouping(html, key)
            if grouping:
                groupings[key] = grouping
                break

    for key, grouping in (previous or {}).items():
        if key in groupings or (retired and key in retired):
            continue
        groupings[key] = grouping

    return groupings


def read_seeds(path: Path = PROGRAMS_PATH) -> list[str]:
    """The program keys someone committed to fetching: `programs.json`."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [str(value).strip() for value in data if str(value).strip()]


def spread(slugs: list[str]) -> list[str]:
    """Order the sitemap so the walk samples all of it, not its alphabetical head.

    `program_slugs` returns a sorted list, so taking the first N unknown every
    night would spend the first months of the budget on `advanced-*` and
    `agentic-*` and never reach the rest of the alphabet. A stable hash gives
    every slug an equal place in line: no seed to store, the same order on every
    machine and every run, and adding a slug to the sitemap does not reorder the
    ones already queued.
    """
    return sorted(slugs, key=lambda slug: hashlib.sha1(slug.encode()).digest())


def discover_candidates(
    index: dict,
    seeds: list[str],
    retired: dict,
    slugs: list[str],
    limit: int = DISCOVER_PER_RUN,
    cached: Iterable[str] = (),
) -> list[str]:
    """The next program pages nobody has fetched yet, in the order given.

    `index` (published), `seeds` (committed), `retired` (tombstones) and `cached`
    (pages already on disk) are everything already paid for. Walking in sitemap
    order means every run advances instead of retrying the head of the list, and a
    404 is recorded once rather than paid for every night.

    `cached` matters as much as the rest: a program page that fetched fine but
    yielded no course list is not in the index, not a seed and not retired, so
    without it the page stays a candidate forever, eats a slot of the nightly
    discovery budget and is refetched never. With it, a cached-but-silent page is
    skipped until someone fixes the adapter and clears the cache.
    """
    known = set(index) | set(seeds) | set(retired) | set(cached)
    candidates = []
    for slug in slugs:
        key = f"specializations/{slug}"
        if key in known:
            continue
        candidates.append(key)
        if len(candidates) >= limit:
            break
    return candidates


def load_seed_keys(path: Path = PROGRAMS_PATH, index_path: Path = GROUPINGS_PATH) -> list[str]:
    """Program keys to fetch when their pages are not cached yet.

    `groupings.json` holds the ones already published; `programs.json` holds the
    programs someone asked for. Published programs come first: a cold cache must
    not lose them to a fetch budget, and a seed can wait a night. A fresh clone
    has an empty page cache, so without the index a rebuild would only know about
    the seeds and drop every program it already has.
    """
    keys = list(read_index(index_path))
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        for value in data:
            key = str(value).strip()
            kind = key.split("/", 1)[0] if "/" in key else ""
            if kind in GROUPING_TYPES and key.count("/") == 1:
                keys.append(key)
    return list(dict.fromkeys(keys))


def fetch_missing(
    keys: list[str],
    fetch=fetch_page,
    cache_dir: Path = CACHE_DIR,
    delay: float = 0.0,
    sleep=time.sleep,
    retired: dict | None = None,
    limit: int | None = None,
    log=print,
) -> int:
    """Fetch seeded program pages that are not in the cache. Returns the count.

    A 404/410 here means the program is gone, not that the run broke: it is
    tombstoned in `retired` (when a dict is given) so discovery never pays for it
    again.

    `limit` caps the pages fetched this run — the caller passes published keys
    first, so a cold cache drains over several nights instead of hammering the
    host with hundreds of requests at once. Prints the pending count and one line
    per fetched page: this loop is where a run spends minutes in silence, and
    silence looks like a hang.
    """
    pending = list(
        dict.fromkeys(
            key
            for key in keys
            if not (retired and key in retired)
            and not (load_page(key, cache_dir) or load_page(f"{key}.landing", cache_dir))
        )
    )
    total = len(pending)
    if limit:
        pending = pending[:limit]
    if not pending:
        return 0
    if len(pending) < total:
        log(f"  fetching {len(pending)} of {total} program page(s); the rest next run")
    else:
        log(f"  fetching {len(pending)} program page(s)")

    fetched = 0
    for index, key in enumerate(pending, 1):
        try:
            html = fetch(f"https://www.coursera.org/{key}")
        except RateLimited:
            raise
        except Retired as error:
            if retired is not None:
                retired[key] = {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "reason": str(error),
                }
            print(f"  ! retired ({key}): {error}")
            continue
        except Exception as error:  # noqa: BLE001 - one bad seed must not block the rest
            print(f"  ! seed failed ({key}): {error}")
            continue
        store_page(key, html, cache_dir)
        fetched += 1
        log(f"  [{index}/{len(pending)}] {key}")
        if delay:
            sleep(jitter(delay))
    return fetched


def read_index(path: Path = GROUPINGS_PATH) -> dict:
    """The index currently on disk, or an empty one when it is missing or broken."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def refuse_reason(new: dict, previous: dict, force: bool = False) -> str | None:
    """Why writing this index would be unsafe, or None when it is fine.

    The index is derived from cached pages, so it may only ever say *more* than
    the version on disk: a smaller rebuild means the cache is missing pages, and
    that is always refused.

    Per-program movement is different. Coursera edits bundles and recounts
    ratings, so one program changing between fetches is news, not corruption.
    A *batch* of them moving at once — course lists and counts both — is the
    stale-cache signature the guard exists for. Only that is refused.
    """
    if force:
        return None

    if len(new) < len(previous):
        return (
            f"refusing to write {len(new)} program(s) over {len(previous)}: the page cache "
            "is incomplete. Re-run with --fetch, or --force if the drop is real."
        )

    moved: list[tuple[str, str]] = []
    for key, old in previous.items():
        entry = new.get(key)
        if entry is None:
            return (
                f"refusing to drop {key}: the page cache is incomplete. "
                "Re-run with --fetch, or --force if the drop is real."
            )

        if (entry.get("courses") or []) != (old.get("courses") or []):
            moved.append((key, "its course list changed"))
            continue

        for field, label in (("ratings_total", "ratings"), ("coursera", "bundle rating")):
            before, after = old.get(field), entry.get(field)
            if (
                isinstance(before, (int, float))
                and isinstance(after, (int, float))
                and after < before
            ):
                moved.append((key, f"its {label} fell from {before} to {after}"))
                break

    limit = max(MIN_MOVED, math.ceil(len(previous) * MAX_MOVED_SHARE))
    if len(moved) > limit:
        key, why = moved[0]
        return (
            f"refusing to write: {len(moved)} of {len(previous)} programs moved "
            f"({key}: {why}). Widespread movement is the signature of a stale cache, "
            "not news from Coursera — --force if real."
        )

    return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m starisk.groupings",
        description="Rebuild data/groupings.json from cached program pages.",
    )
    parser.add_argument("--write", action="store_true", help="write data/groupings.json")
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="fetch seeded program pages that are not cached yet",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="seed the next programs from the sitemap (writes programs.json with --write)",
    )
    parser.add_argument(
        "--discover-limit",
        type=int,
        default=DISCOVER_PER_RUN,
        help=f"programs to discover this run (default {DISCOVER_PER_RUN})",
    )
    parser.add_argument(
        "--fetch-limit",
        type=int,
        default=FETCH_PER_RUN,
        help=f"program pages to fetch this run, 0 for no cap (default {FETCH_PER_RUN})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="write even when the index would lose programs",
    )
    return parser.parse_args(argv)


def main(argv: list[str], on_refusal: Callable[[str], None] | None = None) -> int:
    options = parse_args(argv)
    retired = load_retired()
    known_retired = len(retired)

    if options.discover:
        seeds = read_seeds()
        slugs = spread(program_slugs())
        candidates = discover_candidates(
            read_index(),
            seeds,
            retired,
            slugs,
            options.discover_limit,
            cached=cached_grouping_keys(),
        )
        print(
            f"discovered {len(candidates)} program(s) from {len(slugs)} sitemap slug(s)"
        )
        for key in candidates:
            print(f"  + {key}")
        if candidates and options.write:
            write_atomic(PROGRAMS_PATH, [*seeds, *candidates])
            print(f"wrote {PROGRAMS_PATH} ({len(candidates)} new seed(s))")

    if options.fetch:
        try:
            fetched = fetch_missing(
                load_seed_keys(),
                delay=1.5,
                retired=retired,
                limit=options.fetch_limit or None,
            )
        except RateLimited as error:
            # 2, not 1: the index on disk is still valid, so a caller can carry on.
            print(f"Coursera rate limited the program fetch: {error}", file=sys.stderr)
            return 2
        print(f"seeded {fetched} program page(s)")
        if len(retired) > known_retired:
            write_retired(retired)

    published = read_index()
    groupings = build_groupings(previous=published, retired=retired)
    links = sum(len(grouping["courses"]) for grouping in groupings.values())

    carried = len(set(published) - set(cached_grouping_keys()))
    extra = f" ({carried} carried: no cached page)" if carried else ""
    print(f"groupings: {len(groupings)} | course links: {links}{extra}")
    if not options.write:
        print("report only. re-run with --write to store the index.")
        return 0

    # Compare against what should survive: a tombstoned program is deliberately
    # gone, not a shrinking cache.
    expected = {key: entry for key, entry in published.items() if key not in retired}
    reason = refuse_reason(groupings, expected, force=options.force)
    if reason:
        print(reason, file=sys.stderr)
        # The nightly's notification carries this now: "the index was refused"
        # without naming the program is not something anyone can act on.
        if on_refusal is not None:
            on_refusal(reason)
        return 1

    write_atomic(GROUPINGS_PATH, groupings)
    print(f"wrote {GROUPINGS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
