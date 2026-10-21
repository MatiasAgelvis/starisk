"""Minimal HTTP fetch using only the standard library.

Sends a browser-like User-Agent (Coursera serves the reviews to normal browser
requests) and retries a couple of times. No third-party dependencies.
"""

from __future__ import annotations

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


def fetch_page(url: str, timeout: float = 25, retries: int = 2, backoff: float = 2.0) -> str:
    """Fetch a URL and return its HTML as text."""
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace")
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))

    raise RuntimeError(f"failed to fetch {url}: {last_error}")
