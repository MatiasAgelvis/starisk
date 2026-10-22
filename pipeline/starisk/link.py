"""Resolve my certificates to crawlable course slugs.

Credential pages are client-rendered: anonymous HTML is a `Loading...` shell, so
the certificate URL itself gives up nothing. Coursera's sitemap does — ~23k
`/learn/` slugs, downloaded once. So: match titles to slugs offline, then confirm
each candidate against the live reviews page, which *is* server-rendered. A wrong
slug 404s; a wrong course has the wrong title.

    cd pipeline
    python3 -m starisk.link              # report only, writes nothing
    python3 -m starisk.link --write      # fill `slug`, extend data/sources.json
    python3 -m starisk.link --refresh    # re-download the sitemap

Why this matters: `calibration/courses.json` holds credentials, not course URLs,
so the crawl list and the calibration labels need the same mapping.
"""

from __future__ import annotations

import html as html_module
import json
import re
import sys
import time
from pathlib import Path

from .crawl import SCORES_PATH, SOURCES_PATH, normalize_source, write_atomic
from .fetch import fetch_page

REPO_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = REPO_ROOT / "calibration" / "courses.json"
CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / ".cache" / "coursera-slugs.txt"

SITEMAP_URL = "https://www.coursera.org/sitemap~www~courses.xml"
REVIEWS_URL = "https://www.coursera.org/{key}/reviews"

# Words that carry no signal when matching a title to a slug.
STOPWORDS = frozenset(
    {
        "a", "an", "and", "at", "by", "for", "from", "how", "in", "of", "on",
        "the", "to", "using", "with", "your", "you",
    }
)

# Coursera duplicates most courses per language under the same slug.
_LANGUAGE_SUFFIX = re.compile(r"-(ar|de|es|fr|id|it|ja|ko|nl|pl|pt|ru|th|tr|vi|zhcn|zhtw)$")

# Decorations Coursera adds to a certificate but not to the course page.
_DECORATIONS = re.compile(
    r"\s*\(\s*(?:with\s+)?(?:honou?rs?|distinction)\s*\)|^\s*capstone\s*:\s*", re.IGNORECASE
)

_CONFIRM_THRESHOLD = 0.8
_CANDIDATE_THRESHOLD = 0.35


def tokens(text: str) -> set[str]:
    """Lowercase word set, punctuation and stopwords removed."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return {word for word in cleaned.split() if word and word not in STOPWORDS}


def slug_tokens(slug: str) -> set[str]:
    return tokens(slug.replace("-", " "))


def clean_title(title: str) -> str:
    """Drop the decorations a certificate carries but the course page does not."""
    return " ".join(_DECORATIONS.sub(" ", title).split())


def score(title: set[str], slug: set[str]) -> float:
    """Blend coverage (does the slug cover the title?) with Jaccard."""
    if not title or not slug:
        return 0.0
    overlap = len(title & slug)
    return 0.6 * (overlap / len(title)) + 0.4 * (overlap / len(title | slug))


def candidates(
    title: str,
    slugs: list[str],
    limit: int = 3,
    preferred: frozenset[str] = frozenset(),
) -> list[tuple[str, float]]:
    """Best slug guesses for a certificate title, strongest first."""
    wanted = tokens(clean_title(title))
    ranked = []
    for slug in slugs:
        value = score(wanted, slug_tokens(clean_title(slug.replace("-", " "))))
        if value >= _CANDIDATE_THRESHOLD:
            ranked.append((slug, value))
    # On ties, keep the slug we already have data for, then the shorter one.
    ranked.sort(key=lambda pair: (-pair[1], pair[0] not in preferred, len(pair[0]), pair[0]))
    return ranked[:limit]


def page_title(html: str) -> str:
    """The course title from a reviews page, without Coursera's wrapper text."""
    tag = re.search(r'<meta[^>]*property="og:title"[^>]*>', html)
    if not tag:
        return ""
    content = re.search(r'content="([^"]*)"', tag.group(0))
    if not content:
        return ""

    title = html_module.unescape(content.group(1))
    title = title.removesuffix(" | Coursera")
    title = re.sub(r"^Learner Reviews & Feedback for ", "", title)
    title = re.sub(r"\s+(Course|Specialization|Professional Certificate)$", "", title)
    return title.strip()


def confirm(slug: str, title: str, fetch=fetch_page) -> bool:
    """Is this slug actually the certificate's course? Fetches the reviews page.

    Deliberately strict: the token sets must be *equal* after decorations are
    stripped. A lenient subset check happily maps "Ordered Data Structures" and
    "Unordered Data Structures" both onto `data-structures`, and scoring the wrong
    course is worse than missing one.
    """
    key = normalize_source(slug)
    if "/" not in key:
        key = f"learn/{key}"
    try:
        page = fetch(REVIEWS_URL.format(key=key))
    except Exception:  # noqa: BLE001 - a 404 or a timeout means "not this one"
        return False

    found = tokens(clean_title(page_title(page)))
    wanted = tokens(clean_title(title))
    return bool(found) and found == wanted


