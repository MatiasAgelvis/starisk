// The `/wanted` view of the ask list.
//
// `requests.json` is owned by the pipeline and carries only what Turso knows:
// key, query, ask count, timestamps and when the ask became crawl work. Whether
// it is still waiting or has been scored is derived from `scores.json` /
// `groupings.json` at build time.

import { buildGroupings } from './groupings.js';

const LABELS = {
  course: 'Course',
  specialization: 'Specialization',
  'professional-certificate': 'Professional Certificate',
};

// The public list is for courses and programs. Instructor asks add courses by a
// different path and stay in the inbox/digest rather than becoming a permanent
// "waiting" row here.
const PUBLIC_TYPES = new Set(Object.keys(LABELS));

/** A fragment-safe id: `learn/foo` -> `learn-foo`. */
export function requestAnchor(key) {
  return String(key)
    .replace(/[^a-z0-9]+/gi, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase();
}

function readableQuery(row) {
  const query = String(row.query ?? '').trim();
  if (!query || /^https?:\/\//i.test(query)) return row.key;
  return query;
}

export function buildWanted(snapshot, scores, groupings) {
  const programs = new Map(
    buildGroupings(groupings, scores).map((program) => [program.key, program]),
  );

  const rows = (snapshot?.rows ?? [])
    .filter((row) => PUBLIC_TYPES.has(row.type))
    .map((row) => {
      const isProgram = row.type === 'specialization' || row.type === 'professional-certificate';
      const program = isProgram ? (programs.get(row.key) ?? null) : null;
      const record = row.type === 'course' ? (scores[row.key] ?? null) : null;
      const scored =
        row.type === 'course'
          ? Boolean(record && (typeof record.starisk === 'number' || record.no_reviews === true))
          : Boolean(program && program.scored > 0);

      const title = program?.title || record?.title || row.title || readableQuery(row);
      const showKey = title !== row.key;

      let href = `https://www.coursera.org/${row.key}`;
      let external = true;
      if (row.type === 'course' && record) {
        href = `/${record.slug ?? row.key}`;
        external = false;
      } else if (program) {
        href = `/programs/${row.key}`;
        external = false;
      }

      return {
        ...row,
        label: LABELS[row.type],
        title,
        href,
        external,
        showKey,
        anchor: requestAnchor(row.key),
        record,
        program,
        scored,
        scoredAt: record?.scrapedAt ?? null,
        summary: summaryOf(row, record, program),
      };
    });

  return {
    waiting: rows
      .filter((row) => !row.scored)
      .sort((a, b) => b.requests - a.requests || String(a.key).localeCompare(String(b.key))),
    fulfilled: rows
      .filter((row) => row.scored)
      .sort((a, b) => String(b.added_at ?? '').localeCompare(String(a.added_at ?? ''))),
  };
}

/**
 * The newest scores in the corpus, from the tail of `scores.json`.
 *
 * The file is append-only: the crawl adds keys at the end and never reorders, so
 * the tail is arrival order. A rescored course keeps its position, which is what
 * we want here — this is "what arrived", not "what changed last".
 *
 * Without this the page reads as dead whenever nobody is asking, because
 * "Recently fulfilled" derives from the request queue.
 */
export function buildRecent(scores, limit = 10) {
  const rated = Object.entries(scores).filter(
    ([, record]) => typeof record?.starisk === 'number',
  );

  return rated
    .slice(-limit)
    .reverse()
    .map(([key, record]) => {
      const starisk = record.starisk.toFixed(1);
      return {
        key,
        title: record.title ?? key,
        href: `/${record.slug ?? key}`,
        provider: record.provider ?? null,
        summary:
          typeof record.coursera === 'number'
            ? `Coursera ${record.coursera.toFixed(1)} → Starisk ${starisk}`
            : `Starisk ${starisk}`,
        scrapedAt: record.scrapedAt ?? null,
      };
    });
}

/**
 * The last run, as the data can prove it.
 *
 * There is no run log in git, so "last crawl" is the newest `scrapedAt` and
 * "read in that run" is how many records carry that date. That counts new and
 * rescored courses together — the label says `read`, not `added`, because the
 * corpus cannot tell the two apart after the fact.
 *
 * `queued` is what still has no record: sources minus tombstones. It is the only
 * number here that comes from the crawl list rather than the corpus.
 */
export function buildCrawlStats(scores, sources = [], retired = {}) {
  const records = Object.entries(scores);
  const timed = records.filter(([, record]) => record?.scrapedAt);
  const lastRead = timed.reduce(
    (latest, [, record]) => (record.scrapedAt > latest ? record.scrapedAt : latest),
    '',
  );
  const lastDay = lastRead.slice(0, 10);
  const readInRun = lastDay
    ? timed.filter(([, record]) => String(record.scrapedAt).slice(0, 10) === lastDay).length
    : 0;

  return {
    lastRead,
    lastDay,
    readInRun,
    read: records.length,
    scored: records.filter(([, record]) => typeof record?.starisk === 'number').length,
    queued: sources.filter((key) => !scores[key] && !retired[key]).length,
    listed: sources.length,
  };
}

function summaryOf(row, record, program) {
  if (row.type === 'course') {
    if (!record) return 'Waiting for the crawl';
    if (record.no_reviews) return 'No written reviews yet';
    const coursera = typeof record.coursera === 'number' ? record.coursera.toFixed(1) : '—';
    const starisk = typeof record.starisk === 'number' ? record.starisk.toFixed(1) : '—';
    return `Coursera ${coursera} → Starisk ${starisk}`;
  }

  if (program && program.scored > 0) {
    const average = program.average == null ? '—' : program.average.toFixed(1);
    return `Average ${average} · ${program.scored} of ${program.total} courses scored`;
  }

  return 'Waiting for the crawl';
}
