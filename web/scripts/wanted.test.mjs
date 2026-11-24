import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildCrawlStats, buildRecent, buildWanted, requestAnchor } from '../src/lib/wanted.js';

const scores = {
  'learn/scored': {
    title: 'Scored Course',
    slug: 'learn/scored',
    coursera: 4.8,
    starisk: 3.0,
    reviews: 20,
    scrapedAt: '2026-01-02T10:00:00Z',
  },
  'learn/empty': { title: 'Empty Course', slug: 'learn/empty', no_reviews: true },
};

const groupings = {
  'specializations/a': {
    key: 'specializations/a',
    type: 'specialization',
    title: 'Program A',
    courses: ['learn/scored', 'learn/empty'],
  },
  'specializations/empty': {
    key: 'specializations/empty',
    type: 'specialization',
    title: 'Empty Program',
    courses: ['learn/missing'],
  },
};

const row = (key, type, extra = {}) => ({
  key,
  type,
  query: key,
  requests: 1,
  first_seen: '2026-01-01T00:00:00Z',
  last_seen: '2026-01-01T00:00:00Z',
  added_at: '2026-01-02T00:00:00Z',
  ...extra,
});

const snapshot = {
  generatedAt: '2026-01-03T00:00:00Z',
  rows: [
    row('learn/pending', 'course', { query: 'A Requested Course', requests: 2 }),
    row('learn/scored', 'course', { added_at: '2026-01-02T10:00:00Z' }),
    row('learn/empty', 'course', { added_at: '2026-01-02T09:00:00Z' }),
    row('specializations/a', 'specialization', { requests: 3 }),
    row('specializations/empty', 'specialization', { requests: 2 }),
    row('specializations/waiting', 'specialization', { query: 'Waiting Program' }),
    row('instructor/~123', 'instructor'),
  ],
};

const { waiting, fulfilled } = buildWanted(snapshot, scores, groupings);
const byKey = (rows, key) => rows.find((item) => item.key === key);

test('derives waiting and fulfilled from the scores, not a status column', () => {
  assert.deepEqual(
    waiting.map((item) => item.key),
    ['learn/pending', 'specializations/empty', 'specializations/waiting'],
  );
  assert.deepEqual(
    fulfilled.map((item) => item.key),
    ['learn/scored', 'learn/empty', 'specializations/a'],
  );
});

test('a waiting course uses the title captured by the probe', () => {
  const item = buildWanted(
    {
      generatedAt: null,
      rows: [row('learn/captured', 'course', { title: 'Captured Course', query: 'https://example.test' })],
    },
    {},
    {},
  ).waiting[0];

  assert.equal(item.title, 'Captured Course');
  assert.equal(item.showKey, true);
});

test('a waiting course shows what was asked and points at Coursera', () => {
  const item = byKey(waiting, 'learn/pending');

  assert.equal(item.title, 'A Requested Course');
  assert.equal(item.showKey, true);
  assert.equal(item.href, 'https://www.coursera.org/learn/pending');
  assert.equal(item.external, true);
  assert.equal(item.summary, 'Waiting for the crawl');
});

test('a scored course joins its score and links internally', () => {
  const item = byKey(fulfilled, 'learn/scored');

  assert.equal(item.title, 'Scored Course');
  assert.equal(item.href, '/learn/scored');
  assert.equal(item.external, false);
  assert.equal(item.scoredAt, '2026-01-02T10:00:00Z');
  assert.equal(item.summary, 'Coursera 4.8 → Starisk 3.0');
});

test('a course with no reviews says so instead of inventing a score', () => {
  assert.equal(byKey(fulfilled, 'learn/empty').summary, 'No written reviews yet');
});

test('a program joins the grouping and links to its page', () => {
  const item = byKey(fulfilled, 'specializations/a');

  assert.equal(item.title, 'Program A');
  assert.equal(item.label, 'Specialization');
  assert.equal(item.href, '/programs/specializations/a');
  assert.equal(item.external, false);
  assert.equal(item.summary, 'Average 3.0 · 1 of 2 courses scored');
});

test('a program with no scored courses stays waiting', () => {
  const item = byKey(waiting, 'specializations/empty');

  assert.equal(item.title, 'Empty Program');
  assert.equal(item.scored, false);
  assert.equal(item.summary, 'Waiting for the crawl');
});

test('a program without a grouping is still waiting', () => {
  const item = byKey(waiting, 'specializations/waiting');

  assert.equal(item.title, 'Waiting Program');
  assert.equal(item.showKey, true);
  assert.equal(item.href, 'https://www.coursera.org/specializations/waiting');
  assert.equal(item.external, true);
  assert.equal(item.summary, 'Waiting for the crawl');
});

test('a slug-only ask does not repeat its key as the title', () => {
  const slugOnly = buildWanted(
    { generatedAt: null, rows: [row('learn/slug-only', 'course')] },
    {},
    {},
  ).waiting[0];

  assert.equal(slugOnly.title, 'learn/slug-only');
  assert.equal(slugOnly.showKey, false);
});

test('instructor requests stay out of the public wanted list', () => {
  assert.equal(byKey([...waiting, ...fulfilled], 'instructor/~123'), undefined);
});

test('anchors are fragment-safe', () => {
  assert.equal(requestAnchor('learn/supervised-machine-learning'), 'learn-supervised-machine-learning');
  assert.equal(requestAnchor('instructor/~118561318'), 'instructor-118561318');
});

test('an empty snapshot is an empty page, not a crash', () => {
  assert.deepEqual(buildWanted({ generatedAt: null, rows: [] }, {}, {}), {
    waiting: [],
    fulfilled: [],
  });
});

test('the newest scores come from the tail, newest first', () => {
  const corpus = {
    'learn/first': { title: 'First', starisk: 4.0, coursera: 4.5, scrapedAt: '2026-01-01' },
    'learn/empty': { title: 'Empty', no_reviews: true },
    'learn/last': { title: 'Last', starisk: 3.0, coursera: 3.4, scrapedAt: '2026-02-01' },
  };

  const recent = buildRecent(corpus, 2);

  assert.deepEqual(
    recent.map((entry) => entry.title),
    ['Last', 'First'],
  );
  assert.equal(recent[0].href, '/learn/last');
  assert.equal(recent[0].summary, 'Coursera 3.4 → Starisk 3.0');
  assert.equal(recent[0].scrapedAt, '2026-02-01');
});

test('a missing Coursera number does not break the line', () => {
  const [entry] = buildRecent({ 'learn/solo': { title: 'Solo', starisk: 2.5 } });

  assert.equal(entry.summary, 'Starisk 2.5');
});

test('reads the crawl dashboard from the stats file', () => {
  const stats = buildCrawlStats({
    at: '2026-11-24T11:21:56+00:00',
    mode: 'live',
    added: 120,
    rescored: 0,
    records: 1469,
    scored: 1146,
    queued: 84,
  });

  assert.equal(stats.lastRead, '2026-11-24T11:21:56+00:00');
  assert.equal(stats.added, 120);
  assert.equal(stats.rescored, 0);
  assert.equal(stats.read, 1469);
  assert.equal(stats.scored, 1146);
  assert.equal(stats.queued, 84);
});

test('a missing stats file does not break the page', () => {
  const stats = buildCrawlStats({});

  assert.equal(stats.lastRead, null);
  assert.equal(stats.added, null);
  assert.equal(stats.queued, null);
});
