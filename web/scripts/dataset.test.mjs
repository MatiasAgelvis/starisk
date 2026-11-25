import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildDataset } from '../src/lib/dataset.js';

const scores = {
  'learn/a': {
    title: 'Course A',
    provider: 'Provider',
    categories: ['Business'],
    level: 'Beginner',
    coursera: 4.5,
    ratings_total: 10,
    rating_counts: { 1: 1, 5: 9 },
    starisk: 3.9,
    spread: 1.2,
    reviews: 20,
    reviews_total: 5,
    review_counts: { 5: 20 },
    low_sample: true,
    scrapedAt: '2026-11-25T00:00:00Z',
    instructors: [
      {
        name: 'Ada',
        url: 'https://www.coursera.org/instructor/ada',
        photo: 'https://cdn.example/ada.jpg',
      },
    ],
    // Third-party tier: must never reach the dataset.
    top_review: { text: 'SECRET REVIEW' },
    description: 'SECRET MARKETING',
    image: '/logos/tile/provider.png',
  },
  'learn/empty': { title: 'Course E', no_reviews: true },
};

const groupings = {
  'specializations/s': {
    title: 'Program S',
    type: 'specialization',
    provider: 'Provider',
    url: 'https://www.coursera.org/specializations/s',
    courses: ['learn/a', 'learn/empty'],
    coursera: 4.7,
    ratings_total: 100,
    rating_counts: { 5: 100 },
  },
};

const dataset = buildDataset(scores, groupings, '2026-11-25T12:00:00Z');
const serialized = JSON.stringify(dataset);

test('carries the measurements and the identifiers', () => {
  const course = dataset.courses[0];

  assert.equal(course.key, 'learn/a');
  assert.equal(course.coursera, 4.5);
  assert.equal(course.starisk, 3.9);
  assert.equal(course.reviewsRead, 20);
  assert.deepEqual(course.ratingCounts, { 1: 1, 5: 9 });
  assert.equal(course.lowSample, true);
  assert.deepEqual(course.instructors, [
    { name: 'Ada', profile: 'https://www.coursera.org/instructor/ada' },
  ]);
});

test('never includes third-party prose, marks or photos', () => {
  assert.ok(!serialized.includes('SECRET REVIEW'));
  assert.ok(!serialized.includes('SECRET MARKETING'));
  assert.ok(!serialized.includes('cdn.example'));
  assert.ok(!serialized.includes('/logos/'));
  assert.deepEqual(Object.keys(dataset.courses[0]).sort(), [
    'categories',
    'coursera',
    'instructors',
    'key',
    'level',
    'lowSample',
    'provider',
    'ratingCounts',
    'ratings',
    'reviewCounts',
    'reviewsRead',
    'reviewsTotal',
    'scrapedAt',
    'spread',
    'starisk',
    'title',
  ]);
});

test('a course with no written reviews says so and has no score', () => {
  const course = dataset.courses.find((row) => row.key === 'learn/empty');

  assert.equal(course.noReviews, true);
  assert.equal('starisk' in course, false);
});

test('programs carry membership and a derived average', () => {
  const [program] = dataset.programs;

  assert.deepEqual(program.courses, ['learn/a', 'learn/empty']);
  assert.equal(program.coursera, 4.7);
  assert.equal(program.scored, 1);
  assert.equal(program.total, 2);
  assert.equal(program.average, 3.9);
});

test('counts and licence describe the file', () => {
  assert.equal(dataset.schema, 1);
  assert.equal(dataset.generatedAt, '2026-11-25T12:00:00Z');
  assert.equal(dataset.license.data, 'CC BY 4.0');
  assert.ok(dataset.license.attribution.includes('starisk.matiasagelvis.com'));
  assert.deepEqual(dataset.counts, {
    courses: 2,
    scored: 1,
    noReviews: 1,
    reviewsRead: 20,
    programs: 1,
  });
});
