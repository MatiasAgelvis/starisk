"""Add courses to the crawl list, by URL or by slug.

    cd pipeline
    python3 -m starisk.add https://www.coursera.org/learn/some-course
    python3 -m starisk.add learn/algorithms-part2 financial-markets
    python3 -m starisk.add --from links.txt
    cat links.txt | python3 -m starisk.add --from -
    python3 -m starisk.add --check https://www.coursera.org/learn/typo   # ask Coursera first
    python3 -m starisk.add --dry-run learn/one learn/two

Adding is all this does: it writes `data/sources.json`, and the next
`pipeline:crawl` scores whatever is missing. Duplicates, wrong URL shapes and
garbage are rejected before they reach the list; `--check` also costs one request
to confirm Coursera still serves the reviews page.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from .crawl import SOURCES_PATH, normalize_source, reviews_url, write_atomic
from .fetch import fetch_page

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# v1 scores courses; specializations are crawlable but not scored as a unit (D17).
_TYPES = frozenset({"learn", "specializations"})


def sources_from_text(text: str) -> list[str]:
    """One per line; blank lines and `#` comments are ignored."""
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def classify(raw: str) -> str | None:
    """A normalised key, or None when the input cannot be a Coursera course."""
    key = normalize_source(raw)
    if "/" not in key:
        return None
    kind, slug = key.split("/", 1)
    if kind not in _TYPES or not _SLUG.match(slug):
        return None
    return key


def merge(raw_sources: list[str], existing: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    """`(added, duplicates, invalid, merged)` — pure, so it is testable."""
    keys = list(existing)
    added, duplicates, invalid = [], [], []
    for raw in raw_sources:
        key = classify(raw)
        if key is None:
            invalid.append(raw)
        elif key in keys:
            duplicates.append(key)
        else:
            keys.append(key)
            added.append(key)
    return added, duplicates, invalid, keys


def reachable(key: str, fetch=fetch_page) -> bool:
    """Does Coursera still serve this course's reviews page?"""
    try:
        return bool(fetch(reviews_url(key)))
    except Exception:  # noqa: BLE001 - a 404 is the answer we want to report
        return False


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m starisk.add",
        description="Add Coursera courses to data/sources.json.",
    )
    parser.add_argument(
        "sources",
        nargs="*",
        metavar="URL_OR_SLUG",
        help="course URLs or slugs",
    )
    parser.add_argument(
        "--from",
        dest="source_file",
        metavar="FILE|-",
        help="read one source per line from a file or stdin",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="ask Coursera whether each added course still resolves",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would change without writing",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    options = parse_args(argv)

    raw = list(options.sources)
    if options.source_file:
        text = (
            sys.stdin.read()
            if options.source_file == "-"
            else Path(options.source_file).read_text(encoding="utf-8")
        )
        raw.extend(sources_from_text(text))

    if not raw:
        print(
            "usage: python3 -m starisk.add <url|slug> [more...] "
            "[--from file|-] [--check] [--dry-run]"
        )
        return 1

    existing = json.loads(SOURCES_PATH.read_text(encoding="utf-8")) if SOURCES_PATH.exists() else []
    added, duplicates, invalid, merged = merge(raw, existing)

    missing = []
    if options.check:
        kept = []
        for key in added:
            if reachable(key):
                kept.append(key)
            else:
                missing.append(key)
            time.sleep(0.5)
        added = kept
        merged = [key for key in merged if key not in missing]

    for key in added:
        print(f"  add    {key}")
    for key in duplicates:
        print(f"  exists {key}")
    for key in missing:
        print(f"  gone   {key}  (Coursera did not serve it)")
    for value in invalid:
        print(f"  skip   {value!r}  (not a Coursera course URL)")

    if options.dry_run:
        print(f"\ndry run: {len(added)} would be added, {len(merged)} sources total.")
        return 0

    if added:
        write_atomic(SOURCES_PATH, merged)
        print(f"\nwrote {len(merged)} sources to {SOURCES_PATH} ({len(added)} new).")
        print("next: mise run pipeline:crawl")
    else:
        print("\nnothing to add.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
