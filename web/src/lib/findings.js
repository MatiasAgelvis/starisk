// The numbers behind /findings: two distributions and one scatter.
//
// Everything here is derived from `scores.json` at build time — no new pipeline
// field, no client fetch. The charts the page draws are just these numbers with
// coordinates attached, which is why they can be generated as plain SVG.

import { courses } from './courses.js';

export const MIN = 1;
export const MAX = 5;
export const STARS = [1, 2, 3, 4, 5];

/**
 * Whole-star bucket for a score.
 *
 * Half-up on purpose: 4.5 is a five-star course, which is both what a reader
 * expects and what Python's `round()` would get wrong (banker's rounding sends
 * 4.5 to 4, quietly moving 48 courses out of the top bucket).
 */
export function starOf(value) {
  return Math.min(STARS.length, Math.max(1, Math.floor(value + 0.5)));
}

/**
 * Counts and shares per whole star.
 *
 * Shares, not counts: the two series have different totals (25 scored courses
 * have no Coursera rating), and comparing raw counts would quietly flatter us.
 */
export function histogram(values) {
  const counts = new Array(STARS.length).fill(0);
  for (const value of values) counts[starOf(value) - 1] += 1;
  const total = values.length || 1;
  return counts.map((count, index) => ({
    star: index + 1,
    count,
    share: count / total,
  }));
}

export function mean(values) {
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : 0;
}

/** Pearson's r. Spearman needs a ranking pass and buys nothing on 528 points. */
export function pearson(xs, ys) {
  if (xs.length === 0 || xs.length !== ys.length) return 0;
  const mx = mean(xs);
  const my = mean(ys);
  let num = 0;
  let dx2 = 0;
  let dy2 = 0;
  for (let i = 0; i < xs.length; i += 1) {
    const dx = xs[i] - mx;
    const dy = ys[i] - my;
    num += dx * dy;
    dx2 += dx * dx;
    dy2 += dy * dy;
  }
  const den = Math.sqrt(dx2 * dy2);
  return den ? num / den : 0;
}

/** Stable 0..1 from a string, so the scatter's jitter survives a rebuild. */
function hash(text) {
  let value = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    value ^= text.charCodeAt(i);
    value = Math.imul(value, 16777619);
  }
  return (value >>> 0) / 4294967295;
}

/**
 * Everything `/findings` states, computed once.
 *
 * `rated` holds the plottable courses; 25 scored courses have no headline rating
 * and cannot sit on a scatter of the two.
 */
export function buildFindings(data = courses) {
  const scored = [];
  for (const [key, course] of Object.entries(data)) {
    if (typeof course.starisk !== 'number') continue;
    scored.push({
      key,
      title: course.title ?? key,
      provider: course.provider ?? null,
      starisk: course.starisk,
      coursera: typeof course.coursera === 'number' ? course.coursera : null,
      spread: typeof course.spread === 'number' ? course.spread : null,
      reviews: course.reviews ?? 0,
      // Two independent jitters keep a rebuild pixel-identical.
      jx: hash(`${key}:x`),
      jy: hash(`${key}:y`),
    });
  }

  const rated = [];
  for (const course of scored) {
    // Narrowed into the array so consumers get a non-null number, not a check.
    if (typeof course.coursera === 'number') rated.push({ ...course, coursera: course.coursera });
  }
  const gaps = rated.map((course) => course.coursera - course.starisk);
  const correlation = pearson(
    rated.map((course) => course.coursera),
    rated.map((course) => course.starisk),
  );

  const topGaps = [...rated]
    .map((course) => ({ ...course, gap: course.coursera - course.starisk }))
    .sort((a, b) => b.gap - a.gap || a.title.localeCompare(b.title));

  return {
    scored,
    rated,
    theirs: histogram(rated.map((course) => course.coursera)),
    ours: histogram(scored.map((course) => course.starisk)),
    correlation,
    r2: correlation * correlation,
    // Courses whose star rating rounds differently to Coursera's — the card's
    // "1 in 2". Course-level, not pair-level: it is a fact about the catalogue.
    differentStars: rated.filter((course) => starOf(course.coursera) !== starOf(course.starisk))
      .length,
    medianGap: gaps.length ? gaps.sort((a, b) => a - b)[Math.floor(gaps.length / 2)] : 0,
    inflated: gaps.filter((gap) => gap >= 1.5).length,
    padded: gaps.filter((gap) => gap >= 0.5 && gap < 1.5).length,
    holdsUp: gaps.filter((gap) => gap < 0.5).length,
    topGaps: topGaps.slice(0, 8),
  };
}
