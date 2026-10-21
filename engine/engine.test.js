'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { peerScore, courseScore, reviewWeight, DEFAULTS, SIMPLE } = require('./engine.js');

// Floating point: compare with a tolerance instead of exact equality.
function close(actual, expected, epsilon = 1e-9) {
  assert.ok(
    Math.abs(actual - expected) < epsilon,
    `expected ${actual} to be within ${epsilon} of ${expected}`,
  );
}

test('a single review scores as its own star value', () => {
  close(peerScore([{ stars: 3, likes: 0, ageDays: 18000 }]), 3);
});

test('equal-weight reviews score as the plain mean', () => {
  const reviews = [
    { stars: 5, likes: 0, ageDays: 18000 },
    { stars: 1, likes: 0, ageDays: 18000 },
  ];
  close(peerScore(reviews), 3);
});

test('likes dominate: one heavily-liked review pulls the score', () => {
  const reviews = [
    { stars: 5, likes: 0, ageDays: 18000 },
    { stars: 1, likes: 100, ageDays: 18000 },
  ];
  assert.ok(
    peerScore(reviews) < 2,
    'expected the liked 1-star review to dominate the unliked 5-star review',
  );
});

test('final score blends the peer rating (80%) with the Coursera rating (20%)', () => {
  const course = { reviews: [{ stars: 3, likes: 0, ageDays: 18000 }], courseraScore: 5 };
  // 0.8 * 3 + 0.2 * 5 = 3.4
  close(courseScore(course), 3.4);
});

test('no reviews means unverifiable (-1)', () => {
  assert.equal(courseScore({ reviews: [], courseraScore: 4.5 }), -1);
});

test('custom options change the weighting', () => {
  const reviews = [
    { stars: 5, likes: 0, ageDays: 18000 },
    { stars: 1, likes: 100, ageDays: 18000 },
  ];
  const peerPowerOne = { ...DEFAULTS, peerPower: 1 };
  // With likes no longer squared, the liked review still wins but less sharply.
  assert.ok(peerScore(reviews, peerPowerOne) > peerScore(reviews, DEFAULTS));
});

test('SIMPLE model weights a review by (1 + likes), plainly', () => {
  close(reviewWeight({ stars: 3, likes: 4, ageDays: 18000 }, SIMPLE), 5);
  const reviews = [
    { stars: 5, likes: 0, ageDays: 18000 }, // weight 1
    { stars: 1, likes: 4, ageDays: 18000 }, // weight 5
  ];
  // (5*1 + 1*5) / (1 + 5) = 10/6
  close(peerScore(reviews, SIMPLE), 10 / 6);
});

test('documents the known flaw: the time term barely moves across years', () => {
  const old = reviewWeight({ stars: 4, likes: 10, ageDays: 17800 }, DEFAULTS);
  const recent = reviewWeight({ stars: 4, likes: 10, ageDays: 19100 }, DEFAULTS);
  const ratio = recent / old;
  assert.ok(ratio > 1 && ratio < 1.05, `expected a near-constant weight, got ratio ${ratio}`);
});
