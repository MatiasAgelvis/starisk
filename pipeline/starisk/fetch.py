"""Minimal HTTP fetch using only the standard library.

Sends a browser-like User-Agent (Coursera serves the reviews to normal browser
requests) and retries a couple of times. No third-party dependencies.

Politeness matters here: a growing crawl list means more requests from one
residential IP, and that IP is the asset the whole project depends on. So:
- honour `Retry-After` when the server sends it,
- back off with jitter,
- never retry a 404 (a retired course will still be retired),
- raise `RateLimited` so the crawl can stop instead of digging a hole.
"""

from __future__ import annotations

import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Codes where waiting is useless: the page is gone or forbidden for good.
FATAL_CODES = frozenset({400, 401, 404, 410})
# A subset of those where the *course* is gone, not the request. Coursera retires
# courses; a retired slug answers 404 forever, so it is a fact about the corpus,
# not a failure of this run.
RETIRED_CODES = frozenset({404, 410})
# Codes where the host is telling us to slow down.
RATE_LIMIT_CODES = frozenset({403, 429})


class RateLimited(RuntimeError):
    """The host asked us to slow down. The crawl should stop, not retry harder."""


class Retired(RuntimeError):
    """The course no longer exists. Never retried, and never treated as a broken run."""


def _wait_seconds(error: urllib.error.HTTPError, attempt: int, backoff: float) -> float:
    """Respect Retry-After (seconds or HTTP-date), else back off with jitter."""
    header = error.headers.get("Retry-After") if getattr(error, "headers", None) else None
    if header:
        try:
            return max(float(header), 1.0)
        except ValueError:
            pass
        try:
            when = parsedate_to_datetime(header)
        except (TypeError, ValueError):
            when = None
        if when is not None:
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            return max((when - datetime.now(timezone.utc)).total_seconds(), 1.0)
    return backoff * (attempt + 1) * (1 + random.random() * 0.3)


def _request(
    url: str,
    headers: dict,
    timeout: float,
    retries: int,
    backoff: float,
) -> bytes:
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code in RETIRED_CODES:
                raise Retired(f"HTTP {error.code} for {url}") from error
            if error.code in FATAL_CODES:
                raise RuntimeError(f"HTTP {error.code} for {url}") from error
            if error.code in RATE_LIMIT_CODES:
                # 403/429 is the host telling us to stop. Retrying it is what
                # turns a warning into a block, so fail immediately (SPEC D21).
                raise RateLimited(f"HTTP {error.code} for {url}") from error
            if attempt == retries:
                break
            time.sleep(_wait_seconds(error, attempt, backoff))
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))

    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def fetch_page(url: str, timeout: float = 25, retries: int = 2, backoff: float = 2.0) -> str:
    """Fetch a URL and return its HTML as text."""
    return _request(url, HEADERS, timeout, retries, backoff).decode("utf-8", "replace")


def fetch_bytes(url: str, timeout: float = 25, retries: int = 2, backoff: float = 2.0) -> bytes:
    """Fetch a URL and return the raw body (images)."""
    return _request(
        url, {**HEADERS, "Accept": "image/*,*/*;q=0.8"}, timeout, retries, backoff
    )


def jitter(delay: float, spread: float = 0.5) -> float:
    """Seconds to wait before the next request: the delay, plus up to `spread`.

    A fixed interval is the one pattern a rate limiter can fingerprint for free,
    so the configured delay is a floor, not a schedule — no request ever arrives
    sooner than the caller asked for, and the mean goes up by half the spread.
    `--delay 0` stays 0: tests and offline runs should not sleep at all.
    """
    if delay <= 0:
        return 0.0
    return delay * (1 + random.uniform(0, spread))
