import assert from 'node:assert/strict';
import { test } from 'node:test';

import { handleCourseRequest } from '../src/lib/course-requests.js';

const env = {
  TURSO_DATABASE_URL: 'libsql://starisk-test.turso.io',
  TURSO_AUTH_TOKEN: 'test-token',
  REQUEST_SALT: 'test-salt',
};

const post = (body, headers = {}) =>
  new Request('https://starisk.pages.dev/api/course-request', {
    method: 'POST',
    headers: { 'content-type': 'application/json', ...headers },
    body: JSON.stringify(body),
  });

// A Turso that answers the three shapes this function uses. The rows are keyed
// by the SQL rather than by call order, so tests don't depend on whether the
// schema ran first in this isolate.
function stubTurso({ hits = 1, total = 1, count = 1 } = {}) {
  const original = globalThis.fetch;
  const seen = [];

  globalThis.fetch = async (_url, init) => {
    const { requests } = JSON.parse(init.body);

    const results = requests
      .filter((entry) => entry.type === 'execute')
      .map(({ stmt }) => {
        seen.push(stmt);

        let rows = [];
        if (stmt.sql.includes('RETURNING hits')) {
          const bucket = stmt.args?.[0]?.value === '*' ? total : hits;
          rows = [[{ type: 'integer', value: String(bucket) }]];
        } else if (stmt.sql.includes('RETURNING requests')) {
          rows = [[{ type: 'integer', value: String(count) }]];
        }

        return { type: 'ok', response: { type: 'execute', result: { rows } } };
      });

    return new Response(JSON.stringify({ results }));
  };

  return {
    seen,
    restore() {
      globalThis.fetch = original;
    },
  };
}

test('records a missed course and returns its demand count', async () => {
  const turso = stubTurso({ count: 3 });

  try {
    const response = await handleCourseRequest({
      request: post({ query: 'learn/machine-learning' }),
      env,
    });
    const body = await response.json();

    assert.equal(response.status, 200);
    assert.equal(body.ok, true);
    assert.equal(body.key, 'learn/machine-learning');
    assert.equal(body.count, 3);

    const upsert = turso.seen.find((stmt) => stmt.sql.includes('INSERT INTO course_requests'));
    assert.deepEqual(
      upsert.args.map((arg) => arg.value),
      ['learn/machine-learning', 'learn/machine-learning', 'slug'],
    );
  } finally {
    turso.restore();
  }
});

test('rejects a non-Coursera link without writing anything', async () => {
  const turso = stubTurso();

  try {
    const response = await handleCourseRequest({
      request: post({ query: 'https://www.coursera.com/learn/fuck-you' }),
      env,
    });
    const body = await response.json();

    assert.equal(response.status, 400);
    assert.equal(body.reason, 'url');
    assert.equal(turso.seen.length, 0);
  } finally {
    turso.restore();
  }
});

test('rejects profanity in a course slug', async () => {
  const response = await handleCourseRequest({ request: post({ query: 'learn/fuck-you' }), env });
  const body = await response.json();

  assert.equal(response.status, 400);
  assert.equal(body.reason, 'language');
});

test('refuses writes from another origin', async () => {
  const response = await handleCourseRequest({
    request: post({ query: 'learn/machine-learning' }, { origin: 'https://evil.example' }),
    env,
  });

  assert.equal(response.status, 403);
});

test('refuses bodies larger than a course name', async () => {
  const response = await handleCourseRequest({
    request: post({ query: 'x' }, { 'content-length': '9000' }),
    env,
  });

  assert.equal(response.status, 413);
});

test('rate limits one visitor per hour and the site per day', async () => {
  const hourly = stubTurso({ hits: 7 });
  try {
    const response = await handleCourseRequest({
      request: post({ query: 'learn/machine-learning' }),
      env,
    });
    assert.equal(response.status, 429);
    assert.equal(response.headers.get('retry-after'), '3600');
  } finally {
    hourly.restore();
  }

  const daily = stubTurso({ total: 401 });
  try {
    const response = await handleCourseRequest({
      request: post({ query: 'learn/machine-learning' }),
      env,
    });
    assert.equal(response.status, 429);
  } finally {
    daily.restore();
  }
});

test('a broken Turso is downtime, not a validation error', async () => {
  const originalFetch = globalThis.fetch;
  const originalError = console.error;
  globalThis.fetch = async () => new Response('nope', { status: 500 });
  console.error = () => {};

  try {
    const response = await handleCourseRequest({
      request: post({ query: 'learn/machine-learning' }),
      env,
    });
    const body = await response.json();

    assert.equal(response.status, 503);
    assert.equal(body.error, 'unavailable');
  } finally {
    globalThis.fetch = originalFetch;
    console.error = originalError;
  }
});
