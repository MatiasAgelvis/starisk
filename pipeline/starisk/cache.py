"""A local cache of fetched pages, so re-parsing is free.

The adapter will break — that is a stated risk, not a possibility. Without a
cache, every selector fix means re-fetching the whole list from the one
residential IP the project depends on. With it, `--offline` re-scores from disk.

Stored as gzipped HTML: a reviews page is ~700 KB raw and ~70 KB gzipped, so a
few hundred courses cost tens of megabytes in a gitignored directory.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .paths import CACHE_DIR as STATE_CACHE

CACHE_DIR = STATE_CACHE / "pages"
SUFFIX = ".html.gz"


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


# --- Inspecting the cache -------------------------------------------------
#
# The cache is what makes an adapter fix cheap, so its health is worth a command
# rather than a throwaway script: how much is there, how old, and — after a
# selector change — how much of it the code in this checkout can still read.


def key_of(path: Path) -> str:
    """The inverse of `path_for`: `learn__x.html.gz` -> `learn/x`.

    Only the first separator is replaced; a slug cannot contain `__`, and a
    landing copy keeps its `.landing` suffix (it is a different page).
    """
    return path.name[: -len(SUFFIX)].replace("__", "/", 1)


def _kind_of(key: str) -> str:
    kind = key.split("/", 1)[0]
    return f"{kind} (landing)" if key.endswith(".landing") else kind


def _timestamp(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    return datetime.fromtimestamp(seconds, timezone.utc).date().isoformat()


def _size(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"  # pragma: no cover - a cache this size is not real


def stats(directory: Path = CACHE_DIR) -> dict:
    """Counts, sizes and date range, without opening a single page."""
    kinds: dict[str, dict] = {}
    oldest = newest = None
    pages = 0
    total = 0

    for path in sorted(directory.glob(f"*{SUFFIX}")):
        info = path.stat()
        kind = _kind_of(key_of(path))
        entry = kinds.setdefault(kind, {"pages": 0, "bytes": 0})
        entry["pages"] += 1
        entry["bytes"] += info.st_size
        pages += 1
        total += info.st_size
        oldest = info.st_mtime if oldest is None else min(oldest, info.st_mtime)
        newest = info.st_mtime if newest is None else max(newest, info.st_mtime)

    return {
        "directory": str(directory),
        "pages": pages,
        "bytes": total,
        "kinds": dict(sorted(kinds.items())),
        "oldest": _timestamp(oldest),
        "newest": _timestamp(newest),
    }


def verify(directory: Path = CACHE_DIR) -> dict:
    """Gunzip and re-parse every cached page with the code in this checkout.

    Statuses: `ok` still yields what its kind is for; `empty` is a course page
    Coursera itself marks as having no written reviews (a valid record, not a
    parse failure); `unparsed` means the page arrived but the selectors no longer
    find anything; `unreadable` is a corrupt file; `error` is a parser that threw;
    `unknown` is a key this build has no reader for.

    No requests, so it is the cheap way to answer "how much of my cache can the
    current adapter still read" before a selector change.
    """
    # Imported here, not at module level: `crawl` imports this module, and
    # `groupings` imports `crawl`, so the reverse edge would be circular.
    from .adapter import (
        extract_instructor_courses,
        extract_landing,
        extract_reviews,
        is_empty_reviews_page,
    )
    from .groupings import GROUPING_TYPES, extract_grouping

    def status_of(key: str, html: str | None) -> str:
        if html is None or html == "":
            return "unreadable"

        kind = key.split("/", 1)[0]
        try:
            if key.endswith(".landing"):
                if kind == "learn":
                    landing = extract_landing(html)
                    return "ok" if landing["instructors"] or landing["categories"] else "unparsed"
                if kind in GROUPING_TYPES:
                    return "ok" if extract_grouping(html, key[: -len(".landing")]) else "unparsed"
                return "unknown"
            if kind == "learn":
                if extract_reviews(html):
                    return "ok"
                return "empty" if is_empty_reviews_page(html) else "unparsed"
            if kind == "instructor":
                return "ok" if extract_instructor_courses(html) else "unparsed"
            if kind in GROUPING_TYPES:
                return "ok" if extract_grouping(html, key) else "unparsed"
            return "unknown"
        except Exception:  # noqa: BLE001 - a page that raises is what verify is for
            return "error"

    counts: dict[str, dict[str, int]] = {}
    failures: list[dict] = []

    for path in sorted(directory.glob(f"*{SUFFIX}")):
        key = key_of(path)
        kind = _kind_of(key)
        status = status_of(key, load_page(key, directory))

        bucket = counts.setdefault(kind, {})
        bucket[status] = bucket.get(status, 0) + 1
        if status not in ("ok", "empty"):
            failures.append({"key": key, "kind": kind, "status": status})

    return {"directory": str(directory), "counts": counts, "failures": failures}


def _print_stats(data: dict) -> None:
    print(f"page cache  {data['directory']}")
    width = max((len(kind) for kind in data["kinds"]), default=4)
    for kind, entry in data["kinds"].items():
        print(f"  {kind:<{width}}  {entry['pages']:>6,} pages  {_size(entry['bytes']):>9}")
    print(f"  {'total':<{width}}  {data['pages']:>6,} pages  {_size(data['bytes']):>9}")
    if data["pages"]:
        print(f"  oldest {data['oldest']} · newest {data['newest']}")


def _print_verify(data: dict) -> None:
    print(f"re-parsed  {data['directory']}")
    width = max((len(kind) for kind in data["counts"]), default=4)
    total = 0
    readable = 0
    for kind, bucket in data["counts"].items():
        pages = sum(bucket.values())
        total += pages
        readable += bucket.get("ok", 0) + bucket.get("empty", 0)
        parts = ", ".join(f"{count} {status}" for status, count in sorted(bucket.items()))
        print(f"  {kind:<{width}}  {parts}")

    if total:
        share = readable / total
        print(f"\n{readable:,} of {total:,} pages still parse ({share:.1%})")
        print("'empty' is a course Coursera shows no written reviews for — a valid record.")
    else:
        print("\nno pages cached")

    if data["failures"]:
        print(f"\n{len(data['failures'])} page(s) need attention:")
        for failure in data["failures"][:20]:
            print(f"  {failure['status']:<10} {failure['key']}")
        if len(data["failures"]) > 20:
            print(f"  … and {len(data['failures']) - 20} more (use --json for all)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m starisk.cache",
        description="Inspect the page cache: counts and sizes, or a full reparse.",
    )
    parser.add_argument("command", choices=("stats", "verify"))
    parser.add_argument(
        "--directory", type=Path, default=CACHE_DIR, help="page cache directory"
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    options = parser.parse_args(argv)

    data = stats(options.directory) if options.command == "stats" else verify(options.directory)

    if options.json:
        print(json.dumps(data, indent=2))
    elif options.command == "stats":
        _print_stats(data)
    else:
        _print_verify(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
