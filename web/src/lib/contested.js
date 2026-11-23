// The numbers behind /contested: our own score against the disagreement inside
// its reviews. Like /findings, everything is derived at build time from
// `scores.json`; the page draws plain SVG from these rows.

import { courses } from './courses.js';

export const SCORE_SPLIT = 3.5;
export const SPREAD_SPLIT = 1.2;
export const SPREAD_MAX = 2.2;

export const CELLS = [
  { id: 'contested', label: 'Contested', note: 'low score, reviews scatter' },
  { id: 'divisive', label: 'Divisive', note: 'high score, reviews scatter' },
  { id: 'consensusGood', label: 'Consensus good', note: 'high score, reviews agree' },
  { id: 'consensusPoor', label: 'Consensus poor', note: 'low score, reviews agree' },
];

/** Stable 0..1 from a string, so the jitter survives a rebuild. */
function hash(text) {
  let value = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    value ^= text.charCodeAt(i);
    value = Math.imul(value, 16777619);
  }
  return (value >>> 0) / 4294967295;
}

export function cellOf(score, spread) {
  const highScore = score >= SCORE_SPLIT;
  const highSpread = spread >= SPREAD_SPLIT;
  if (highScore) return highSpread ? 'divisive' : 'consensusGood';
  return highSpread ? 'contested' : 'consensusPoor';
}

/**
 * Everything `/contested` states, computed once.
 *
 * A course needs both a score and a spread to sit on the plot. Both thresholds
 * are fixed rather than median splits: the score axis is skewed high, so a
 * median "low score" would land around 4.4 and read wrong.
 */
export function buildContested(data = courses) {
  const rows = [];
  const counts = { contested: 0, divisive: 0, consensusGood: 0, consensusPoor: 0 };

  for (const [key, course] of Object.entries(data)) {
    if (typeof course.starisk !== 'number' || typeof course.spread !== 'number') continue;
    const row = {
      key,
      title: course.title ?? key,
      provider: course.provider ?? null,
      score: course.starisk,
      spread: course.spread,
      reviews: course.reviews ?? 0,
      // Two independent jitters keep a rebuild pixel-identical.
      jx: hash(`${key}:cx`),
      jy: hash(`${key}:cy`),
      cell: cellOf(course.starisk, course.spread),
    };
    counts[row.cell] += 1;
    rows.push(row);
  }

  const contested = rows
    .filter((row) => row.cell === 'contested')
    .sort(
      (a, b) => b.spread - a.spread || a.score - b.score || a.title.localeCompare(b.title),
    );

  return { rows, counts, contested, total: rows.length };
}
