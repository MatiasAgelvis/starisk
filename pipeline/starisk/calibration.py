"""Calibration: turn `Certificates.md` into a labeled dataset, and compare a
model against my own gut ranking (Spearman).

The labels are mine; fill `label` in `calibration/courses.json` (higher = better).
The scores come from `scores.json` once the crawler has run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .crawl import SCORES_PATH, write_atomic
from .rank import average_ranks, spearman

REPO_ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_PATH = REPO_ROOT / "calibration" / "courses.json"

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


def score_key(entry: dict) -> str | None:
    """`calibration` slugs are bare (`machine-learning`); scores are keyed by type."""
    slug = (entry.get("slug") or "").strip()
    if not slug:
        return None
    return slug if "/" in slug else f"learn/{slug}"


def _score_for(entry: dict, scores: dict):
    key = score_key(entry)
    record = scores.get(key) if key else None
    if not record or "starisk" not in record:
        return None
    return record["starisk"]


def correlate(courses: list[dict], scores: dict):
    """Spearman between my labels and the model's scores.

    Returns (rho, pairs). rho is None when there is nothing to compare yet.
    """
    pairs = []
    for course in courses:
        if course.get("label") is None:
            continue
        score = _score_for(course, scores)
        if score is not None:
            pairs.append((course, score))

    if len(pairs) < 2:
        # Spearman needs at least two points; one pair has no variance.
        return None, pairs

    rho = spearman(
        [course["label"] for course, _ in pairs],
        [score for _, score in pairs],
    )
    return rho, pairs


def disagreements(pairs: list[tuple[dict, float]], limit: int = 8) -> list[dict]:
    """Courses where my ranking and the model's ranking differ most."""
    if len(pairs) < 2:
        return []

    mine = average_ranks([course["label"] for course, _ in pairs])
    theirs = average_ranks([score for _, score in pairs])

    rows = []
    for (course, score), my_rank, their_rank in zip(pairs, mine, theirs):
        rows.append(
            {
                "title": course["title"],
                "label": course["label"],
                "score": score,
                "delta": round(my_rank - their_rank, 1),
            }
        )
    rows.sort(key=lambda row: -abs(row["delta"]))
    return rows[:limit]


def report(courses: list[dict], scores: dict) -> dict:
    mapped = [course for course in courses if score_key(course)]
    labelled = [course for course in mapped if course.get("label") is not None]
    rho, pairs = correlate(courses, scores)
    unscored = [course["title"] for course in labelled if _score_for(course, scores) is None]

    return {
        "mapped": len(mapped),
        "labelled": len(labelled),
        "comparable": len(pairs),
        "rho": rho,
        "unscored": unscored,
        "disagreements": disagreements(pairs),
    }


def label_cli(courses: list[dict], path: Path) -> int:
    """Ask for a gut score, one course at a time, blind.

    Deliberately does not show the model's score: seeing it would anchor the
    answer and turn calibration into confirmation.
    """
    todo = [
        course
        for course in courses
        if score_key(course) and course.get("label") is None
    ]
    if not todo:
        print("nothing left to label. re-run the report to see the result.")
        return 0

    print(f"{len(todo)} mapped courses without a label. 1-5, higher = better.")
    print("s = skip, q = quit (answers are saved as you go).\n")

    for index, course in enumerate(todo, 1):
        print(f"[{index}/{len(todo)}] {course['title']}")
        raw = input("    your rating: ").strip().lower()
        if raw == "q":
            break
        if raw == "s" or not raw:
            continue
        try:
            course["label"] = float(raw)
        except ValueError:
            print("    not a number, skipped")
            continue
        write_atomic(path, courses)

    write_atomic(path, courses)
    done = sum(1 for course in courses if course.get("label") is not None)
    print(f"\nlabelled {done}/{len(courses)} credentials")
    return 0


def main(argv: list[str]) -> int:
    """
    python -m starisk.calibration                      # report
    python -m starisk.calibration --label              # ask, one course at a time
    python -m starisk.calibration --parse <Certificate.md>   # rebuild the file
    """
    courses = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))

    if "--parse" in argv:
        source = Path(argv[argv.index("--parse") + 1])
        entries = parse_certificates(source.read_text(encoding="utf-8"))
        write_atomic(CALIBRATION_PATH, entries)
        print(f"wrote {len(entries)} entries to {CALIBRATION_PATH}")
        return 0

    if "--label" in argv:
        return label_cli(courses, CALIBRATION_PATH)

    scores = json.loads(SCORES_PATH.read_text(encoding="utf-8")) if SCORES_PATH.exists() else {}
    result = report(courses, scores)
    print(
        f"mapped {result['mapped']} | labelled {result['labelled']} "
        f"| comparable {result['comparable']}"
    )

    if result["rho"] is None:
        print("\nnothing to correlate yet: add labels with `--label`.")
        return 0

    print(f"\nSpearman rho = {result['rho']:+.2f}  (n={result['comparable']})")
    if result["unscored"]:
        print(f"labelled but not in scores.json: {', '.join(result['unscored'])}")
    if result["disagreements"]:
        print("\nbiggest disagreements (my rank minus the model's):")
        for row in result["disagreements"]:
            print(
                f"  {row['delta']:+.1f}  mine {row['label']:.0f} / model {row['score']:.1f}"
                f"   {row['title'][:58]}"
            )
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv))
