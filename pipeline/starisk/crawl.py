"""Crawl Coursera courses and write `data/scores.json`.

    cd pipeline
    python3 -m starisk.crawl                     # uses data/sources.json
    python3 -m starisk.crawl --force             # ignore freshness, refetch all
    python3 -m starisk.crawl --max-age 7         # refetch anything older than 7 days
    python3 -m starisk.crawl --limit 10          # budget: at most 10 fetches
    python3 -m starisk.crawl --delay 3           # politer
    python3 -m starisk.crawl learn/machine-learning   # one-off source

Design notes:
- One request per course (the first page is sorted "Most Helpful", which is the
  signal the model cares about).
- Fail-safe: a page that parses to zero reviews never overwrites a good record.
- Idempotent: sources are normalised and deduped, and records younger than
  `--max-age` are skipped without a request. So re-running is cheap.
- Ordered by staleness (never-scraped first, then oldest), so `--limit` makes
  progress across runs instead of re-doing the top of the list.
- Atomic write: the file is replaced only once fully written.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .adapter import REVIEW_CARD, extract_aggregate, extract_details, extract_reviews
from .engine import SIMPLE, course_score, peer_spread, review_spread
from .fetch import RateLimited, fetch_page

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SOURCES_PATH = DATA_DIR / "sources.json"
SCORES_PATH = DATA_DIR / "scores.json"

DEFAULT_DELAY = 1.5

# Reviews move slowly; a month-old score is still honest. `--force` ignores this.
DEFAULT_MAX_AGE_DAYS = 30

# Below this, a score is a coin flip dressed as a number. The site says so.
LOW_SAMPLE = 8

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


def unique_sources(sources: list[str]) -> list[str]:
    """Normalise and dedupe: a full URL, a bare slug and `/learn/x` are one course."""
    return list(dict.fromkeys(normalize_source(source) for source in sources))


def is_fresh(record: dict | None, now: datetime, max_age_days: float) -> bool:
    """Was this record scraped recently enough to skip? Failed records never count."""
    if not record or "starisk" not in record:
        return False
    raw = record.get("scrapedAt")
    if not raw:
        return False
    try:
        when = datetime.fromisoformat(raw)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now - when) < timedelta(days=max_age_days)


def order_by_staleness(keys: list[str], scores: dict) -> list[str]:
    """Never-scraped first, then oldest first.

    Ordering matters once `--limit` is in play: a partial run should always make
    progress instead of re-fetching the head of the list every time.
    """

    def rank(key: str):
        raw = (scores.get(key) or {}).get("scrapedAt")
        return (0, "") if not raw else (1, raw)

    return sorted(keys, key=rank)


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
        "spread": round(review_spread(reviews), 2),
        "spread_weighted": round(peer_spread(reviews, SIMPLE), 2),
        "reviews": len(reviews),
        "top_review": _top_review(reviews),
        "model": "simple",
    }

    # Present on most course pages, missing on some. Omit rather than emit null.
    for field, value in (
        ("reviews_total", aggregate["reviews_total"]),
        ("ratings_total", aggregate["ratings_total"]),
        ("rating_counts", aggregate["counts"]),
        ("level", details["level"]),
        ("enrollment", details["enrollment"]),
    ):
        if value is not None:
            record[field] = value

    # JSON-LD reviews carry no like counts, so every weight collapses to 1.
    if REVIEW_CARD not in html:
        record["source"] = "jsonld"
    if len(reviews) < LOW_SAMPLE:
        record["low_sample"] = True

    return record


def crawl(
    sources: list[str],
    fetch=fetch_page,
    existing: dict | None = None,
    delay: float = 0.0,
    now: datetime | None = None,
    sleep=time.sleep,
    max_age_days: float | None = None,
    limit: int | None = None,
) -> dict:
    """Fetch, score and merge. Returns the updated scores dict."""
    scores = dict(existing or {})
    moment = now or datetime.now(timezone.utc)
    stamp = moment.isoformat()

    work = order_by_staleness(unique_sources(sources), scores)
    if limit is not None:
        work = work[:limit]

    for key in work:
        if max_age_days is not None and is_fresh(scores.get(key), moment, max_age_days):
            continue

        url = reviews_url(key)

        try:
            html = fetch(url)
        except RateLimited as error:
            # Stop the run. The next one starts with this course, because it is
            # the stalest one left.
            record = scores.get(key) or {}
            record["error"] = f"rate limited: {error}"
            scores[key] = record
            break
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


def parse_args(argv: list[str]) -> dict:
    options = {
        "delay": DEFAULT_DELAY,
        "max_age": float(DEFAULT_MAX_AGE_DAYS),
        "limit": None,
        "sources": None,
    }
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--delay":
            options["delay"] = float(argv[index + 1])
            index += 2
        elif arg == "--max-age":
            options["max_age"] = float(argv[index + 1])
            index += 2
        elif arg == "--limit":
            options["limit"] = int(argv[index + 1])
            index += 2
        elif arg == "--force":
            options["max_age"] = 0.0
            index += 1
        else:
            options["sources"] = options["sources"] or []
            options["sources"].append(arg)
            index += 1
    return options


def main(argv: list[str]) -> int:
    options = parse_args(argv)

    if options["sources"]:
        sources = options["sources"]
    elif SOURCES_PATH.exists():
        sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    else:
        sources = []

    sources = unique_sources(sources)
    if not sources:
        print(f"no sources. add course slugs to {SOURCES_PATH}")
        return 1

    existing = (
        json.loads(SCORES_PATH.read_text(encoding="utf-8"))
        if SCORES_PATH.exists()
        else {}
    )

    moment = datetime.now(timezone.utc)
    skipped = (
        sum(1 for key in sources if is_fresh(existing.get(key), moment, options["max_age"]))
        if options["max_age"]
        else 0
    )
    planned = len(sources) - skipped
    if options["limit"] is not None:
        planned = min(planned, options["limit"])

    scores = crawl(
        sources,
        existing=existing,
        delay=options["delay"],
        now=moment,
        max_age_days=options["max_age"],
        limit=options["limit"],
    )
    write_atomic(SCORES_PATH, scores)

    scored = sum(1 for record in scores.values() if "starisk" in record)
    print(
        f"listed {len(sources)} | skipped fresh {skipped} | fetched {planned} "
        f"| records {len(scores)} | scored {scored}"
    )
    if any(str(record.get("error", "")).startswith("rate limited") for record in scores.values()):
        print(
            "stopped early: the host rate-limited us. Re-run later — it resumes at the "
            "stalest course, so nothing is repeated."
        )
    print(f"wrote {SCORES_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
