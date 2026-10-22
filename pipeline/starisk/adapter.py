"""Turns a live Coursera reviews page into the review dicts the engine wants:
{"stars": float, "likes": int, "age_days": float}.

Coursera renders the reviews server-side using semantic hooks (`data-e2e`,
`data-testid`, `aria-label`), so we parse those — not the hashed CSS classes the
2022 extension relied on. Those hooks are Coursera's own test hooks and change
far less often; if this breaks, the fix is a selector, not a rewrite.

Data found on the page (verified against live snapshots):
  card    : data-e2e="review-table-card"
  stars   : aria-label="Rated 1.0 out of 5 stars"   (half stars included)
  likes   : aria-label="This was helpful (80)"
  date    : e.g. "Nov 14, 2022"
  overall : JSON-LD <script type="application/ld+json"> aggregateRating
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape

REVIEW_CARD = 'data-e2e="review-table-card"'
CML_VIEWER = 'data-testid="cml-viewer"'

# A card slice ends at the next card, so the *last* slice runs to the end of the
# document and swallows the footer. The review body starts at `cml-viewer`; the
# window below is far larger than any review and far smaller than the footer.
REVIEW_WINDOW = 12000

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_LD_JSON = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S
)
_STARS = re.compile(r"Rated ([\d.]+) out of 5 stars")
_LIKES = re.compile(r"This was helpful \((\d+)\)")
_DATE = re.compile(r"\b([A-Z][a-z]{2,8} \d{1,2}, \d{4})\b")
_TEXT_NODE = re.compile(r">([^<>]{40,})<")
_OLD_RATING = re.compile(r'data-test="number-star-rating">([\d.]+)')
_OG_TITLE = (
    re.compile(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"'),
    re.compile(r'<meta[^>]+content="([^"]*)"[^>]+property="og:title"'),
)
_TITLE_TAG = re.compile(r"<title[^>]*>([^<]+)</title>")

# Coursera embeds its own rating data in a serialised Apollo cache. Verified on
# all 8 live snapshots, including pages whose JSON-LD omits `ratingValue`:
#   "ratingCountsByStar":{"fiveStarRatingCount":255087,...,"oneStarRatingCount":1641}
#   "ratings":{"averageFiveStarRating":4.784...}
# This is the *population* — every rating Coursera ever received — not the ~20
# reviews we read.
_RATING_COUNTS = re.compile(r'"ratingCountsByStar":\{[^}]*\}')
_AVERAGE = re.compile(r'"averageFiveStarRating":([\d.]+)')
_STAR_KEYS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}

# Landing pages carry what the reviews page does not: who teaches the course and
# which subjects Coursera files it under. A course can sit in several domains.
_DOMAINS = re.compile(
    r'"domainName":"([^"]+)","subdomainId":"[^"]*","subdomainName":"([^"]*)"'
)
_INSTRUCTOR_REF = re.compile(r'"instructors":\[([^\]]*)\]')

_DATE_FORMATS = (
    "%b %d, %Y",
    "%B %d, %Y",
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%fZ",
)


def _find_type(node, types: tuple[str, ...]):
    if isinstance(node, dict):
        if node.get("@type") in types:
            return node
        for value in node.values():
            found = _find_type(value, types)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_type(value, types)
            if found:
                return found
    return None


def extract_landing(html: str) -> dict:
    """Instructors and subjects from a course landing page.

    The reviews page does not carry either; `/learn/<slug>` is server-rendered and
    does. Names come from the JSON-LD (which also has bios and photos for later),
    falling back to the page's own data blob; subjects come from `domains`.
    """
    result = {"instructors": [], "categories": []}

    for block in _LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        product = _find_type(data, ("Product", "Course"))
        if not product:
            continue

        raw = product.get("instructor") or product.get("author") or []
        if isinstance(raw, dict):
            raw = [raw]
        names = []
        for person in raw:
            name = person.get("name") if isinstance(person, dict) else person
            if name:
                names.append(unescape(str(name)).strip())
        if names:
            result["instructors"] = list(dict.fromkeys(names))
            break
        # Not every JSON-LD Course carries the instructor; keep looking (the
        # @graph block usually does).

    if not result["instructors"]:
        # Resolve the blob's __ref handles. The person records use `fullName`.
        for block in _INSTRUCTOR_REF.findall(html):
            for identifier in re.findall(r'"__ref":"DescriptionPage_Instructor:(\d+)"', block):
                anchor = re.search(
                    r'"DescriptionPage_Instructor:%s":' % identifier, html
                )
                if not anchor:
                    continue
                window = html[anchor.end() : anchor.end() + 800]
                match = re.search(r'"(?:fullName|name)":"([^"]+)"', window)
                if match:
                    result["instructors"].append(unescape(match.group(1)).strip())
            if result["instructors"]:
                break
        result["instructors"] = list(dict.fromkeys(result["instructors"]))

    categories = []
    for domain, _subdomain in _DOMAINS.findall(html):
        name = unescape(domain).strip()
        if name and name not in categories:
            categories.append(name)
    result["categories"] = categories

    return result


def extract_population(html: str) -> dict:
    """Coursera's full star distribution and true average, from the page data.

    Returns `counts` keyed by star value (1-5) and `total`. Empty when the page
    does not carry the blob (the reviews list still does on older markup).
    """
    result = {"average": None, "counts": None, "total": None}

    counts_match = _RATING_COUNTS.search(html)
    if counts_match:
        counts = {}
        for name, value in re.findall(
            r'"(one|two|three|four|five)StarRatingCount":(\d+)', counts_match.group(0)
        ):
            counts[_STAR_KEYS[name]] = int(value)
        if counts:
            result["counts"] = dict(sorted(counts.items()))
            result["total"] = sum(counts.values())

    average_match = _AVERAGE.search(html)
    if average_match:
        try:
            result["average"] = float(average_match.group(1))
        except ValueError:
            pass

    return result


def extract_aggregate(html: str) -> dict:
    """Coursera's headline rating and the population behind it.

    `ratings_total` counts star ratings, `reviews_total` counts *written* reviews.
    We only read the first page (~20), so keeping the denominator is what makes
    the sampling honest — and it is the input a shrinkage model needs.
    """
    result = {"rating": None, "ratings_total": None, "reviews_total": None}

    for block in _LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        product = _find_type(data, ("Product", "Course"))
        if not product:
            continue

        aggregate = product.get("aggregateRating") or {}
        result["ratings_total"] = _as_int(aggregate.get("ratingCount"))
        result["reviews_total"] = _as_int(aggregate.get("reviewCount"))
        value = aggregate.get("ratingValue")
        if value is not None:
            try:
                result["rating"] = float(value)
            except (TypeError, ValueError):
                pass
        break

    if result["rating"] is None:
        match = _OLD_RATING.search(html)
        if match:
            result["rating"] = float(match.group(1))

    # The embedded population is more complete than the JSON-LD aggregate.
    population = extract_population(html)
    if result["rating"] is None:
        result["rating"] = population["average"]
    # Prefer the population total: it is the sum of the counts we store, so the
    # sample statement and the distribution can never disagree.
    if population["total"] is not None:
        result["ratings_total"] = population["total"]
    result["counts"] = population["counts"]

    return result


def extract_coursera_score(html: str) -> float:
    """Coursera's overall rating, from the JSON-LD aggregate when present."""
    rating = extract_aggregate(html)["rating"]
    return rating if rating is not None else float("nan")


