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
import unicodedata
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

# Some reviews pages ship the site's boilerplate as their title. Storing it would
# put "Coursera | Online Courses…" at the top of a course page, which is worse
# than having no title at all — the landing page usually knows the real name.
_GENERIC_TITLES = frozenset(
    {
        "coursera",
        "coursera plus",
        "coursera | online courses from top universities. join for free",
    }
)

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

# Each instructor is linked to their own profile, but only the first few of the
# teaching team get a link — the rest render as plain text. The page data blob
# holds the *whole* roster, with a stable numeric id, a vanity slug when Coursera
# assigned one, and the profile fields.
_INSTRUCTOR_LINK = re.compile(
    r'href="/instructor/([^"#?]+)"[^>]*>\s*<span[^>]*>([^<]+)</span>'
)
_INSTRUCTOR_RECORD = re.compile(r'"DescriptionPage_Instructor:(\d+)":\{')
_TITLE = re.compile(r"^(?:prof\.?|dr\.?|mr\.?|ms\.?|mrs\.?)\s+", re.IGNORECASE)
_CREDENTIAL = re.compile(r",?\s+(?:ph\.?\s?d\.?|m\.?\s?d\.?)$", re.IGNORECASE)

# Coursera duplicates most courses per language under the same slug
# (`ai-for-everyone-fr`). They are the same course, so one is enough.
LANGUAGE_SUFFIX = re.compile(
    r"-(ar|de|es|fr|id|it|ja|ko|nl|pl|pt|ru|th|tr|vi|zhcn|zhtw)$"
)

# Pages that list courses rather than teach one: a specialization lists its
# constituent courses, an instructor profile lists everything they teach. Both
# hooks are Coursera's own test hooks.
SPECIALIZATION_COURSE = 'data-e2e="sdp-course-list-link"'
INSTRUCTOR_COURSE = 'data-e2e="course-card"'

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


