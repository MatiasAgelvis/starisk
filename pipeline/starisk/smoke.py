"""Live checks: does Coursera still parse, and is the deployed data still served?

The unit suite runs on fixtures, and a fixture cannot tell you the one thing that
matters here: whether the page on the other side still looks like the fixture.
These checks make five requests, so they are opt-in (`STARISK_LIVE=1`) and they
run *before* the nightly crawl — when a selector changes, the run should stop
before it caches an hour of pages it cannot read.

Two kinds of problem, deliberately different:

- **adapter** (Coursera): gates the run. Nothing downstream is trustworthy.
- **site** (our own deployment): a warning. A stale or broken deploy says nothing
  about whether today's crawl is good.

Every check asserts what must hold, never an exact number: a rating stays in
0–5, a page yields reviews, a program lists courses.
"""

from __future__ import annotations

import os
import urllib.request
from dataclasses import dataclass, field

from .adapter import extract_details
from .crawl import reviews_url, score_page
from .fetch import fetch_page
from .groupings import extract_grouping

# One key per parsing path the crawl actually branches on.
COURSE_KEY = "learn/machine-learning"
LOW_SAMPLE_KEY = "learn/introduction-test-driven-development"
PROGRAM_KEY = "specializations/excel"

# The canonical deployment. Override for a preview or a local build.
SITE = os.environ.get("STARISK_SITE", "https://starisk.matiasagelvis.com")

# The published scores file is ~3 MB; anything near-empty means a broken build.
MIN_SCORES_BYTES = 1_000_000


@dataclass
class Problem:
    check: str
    detail: str

    def __str__(self) -> str:
        return f"{self.check}: {self.detail}"


@dataclass
class Report:
    adapter: list[Problem] = field(default_factory=list)
    site: list[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Only the adapter gates a run; see the module docstring."""
        return not self.adapter


def check_course(key: str = COURSE_KEY, fetch=fetch_page) -> list[Problem]:
    """A reviews page still yields a score in range, from a non-empty sample."""
    try:
        html = fetch(reviews_url(key))
    except Exception as error:  # noqa: BLE001 - a live check reports, it does not raise
        return [Problem(f"reviews {key}", f"fetch failed: {error}")]

    result = score_page(html)
    if result is None:
        return [Problem(f"reviews {key}", "no reviews parsed (markup changed?)")]

    problems = []
    coursera = result.get("coursera")
    if coursera is not None and not 0 <= coursera <= 5:
        problems.append(Problem(f"reviews {key}", f"rating out of range: {coursera}"))
    if not (result.get("reviews") or 0) > 0:
        problems.append(Problem(f"reviews {key}", "parsed zero reviews"))
    if "starisk" not in result:
        problems.append(Problem(f"reviews {key}", "no starisk score produced"))
    return problems


def check_landing(key: str = COURSE_KEY, fetch=fetch_page) -> list[Problem]:
    """The landing page still carries the title and provider the site shows."""
    try:
        html = fetch(f"https://www.coursera.org/{key}")
    except Exception as error:  # noqa: BLE001
        return [Problem(f"landing {key}", f"fetch failed: {error}")]

    details = extract_details(html)
    return [
        Problem(f"landing {key}", f"missing {field}")
        for field in ("title", "provider")
        if not details.get(field)
    ]


def check_program(key: str = PROGRAM_KEY, fetch=fetch_page) -> list[Problem]:
    """A program page still lists its courses and its title."""
    try:
        html = fetch(f"https://www.coursera.org/{key}")
    except Exception as error:  # noqa: BLE001
        return [Problem(f"program {key}", f"fetch failed: {error}")]

    grouping = extract_grouping(html, key)
    if grouping is None:
        return [Problem(f"program {key}", "no program parsed (markup changed?)")]
    if not grouping.get("courses"):
        return [Problem(f"program {key}", "program lists no courses")]
    return []


def check_site(site: str = SITE, opener=urllib.request.urlopen) -> list[Problem]:
    """The deployed data file: reachable, cross-origin, and not suspiciously small.

    HEAD, not GET: this runs every night and the file is 3 MB. The header is the
    part the bookmarklet depends on, and a bookmarklet that cannot read this file
    fails silently — which is exactly the failure a check should catch.
    """
    url = f"{site.rstrip('/')}/data/scores.json"
    request = urllib.request.Request(url, method="HEAD")
    try:
        with opener(request, timeout=25) as response:
            headers = response.headers
            status = response.status
    except Exception as error:  # noqa: BLE001
        return [Problem("site", f"{url}: {error}")]

    problems = []
    if status != 200:
        problems.append(Problem("site", f"{url}: HTTP {status}"))
    if headers.get("access-control-allow-origin") != "*":
        problems.append(Problem("site", f"{url}: no CORS header"))
    size = int(headers.get("content-length") or 0)
    if size < MIN_SCORES_BYTES:
        problems.append(Problem("site", f"{url}: {size} bytes (expected > {MIN_SCORES_BYTES})"))
    return problems


def run(fetch=fetch_page, site: str = SITE, opener=urllib.request.urlopen) -> Report:
    adapter = [
        *check_course(COURSE_KEY, fetch),
        *check_course(LOW_SAMPLE_KEY, fetch),
        *check_landing(COURSE_KEY, fetch),
        *check_program(PROGRAM_KEY, fetch),
    ]
    return Report(adapter=adapter, site=check_site(site, opener))
