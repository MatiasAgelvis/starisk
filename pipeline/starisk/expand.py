"""Grow data/sources.json from pages that already list courses.

The crawl list is curated, but three kinds of page hand out more of it for the
price of one request each (or none at all):

  specializations  a certificate -> the courses the specialization is made of
  instructors      a teacher already indexed -> everything else they teach
  programs         the derived program index -> the courses of a bundle we publish

Programs carry no request cost: `groupings.json` already holds the membership, so
the lever just makes sure every course in a published bundle is queued. That is
the purposeful version of the instructor lever — a bundle someone chose to
publish, not everything a publisher ever taught.

Neither lever is "crawl Coursera": the sitemap has ~23k courses and this stays
explicit and small.

    cd pipeline
    python3 -m starisk.expand                 # report every lever, write nothing
    python3 -m starisk.expand --write         # extend data/sources.json
    python3 -m starisk.expand --programs      # one lever only
    python3 -m starisk.expand --limit 10      # at most 10 parent pages
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from .adapter import extract_instructor_courses, extract_specialization_courses
from .cache import CACHE_DIR, load_page, store_page
from .crawl import SCORES_PATH, SOURCES_PATH, load_retired, normalize_source, write_atomic
from .fetch import fetch_page
from .groupings import read_index
from .link import CALIBRATION_PATH, candidates, clean_title, page_title, tokens
from .paths import CACHE_DIR as STATE_CACHE
from .sitemap import load_slugs as load_cached_slugs

SITEMAP_URL = "https://www.coursera.org/sitemap~www~specializations.xml"
SPECIALIZATION_URL = "https://www.coursera.org/specializations/{slug}"
INSTRUCTOR_URL = "https://www.coursera.org/instructor/{slug}"
SITEMAP_CACHE = STATE_CACHE / "coursera-specializations.txt"

DELAY = 1.5

_SPECIALIZATION = re.compile(r"\s+Specialization$", re.IGNORECASE)


def bare_title(title: str) -> str:
    """\"Deep Learning Specialization\" and \"Deep Learning\" are the same thing."""
    return _SPECIALIZATION.sub("", clean_title(title))


def load_slugs(
    fetch=fetch_page,
    refresh: bool = False,
    cache_path: Path = SITEMAP_CACHE,
) -> list[str]:
    """Specialization slugs from Coursera's sitemap, cached to disk."""
    return load_cached_slugs(
        SITEMAP_URL,
        "/specializations/",
        cache_path,
        fetch=fetch,
        refresh=refresh,
    )


def _page(key: str, url: str, fetch, delay, sleep, cache_dir) -> str | None:
    """Cached GET. Instructor and specialization pages are fetched once."""
    html = load_page(key, cache_dir)
    if html is not None:
        return html
    try:
        html = fetch(url)
    except Exception:  # noqa: BLE001 - a dead parent page is not fatal
        return None
    store_page(key, html, cache_dir)
    if delay:
        sleep(delay)
    return html


def resolve_specialization(
    entry: dict,
    slugs: list[str],
    fetch=fetch_page,
    delay: float = DELAY,
    sleep=time.sleep,
    cache_dir: Path = CACHE_DIR,
) -> tuple[str | None, str | None]:
    """Find the specialization slug for a certificate, confirmed by `og:title`.

    The title check is the same rule as the course mapping: a wrong slug is worse
    than a missing one, so a candidate only wins if the page names itself exactly.
    """
    wanted = tokens(bare_title(entry["title"]))
    for slug, _value in candidates(bare_title(entry["title"]), slugs, limit=3):
        html = _page(f"specializations/{slug}", SPECIALIZATION_URL.format(slug=slug), fetch, delay, sleep, cache_dir)
        if html and tokens(bare_title(page_title(html))) == wanted:
            return slug, html
    return None, None


def indexed_instructors(scores: dict) -> dict[str, dict]:
    """Every person with a Coursera profile, once."""
    people: dict[str, dict] = {}
    for record in scores.values():
        for person in record.get("instructors") or []:
            slug = person.get("slug")
            if slug and slug not in people:
                people[slug] = person
    return people


def instructor_courses(
    slugs: list[str],
    fetch=fetch_page,
    delay: float = DELAY,
    sleep=time.sleep,
    cache_dir: Path = CACHE_DIR,
    offline: bool = False,
) -> dict[str, list[str]]:
    """Course keys for these instructor profiles, keyed by instructor slug.

    A slug missing from the result could not be read. With `offline`, only the
    page cache is consulted — the same rule as `build_groupings`.
    """
    found: dict[str, list[str]] = {}
    for slug in slugs:
        key = f"instructor/{slug}"
        html = (
            load_page(key, cache_dir)
            if offline
            else _page(key, INSTRUCTOR_URL.format(slug=slug), fetch, delay, sleep, cache_dir)
        )
        if html is None:
            continue
        found[slug] = [f"learn/{course}" for course in extract_instructor_courses(html)]
    return found


