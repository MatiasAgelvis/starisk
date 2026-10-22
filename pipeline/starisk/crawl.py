"""Crawl Coursera courses and write `data/scores.json`.

    cd pipeline
    python3 -m starisk.crawl                  # uses data/sources.json
    python3 -m starisk.crawl --delay 2        # slower, politer
    python3 -m starisk.crawl learn/machine-learning   # one-off source

Design notes:
- One request per course (the first page is sorted "Most Helpful", which is the
  signal the model cares about).
- Fail-safe: a page that parses to zero reviews never overwrites a good record.
- Atomic write: the file is replaced only once fully written.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from .adapter import extract_aggregate, extract_details, extract_reviews
from .engine import SIMPLE, course_score, peer_spread
from .fetch import fetch_page

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SOURCES_PATH = DATA_DIR / "sources.json"
SCORES_PATH = DATA_DIR / "scores.json"

DEFAULT_DELAY = 1.5

_SOURCE_PATTERN = re.compile(r"coursera\.org/([^/?#]+)/([^/?#]+)")


def normalize_source(source: str) -> str:
    """Accept a bare slug, a path, or a full Coursera URL.

    "learn/x", "/learn/x/", "https://www.coursera.org/learn/x" and
    ".../learn/x/reviews" all become "learn/x".
    """
    match = _SOURCE_PATTERN.search(source)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return source.strip().strip("/")


def reviews_url(source: str) -> str:
    return f"https://www.coursera.org/{normalize_source(source)}/reviews"


def _top_review(reviews: list[dict]) -> dict | None:
    """The most-upvoted *critical* review (<=3 stars), else the most upvoted."""
    if not reviews:
        return None
    critical = [review for review in reviews if review["stars"] <= 3] or reviews
    top = max(critical, key=lambda review: review["likes"])
    return {
        "text": (top.get("text") or "").strip()[:600] or None,
        "stars": top["stars"],
        "likes": top["likes"],
    }


def score_page(html: str) -> dict | None:
    """Score one reviews page. Returns None when there is nothing to score."""
    reviews = extract_reviews(html)
    if not reviews:
        return None

    details = extract_details(html)
    aggregate = extract_aggregate(html)
    coursera = aggregate["rating"] if aggregate["rating"] is not None else float("nan")

    record = {
        "title": details["title"],
        "provider": details["provider"],
        "description": details["description"],
        "image": details["image"],
        "coursera": None if coursera != coursera else round(coursera, 1),  # NaN -> None
        "starisk": round(
            course_score({"reviews": reviews, "coursera": coursera}, SIMPLE), 1
        ),
        "spread": round(peer_spread(reviews, SIMPLE), 2),
        "reviews": len(reviews),
        "top_review": _top_review(reviews),
        "model": "simple",
    }

    # Present on most course pages, missing on some. Omit rather than emit null.
    for field, value in (
        ("reviews_total", aggregate["reviews_total"]),
        ("ratings_total", aggregate["ratings_total"]),
        ("level", details["level"]),
        ("enrollment", details["enrollment"]),
    ):
        if value is not None:
            record[field] = value

    return record


def crawl(
    sources: list[str],
    fetch=fetch_page,
    existing: dict | None = None,
    delay: float = 0.0,
    now: datetime | None = None,
    sleep=time.sleep,
) -> dict:
    """Fetch, score and merge. Returns the updated scores dict."""
    scores = dict(existing or {})
    stamp = (now or datetime.now(timezone.utc)).isoformat()

    for source in sources:
        key = normalize_source(source)
        url = reviews_url(key)

        try:
            html = fetch(url)
        except Exception as error:  # noqa: BLE001 - one bad course must not stop the crawl
            record = scores.get(key) or {}
            record["error"] = f"fetch: {error}"
            scores[key] = record
            continue

        result = score_page(html)
        if result is None:
            # Never overwrite a good record with a failed parse.
            record = scores.get(key) or {}
            record["error"] = "no reviews parsed (markup changed?)"
            scores[key] = record
        else:
            scores[key] = {**result, "slug": key, "scrapedAt": stamp}

        if delay:
            sleep(delay)

    return scores


def write_atomic(path: Path, data: dict) -> None:
    """Write JSON in one atomic replace, so a crash cannot truncate the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def parse_args(argv: list[str]) -> tuple[float, list[str] | None]:
    delay = DEFAULT_DELAY
    sources: list[str] | None = None
    index = 0
    while index < len(argv):
        if argv[index] == "--delay":
            delay = float(argv[index + 1])
            index += 2
        else:
            sources = sources or []
            sources.append(argv[index])
            index += 1
    return delay, sources


def main(argv: list[str]) -> int:
    delay, cli_sources = parse_args(argv)

    if cli_sources:
        sources = cli_sources
    elif SOURCES_PATH.exists():
        sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    else:
        sources = []

    if not sources:
        print(f"no sources. add course slugs to {SOURCES_PATH}")
        return 1

    existing = (
        json.loads(SCORES_PATH.read_text(encoding="utf-8"))
        if SCORES_PATH.exists()
        else {}
    )

    scores = crawl(sources, existing=existing, delay=delay)
    write_atomic(SCORES_PATH, scores)

    scored = sum(1 for record in scores.values() if "starisk" in record)
    print(f"crawled {len(sources)} | records: {len(scores)} | scored: {scored}")
    print(f"wrote {SCORES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
