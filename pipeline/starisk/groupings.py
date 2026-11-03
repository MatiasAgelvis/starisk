"""Derive program membership from cached specialization pages.

A program (specialization or Professional Certificate) is a many-to-many
relationship: a program contains many courses, and a course can sit in several
programs. This module builds the derived index — conceptually the `programs`
table plus the `program_courses` join — from pages that already list their
courses. The `courses` values are foreign keys into `scores.json`.

No network: it reads the page cache. Program pages are fetched by `expand` (for
specializations) or added explicitly (for Professional Certificates).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .adapter import extract_details, extract_specialization_courses, extract_title
from .cache import CACHE_DIR, load_page
from .crawl import DATA_DIR, write_atomic

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
    """One program from its landing page, or None when the page has no courses."""
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
    provider = extract_details(html).get("provider")
    if provider:
        grouping["provider"] = provider
    return grouping


def cached_grouping_keys(directory: Path = CACHE_DIR) -> list[str]:
    """Program keys whose pages are already in the cache, in filename order."""
    keys = []
    for path in sorted(directory.glob("*.html.gz")):
        key = grouping_key(path)
        if key:
            keys.append(key)
    return list(dict.fromkeys(keys))


def build_groupings(directory: Path = CACHE_DIR) -> dict[str, dict]:
    """The derived program index, keyed by `type/slug`.

    A specialization that is also a crawl source has a base page plus a
    `.landing` copy; either can carry the course list, so try both.
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
    return groupings


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m starisk.groupings",
        description="Rebuild data/groupings.json from cached program pages.",
    )
    parser.add_argument("--write", action="store_true", help="write data/groupings.json")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    options = parse_args(argv)
    groupings = build_groupings()
    links = sum(len(grouping["courses"]) for grouping in groupings.values())

    print(f"groupings: {len(groupings)} | course links: {links}")
    if not options.write:
        print("report only. re-run with --write to store the index.")
        return 0

    write_atomic(GROUPINGS_PATH, groupings)
    print(f"wrote {GROUPINGS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
