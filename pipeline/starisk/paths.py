"""Where the pipeline keeps its things, and what each of them is.

Three locations, three different jobs:

- `pipeline/data` — the corpus. **Not state**: it lives in the checkout, is
  published through git like any other file, and the crawl reads and writes it
  there. Any machine's checkout is a valid starting point, because it comes from
  `develop`.
- the page cache — bytes fetched from Coursera. Expensive to rebuild, worthless
  to commit. Per machine, best effort: use it if it's there, fetch if it isn't.
  `STARISK_CACHE` moves it, which is what lets a container throw its checkout
  away without throwing the cache away.
- the logs — the run record and the lock. `STARISK_LOGS` moves them, because the
  nightly's checkout does not survive the process.

Read once, at import.
"""

from __future__ import annotations

import os
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = PIPELINE_DIR.parent


def _directory(variable: str, default: Path) -> Path:
    value = os.environ.get(variable, "").strip()
    return Path(value).expanduser().resolve() if value else default


DATA_DIR = PIPELINE_DIR / "data"
CACHE_DIR = _directory("STARISK_CACHE", DATA_DIR / ".cache")
LOG_DIR = _directory("STARISK_LOGS", REPO_DIR / "logs")
