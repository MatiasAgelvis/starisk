'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { extractCourseraScore, extractReviews } = require('./adapter.js');

const FIXTURE = path.join(__dirname, '..', 'test', 'pages', 'coursera', 'review.html');
const html = fs.readFileSync(FIXTURE, 'utf8');

test('reads Coursera\'s aggregate rating from the page', () => {
  assert.equal(extractCourseraScore(html), 4.0);
});

test('extracts every review on the page', () => {
  assert.equal(extractReviews(html).length, 25);
});

test('parses the most-liked review correctly', () => {
  const first = extractReviews(html)[0];
  // The top review is a 1-star takedown with 102 "helpful" votes.
  assert.equal(first.stars, 1);
  assert.equal(first.likes, 102);
  assert.ok(first.ageDays > 18000, `expected a 2019 date, got ${first.ageDays}`);
});

test('every review has a star value between 0 and 5', () => {
  for (const review of extractReviews(html)) {
    assert.ok(review.stars >= 0 && review.stars <= 5, `bad stars: ${review.stars}`);
    assert.ok(Number.isFinite(review.ageDays), 'expected a parsed date');
  }
});
