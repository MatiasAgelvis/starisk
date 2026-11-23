import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  MIN_REVIEWS,
  SCORE_SPLIT,
  SPREAD_SPLIT,
  buildContested,
  cellOf,
  spreadShareBelow,
} from '../src/lib/contested.js';

const fixture = {
  'learn/contested': { title: 'Contested', starisk: 3.0, spread: 1.8, reviews: 20 },
  'learn/divisive': { title: 'Divisive', starisk: 4.6, spread: 1.6, reviews: 20 },
  'learn/good': { title: 'Good', starisk: 4.4, spread: 0.6, reviews: 20 },
  'learn/poor': { title: 'Poor', starisk: 2.3, spread: 0.5, reviews: 20 },
  'learn/on-the-line': { title: 'On the line', starisk: 3.5, spread: 1.2, reviews: 20 },
  'learn/too-few': { title: 'Too few', starisk: 4.6, spread: 0.4, reviews: 5 },
  'learn/no-spread': { title: 'No spread', starisk: 4.0 },
  'learn/no-score': { title: 'No score', spread: 1.5 },
};

test('the split is inclusive on both thresholds', () => {
  assert.equal(cellOf(SCORE_SPLIT, 0, 20), 'consensusGood');
  assert.equal(cellOf(SCORE_SPLIT - 0.1, 0, 20), 'consensusPoor');
  assert.equal(cellOf(5, SPREAD_SPLIT, 20), 'divisive');
  assert.equal(cellOf(5, SPREAD_SPLIT - 0.1, 20), 'consensusGood');
});

test('under the sample bar there is no quadrant, whatever the numbers say', () => {
  assert.equal(cellOf(4.6, 0.4, MIN_REVIEWS - 1), 'tooFew');
  assert.equal(cellOf(4.6, 0.4, MIN_REVIEWS), 'consensusGood');
  assert.equal(cellOf(4.6, 0.4), 'tooFew'); // no reviews at all
});

test('buildContested only plots courses with both a score and a spread', () => {
  const data = buildContested(fixture);
  assert.equal(data.total, 6); // the two incomplete records are dropped
  assert.equal(data.rows.length, 6);
});

test('buildContested counts each cell', () => {
  const data = buildContested(fixture);
  assert.deepEqual(data.counts, {
    contested: 1,
    divisive: 2, // divisive + on-the-line
    consensusGood: 1,
    consensusPoor: 1,
    tooFew: 1, // too-few, even though its numbers look consensus-good
  });
});

test('a course with no title falls back to its key', () => {
  const data = buildContested({ 'learn/untitled': { starisk: 2.0, spread: 1.5 } });
  assert.equal(data.rows[0].title, 'learn/untitled');
});

test('spreadShareBelow counts only strictly lower spreads', () => {
  const data = {
    'learn/a': { spread: 0.5 },
    'learn/b': { spread: 1.0 },
    'learn/c': { spread: 2.0 },
    'learn/d': {}, // no spread: ignored
  };
  assert.equal(spreadShareBelow(0.5, data), 0);
  assert.equal(spreadShareBelow(1.0, data), 1 / 3);
  assert.equal(spreadShareBelow(2.0, data), 2 / 3);
  assert.equal(spreadShareBelow(3.0, data), 1);
  assert.equal(spreadShareBelow(1.0, {}), 0);
});
