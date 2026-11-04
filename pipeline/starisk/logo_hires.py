"""Fetch the partner's square mark at the two sizes the site actually draws.

`scores.json` points at the 160x60 lockup Coursera puts in a course's JSON-LD.
It is sharp in a table cell and soft the moment it is drawn big — and some
providers do not put a logo there at all, just a stock course photo. The course
page header, meanwhile, carries the partner's square brand mark, which is a
real logo and is available at 2-3x the resolution.

So we keep two sizes of that mark:

    web/public/logos/tile/<stem>.<ext>   dpr=1, ~180px  (tables)
    web/public/logos/full/<stem>.<ext>   dpr=2, 360-720px (course page)
    web/src/data/logo-sizes.json         {"<stem>": {"tile": …, "full": …}}

Keyed by provider stem rather than by image path: `logos.py --prune` repoints
`image` at the tile file, and a path key would stop matching the moment it did.

A table cell is ~36px, so the dpr=1 render is already 2x oversampled on a Retina
screen and a third of the weight of the dpr=2 one. The small original stays where
it is and remains the fallback when a provider has no header mark.

Only the cached page knows the header mark's URL, which is why this reads the
cache rather than `scores.json`. Fail-safe and idempotent: an existing file is
reused, and a failed download simply leaves that size out.

    cd pipeline
    python3 -m starisk.logo_hires
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

from .cache import CACHE_DIR, load_page
from .crawl import SCORES_PATH, write_atomic
from .fetch import fetch_bytes
from .logos import LOGO_DIR, sniff_extension
from .naming import IMAGE_PREFIX, stem

# name -> device pixel ratio. The directory is named after the size, not the dpr,
# so the web build can ask for a role ("tile", "full") rather than a number.
VARIANTS = (("tile", 1), ("full", 2))
MAP_PATH = Path(__file__).resolve().parents[2] / "web" / "src" / "data" / "logo-sizes.json"

_HEADER_LOGO = re.compile(r'<img src="(https://[^"]*coursera-university-assets[^"]*)"')


def header_logo_url(html: str) -> str | None:
    """The partner mark in a course page's header (not the JSON-LD thumbnail)."""
    match = _HEADER_LOGO.search(html)
    if match is None:
        return None
    return match.group(1).replace("&amp;", "&")


def hires_url(url: str, dpr: int = 2) -> str:
    """Ask the proxy for the same asset at `dpr` times its natural size."""
    base = url.partition("?")[0]
    return f"{base}?auto=format%2Ccompress&dpr={dpr}"


def _existing(directory: Path, stem: str) -> Path | None:
    for candidate in sorted(directory.glob(f"{stem}.*")):
        return candidate
    return None


def _write(path: Path, body: bytes) -> Path:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(body)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def _find_url(keys: list[str], cache_dir: Path) -> str | None:
    """Any one of a provider's cached pages will do; they share the same mark."""
    for key in keys:
        html = load_page(key, cache_dir)
        if html:
            url = header_logo_url(html)
            if url:
                return url
    return None


def localize_hires(
    scores: dict,
    cache_dir: Path = CACHE_DIR,
    out_dir: Path = LOGO_DIR,
    fetch=fetch_bytes,
    log=print,
) -> dict[str, dict[str, str]]:
    """Download each size of the square mark and map the small path to them."""
    keys_by_image: dict[str, list[str]] = {}
    for key, record in scores.items():
        image = record.get("image")
        if not isinstance(image, str) or not image.startswith(IMAGE_PREFIX):
            continue
        keys_by_image.setdefault(stem(record), []).append(key)

    mapping: dict[str, dict[str, str]] = {}
    for name, keys in keys_by_image.items():
        url: str | None = None
        sizes: dict[str, str] = {}

        for variant, dpr in VARIANTS:
            directory = out_dir / variant
            directory.mkdir(parents=True, exist_ok=True)

            found = _existing(directory, name)
            if found is None:
                if url is None:
                    url = _find_url(keys, cache_dir) or ""
                if not url:
                    log(f"  ! no header logo for {name} (page not cached)")
                    break

                try:
                    body = fetch(hires_url(url, dpr))
                except Exception as error:  # noqa: BLE001 - a logo must not stop the run
                    log(f"  ! {variant} failed ({name}): {error}")
                    continue

                extension = sniff_extension(body)
                if extension is None:
                    log(f"  ! {variant} skipped ({name}): unrecognised image format")
                    continue

                found = _write(directory / f"{name}{extension}", body)

            sizes[variant] = f"{IMAGE_PREFIX}{variant}/{found.name}"

        if sizes:
            mapping[name] = sizes

    return mapping


def main(argv: list[str]) -> int:
    if not SCORES_PATH.exists():
        print(f"no scores yet. run the crawl first: {SCORES_PATH}")
        return 1

    scores = json.loads(SCORES_PATH.read_text(encoding="utf-8"))
    mapping = localize_hires(scores)
    write_atomic(MAP_PATH, mapping)

    tiles = sum(1 for sizes in mapping.values() if "tile" in sizes)
    print(f"logo variants: {len(mapping)} providers ({tiles} tile, "
          f"{sum(1 for s in mapping.values() if 'full' in s)} full)")
    print(f"mapping: {MAP_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
