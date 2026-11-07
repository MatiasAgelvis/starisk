// The server side of a course request: validate, rate limit, upsert.
//
// Kept apart from the HTTP adapter so the shape of the host does not leak into
// the logic. `web/api/course-request.js` is the Vercel Edge entry point; another
// host's function (Cloudflare Pages, for example) would be the same ten lines
// around `handleCourseRequest`.
//
// Turso is called over its HTTP API, so this module needs no driver, no Node
// built-ins, and no dependency at all. It also means it runs unchanged in an
// edge isolate and under `node --test`.

import { REASON_MESSAGES, validateQuery } from './requests.js';

const PER_HOUR = 6; // one visitor, one clock hour
const PER_DAY = 400; // the whole site, one UTC day
const BODY_LIMIT = 2048;

const json = (body, status = 200, headers = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
      ...headers,
    },
  });

const text = (value) => ({ type: 'text', value });

// Created on the first request in an isolate, then assumed. Keeping the DDL here
// means there is one source of truth for the schema — no separate .sql file to
// drift — and a fresh database works without a manual step.
const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS course_requests (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     key TEXT NOT NULL UNIQUE,
     query TEXT NOT NULL,
     kind TEXT NOT NULL,
     requests INTEGER NOT NULL DEFAULT 1,
     status TEXT NOT NULL DEFAULT 'new',
     first_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
     last_seen TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
   )`,
  `CREATE INDEX IF NOT EXISTS course_requests_queue
     ON course_requests (status, requests DESC)`,
  `CREATE TABLE IF NOT EXISTS request_hits (
     ip_hash TEXT NOT NULL,
     window TEXT NOT NULL,
     hits INTEGER NOT NULL DEFAULT 0,
     PRIMARY KEY (ip_hash, window)
   )`,
];

let schemaReady = false;

/**
 * One HTTP round trip for several statements. Turso answers in order, so a
 * result can be matched to the statement that produced it.
 *
 * @param {Record<string, string | undefined>} env
 * @param {{ sql: string, args?: unknown[] }[]} statements
 * @returns {Promise<Array<Array<{ type: string, value: unknown }[]>>>}
 */
async function turso(env, statements) {
  const base = String(env.TURSO_DATABASE_URL ?? '')
    .replace(/^libsql:\/\//, 'https://')
    .replace(/\/+$/, '');
  if (!base || !env.TURSO_AUTH_TOKEN) throw new Error('Turso is not configured');

  const response = await fetch(`${base}/v2/pipeline`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${env.TURSO_AUTH_TOKEN}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      requests: [
        ...statements.map((stmt) => ({ type: 'execute', stmt })),
        { type: 'close' },
      ],
    }),
  });

  if (!response.ok) throw new Error(`Turso responded ${response.status}`);
  const payload = await response.json();

  return statements.map((_, index) => {
    const result = payload.results?.[index];
    if (result?.type !== 'ok') {
      throw new Error(`Turso query failed: ${result?.error?.message ?? 'unknown'}`);
    }
    return result.response?.result?.rows ?? [];
  });
}

/** 64 bits is plenty to count a visitor without keeping the address. */
async function visitorHash(request, salt) {
  const ip =
    request.headers.get('cf-connecting-ip') ??
    request.headers.get('x-real-ip') ??
    request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ??
    'unknown';

  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(`${salt ?? ''}:${ip}`),
  );

  return [...new Uint8Array(digest).slice(0, 8)]
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('');
}

/**
 * @param {{ request: Request, env: Record<string, string | undefined> }} context
 * @returns {Promise<Response>}
 */
export async function handleCourseRequest({ request, env }) {
  // Same-origin only. A browser will not let another site read this response
  // without CORS headers, but a matching Origin check keeps scripted writes out
  // of the table as well.
  const origin = request.headers.get('origin');
  if (origin && origin !== new URL(request.url).origin) {
    return json({ ok: false, error: 'forbidden' }, 403);
  }

  const declared = Number(request.headers.get('content-length') ?? 0);
  if (declared > BODY_LIMIT) return json({ ok: false, error: 'too_large' }, 413);

  let body;
  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: 'invalid' }, 400);
  }

  const validation = validateQuery(body?.query);
  if (!validation.ok) {
    return json(
      {
        ok: false,
        error: 'invalid',
        reason: validation.reason,
        message: REASON_MESSAGES[validation.reason],
      },
      400,
    );
  }

  try {
    if (!schemaReady) {
      await turso(
        env,
        SCHEMA.map((sql) => ({ sql })),
      );
      schemaReady = true;
    }

    const hash = await visitorHash(request, env.REQUEST_SALT);
    const hour = new Date().toISOString().slice(0, 13);
    const day = hour.slice(0, 10);
    // A day and a bit of slack: enough to keep the hourly window accurate across
    // clock skew, little enough that the table stays tiny.
    const expire = new Date(Date.now() - 36 * 3600_000).toISOString().slice(0, 13);

    const [, hourly, daily] = await turso(env, [
      { sql: 'DELETE FROM request_hits WHERE window < ?', args: [text(expire)] },
      {
        sql: `INSERT INTO request_hits (ip_hash, window, hits) VALUES (?, ?, 1)
              ON CONFLICT(ip_hash, window) DO UPDATE SET hits = hits + 1
              RETURNING hits`,
        args: [text(hash), text(hour)],
      },
      {
        sql: `INSERT INTO request_hits (ip_hash, window, hits) VALUES (?, ?, 1)
              ON CONFLICT(ip_hash, window) DO UPDATE SET hits = hits + 1
              RETURNING hits`,
        args: [text('*'), text(day)],
      },
    ]);

    const hits = Number(hourly[0]?.[0]?.value ?? 0);
    const total = Number(daily[0]?.[0]?.value ?? 0);
    if (hits > PER_HOUR || total > PER_DAY) {
      return json({ ok: false, error: 'rate_limited' }, 429, { 'retry-after': '3600' });
    }

    const [rows] = await turso(env, [
      {
        sql: `INSERT INTO course_requests (key, query, kind) VALUES (?, ?, ?)
              ON CONFLICT(key) DO UPDATE SET
                requests = requests + 1,
                query = excluded.query,
                last_seen = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
              RETURNING requests`,
        args: [text(validation.key), text(validation.query), text(validation.kind)],
      },
    ]);

    return json({
      ok: true,
      key: validation.key,
      kind: validation.kind,
      count: Number(rows[0]?.[0]?.value ?? 1),
    });
  } catch (error) {
    // A misconfigured binding should look like downtime, not like a validation
    // problem: the visitor did nothing wrong and the name is worth retrying.
    console.error('course-request:', error);
    return json({ ok: false, error: 'unavailable' }, 503);
  }
}