def plan(
    scores: dict,
    entries: list[dict],
    existing=(),
    fetch=fetch_page,
    delay: float = 0.0,
    sleep=time.sleep,
    cache_dir: Path = CACHE_DIR,
    slug_cache: Path = SITEMAP_CACHE,
    specializations: bool = True,
    instructors: bool = False,
    programs: bool = False,
    limit: int | None = None,
    refresh: bool = False,
    log=None,
    retired=(),
    program_index: dict | None = None,
) -> tuple[dict[str, list[str]], list[str]]:
    """Work out which courses to add, and why.

    Returns `{key: [parents that linked it]}` plus printable report lines. Nothing
    here writes to `sources.json`; `main` does, only under `--write`. `log`, when
    given, receives each line as it happens (with progress), so a long run does
    not look frozen.
    """
    known = {normalize_source(source) for source in existing}
    found: dict[str, list[str]] = {}
    lines: list[str] = []
    budget = limit
    started = time.monotonic()

    def report(line: str, live: str | None = None) -> None:
        lines.append(line)
        if log:
            log(live or line)

    def progress(index: int, total: int, line: str) -> str:
        elapsed = time.monotonic() - started
        return f"[{index}/{total} {elapsed:5.1f}s] {line.strip()}"

    if specializations:
        report("specializations: reading sitemap...")
        slugs = load_slugs(fetch=fetch, refresh=refresh, cache_path=slug_cache)
        certificates = [
            entry
            for entry in entries
            if entry.get("issuer") == "Coursera" and entry.get("type") == "specialization"
        ]
        report(f"specializations: {len(slugs)} slugs in the sitemap")
        resolved = 0
        for index, entry in enumerate(certificates, 1):
            if budget is not None and budget <= 0:
                report("  (budget reached)")
                break
            if budget is not None:
                budget -= 1
            slug, html = resolve_specialization(entry, slugs, fetch, delay, sleep, cache_dir)
            if not html:
                line = f"  miss   {entry['title'][:52]}"
                report(line, progress(index, len(certificates), line))
                continue
            resolved += 1
            courses = extract_specialization_courses(html)
            for course in courses:
                found.setdefault(f"learn/{course}", []).append(f"specialization:{slug}")
            line = f"  ok     {entry['title'][:52]:54} {slug:30} {len(courses)} courses"
            report(line, progress(index, len(certificates), line))
        report(f"  resolved {resolved}/{len(certificates)} certificates")

    if instructors:
        people = indexed_instructors(scores)
        report(f"instructors: {len(people)} indexed")
        visited = 0
        for index, (slug, person) in enumerate(people.items(), 1):
            if budget is not None and budget <= 0:
                report("  (budget reached)")
                break
            if budget is not None:
                budget -= 1
            html = _page(
                f"instructor/{slug}",
                INSTRUCTOR_URL.format(slug=slug),
                fetch,
                delay,
                sleep,
                cache_dir,
            )
            if not html:
                line = f"  miss   {person.get('name', slug)}"
                report(line, progress(index, len(people), line))
                continue
            visited += 1
            courses = extract_instructor_courses(html)
            for course in courses:
                found.setdefault(f"learn/{course}", []).append(f"instructor:{slug}")
            line = f"  ok     {(person.get('name') or slug)[:52]:54} {len(courses)} courses"
            report(line, progress(index, len(people), line))
        report(f"  read {visited}/{len(people)} profiles")

    if programs:
        index = program_index if program_index is not None else read_index()
        links = 0
        for key, group in index.items():
            for course in group.get("courses") or []:
                links += 1
                found.setdefault(normalize_source(course), []).append(f"program:{key}")
        report(f"programs: {len(index)} programs, {links} course links")

    new = {key: parents for key, parents in found.items() if key not in known}
    # A retired course must not come back through a profile that still lists it.
    gone = {key for key in new if key in retired}
    new = {key: parents for key, parents in new.items() if key not in gone}
    report("")
    report(
        f"linked {len(found)} courses | already listed "
        f"{len(found) - len(new) - len(gone)} | retired {len(gone)} | new {len(new)}"
    )
    if delay:
        requests = len(new) * 2  # reviews page + landing page, per D18
        report(
            f"estimated crawl: {requests} requests, about {requests * delay / 60:.1f} min "
            f"at {delay:g}s between requests"
        )
    return new, lines


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m starisk.expand",
        description="Grow data/sources.json from specializations, instructors and programs.",
    )
    parser.add_argument("--write", action="store_true", help="extend data/sources.json")
    parser.add_argument("--refresh", action="store_true", help="re-download the sitemap")
    parser.add_argument(
        "--specializations",
        action="store_true",
        help="use only the specialization lever",
    )
    parser.add_argument(
        "--instructors",
        action="store_true",
        help="use only the instructor lever",
    )
    parser.add_argument(
        "--programs",
        action="store_true",
        help="use only the program lever (no requests: reads groupings.json)",
    )
    parser.add_argument("--limit", type=int, help="visit at most this many parent pages")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    options = parse_args(argv)

    entries = (
        json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
        if CALIBRATION_PATH.exists()
        else []
    )
    scores = (
        json.loads(SCORES_PATH.read_text(encoding="utf-8")) if SCORES_PATH.exists() else {}
    )
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8")) if SOURCES_PATH.exists() else []

    # No lever flag means every lever, which is what the nightly runs.
    chosen = options.specializations or options.instructors or options.programs

    new, _lines = plan(
        scores,
        entries,
        existing=sources,
        delay=DELAY,
        specializations=options.specializations or not chosen,
        instructors=options.instructors or not chosen,
        programs=options.programs or not chosen,
        limit=options.limit,
        refresh=options.refresh,
        log=lambda line: print(line, flush=True),
        retired=load_retired(),
    )

    if not options.write:
        print("\nreport only. re-run with --write to add them to data/sources.json.")
        return 0

    merged = list(dict.fromkeys([*sources, *sorted(new)]))
    write_atomic(SOURCES_PATH, merged)
    print(f"\nwrote {len(merged)} sources to {SOURCES_PATH} ({len(new)} new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
