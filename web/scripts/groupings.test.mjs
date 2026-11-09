import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildGroupings, buildProgramLookup, typeLabel } from '../src/lib/groupings.js';

const groupings = {
  'specializations/a': {
    key: 'specializations/a',
    type: 'specialization',
    title: 'Program A',
    provider: 'Test U',
    courses: ['learn/one', 'learn/two', 'learn/missing'],
  },
  'professional-certificates/b': {
    key: 'professional-certificates/b',
    type: 'professional-certificate',
    title: 'Program B',
    courses: ['learn/three'],
  },
};

const scores = {
  'learn/one': { starisk: 4.0, reviews: 10, title: 'One' },
  'learn/two': { starisk: 2.0, reviews: 30, title: 'Two' },
  'learn/three': { starisk: 5.0, reviews: 0, title: 'Three' },
  'specializations/a': { starisk: 3.5 },
};

test('the lookup payload keeps only what the island draws', () => {
  const lookup = buildProgramLookup(groupings, scores);
  const program = lookup['specializations/a'];

  assert.equal(program.title, 'Program A');
  assert.equal(program.label, 'Specialization');
  assert.equal(program.provider, 'Test U');
  assert.equal(program.average, 2.5);
  assert.equal(program.scored, 2);
  assert.equal(program.total, 3);
  assert.equal(program.reviews, 40);
});

test('a program with no scores still appears in the lookup', () => {
  const lookup = buildProgramLookup(
    {
      'professional-certificates/empty': {
        key: 'professional-certificates/empty',
        type: 'professional-certificate',
        title: 'Empty Program',
        courses: ['learn/missing'],
      },
    },
    {},
  );

  assert.equal(lookup['professional-certificates/empty'].average, null);
  assert.equal(lookup['professional-certificates/empty'].scored, 0);
  assert.equal(lookup['professional-certificates/empty'].total, 1);
});

test('weights the average by reviews read', () => {
  const program = buildGroupings(groupings, scores).find(
    (row) => row.key === 'specializations/a',
  );

  // (4*10 + 2*30) / 40 = 2.5, not the plain mean of 3.0.
  assert.equal(program.key, 'specializations/a');
  assert.equal(program.average, 2.5);
  assert.equal(program.low, 2.0);
  assert.equal(program.high, 4.0);
  assert.equal(program.scored, 2);
  assert.equal(program.total, 3);
  assert.equal(program.complete, false);
  assert.equal(program.reviews, 40);
  assert.equal(program.programRating, 3.5);
});

test('falls back to the plain mean when no course has reviews', () => {
  const [program] = buildGroupings(groupings, scores).filter(
    (row) => row.key === 'professional-certificates/b',
  );

  assert.equal(program.average, 5.0);
  assert.equal(program.scored, 1);
  assert.equal(program.complete, true);
  assert.equal(program.programRating, null);
});

test('keeps unscored and missing courses in the list', () => {
  const program = buildGroupings(groupings, scores).find(
    (row) => row.key === 'specializations/a',
  );
  const keys = program.courses.map((course) => course.key);

  assert.deepEqual(keys, ['learn/one', 'learn/two', 'learn/missing']);
  assert.equal(program.courses[2].starisk, undefined);
});

test('sorts scored programs first and labels both program types', () => {
  const programs = buildGroupings(groupings, scores);

  assert.deepEqual(
    programs.map((program) => program.key),
    ['professional-certificates/b', 'specializations/a'],
  );
  assert.equal(typeLabel('specialization'), 'Specialization');
  assert.equal(typeLabel('professional-certificate'), 'Professional Certificate');
});

test('a program with no scored courses has no average', () => {
  const [program] = buildGroupings(
    { 'specializations/empty': { title: 'Empty', courses: ['learn/missing'] } },
    {},
  );

  assert.equal(program.average, null);
  assert.equal(program.scored, 0);
  assert.equal(program.total, 1);
  assert.equal(program.complete, false);
});
