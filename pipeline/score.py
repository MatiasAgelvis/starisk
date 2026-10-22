#!/usr/bin/env python3
"""Score saved Coursera reviews pages.

    cd pipeline
    python3 score.py ../samples/live/*.html
"""

from __future__ import annotations

import sys
from pathlib import Path

from starisk.adapter import extract_coursera_score, extract_reviews
from starisk.engine import DEFAULTS, SIMPLE, course_score


def fmt(value: float) -> str:
    if value != value or value < 0:  # NaN or unverifiable
        return "n/a"
    return f"{value:.1f}"


def main(files: list[str]) -> int:
    if not files:
        print("usage: python3 score.py <reviews-page.html> [...]")
        return 1

    print(f"{'page':36}{'coursera':>9}{'reviews':>8}{'original':>10}{'simple':>8}")
    for file in files:
        html = Path(file).read_text(encoding="utf-8")
        coursera = extract_coursera_score(html)
        reviews = extract_reviews(html)

        original = course_score({"reviews": reviews, "coursera": coursera}, DEFAULTS) if reviews else -1
        simple = course_score({"reviews": reviews, "coursera": coursera}, SIMPLE) if reviews else -1

        print(
            f"{Path(file).name:36}{fmt(coursera):>9}{len(reviews):>8}"
            f"{fmt(original):>10}{fmt(simple):>8}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
