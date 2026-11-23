import assert from 'node:assert/strict';
import { test } from 'node:test';

import { SCORE_SPLIT, SPREAD_SPLIT, buildContested, cellOf } from '../src/lib/contested.js';

const fixture = {
  'learn/contested': { title: 'Contested', starisk: 3.0, spread: 1.8, reviews: 20 },
  'learn/divisive': { title: 'Divisive', starisk: 4.6, spread: 1.6, reviews: 20 },
  'learn/good': { title: 'Good', starisk: 4.4, spread: 0.6, reviews: 20 },
  'learn/poor': { title: 'Poor', starisk: 2.3, spread: 0.5, reviews: 20 },
  'learn/on-the-line': { title: 'On the line', starisk: 3.5, spread: 1.2, reviews: 20 },
  'learn/no-spread': { title: 'No spread', starisk: 4.0 },
  'learn/no-score': { title: 'No score', spread: 1.5 },
};

test('the split is inclusive on both thresholds', () => {
  assert.equal(cellOf(SCORE_SPLIT, 0), 'consensusGood');
  assert.equal(cellOf(SCORE_SPLIT - 0.1, 0), 'consensusPoor');
  assert.equal(cellOf(5, SPREAD_SPLIT), 'divisive');
  assert.equal(cellOf(5, SPREAD_SPLIT - 0.1), 'consensusGood');
});

test('buildContested only plots courses with both a score and a spread', () => {
  const data = buildContested(fixture);
  assert.equal(data.total, 5); // the two incomplete records are dropped
  assert.equal(data.rows.length, 5);
});

test('buildContested counts each cell', () => {
  const data = buildContested(fixture);
  assert.deepEqual(data.counts, {
    contested: 1,
    divisive: 2, // divisive + on-the-line
    consensusGood: 1,
    consensusPoor: 1,
  });
});

test('the contested list is sorted by spread, then score, then title', () => {
  const data = buildContested(fixture);
  assert.deepEqual(
    data.contested.map((course) => course.title),
    ['Contested'],
  );
});

test('the contested list breaks spread ties by the lower score', () => {
  const data = buildContested({
    'learn/high': { title: 'High', starisk: 3.4, spread: 1.9 },
    'learn/low': { title: 'Low', starisk: 2.1, spread: 1.9 },
  });
  assert.deepEqual(
    data.contested.map((course) => course.title),
    ['Low', 'High'],
  );
});

test('a course with no title falls back to its key', () => {
  const data = buildContested({ 'learn/untitled': { starisk: 2.0, spread: 1.5 } });
  assert.equal(data.rows[0].title, 'learn/untitled');
});