def _as_int(value) -> int | None:
    """'32,331' or 32331.0 -> 32331."""
    if value is None:
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def extract_title(html: str) -> str | None:
    """The course's display name: JSON-LD first, then og:title, then <title>."""
    for block in _LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        product = _find_type(data, ("Product", "Course"))
        if product and product.get("name"):
            return unescape(str(product["name"])).strip()

    for pattern in _OG_TITLE:
        match = pattern.search(html)
        if match and match.group(1).strip():
            return unescape(match.group(1)).strip()

    match = _TITLE_TAG.search(html)
    return unescape(match.group(1)).strip() if match else None


def extract_details(html: str) -> dict:
    """Course metadata from JSON-LD: title, description, provider, image URL.

    Partner naming is inconsistent: most pages use `brand`, some (IBM) use
    `provider`. Missing the fallback silently blanks the logo and the label.
    """
    details = {
        "title": None,
        "description": None,
        "provider": None,
        "image": None,
        "level": None,
        "enrollment": None,
    }

    for block in _LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        product = _find_type(data, ("Product", "Course"))
        if not product:
            continue

        if product.get("name"):
            details["title"] = unescape(str(product["name"])).strip()
        if product.get("description"):
            details["description"] = unescape(str(product["description"])).strip()

        brand = None
        for key in ("brand", "provider", "publisher"):
            candidate = product.get(key)
            if isinstance(candidate, dict):
                candidate = candidate.get("name")
            if candidate:
                brand = candidate
                break
        if brand:
            details["provider"] = unescape(str(brand)).strip()

        level = product.get("educationalLevel")
        if level:
            details["level"] = unescape(str(level)).strip()

        enrollment = product.get("totalHistoricalEnrollment")
        if enrollment is not None:
            details["enrollment"] = _as_int(enrollment)

        image = product.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        if image:
            details["image"] = str(image)

        if details["title"]:
            break

    if details["title"] is None:
        details["title"] = extract_title(html)

    return details


