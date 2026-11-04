"""How a provider becomes a logo filename.

`logos.py` names the file; `crawl.py` compares a record's existing path against the
provider it now claims to have. One definition keeps the two from drifting — and it
keeps the import graph acyclic, since `logos` already imports `crawl`.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

IMAGE_PREFIX = "/logos/"
MAX_STEM = 64


def provider_slug(name: str) -> str:
    """'DeepLearning.AI' -> 'deeplearning-ai'. Stable, filesystem-safe."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    # Filesystem limit is 255 bytes per component; a wrong provider name must not
    # become a 900-character filename (Errno 63).
    return slug[:MAX_STEM].strip("-") or "provider"


def stem(record: dict) -> str:
    """Filename stem for a record's logo: its provider, or a URL hash.

    An older crawl could store a serialized JSON-LD person as `provider`; that is
    not a name, so it must never reach the filename. Those get the hash fallback.
    """
    provider = str(record.get("provider") or "").strip()
    image = str(record.get("image") or "")
    if provider and "@type" not in provider and not provider.startswith(("[", "{")):
        return provider_slug(provider)
    return hashlib.sha1(image.encode()).hexdigest()[:10]