def resolve(
    entries: list[dict],
    slugs: list[str],
    fetch=fetch_page,
    delay: float = 0.0,
    sleep=time.sleep,
    preferred: frozenset[str] = frozenset(),
) -> list[dict]:
    """Resolve every Coursera single-course credential to a confirmed slug."""
    results = []
    for entry in entries:
        if entry.get("issuer") != "Coursera" or entry.get("type") != "course":
            continue

        ranked = candidates(entry["title"], slugs, preferred=preferred)
        # Prefer a slug we already have data for, even if a shorter one scores
        # marginally higher (`financial-markets-global` over `financial-markets-`).
        ranked.sort(key=lambda pair: pair[0] not in preferred)

        chosen = None
        for slug, value in ranked:
            if confirm(slug, entry["title"], fetch):
                chosen = (slug, value)
                break
            if delay:
                sleep(delay)

        # Flag only when the slug carries a word the title does not — that is the
        # signature of a different course with the same name ("Sequence Models"
        # -> nlp-sequence-models). A slug that merely abbreviates the title
        # (algorithms-divide-conquer) is normal and fine.
        review = False
        if chosen:
            extra = slug_tokens(chosen[0]) - tokens(clean_title(entry["title"]))
            review = bool(extra)

        results.append(
            {
                "title": entry["title"],
                "slug": chosen[0] if chosen else None,
                "score": round(chosen[1], 2) if chosen else None,
                "review": review,
                "rejected": [slug for slug, _ in ranked if not chosen or slug != chosen[0]],
                "tried": len(ranked),
                "ambiguous_with": [],
            }
        )
        if delay:
            sleep(delay)

    # Two certificates resolving to one slug means at least one is wrong.
    claims: dict[str, list[dict]] = {}
    for result in results:
        if result["slug"]:
            claims.setdefault(result["slug"], []).append(result)
    for slug, group in claims.items():
        if len(group) > 1:
            for result in group:
                result["slug"] = None
                result["ambiguous_with"] = [other["title"] for other in group if other is not result]

    return results


def load_slugs(refresh: bool = False, fetch=fetch_page) -> list[str]:
    """Read the cached sitemap, downloading it when missing or `refresh`."""
    if not CACHE_PATH.exists() or refresh:
        print(f"downloading {SITEMAP_URL} ...")
        xml = fetch(SITEMAP_URL)
        found = []
        for loc in re.findall(r"<loc>([^<]+)</loc>", xml):
            if "/learn/" in loc:
                slug = loc.rsplit("/learn/", 1)[1].strip("/")
                if slug and not _LANGUAGE_SUFFIX.search(slug):
                    found.append(slug)
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text("\n".join(sorted(set(found))) + "\n", encoding="utf-8")

    return [line.strip() for line in CACHE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_back(entries: list[dict], results: list[dict], include_review: bool = False) -> int:
    """Store each confirmed slug on its credential, and grow the crawl list.

    Only exact matches are written by default; `--all` includes the flagged ones.
    """
    confirmed = {
        result["title"]: result["slug"]
        for result in results
        if result["slug"] and (include_review or not result["review"])
    }
    for entry in entries:
        slug = confirmed.get(entry["title"])
        if slug:
            entry["slug"] = slug
    write_atomic(CALIBRATION_PATH, entries)

    existing = json.loads(SOURCES_PATH.read_text(encoding="utf-8")) if SOURCES_PATH.exists() else []
    merged = list(dict.fromkeys([*existing, *(f"learn/{slug}" for slug in confirmed.values())]))
    write_atomic(SOURCES_PATH, merged)
    return len(confirmed)


def main(argv: list[str]) -> int:
    write = "--write" in argv
    refresh = "--refresh" in argv

    entries = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    slugs = load_slugs(refresh=refresh)
    print(f"slugs: {len(slugs)}")

    # Prefer slugs we already have scores for when candidates tie.
    preferred = frozenset()
    if SCORES_PATH.exists():
        scored = json.loads(SCORES_PATH.read_text(encoding="utf-8"))
        preferred = frozenset(key.rsplit("/", 1)[-1] for key in scored)

    results = resolve(entries, slugs, delay=0.5, preferred=preferred)
    found = [r for r in results if r["slug"]]
    exact = [r for r in found if not r["review"]]

    for result in results:
        if result["slug"] and result["review"]:
            print(f"  review      {result['title'][:50]:52} -> {result['slug']}")
        elif result["slug"]:
            print(f"  ok    {result['score']:.2f}  {result['title'][:50]:52} -> {result['slug']}")
        elif result["ambiguous_with"]:
            others = "; ".join(t[:30] for t in result["ambiguous_with"])
            print(f"  ambig       {result['title'][:50]:52} (also claimed by: {others})")
        elif result["tried"]:
            tried = ", ".join(result["rejected"]) or "—"
            print(f"  miss        {result['title'][:50]:52} (tried: {tried})")
        else:
            print(f"  miss        {result['title'][:50]:52} (no candidate)")

    print(f"\nconfirmed {len(found)}/{len(results)} ({len(exact)} exact, {len(found) - len(exact)} need review)")
    if write:
        written = write_back(entries, results, include_review="--all" in argv)
        print(f"wrote {written} slugs to {CALIBRATION_PATH} and {SOURCES_PATH}")
    else:
        print("report only. re-run with --write to store the mapping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
