"""Self-host the provider logos.

Coursera serves course images through a third-party image proxy. Hotlinking it
means every visitor's IP reaches Coursera's CDN, one URL change breaks every logo
at once, and we get no cache headers. So: download each *unique* provider image
once, keep the bytes, and point `scores.json` at the local copy.

No transcoding. The originals are ~160x60 PNGs of a few KB — smaller than the
HTTP overhead of the page that shows them — and re-encoding would drag a
non-stdlib encoder into a pipeline that is deliberately stdlib-only.

    cd pipeline
    python3 -m starisk.logos             # fetch whatever is missing
    python3 -m starisk.logos --force     # re-download everything
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

from .crawl import SCORES_PATH, write_atomic
from .fetch import fetch_bytes

LOGO_DIR = Path(__file__).resolve().parents[2] / "web" / "public" / "logos"
IMAGE_PREFIX = "/logos/"

# Extensions we are willing to store. Alpha matters: several provider marks are
# white-on-transparent, which is why JPEG is not a safe blanket choice.
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def provider_slug(name: str) -> str:
    """'DeepLearning.AI' -> 'deeplearning-ai'. Stable, filesystem-safe."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    return slug or "provider"


def sniff_extension(body: bytes) -> str | None:
    """Identify an image from its bytes. Returns None for anything unknown."""
    for signature, extension in _SIGNATURES:
        if body.startswith(signature):
            return extension
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return ".webp"
    if body.lstrip()[:4] in (b"<svg", b"<?xm"):
        return ".svg"
    return None


def _is_remote(image: object) -> bool:
    return isinstance(image, str) and image.startswith(("http://", "https://"))


def _existing(out_dir: Path, stem: str) -> Path | None:
    for candidate in sorted(out_dir.glob(f"{stem}.*")):
        return candidate
    return None


def localize_images(
    scores: dict,
    fetch=fetch_bytes,
    out_dir: Path = LOGO_DIR,
    force: bool = False,
    log=print,
) -> dict:
    """Download each unique provider logo and rewrite `image` to a local path.

    Fail-safe: a logo that cannot be fetched keeps its remote URL, so a bad
    download never blanks the site. Idempotent: an existing file is reused
    unless `force` is set.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # One download per provider: three DeepLearning.AI courses, one file.
    wanted: dict[str, str] = {}
    for record in scores.values():
        image = record.get("image")
        if not _is_remote(image):
            continue
        provider = (record.get("provider") or "").strip()
        stem = provider_slug(provider) if provider else hashlib.sha1(image.encode()).hexdigest()[:10]
        wanted.setdefault(stem, image)

    resolved: dict[str, str] = {}
    for stem, url in wanted.items():
        found = None if force else _existing(out_dir, stem)
        if found is not None:
            resolved[stem] = f"{IMAGE_PREFIX}{found.name}"
            continue

        try:
            body = fetch(url)
        except Exception as error:  # noqa: BLE001 - a logo must not stop the pipeline
            log(f"  ! logo failed ({stem}): {error}")
            continue

        extension = sniff_extension(body)
        if extension is None:
            log(f"  ! logo skipped ({stem}): unrecognised image format")
            continue

        path = out_dir / f"{stem}{extension}"
        path.write_bytes(body)
        resolved[stem] = f"{IMAGE_PREFIX}{path.name}"

    for record in scores.values():
        if not _is_remote(record.get("image")):
            continue
        provider = (record.get("provider") or "").strip()
        stem = provider_slug(provider) if provider else hashlib.sha1(record["image"].encode()).hexdigest()[:10]
        if stem in resolved:
            record["image"] = resolved[stem]

    return scores


def main(argv: list[str]) -> int:
    force = "--force" in argv

    if not SCORES_PATH.exists():
        print(f"no scores yet. run the crawl first: {SCORES_PATH}")
        return 1

    scores = json.loads(SCORES_PATH.read_text(encoding="utf-8"))
    localize_images(scores, force=force)
    write_atomic(SCORES_PATH, scores)

    local = sum(1 for record in scores.values() if str(record.get("image", "")).startswith(IMAGE_PREFIX))
    print(f"logos: {local}/{len(scores)} local | dir: {LOGO_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
