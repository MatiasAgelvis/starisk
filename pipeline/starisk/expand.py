"""Grow data/sources.json from pages that already list courses.

The crawl list is curated, but two kinds of page hand out more of it for the
price of one request each:

  specializations  a certificate -> the courses the specialization is made of
  instructors      a teacher already indexed -> everything else they teach

Both answer "what belongs next to what I already crawled", which is the right
question for this corpus. Neither is "crawl Coursera": the sitemap has ~23k
courses and this stays explicit and small.

    cd pipeline
    python3 -m starisk.expand                 # report both levers, write nothing
    python3 -m starisk.expand --write         # extend data/sources.json
    python3 -m starisk.expand --instructors   # one lever only
    python3 -m starisk.expand --limit 10      # at most 10 parent pages
    python3 -m starisk.expand --refresh       # re-download the sitemap

Parent pages are cached, so a second run costs no requests.
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

from .adapter import extract_instructor_courses, extract_specialization_courses
from .cache import CACHE_DIR, load_page, store_page
from .crawl import SCORES_PATH, SOURCES_PATH, normalize_source, write_atomic
from .fetch import fetch_page
from .link import CALIBRATION_PATH, candidates, clean_title, page_title, tokens

SITEMAP_URL = "https://www.coursera.org/sitemap~www~specializations.xml"
SPECIALIZATION_URL = "https://www.coursera.org/specializations/{slug}"
INSTRUCTOR_URL = "https://www.coursera.org/instructor/{slug}"
SITEMAP_CACHE = Path(__file__).resolve().parents[1] / "data" / ".cache" / "coursera-specializations.txt"

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
    if not cache_path.exists() or refresh:
        xml = fetch(SITEMAP_URL)
        found = []
        for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
            if "/specializations/" in loc:
                slug = loc.rsplit("/specializations/", 1)[1].strip("/")
                if slug:
                    found.append(slug)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("\n".join(sorted(set(found))) + "\n", encoding="utf-8")
    return [
        line.strip()
        for line in cache_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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
    limit: int | None = None,
    refresh: bool = False,
) -> tuple[dict[str, list[str]], list[str]]:
    """Work out which courses to add, and why.

    Returns `{key: [parents that linked it]}` plus printable report lines. Nothing
    here writes to `sources.json`; `main` does, only under `--write`.
    """
    known = {normalize_source(source) for source in existing}
    found: dict[str, list[str]] = {}
    lines: list[str] = []
    budget = limit

    if specializations:
        slugs = load_slugs(fetch=fetch, refresh=refresh, cache_path=slug_cache)
        certificates = [
            entry
            for entry in entries
            if entry.get("issuer") == "Coursera" and entry.get("type") == "specialization"
        ]
        lines.append(f"specializations: {len(slugs)} slugs in the sitemap")
        resolved = 0
        for entry in certificates:
            if budget is not None and budget <= 0:
                lines.append("  (budget reached)")
                break
            if budget is not None:
                budget -= 1
            slug, html = resolve_specialization(entry, slugs, fetch, delay, sleep, cache_dir)
            if not html:
                lines.append(f"  miss   {entry['title'][:52]}")
                continue
            resolved += 1
            courses = extract_specialization_courses(html)
            for course in courses:
                found.setdefault(f"learn/{course}", []).append(f"specialization:{slug}")
            lines.append(
                f"  ok     {entry['title'][:52]:54} {slug:30} {len(courses)} courses"
            )
        lines.append(f"  resolved {resolved}/{len(certificates)} certificates")

    if instructors:
        people = indexed_instructors(scores)
        lines.append(f"instructors: {len(people)} indexed")
        visited = 0
        for slug, person in people.items():
            if budget is not None and budget <= 0:
                lines.append("  (budget reached)")
                break
            if budget is not None:
                budget -= 1
            html = _page(f"instructor/{slug}", INSTRUCTOR_URL.format(slug=slug), fetch, delay, sleep, cache_dir)
            if not html:
                lines.append(f"  miss   {person.get('name', slug)}")
                continue
            visited += 1
            courses = extract_instructor_courses(html)
            for course in courses:
                found.setdefault(f"learn/{course}", []).append(f"instructor:{slug}")
            lines.append(f"  ok     {(person.get('name') or slug)[:52]:54} {len(courses)} courses")
        lines.append(f"  read {visited}/{len(people)} profiles")

    new = {key: parents for key, parents in found.items() if key not in known}
    lines.append("")
    lines.append(
        f"linked {len(found)} courses | already listed {len(found) - len(new)} | new {len(new)}"
    )
    if delay:
        requests = len(new) * 2  # reviews page + landing page, per D18
        lines.append(
            f"estimated crawl: {requests} requests, about {requests * delay / 60:.1f} min "
            f"at {delay:g}s between requests"
        )
    return new, lines


def main(argv: list[str]) -> int:
    write = "--write" in argv
    refresh = "--refresh" in argv
    only_specializations = "--specializations" in argv
    only_instructors = "--instructors" in argv
    limit = None
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])

    entries = (
        json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
        if CALIBRATION_PATH.exists()
        else []
    )
    scores = (
        json.loads(SCORES_PATH.read_text(encoding="utf-8")) if SCORES_PATH.exists() else {}
    )
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8")) if SOURCES_PATH.exists() else []

    new, lines = plan(
        scores,
        entries,
        existing=sources,
        delay=DELAY,
        specializations=only_specializations or not only_instructors,
        instructors=only_instructors or not only_specializations,
        limit=limit,
        refresh=refresh,
    )
    print("\n".join(lines))

    if not write:
        print("\nreport only. re-run with --write to add them to data/sources.json.")
        return 0

    merged = list(dict.fromkeys([*sources, *sorted(new)]))
    write_atomic(SOURCES_PATH, merged)
    print(f"\nwrote {len(merged)} sources to {SOURCES_PATH} ({len(new)} new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
