"""Calibration: turn `Certificates.md` into a labeled dataset, and compare a
model against my own gut ranking (Spearman).

The labels are mine; fill `label` in `calibration/courses.json` (higher = better).
The scores come from `scores.json` once the crawler has run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .rank import spearman

REPO_ROOT = Path(__file__).resolve().parents[2]

_LINK = re.compile(r"^\[([^\]]+)\]\(([^)]+)\)")
_AUTHORITY = re.compile(r"Issuing [Aa]uthority:\s*(.+?)\s*$")
_DATE = re.compile(r"Issue Date:?\s*(.+?)\s*$")
_CREDENTIAL = re.compile(r"Credential ID:\s*(.+?)\s*$")


def parse_certificates(text: str) -> list[dict]:
    """Parse a Certificates.md into entries with an empty `label`."""
    entries = []
    current = None

    for line in text.splitlines():
        link = _LINK.match(line)
        if link:
            if current:
                entries.append(current)
            current = {
                "title": link.group(1),
                "url": link.group(2),
                "issuer": None,
                "date": None,
                "credential_id": None,
            }
            continue

        if current is None:
            continue

        for pattern, key in (
            (_AUTHORITY, "issuer"),
            (_DATE, "date"),
            (_CREDENTIAL, "credential_id"),
        ):
            match = pattern.search(line)
            if match:
                current[key] = match.group(1).strip()

    if current:
        entries.append(current)

    for entry in entries:
        entry["type"] = (
            "specialization" if "specialization" in entry["title"].lower() else "course"
        )
        entry["label"] = None

    return entries


def _score_for(course: dict, scores: dict):
    if course["url"] in scores:
        return scores[course["url"]]
    return scores.get(course["title"])


def correlate(courses: list[dict], scores: dict):
    """Spearman between my labels and the model's scores.

    Returns (rho, pairs). rho is None when there is nothing to compare yet.
    """
    pairs = []
    for course in courses:
        if course.get("label") is None:
            continue
        score = _score_for(course, scores)
        if score is not None and score >= 0:
            pairs.append((course, score))

    if not pairs:
        return None, []

    rho = spearman(
        [course["label"] for course, _ in pairs],
        [score for _, score in pairs],
    )
    return rho, pairs


def main(argv: list[str]) -> int:
    """python -m starisk.calibration <Certificates.md> [out.json]"""
    if len(argv) < 2:
        print("usage: python -m starisk.calibration <Certificates.md> [out.json]")
        return 1

    source = Path(argv[1])
    destination = (
        Path(argv[2]) if len(argv) > 2 else REPO_ROOT / "calibration" / "courses.json"
    )

    entries = parse_certificates(source.read_text(encoding="utf-8"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"wrote {len(entries)} entries to {destination}")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv))
