"""Rank correlation, used to check a model against a hand-made ranking.

Spearman = Pearson correlation computed on ranks (ties get average ranks).
"""

from __future__ import annotations


def average_ranks(values: list[float]) -> list[float]:
    """1-based ranks; values that tie share the average of their ranks."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)

    i = 0
    n = len(order)
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1

    return ranks


def spearman(xs: list[float], ys: list[float]) -> float:
    """Rank correlation, with 0.0 when either side has no variance.

    A constant series has no ranks to correlate, so the coefficient is
    undefined; returning 0.0 keeps a small or degenerate calibration set from
    crashing the report.
    """
    if len(xs) != len(ys) or not xs:
        raise ValueError("spearman needs two equal-length, non-empty arrays")

    rx = average_ranks(xs)
    ry = average_ranks(ys)
    n = len(rx)

    mean_x = sum(rx) / n
    mean_y = sum(ry) / n

    covariance = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
    variance_x = sum((a - mean_x) ** 2 for a in rx)
    variance_y = sum((b - mean_y) ** 2 for b in ry)

    if variance_x == 0 or variance_y == 0:
        return 0.0

    return covariance / (variance_x * variance_y) ** 0.5
