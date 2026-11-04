import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ariaSortFor, compareValues, paginate, toggleSort } from '../src/lib/table.js';

test('nulls sort last in both directions', () => {
  assert.ok(compareValues(null, 3, 'asc') > 0);
  assert.ok(compareValues(null, 3, 'desc') > 0);
  assert.equal(compareValues(null, null), 0);
});

test('numbers and strings respect direction', () => {
  assert.ok(compareValues(2, 1, 'desc') < 0);
  assert.ok(compareValues(2, 1, 'asc') > 0);
  assert.ok(compareValues('a', 'b', 'asc') < 0);
  assert.ok(compareValues('a', 'b', 'desc') > 0);
});

test('toggleSort flips direction and starts text columns ascending', () => {
  assert.deepEqual(toggleSort('title', 'title', 'desc', 'title'), {
    key: 'title',
    direction: 'asc',
  });
  assert.deepEqual(toggleSort('starisk', 'title', 'asc', 'title'), {
    key: 'starisk',
    direction: 'desc',
  });
  assert.deepEqual(toggleSort('name', 'other', 'desc', 'name'), {
    key: 'name',
    direction: 'asc',
  });
});

test('ariaSortFor reports only the active column', () => {
  assert.equal(ariaSortFor('title', 'title', 'asc'), 'ascending');
  assert.equal(ariaSortFor('title', 'title', 'desc'), 'descending');
  assert.equal(ariaSortFor('title', 'other', 'asc'), 'none');
});

test('paginate clamps the page and reports the window', () => {
  const rows = [1, 2, 3, 4, 5];

  assert.deepEqual(paginate(rows, 2, 2), {
    pageCount: 3,
    current: 2,
    visible: [3, 4],
    first: 3,
    last: 4,
  });
  assert.deepEqual(paginate(rows, 99, 2), {
    pageCount: 3,
    current: 3,
    visible: [5],
    first: 5,
    last: 5,
  });
  assert.deepEqual(paginate([], 1, 25), {
    pageCount: 1,
    current: 1,
    visible: [],
    first: 0,
    last: 0,
  });
});
