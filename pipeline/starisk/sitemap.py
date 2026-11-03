"""Read Coursera's sitemap XML into a cached list of slugs.

Both the course mapper (`link`) and the expansion pass (`expand`) need the same
thing: download a sitemap once, keep the slugs under a path segment, and re-read
the cache on later runs. The only differences are the URL, the segment and
whether language variants are dropped.
"""

from __future__ import annotations

import re
from pathlib import Path

from .fetch import fetch_page

_LOC = re.compile(r"<loc>([^<]+)</loc>")


def load_slugs(
    url: str,
    marker: str,
    cache_path: Path,
    fetch=fetch_page,
    refresh: bool = False,
    reject: re.Pattern[str] | None = None,
) -> list[str]:
    """Slugs under `marker`, cached to disk.

    `marker` includes its trailing slash (`/learn/`), so the slug is whatever
    follows it. `reject` drops variants that are not separate entries (language
    suffixes, in the course sitemap).
    """
    if not cache_path.exists() or refresh:
        xml = fetch(url)
        found = []
        for loc in _LOC.findall(xml):
            if marker not in loc:
                continue
            slug = loc.rsplit(marker, 1)[1].strip("/")
            if slug and (reject is None or not reject.search(slug)):
                found.append(slug)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text("\n".join(sorted(set(found))) + "\n", encoding="utf-8")

    return [
        line.strip()
        for line in cache_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
