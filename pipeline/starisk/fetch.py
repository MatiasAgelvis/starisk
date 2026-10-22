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
# Codes where the host is telling us to slow down.
RATE_LIMIT_CODES = frozenset({403, 429})


class RateLimited(RuntimeError):
    """The host asked us to slow down. The crawl should stop, not retry harder."""


def _wait_seconds(error: urllib.error.HTTPError, attempt: int, backoff: float) -> float:
    """Respect Retry-After, else back off with jitter."""
    header = error.headers.get("Retry-After") if getattr(error, "headers", None) else None
    if header:
        try:
            return max(float(header), 1.0)
        except ValueError:
            pass
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
            if error.code in FATAL_CODES:
                raise RuntimeError(f"HTTP {error.code} for {url}") from error
            if attempt == retries:
                if error.code in RATE_LIMIT_CODES:
                    raise RateLimited(f"HTTP {error.code} for {url}") from error
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
