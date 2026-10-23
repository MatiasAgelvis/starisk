"""Starisk scoring engine.

A faithful Python port of the original 2021 JavaScript math. The behavior is
deliberately identical to `engine/engine.js` (the old extension), so the ported
tests are a spec, not a redesign.

The math:

    weight(review) = (base_review_value + likes) ** peer_power * age_days ** timedecay
    peer_score     = SUM(stars * weight) / SUM(weight)
    course_score   = peer_weight * peer_score + (1 - peer_weight) * coursera

`age_days` is days since the Unix epoch, exactly as the original computed it —
which makes the time term almost constant across years. That is a known flaw of
the original model, reproduced here on purpose.
"""

from __future__ import annotations

import math

# The original tuning, kept verbatim so the faithful model stays reproducible.
DEFAULTS = {
    "peer_power": 2,
    "timedecay": 0.3,
    "base_review_value": 2,
    "peer_weight": 0.8,
}

# The simplified model, expressible purely as parameters:
#     weight = (1 + likes) ** 1 * age_days ** 0 = 1 + likes
#     score  = SUM(stars * (1 + likes)) / SUM(1 + likes)
# i.e. "every reviewer is one voice, and every upvote is one more voice."
SIMPLE = {
    "peer_power": 1,
    "timedecay": 0,
    "base_review_value": 1,
    "peer_weight": 1,
}

# The calibrated model (2026-10): same shape, likes compressed by sqrt.
#
# Why: on 29 hand-labelled courses, unbounded likes let one review own a score.
# Tempering — sqrt, log, or capping likes at 10, or ignoring votes entirely —
# all land at rho ~0.68-0.70 against my gut ranking, versus 0.62 for `1 + likes`
# and 0.57 for the 2021 squared model. The differences are inside the noise
# (bootstrap: sqrt wins 79% of resamples, CIs overlap), but the direction is
# consistent and the failure mode it removes is real. A 663-like review should
# not count 663 times; under sqrt it counts ~26 times. Upvotes still matter.
CALIBRATED = {
    "peer_power": 0.5,
    "timedecay": 0,
    "base_review_value": 1,
    "peer_weight": 1,
}


def review_weight(review: dict, options: dict | None = None) -> float:
    """Weight of a single review: how much its star count should count."""
    opts = options or DEFAULTS
    peers = (opts["base_review_value"] + review["likes"]) ** opts["peer_power"]
    if opts["timedecay"] == 0:
        time = 1.0
    else:
        time = review["age_days"] ** opts["timedecay"]
    return peers * time


def peer_score(reviews: list[dict], options: dict | None = None) -> float:
    """Like-weighted average of the reviewers' star ratings."""
    opts = options or DEFAULTS
    weighted = 0.0
    total_weight = 0.0
    for review in reviews:
        weight = review_weight(review, opts)
        weighted += review["stars"] * weight
        total_weight += weight
    return 0.0 if total_weight == 0 else weighted / total_weight


def review_spread(reviews: list[dict]) -> float:
    """Plain standard deviation of the stars: do learners disagree with each other?

    Unweighted on purpose. Weighting by likes measures *endorsement*, and when one
    review dominates it drags the weighted mean onto itself — so the weighted
    spread collapses and a bitterly contested course looks unanimous. That
    collapse is real information (`peer_spread`), but it is not the dispersion we
    want for "contested".
    """
    if len(reviews) < 2:
        return 0.0

    values = [review["stars"] for review in reviews]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.sqrt(variance)


def peer_spread(reviews: list[dict], options: dict | None = None) -> float:
    """Like-weighted standard deviation of the stars, in stars.

    The score says where the weight sits; this says how split the *endorsed*
    reviews are. Beware: it shrinks when one review dominates, because the mean
    moves to it. Read it next to `review_spread`.
    """
    opts = options or DEFAULTS
    if not reviews:
        return 0.0

    mean = peer_score(reviews, opts)
    total = 0.0
    weighted = 0.0
    for review in reviews:
        weight = review_weight(review, opts)
        weighted += weight * (review["stars"] - mean) ** 2
        total += weight

    return 0.0 if total == 0 else math.sqrt(weighted / total)


def course_score(course: dict, options: dict | None = None) -> float:
    """Final score for a course. Returns -1.0 when there is nothing to verify."""
    opts = options or DEFAULTS
    reviews = course["reviews"]
    if not reviews:
        return -1.0

    peer = peer_score(reviews, opts)
    coursera = course.get("coursera", float("nan"))
    if coursera != coursera:  # NaN: page had no aggregate rating
        return peer
    return opts["peer_weight"] * peer + (1 - opts["peer_weight"]) * coursera
