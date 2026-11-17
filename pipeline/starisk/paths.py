"""Where the pipeline keeps state, and where the code lives.

The JSON corpus and the page cache are *state*: they accumulate across runs and
must survive a fresh checkout. Everything else — provider logos, the derived
logo sizes, `web/src/data` — is repo content, rebuilt or committed like any other
file.

By default state is `pipeline/data` inside the checkout, which is what `mise run`
and the tests expect. The nightly container points `STARISK_DATA` at a volume
instead, so it can throw away its clone every run and still start from the corpus
it built last night.

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


DATA_DIR = _directory("STARISK_DATA", PIPELINE_DIR / "data")
CACHE_DIR = DATA_DIR / ".cache"
# The run record and the lock are state as well: the nightly's checkout is thrown
# away, so anything worth keeping after the process exits lives here.
LOG_DIR = _directory("STARISK_LOGS", REPO_DIR / "logs")
