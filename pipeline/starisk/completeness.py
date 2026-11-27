"""How much of each Coursera product family the corpus covers.

Internal, not a product page. Two sources of truth:

  - the sitemaps give each family's total (cached on disk)
  - `scores.json` and `groupings.json` give what we have read or published

Writes `data/completeness.json`, which the site renders at `/coverage`.

    cd pipeline
    python3 -m starisk.completeness            # report only; no network if cached
    python3 -m starisk.completeness --write    # write data/completeness.json
    python3 -m starisk.completeness --refresh  # re-download every sitemap first
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .crawl import DATA_DIR, SCORES_PATH
from .groupings import GROUPINGS_PATH
from .link import load_slugs as course_slugs
from .paths import CACHE_DIR
from .sitemap import load_slugs, procert_slugs, program_slugs

COMPLETENESS_PATH = DATA_DIR / "completeness.json"

# Families whose pages we can count from a sitemap we do not otherwise read.
EXTRA_SITEMAPS = {
    "projects": (
        "https://www.coursera.org/sitemap~www~guided-projects.xml",
        "/projects/",
        CACHE_DIR / "coursera-projects.txt",
    ),
    "mastertrack": (
        "https://www.coursera.org/sitemap~www~mastertrack.xml",
        "/mastertrack/",
        CACHE_DIR / "coursera-mastertrack.txt",
    ),
    "degrees": (
        "https://www.coursera.org/sitemap~www~degrees.xml",
        "/degrees/",
        CACHE_DIR / "coursera-degrees.txt",
    ),
}

FAMILIES = [
    ("courses", "Courses", "learn"),
    ("specializations", "Specializations", "specializations"),
    ("professional-certificates", "Professional Certificates", "professional-certificates"),
    ("projects", "Guided Projects", "projects"),
    ("mastertrack", "MasterTrack", "mastertrack"),
    ("degrees", "Degrees", "degrees"),
]


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _extra_slugs(kind: str, refresh: bool) -> list[str]:
    url, marker, cache = EXTRA_SITEMAPS[kind]
    return load_slugs(url, marker, cache, refresh=refresh)


def _count(keys, path: str) -> tuple[int, int]:
    """(have, scored) for keys under `path`."""
    have = 0
    scored = 0
    for key, record in keys.items():
        if not key.startswith(path + "/"):
            continue
        have += 1
        if isinstance(record.get("starisk"), (int, float)):
            scored += 1
    return have, scored


def build(refresh: bool = False) -> dict:
    scores = _read(SCORES_PATH)
    groupings = _read(GROUPINGS_PATH)

    totals = {
        "courses": len(course_slugs(refresh=refresh)),
        "specializations": len(program_slugs(refresh=refresh)),
        "professional-certificates": len(procert_slugs(refresh=refresh)),
        "projects": len(_extra_slugs("projects", refresh)),
        "mastertrack": len(_extra_slugs("mastertrack", refresh)),
        "degrees": len(_extra_slugs("degrees", refresh)),
    }

    rows = []
    for kind, label, path in FAMILIES:
        source = scores if kind == "courses" else groupings
        have, scored = _count(source, path)
        row = {
            "kind": kind,
            "label": label,
            "path": path,
            "total": totals[kind],
            "have": have,
        }
        if scored:
            row["scored"] = scored
        rows.append(row)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "families": rows,
    }


def report(data: dict) -> None:
    for row in data["families"]:
        share = row["have"] / row["total"] * 100 if row["total"] else 0.0
        extra = f" ({row['scored']} scored)" if row.get("scored") is not None else ""
        print(
            f"{row['label']:<24} {row['have']:>7,} / {row['total']:>7,} "
            f"{share:5.1f}%{extra}"
        )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m starisk.completeness",
        description="Report how much of each Coursera product family the corpus covers.",
    )
    parser.add_argument("--write", action="store_true", help="write data/completeness.json")
    parser.add_argument(
        "--refresh", action="store_true", help="re-download every sitemap first"
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    options = parse_args(argv)
    data = build(refresh=options.refresh)
    report(data)

    if options.write:
        COMPLETENESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        COMPLETENESS_PATH.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {COMPLETENESS_PATH}")
    else:
        print("\nreport only. re-run with --write to store it for the site.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
