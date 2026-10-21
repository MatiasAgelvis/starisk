'use strict';

// Stellaid scoring engine.
//
// Extracted from the 2021 browser extension so the idea can run on its own:
// no browser, no network, no scraping, no dependencies.
//
// The math below is kept faithful to the original `coursera-utils.js`:
//
//   weight(review) = (baseReviewValue + likes) ^ peerPower * ageDays ^ timedecay
//   peerScore      = SUM(stars * weight) / SUM(weight)
//   finalScore     = peerWeight * peerScore + (1 - peerWeight) * courseraScore
//
// Note on `ageDays`: the original computed days since the Unix epoch, so this
// term is close to constant across years. That is a known flaw of the original
// model, reproduced here on purpose so the engine is a faithful starting point
// rather than a rewrite. See the postmortem.

// The original tuning, kept verbatim so the faithful model stays reproducible.
const DEFAULTS = {
  peerPower: 2,
  timedecay: 0.3,
  baseReviewValue: 2,
  peerWeight: 0.8,
};

// A simplified model, expressible purely as options:
//   weight = (1 + likes) ^ 1 * ageDays ^ 0  =  1 + likes
//   score  = SUM(stars * (1 + likes)) / SUM(1 + likes)
//
// i.e. "every reviewer is one voice, and every upvote is one more voice."
// It drops the time term (which barely moves anything), the likes-squared
// exaggeration, and the Coursera blend. One knob left: whether you re-add a
// blend weight.
const SIMPLE = { peerPower: 1, baseReviewValue: 1, timedecay: 0, peerWeight: 1 };

// A review is a plain object: { stars, likes, ageDays }.
// `stars` is 0..5 (half stars allowed), `likes` is the "this is helpful" count,
// `ageDays` is days since the Unix epoch, matching the original.
function reviewWeight(review, options = DEFAULTS) {
  const peers = Math.pow(options.baseReviewValue + review.likes, options.peerPower);
  const time = Math.pow(review.ageDays, options.timedecay);
  return peers * time;
}

function peerScore(reviews, options = DEFAULTS) {
  let weighted = 0;
  let totalWeight = 0;

  for (const review of reviews) {
    const weight = reviewWeight(review, options);
    weighted += review.stars * weight;
    totalWeight += weight;
  }

  return totalWeight === 0 ? 0 : weighted / totalWeight;
}

// A course is { reviews, courseraScore }. Returns -1 when there is nothing to
// verify, matching the original `getCourseScore` behaviour.
function courseScore(course, options = DEFAULTS) {
  const { reviews, courseraScore } = course;

  if (reviews.length === 0) {
    return -1;
  }

  return options.peerWeight * peerScore(reviews, options)
    + (1 - options.peerWeight) * courseraScore;
}

module.exports = { DEFAULTS, SIMPLE, reviewWeight, peerScore, courseScore };