def identity_key(name: str) -> str:
    """A name reduced to its matching form: titles and credentials dropped.

    Names are not identities — people collide, and the same person is spelled
    "Prof. Peter J Stuckey" on one page and "Peter Stuckey" on another. This key
    matches the two so one person keeps one page; it also names the page of
    someone whose Coursera slug is only a numeric ref.
    """
    cleaned = _CREDENTIAL.sub("", name)
    cleaned = _TITLE.sub("", cleaned)
    ascii_name = (
        unicodedata.normalize("NFKD", cleaned).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def _page_slug(coursera_slug: str | None, name: str) -> str:
    """Our URL segment for an instructor.

    Coursera's slug is the identity, but several are anonymous numeric refs
    (`~219741545`), so those fall back to the person's name. A readable URL also
    survives Coursera assigning a vanity slug later.
    """
    if coursera_slug:
        bare = coursera_slug.rsplit("/", 1)[-1]
        if not bare.lstrip("~").isdigit():
            return bare
    return identity_key(name)


def _instructor(name: str, slug: str | None) -> dict:
    """A person we only know by name (no page data), in the same shape as a record."""
    display = " ".join(name.split())
    return {
        "name": display,
        "slug": slug,
        "url": f"https://www.coursera.org/instructor/{slug}" if slug else None,
        "page": _page_slug(slug, name),
        "id": None,
        "role": None,
        "department": None,
        "learners": None,
        "courses_taught": None,
        "photo": None,
    }


def _json_object_at(html: str, start: int) -> str | None:
    """The JSON object beginning at `start`, by counting braces outside strings."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(html)):
        char = html[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return html[start : index + 1]
    return None


def _instructor_from_record(ident: str, data: dict) -> dict | None:
    """One person from the page data blob.

    Every instructor has a profile page: the vanity slug when Coursera assigned
    one, the numeric ref otherwise (`/instructor/~219741545`). Both resolve; the
    numeric form is what the landing page links to for people without a vanity
    slug. Their own page gets a readable slug either way.
    """
    name = data.get("fullName") or data.get("name")
    if not name:
        return None

    short = str(data.get("shortName") or "").strip()
    slug = short or f"~{ident}"
    return {
        "name": " ".join(str(name).split()),
        "slug": slug,
        "url": f"https://www.coursera.org/instructor/{slug}",
        "page": short or identity_key(str(name)),
        "id": ident,
        "role": (data.get("title") or "").strip() or None,
        "department": (data.get("department") or "").strip() or None,
        "learners": _as_int(data.get("learnersReached")),
        "courses_taught": _as_int(data.get("coursesTaught")),
        "photo": data.get("photo") or None,
    }


def _instructors_from_blob(html: str) -> list[dict]:
    """The whole teaching team, in the page's own order."""
    found = {}
    for match in _INSTRUCTOR_RECORD.finditer(html):
        body = _json_object_at(html, match.end() - 1)
        if not body:
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            continue
        record = _instructor_from_record(match.group(1), data)
        if record:
            found[match.group(1)] = record

    if not found:
        return []

    refs = _INSTRUCTOR_REF.search(html)
    order = []
    if refs:
        order = list(
            dict.fromkeys(
                re.findall(r'"__ref":"DescriptionPage_Instructor:(\d+)"', refs.group(1))
            )
        )

    # The course's own `instructors` array is the roster; the blob holds those
    # records and nothing else (verified on every cached page). Trust it when it
    # is there, so a person bled in from a related-course block cannot join the
    # teaching team.
    if order:
        return [found[ident] for ident in order if ident in found]
    return list(found.values())


def _instructors_from_links(html: str) -> list[dict]:
    """Fallback when the page data is missing: the linked instructors, plus any
    co-instructor the page only names in its JSON-LD."""
    records = []
    seen = set()
    for slug, name in _INSTRUCTOR_LINK.findall(html):
        if slug in seen:
            continue
        seen.add(slug)
        records.append(_instructor(unescape(name), slug))

    if records:
        known = {record["name"].casefold() for record in records}
        records.extend(
            _instructor(name, None)
            for name in _names_from_jsonld(html)
            if " ".join(name.split()).casefold() not in known
        )
    return records


def _names_from_jsonld(html: str) -> list[str]:
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
            return list(dict.fromkeys(names))
        # Not every JSON-LD Course carries the instructor; keep looking (the
        # @graph block usually does).
    return []


def extract_landing(html: str) -> dict:
    """Instructors and subjects from a course landing page.

    The reviews page does not carry either; `/learn/<slug>` is server-rendered and
    does. The page data blob has the complete teaching team — including the
    instructors the hero does not link — so it wins; the rendered links and then
    the JSON-LD are the fallbacks. Subjects come from `domains`.
    """
    instructors = _instructors_from_blob(html) or _instructors_from_links(html)
    if not instructors:
        instructors = [_instructor(name, None) for name in _names_from_jsonld(html)]

    categories = []
    for domain, _subdomain in _DOMAINS.findall(html):
        name = unescape(domain).strip()
        if name and name not in categories:
            categories.append(name)

    return {"instructors": instructors, "categories": categories}


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


def _clean_title(value) -> str | None:
    """A usable page title, or None when it is Coursera's own boilerplate."""
    title = " ".join(unescape(str(value)).split())
    if not title or title.casefold() in _GENERIC_TITLES:
        return None
    return title


def extract_title(html: str) -> str | None:
    """The course's display name: JSON-LD first, then og:title, then <title>."""
    for block in _LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        product = _find_type(data, ("Product", "Course"))
        if product and product.get("name"):
            title = _clean_title(product["name"])
            if title:
                return title

    for pattern in _OG_TITLE:
        match = pattern.search(html)
        if match and match.group(1).strip():
            title = _clean_title(match.group(1))
            if title:
                return title

    match = _TITLE_TAG.search(html)
    return _clean_title(match.group(1)) if match else None


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
            details["title"] = _clean_title(product["name"])
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


def _course_slugs(html: str, marker: str) -> list[str]:
    """Course slugs from the links around `marker`.

    The marker sits on the anchor itself on a specialization page, and on a
    descendant `<div>` on an instructor page, so walk back to the enclosing `<a>`
    and read the href it carries.
    """
    slugs = []
    for match in re.finditer(re.escape(marker), html):
        start = html.rfind("<a ", 0, match.start())
        if start < 0:
            continue
        href = re.search(r'href="([^"]+)"', html[start : match.start()])
        if not href:
            continue
        target = unescape(href.group(1))
        course = re.match(r"/learn/([^/?#]+)", target)
        if not course or LANGUAGE_SUFFIX.search(course.group(1)):
            continue
        if course.group(1) not in slugs:
            slugs.append(course.group(1))
    return slugs


def extract_specialization_courses(html: str) -> list[str]:
    """The constituent courses of a specialization page."""
    return _course_slugs(html, SPECIALIZATION_COURSE)


def extract_instructor_courses(html: str) -> list[str]:
    """Every course an instructor profile links to, language variants dropped."""
    return _course_slugs(html, INSTRUCTOR_COURSE)
