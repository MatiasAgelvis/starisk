'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { averageRanks, spearman } = require('./rank.js');

test('averageRanks assigns 1-based average ranks, ties share a rank', () => {
  assert.deepEqual(averageRanks([10, 20, 30]), [1, 2, 3]);
  assert.deepEqual(averageRanks([30, 10, 20]), [3, 1, 2]);
  // two values tie for ranks 1 and 2 -> both get 1.5
  assert.deepEqual(averageRanks([5, 5, 9]), [1.5, 1.5, 3]);
});

test('spearman is 1 for identical orderings', () => {
  assert.equal(spearman([1, 2, 3, 4, 5], [10, 20, 30, 40, 50]), 1);
});

test('spearman is -1 for exactly reversed orderings', () => {
  assert.equal(spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]), -1);
});

test('spearman matches a known value', () => {
  // ranks [1,2,3,4,5] vs [2,1,4,3,5] -> 0.8
  assert.ok(Math.abs(spearman([1, 2, 3, 4, 5], [2, 1, 4, 3, 5]) - 0.8) < 1e-12);
});
