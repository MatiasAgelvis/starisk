"""Crawl Coursera courses and write `data/scores.json`.

    cd pipeline
    python3 -m starisk.crawl                     # uses data/sources.json
    python3 -m starisk.crawl --force             # ignore freshness, refetch all
    python3 -m starisk.crawl --max-age 7         # refetch anything older than 7 days
    python3 -m starisk.crawl --limit 10          # budget: at most 10 fetches
    python3 -m starisk.crawl --offline           # re-score from cached pages, no requests
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
- Every fetched page is cached (gzipped), so an adapter fix can be re-scored with
  `--offline` instead of re-fetching the list.
- Atomic write: the file is replaced only once fully written.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .adapter import (
    REVIEW_CARD,
    extract_aggregate,
    extract_details,
    extract_landing,
    extract_reviews,
    identity_key,
)
from .cache import CACHE_DIR, load_page, store_page
from .engine import CALIBRATED, course_score, peer_spread, review_spread
from .fetch import RateLimited, fetch_page

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SOURCES_PATH = DATA_DIR / "sources.json"
SCORES_PATH = DATA_DIR / "scores.json"

DEFAULT_DELAY = 1.5

# Reviews move slowly; a month-old score is still honest. `--force` ignores this.
DEFAULT_MAX_AGE_DAYS = 30

# Below this, a score is a coin flip dressed as a number. The site says so.
LOW_SAMPLE = 15

# Long enough to hold most reviews whole; still an excerpt, not a repost.
TOP_REVIEW_LIMIT = 1200

_SOURCE_PATTERN = re.compile(r"coursera\.org/([^/?#]+)/([^/?#]+)")


def normalize_source(source: str) -> str:
    """Accept a bare slug, a path, or a full Coursera URL.

    "learn/x", "/learn/x/", "https://www.coursera.org/learn/x" and
    ".../learn/x/reviews" all become "learn/x". A bare "x" is assumed to be a
    course (v1 is courses-only, D17), so it cannot silently produce a URL with
    no type segment.
    """
    match = _SOURCE_PATTERN.search(source)
    if match:
        return f"{match.group(1)}/{match.group(2)}"

    key = source.strip().strip("/")
    if key and "/" not in key:
        return f"learn/{key}"
    return key


def reviews_url(source: str) -> str:
    return f"https://www.coursera.org/{normalize_source(source)}/reviews"


def details_url(source: str) -> str:
    return f"https://www.coursera.org/{normalize_source(source)}"


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


def excerpt(text: str, limit: int = TOP_REVIEW_LIMIT) -> str:
    """Trim to `limit` characters without ending mid-word or mid-sentence.

    The dissent is the centrepiece of a course page; a review that stops at
    "…fee was pa" reads as broken. Prefer a sentence end in the second half of
    the window, else the last whole word, and mark the cut.
    """
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= limit:
        return cleaned

    window = cleaned[:limit]
    sentence = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if sentence >= limit * 0.5:
        return window[: sentence + 1].rstrip() + " …"

    space = window.rfind(" ")
    return (window[:space] if space > 0 else window).rstrip(" ,;:-—") + "…"


def _top_review(reviews: list[dict]) -> dict | None:
    """The most-upvoted critical review with a body, else the most-upvoted one.

    `kind` matters: when every critical review on the page is rating-only, the
    fallback is *praise*, and presenting that as the dissent is a lie. Five of
    the first 34 courses hit this.
    """
    if not reviews:
        return None

    with_text = [review for review in reviews if (review.get("text") or "").strip()]
    critical = [review for review in with_text if review["stars"] <= 3]

    if critical:
        top, kind = max(critical, key=lambda review: review["likes"]), "dissent"
    elif with_text:
        top, kind = max(with_text, key=lambda review: review["likes"]), "consensus"
    else:
        return None

    return {
        "kind": kind,
        "text": excerpt(top["text"]) or None,
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
            course_score({"reviews": reviews, "coursera": coursera}, CALIBRATED), 1
        ),
        "spread": round(review_spread(reviews), 2),
        "spread_weighted": round(peer_spread(reviews, CALIBRATED), 2),
        "reviews": len(reviews),
        # The sample's own rating distribution, so a page can say "3 of 20 rated
        # it 3★ or lower, but none of them wrote a comment" instead of guessing.
        "review_counts": {
            str(star): count for star, count in sorted(Counter(r["stars"] for r in reviews).items())
        },
        "top_review": _top_review(reviews),
        "model": "sqrt-likes",
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


def landing_html(key: str, fetch, cache_dir: Path) -> str | None:
    """Instructors and subjects are nice to have; never fatal.

    Waits for the caller to throttle: the crawl sleeps before calling this.
    """
    try:
        landing = fetch(details_url(key))
    except RateLimited:
        raise
    except Exception:  # noqa: BLE001 - a missing landing page must not fail the course
        return None
    store_page(f"{key}.landing", landing, cache_dir)
    return landing


def crawl(
    sources: list[str],
    fetch=fetch_page,
    existing: dict | None = None,
    delay: float = 0.0,
    now: datetime | None = None,
    sleep=time.sleep,
    max_age_days: float | None = None,
    limit: int | None = None,
    offline: bool = False,
    cache_dir: Path = CACHE_DIR,
    progress=None,
) -> dict:
    """Fetch, score and merge. Returns the updated scores dict.

    `progress(done, total, key)` is called before each course, so a caller can
    draw a counter or a bar. The library prints nothing on its own.
    """
    scores = dict(existing or {})
    moment = now or datetime.now(timezone.utc)
    stamp = moment.isoformat()

    work = order_by_staleness(unique_sources(sources), scores)
    # Drop fresh records before taking the budget, so `total` is the work actually
    # about to happen rather than "the list". Staleness ordering already puts them
    # last, so this does not change which courses a `--limit` run picks.
    if max_age_days is not None:
        work = [key for key in work if not is_fresh(scores.get(key), moment, max_age_days)]
    if limit is not None:
        work = work[:limit]

    total = len(work)
    for index, key in enumerate(work, start=1):
        if progress:
            progress(index, total, key)

        url = reviews_url(key)

        if offline:
            html = load_page(key, cache_dir)
            landing = load_page(f"{key}.landing", cache_dir)
            if html is None:
                # Offline is a re-parse mode, not a crawl. A page we never fetched
                # says nothing about the course, so leave the record alone instead
                # of writing an error stub for every queued source.
                continue
        else:
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
            store_page(key, html, cache_dir)
            if delay:
                sleep(delay)  # breathe between the reviews page and the landing page
            try:
                landing = landing_html(key, fetch, cache_dir)
            except RateLimited as error:
                record = scores.get(key) or {}
                record["error"] = f"rate limited: {error}"
                scores[key] = record
                break

        result = score_page(html)
        if result is None:
            # Never overwrite a good record with a failed parse.
            record = scores.get(key) or {}
            record["error"] = "no reviews parsed (markup changed?)"
            scores[key] = record
        else:
            if landing:
                result.update(extract_landing(landing))
                # The landing page is the description page: title, provider,
                # image and level live there. The reviews page sometimes carries
                # the site's boilerplate instead (seen on every specialization),
                # so the landing wins whenever it has something to say.
                details = extract_details(landing)
                for field in ("title", "provider", "image", "description", "level", "enrollment"):
                    if details.get(field):
                        result[field] = details[field]
            # Re-parsing a cached page is not a fresh scrape: keep the old stamp.
            previous = scores.get(key) or {}
            stamped = previous.get("scrapedAt", stamp) if offline else stamp
            scores[key] = {**result, "slug": key, "scrapedAt": stamped}

        if delay:
            sleep(delay)

    return resolve_instructors(scores)


def resolve_instructors(scores: dict) -> dict:
    """Give a name-only instructor the identity of the same person elsewhere.

    Coursera links only some of a course's instructors, so the same teacher can
    arrive once with a profile and once without. Taking the known identity keeps
    one person on one page instead of splitting them in two.
    """
    known = {}
    for record in scores.values():
        for instructor in record.get("instructors") or []:
            if instructor.get("slug"):
                known.setdefault(identity_key(instructor["name"]), instructor)

    for record in scores.values():
        for instructor in record.get("instructors") or []:
            if instructor.get("slug"):
                continue
            match = known.get(identity_key(instructor["name"]))
            if match:
                instructor["slug"] = match["slug"]
                instructor["url"] = match["url"]
                instructor["page"] = match["page"]
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
        "offline": False,
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
        elif arg == "--offline":
            options["offline"] = True
            index += 1
        else:
            options["sources"] = options["sources"] or []
            options["sources"].append(arg)
            index += 1
    return options


def progress_line(done: int, total: int, key: str, elapsed: float, width: int = 22) -> str:
    """One line of crawl progress: bar, position, ETA and the course in flight.

    Fixed-width on purpose: it is redrawn with `\r`, so every line must paint over
    the previous one without leaving debris.
    """
    filled = round(width * done / total) if total else width
    bar = "#" * filled + "-" * (width - filled)
    remaining = (elapsed / done) * (total - done) if done else 0.0
    return f"[{bar}] {done:>3}/{total}  {remaining:>5.0f}s left  {key[:44]:<44}"


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
    # Offline means "re-parse what we already have": freshness is irrelevant.
    max_age = 0.0 if options["offline"] else options["max_age"]
    skipped = (
        sum(1 for key in sources if is_fresh(existing.get(key), moment, max_age))
        if max_age
        else 0
    )
    planned = len(sources) - skipped
    if options["limit"] is not None:
        planned = min(planned, options["limit"])

    state = {"drawn": False}
    started = time.monotonic()
    interactive = sys.stdout.isatty()

    def report(done, total, key):
        state["drawn"] = True
        line = progress_line(done, total, key, time.monotonic() - started)
        if interactive:
            sys.stdout.write("\r" + line)
            sys.stdout.flush()
        else:
            # Redirected to a file or a CI log: one line per course, no carriage returns.
            print(line)

    scores = crawl(
        sources,
        existing=existing,
        delay=options["delay"],
        now=moment,
        max_age_days=max_age,
        limit=options["limit"],
        offline=options["offline"],
        progress=report,
    )
    if state["drawn"] and interactive:
        sys.stdout.write("\n")
    write_atomic(SCORES_PATH, scores)

    scored = sum(1 for record in scores.values() if "starisk" in record)
    verb = "reparsed" if options["offline"] else "fetched"
    print(
        f"listed {len(sources)} | skipped fresh {skipped} | {verb} {planned} "
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
