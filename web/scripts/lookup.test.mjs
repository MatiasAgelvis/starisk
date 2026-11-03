import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildLookup } from '../src/lib/lookup.js';

test('keeps scored courses and explicit empty states, drops failed scrapes', () => {
  const lookup = buildLookup({
    'learn/scored': {
      title: 'Scored',
      slug: 'learn/scored',
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
  assert.equal(lookup['learn/empty'].no_reviews, true);
  assert.equal(lookup['learn/empty'].ratings_total, 2);
  assert.equal(lookup['learn/broken'], undefined);
});

test('falls back to the record key when slug is absent', () => {
  const lookup = buildLookup({ 'learn/x': { starisk: 4.0 } });

  assert.equal(lookup['learn/x'].slug, 'learn/x');
});

test('a no_reviews record has no score to render', () => {
  const lookup = buildLookup({ 'learn/x': { no_reviews: true } });

  assert.equal(lookup['learn/x'].starisk, undefined);
});
