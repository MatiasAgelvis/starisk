// The numbers behind the quadrant view: our own score against the disagreement
// inside its reviews. Like /findings, everything is derived at build time from
// `scores.json`; the chart draws plain SVG from these rows.

import { courses } from './courses.js';

export const SCORE_SPLIT = 3.5;
export const SPREAD_SPLIT = 1.2;
export const SPREAD_MAX = 2.2;

// Below this many readable reviews, "consensus" is not earned: one review has a
// spread of zero by definition. Matches the pipeline's `low_sample` bar.
export const MIN_REVIEWS = 15;

// Order matches the quadrant grid: rows are spread (high on top), columns are
// score (low on the left), so reading left→right, top→bottom is contested,
// divisive, consensus poor, consensus good.
export const CELLS = [
  { id: 'contested', label: 'Contested', note: 'low score, reviews scatter', badge: 'badge-warning' },
  { id: 'divisive', label: 'Divisive', note: 'high score, reviews scatter', badge: 'badge-info' },
  {
    id: 'consensusPoor',
    label: 'Consensus Poor',
    note: 'low score, reviews agree',
    badge: 'badge-error',
  },
  {
    id: 'consensusGood',
    label: 'Consensus Good',
    note: 'high score, reviews agree',
    badge: 'badge-success',
  },
];

/** Not a quadrant: the sample is too small to label. */
export const TOO_FEW = { id: 'tooFew', label: 'Too few reviews', badge: 'badge-ghost' };

/** Stable 0..1 from a string, so the jitter survives a rebuild. */
function hash(text) {
  let value = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    value ^= text.charCodeAt(i);
    value = Math.imul(value, 16777619);
  }
  return (value >>> 0) / 4294967295;
}

export function cellOf(score, spread, reviews) {
  if (!(reviews >= MIN_REVIEWS)) return 'tooFew';
  const highScore = score >= SCORE_SPLIT;
  const highSpread = spread >= SPREAD_SPLIT;
  if (highScore) return highSpread ? 'divisive' : 'consensusGood';
  return highSpread ? 'contested' : 'consensusPoor';
}

/**
 * Everything the quadrant section states, computed once.
 *
 * Both thresholds are fixed rather than median splits: the score axis is skewed
 * high, so a median "low score" would land around 4.4 and read wrong.
 */
export function buildContested(data = courses) {
  const rows = [];
  const counts = { contested: 0, divisive: 0, consensusGood: 0, consensusPoor: 0, tooFew: 0 };

  for (const [key, course] of Object.entries(data)) {
    if (typeof course.starisk !== 'number' || typeof course.spread !== 'number') continue;
    const reviews = course.reviews ?? 0;
    const row = {
      key,
      title: course.title ?? key,
      provider: course.provider ?? null,
      score: course.starisk,
      spread: course.spread,
      reviews,
      coursera: typeof course.coursera === 'number' ? course.coursera : null,
      ratings: typeof course.ratings_total === 'number' ? course.ratings_total : null,
      // Two independent jitters keep a rebuild pixel-identical.
      jx: hash(`${key}:cx`),
      jy: hash(`${key}:cy`),
      cell: cellOf(course.starisk, course.spread, reviews),
    };
    counts[row.cell] += 1;
    rows.push(row);
  }

  return { rows, counts, total: rows.length };
}

/**
 * Share of plotted courses with a strictly lower spread (0..1).
 *
 * Course pages turn this into "top N% by disagreement"; ties share the lower
 * rank, which is honest when many courses sit at the cap of 2.0.
 */
export function spreadShareBelow(spread, data = courses) {
  let lower = 0;
  let total = 0;
  for (const course of Object.values(data)) {
    if (typeof course.spread !== 'number') continue;
    total += 1;
    if (course.spread < spread) lower += 1;
  }
  return total ? lower / total : 0;
}
