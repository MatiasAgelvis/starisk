import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildLookup, normalizeCourseKey } from '../src/lib/lookup.js';

test('keeps scored courses and explicit empty states, drops failed scrapes', () => {
  const lookup = buildLookup({
    'learn/scored': {
      title: 'Scored',
      slug: 'learn/scored',
      provider: 'IBM',
      starisk: 3.2,
      coursera: 4.8,
      reviews: 20,
    },
    'learn/empty': {
      title: 'Empty',
      slug: 'learn/empty',
      no_reviews: true,
      reviews: 0,
      ratings_total: 2,
    },
    'learn/broken': { error: 'no reviews parsed (markup changed?)' },
  });

  assert.deepEqual(Object.keys(lookup), ['learn/scored', 'learn/empty']);
  assert.equal(lookup['learn/scored'].starisk, 3.2);
  assert.equal(lookup['learn/scored'].provider, 'IBM');
  assert.equal(lookup['learn/empty'].no_reviews, true);
  assert.equal(lookup['learn/empty'].ratings_total, 2);
  assert.equal(lookup['learn/broken'], undefined);
});

test('normalizes URLs, paths, and bare slugs', () => {
  assert.equal(
    normalizeCourseKey('https://www.coursera.org/learn/machine-learning/reviews'),
    'learn/machine-learning',
  );
  assert.equal(normalizeCourseKey('/learn/machine-learning/'), 'learn/machine-learning');
  assert.equal(normalizeCourseKey('learn/machine-learning'), 'learn/machine-learning');
  assert.equal(normalizeCourseKey('machine-learning'), 'learn/machine-learning');
  assert.equal(
    normalizeCourseKey('specializations/deep-learning'),
    'specializations/deep-learning',
  );
  assert.equal(normalizeCourseKey('  '), '');
});

test('slugs are case-insensitive, like Coursera\'s', () => {
  assert.equal(
    normalizeCourseKey('https://www.coursera.org/learn/Machine-Learning'),
    'learn/machine-learning',
  );
  assert.equal(normalizeCourseKey('Learn/Machine-Learning'), 'learn/machine-learning');
});


test('falls back to the record key when slug is absent', () => {
  const lookup = buildLookup({ 'learn/x': { starisk: 4.0 } });

  assert.equal(lookup['learn/x'].slug, 'learn/x');
});

test('a no_reviews record has no score to render', () => {
  const lookup = buildLookup({ 'learn/x': { no_reviews: true } });

  assert.equal(lookup['learn/x'].starisk, undefined);
});
