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

REVIEW_CARD = 'data-e2e="review-table-card"'

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_LD_JSON = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S
)
_STARS = re.compile(r"Rated ([\d.]+) out of 5 stars")
_LIKES = re.compile(r"This was helpful \((\d+)\)")
_DATE = re.compile(r"\b([A-Z][a-z]{2,8} \d{1,2}, \d{4})\b")
_OLD_RATING = re.compile(r'data-test="number-star-rating">([\d.]+)')

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


def extract_coursera_score(html: str) -> float:
    """Coursera's overall rating, from the JSON-LD aggregate when present."""
    for block in _LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        product = _find_type(data, ("Product", "Course"))
        if product:
            aggregate = product.get("aggregateRating") or {}
            value = aggregate.get("ratingValue")
            if value is not None:
                return float(value)

    match = _OLD_RATING.search(html)
    return float(match.group(1)) if match else float("nan")


def _age_days(text: str) -> float:
    cleaned = text.strip()
    for date_format in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(cleaned, date_format).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        return (parsed - _EPOCH).total_seconds() / 86_400
    return float("nan")


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
                }
            )

        if reviews:
            return reviews

    return []


def extract_reviews(html: str) -> list[dict]:
    """Prefer DOM cards (they carry likes); fall back to JSON-LD reviews."""
    return _reviews_from_cards(html) or _reviews_from_jsonld(html)
