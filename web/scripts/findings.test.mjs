import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildFindings, histogram, pearson, starOf } from '../src/lib/findings.js';

test('scores round half-up to whole stars, clamped to the axis', () => {
  assert.equal(starOf(1.0), 1);
  assert.equal(starOf(1.4), 1);
  assert.equal(starOf(1.5), 2);
  assert.equal(starOf(4.4), 4);
  // Half-up, not banker's: `round(4.5)` in Python/`toFixed`-land would say 4 and
  // quietly move 48 courses out of the top bucket.
  assert.equal(starOf(4.5), 5);
  assert.equal(starOf(5.0), 5);
  assert.equal(starOf(0.2), 1); // below the axis
  assert.equal(starOf(9), 5); // above it
});

test('a histogram counts per star, and shares sum to one', () => {
  const bins = histogram([4.8, 4.9, 4.6, 3.2, 1.1]);
  assert.equal(bins.length, 5);
  assert.equal(
    bins.reduce((total, bin) => total + bin.count, 0),
    5,
  );
  assert.ok(Math.abs(bins.reduce((total, bin) => total + bin.share, 0) - 1) < 1e-9);
  assert.equal(bins[4].count, 3); // 4.6, 4.8, 4.9
  assert.equal(bins[2].count, 1); // 3.2
  assert.equal(bins[0].count, 1); // 1.1
  assert.deepEqual(
    bins.map((bin) => bin.star),
    [1, 2, 3, 4, 5],
  );
});

test('shares, not counts, are what the two series compare on', () => {
  // A short series should not look smaller than a long one with the same shape.
  const short = histogram([4.8, 4.8]);
  const long = histogram([4.8, 4.8, 4.8, 4.8, 4.8, 4.8]);
  assert.equal(short[4].share, long[4].share);
  assert.notEqual(short[4].count, long[4].count);
});

test('pearson is -1, 0 or 1 where it should be', () => {
  assert.equal(pearson([1, 2, 3], [2, 4, 6]), 1);
  assert.equal(pearson([1, 2, 3], [6, 4, 2]), -1);
  assert.equal(pearson([1, 1, 1], [1, 2, 3]), 0); // no variance
  assert.equal(pearson([], []), 0);
});

const fixture = {
  'learn/a': { title: 'A', coursera: 4.8, starisk: 1.5, reviews: 20, spread: 1.2 },
  'learn/b': { title: 'B', coursera: 4.6, starisk: 4.5, reviews: 20, spread: 0.8 },
  'learn/c': { coursera: 4.0, starisk: 3.0, reviews: 20 },
  'learn/d': { title: 'D', starisk: 4.9, reviews: 20 }, // no headline rating
  'learn/e': { title: 'E', coursera: null, no_reviews: true }, // not scored
};

test('buildFindings separates scored from plottable courses', () => {
  const data = buildFindings(fixture);
  assert.equal(data.scored.length, 4); // a, b, c, d
  assert.equal(data.rated.length, 3); // a, b, c
  assert.deepEqual(
    data.topGaps.map((course) => course.title),
    ['A', 'learn/c', 'B'], // c has no title, so it falls back to its key
  );
});

test('buildFindings buckets the gap exactly as the verdicts do', () => {
  const data = buildFindings(fixture);
  // A: 4.8 - 1.5 = 3.3 → inflated; C: 1.0 → padded; B: 0.1 → holds up
  assert.equal(data.inflated, 1);
  assert.equal(data.padded, 1);
  assert.equal(data.holdsUp, 1);
});

test('buildFindings puts each course in its star bucket', () => {
  const data = buildFindings(fixture);
  // Starisk: 1.5, 4.5, 3.0, 4.9 → 2★, 5★, 3★, 5★
  assert.equal(data.ours[4].count, 2);
  assert.equal(data.ours[1].count, 1);
  assert.equal(data.ours[2].count, 1);
  // Coursera: 4.8, 4.6, 4.0 → 5★, 5★, 4★
  assert.equal(data.theirs[4].count, 2);
  assert.equal(data.theirs[3].count, 1);
});

test('buildFindings counts courses whose star rating rounds differently', () => {
  const data = buildFindings(fixture);
  // a: 5★ vs 2★ differ · b: 5★ vs 5★ same · c: 4★ vs 3★ differ
  assert.equal(data.differentStars, 2);
});

test('a course with no title falls back to its key', () => {
  const data = buildFindings(fixture);
  assert.ok(data.scored.some((course) => course.title === 'learn/c'));
});
