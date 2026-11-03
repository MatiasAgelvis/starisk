"""A local cache of fetched pages, so re-parsing is free.

The adapter will break — that is a stated risk, not a possibility. Without a
cache, every selector fix means re-fetching the whole list from the one
residential IP the project depends on. With it, `--offline` re-scores from disk.

Stored as gzipped HTML: a reviews page is ~700 KB raw and ~70 KB gzipped, so a
few hundred courses cost tens of megabytes in a gitignored directory.
"""

from __future__ import annotations

import gzip
import os
import tempfile
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / ".cache" / "pages"


def path_for(key: str, directory: Path = CACHE_DIR) -> Path:
    """`learn/machine-learning` -> `learn__machine-learning.html.gz`."""
    return directory / f"{key.replace('/', '__')}.html.gz"


def store_page(key: str, html: str, directory: Path = CACHE_DIR) -> Path:
    """Write a page through a temporary file, then replace the old copy.

    A crash mid-write leaves the previous page intact instead of a truncated
    gzip stream that would abort the next offline reparse.
    """
    path = path_for(key, directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    os.close(descriptor)
    try:
        with gzip.open(temporary, "wt", encoding="utf-8") as handle:
            handle.write(html)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def load_page(key: str, directory: Path = CACHE_DIR) -> str | None:
    """Read a cached page, treating a corrupt file as a miss.

    A truncated cache is not data: an offline reparse should skip the course
    and leave its record alone, not abort the whole run.
    """
    path = path_for(key, directory)
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return handle.read()
    except (OSError, EOFError, UnicodeDecodeError):
        return None


def has_page(key: str, directory: Path = CACHE_DIR) -> bool:
    return path_for(key, directory).exists()