def _age_days(text: str) -> float:
    cleaned = text.strip()
    for date_format in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        return (parsed - _EPOCH).total_seconds() / 86_400
    return float("nan")


def _inner_html(html: str, marker: str, tag: str = "div") -> str | None:
    """Inner HTML of the element whose opening tag contains `marker`.

    Depth-balanced rather than windowed: the review body is a div with nested
    divs, and the last card's slice otherwise runs into the page footer.
    """
    start = html.find(marker)
    if start < 0:
        return None

    open_start = html.rfind("<", 0, start)
    open_end = html.find(">", start)
    if open_start < 0 or open_end < 0:
        return None

    pattern = re.compile(rf"<(/?){tag}\b", re.IGNORECASE)
    depth = 1
    position = open_end + 1
    while True:
        match = pattern.search(html, position)
        if not match:
            return html[open_end + 1 :]
        depth += -1 if match.group(1) else 1
        if depth == 0:
            return html[open_end + 1 : match.start()]
        position = match.end()


def _review_text(block: str) -> str | None:
    """The review body: the longest plain-text node inside the review element.

    Scripts and styles are stripped first: the page embeds serialised JSON whose
    strings look exactly like long text nodes, and one course's "review" came out
    as `"id":"ComponentLink~..."`.
    """
    cleaned = re.sub(r"<script.*?</script>|<style.*?</style>", " ", block, flags=re.S)

    region = _inner_html(cleaned, CML_VIEWER) or cleaned[:REVIEW_WINDOW]

    candidates = [
        unescape(text).strip()
        for text in _TEXT_NODE.findall(region)
        if not text.strip().startswith("This was helpful")
    ]
    return max(candidates, key=len) if candidates else None


def _reviews_from_cards(html: str) -> list[dict]:
    """Reviews rendered server-side as cards (these include like counts)."""
    blocks = html.split(REVIEW_CARD)[1:]

    reviews = []
    for block in blocks:
        stars_match = _STARS.search(block)
        if not stars_match:
            # Not a review card we understand (or markup changed): skip it
            # rather than fabricate a rating.
            continue

        likes_match = _LIKES.search(block)
        date_match = _DATE.search(block)

        reviews.append(
            {
                "stars": float(stars_match.group(1)),
                "likes": int(likes_match.group(1)) if likes_match else 0,
                "age_days": _age_days(date_match.group(1)) if date_match else float("nan"),
                "text": _review_text(block),
            }
        )

    return reviews


def _reviews_from_jsonld(html: str) -> list[dict]:
    """Reviews from the JSON-LD block. No like counts exist here."""
    for block in _LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue

        product = _find_type(data, ("Product", "Course"))
        if not product:
            continue

        raw = product.get("review") or []
        if isinstance(raw, dict):
            raw = [raw]

        reviews = []
        for review in raw:
            rating = (review.get("reviewRating") or {}).get("ratingValue")
            if rating is None:
                continue
            published = review.get("datePublished")
            reviews.append(
                {
                    "stars": float(rating),
                    "likes": 0,
                    "age_days": _age_days(str(published)) if published else float("nan"),
                    "text": unescape(str(review.get("reviewBody") or "")).strip() or None,
                }
            )

        if reviews:
            return reviews

    return []


def extract_reviews(html: str) -> list[dict]:
    """Prefer DOM cards (they carry likes); fall back to JSON-LD reviews."""
    return _reviews_from_cards(html) or _reviews_from_jsonld(html)
