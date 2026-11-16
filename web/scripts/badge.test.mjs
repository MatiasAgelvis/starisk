import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildBadge } from '../src/lib/badge.js';

const scores = {
  'learn/scored': {
    title: 'Scored',
    starisk: 3.3333333,
    coursera: 4.8888888,
    reviews: 19,
    description: 'a long body nobody on a badge needs',
    top_review: { text: 'a review body', likes: 80, stars: 1 },
    instructors: [{ name: 'Someone' }],
  },
  'learn/low': { title: 'Low', starisk: 5, coursera: 3.6, reviews: 2, low_sample: true },
  'learn/unrated': { title: 'Unrated', starisk: 4.2, reviews: 7 },
  'learn/error': { error: 'no_reviews' },
  'learn/empty': {},
};

const groupings = {
  'specializations/one': {
    key: 'specializations/one',
    title: 'Program One',
    type: 'specialization',
    courses: ['learn/scored', 'learn/low', 'learn/error'],
  },
  'specializations/none': {
    key: 'specializations/none',
    title: 'Program None',
    type: 'specialization',
    courses: ['learn/error', 'learn/empty'],
  },
};

test('keeps only the records a badge can draw', () => {
  const { courses } = buildBadge(scores, groupings, null);

  assert.deepEqual(Object.keys(courses).sort(), [
    'learn/low',
    'learn/scored',
    'learn/unrated',
  ]);
});

test('carries five fields and no bodies', () => {
  const { courses } = buildBadge(scores, groupings, null);

  assert.deepEqual(courses['learn/scored'], { t: 'Scored', s: 3.33, c: 4.89, n: 19 });
  assert.equal('description' in courses['learn/scored'], false);
  assert.equal('top_review' in courses['learn/scored'], false);
  assert.equal('instructors' in courses['learn/scored'], false);
});

test('omits the headline rating when there is none, and flags low samples', () => {
  const { courses } = buildBadge(scores, groupings, null);

  assert.equal('c' in courses['learn/unrated'], false);
  assert.equal('l' in courses['learn/unrated'], false);
  assert.equal(courses['learn/low'].l, 1);
});

test('programs carry the weighted average and both counts', () => {
  const { programs } = buildBadge(scores, groupings, null);
  const program = programs['specializations/one'];

  // (3.3333333 * 19 + 5 * 2) / 21 = 3.49206…, rounded to two places.
  assert.equal(program.t, 'Program One');
  assert.equal(program.s, 3.49);
  assert.equal(program.n, 2);
  assert.equal(program.m, 3);
});

test('a program with nothing read is left out', () => {
  const { programs } = buildBadge(scores, groupings, null);

  assert.equal('specializations/none' in programs, false);
});

test('wanted is the ask list, deduplicated, and empty when there is no snapshot', () => {
  const withRows = buildBadge(scores, groupings, {
    rows: [{ key: 'learn/asked' }, { key: 'learn/asked' }, {}],
  });

  assert.deepEqual(withRows.wanted, ['learn/asked']);
  assert.deepEqual(buildBadge(scores, groupings, null).wanted, []);
  assert.deepEqual(buildBadge(scores, groupings, {}).wanted, []);
});

test('the payload survives a JSON round trip', () => {
  const badge = buildBadge(scores, groupings, { rows: [{ key: 'learn/asked' }] });

  assert.deepEqual(JSON.parse(JSON.stringify(badge)), badge);
});;
