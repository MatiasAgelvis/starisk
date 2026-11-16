// The bookmarklet's payload (IDEAS.md I1).
//
// `scores.json` is 3.3 MB on disk and 765 KB over the wire. That is the wrong
// shape for a badge that needs five fields per course and has to be parsed on a
// page someone else owns. This keeps only the records a badge can draw — a
// course with no Starisk score has nothing to say, so it is not here — and
// shortens the keys: 816 courses and 23 programs come to ~98 KB, 24 KB gzipped.
//
// Served at `/data/badge.json` by `pages/data/badge.json.ts`, the same pattern
// as `/data/scores.json`. Not a second copy of anything: both derive from the
// same build-time import.

import { buildGroupings } from './groupings.js';

/** Two decimals is more than any badge or gap renders, and less than the raw float. */
const round = (value) => Math.round(value * 100) / 100;

/**
 * @param {Record<string, any>} scores
 * @param {Record<string, any>} groupings
 * @param {{ rows?: { key?: string }[] } | null} [requests]
 * @returns {{
 *   courses: Record<string, { t: string, s: number, c?: number, n?: number, l?: 1 }>,
 *   programs: Record<string, { t: string, s: number, n: number, m: number }>,
 *   wanted: string[],
 * }}
 */
export function buildBadge(scores, groupings, requests) {
  const courses = {};

  for (const [key, record] of Object.entries(scores)) {
    if (typeof record?.starisk !== 'number') continue;

    /** @type {{ t: string, s: number, c?: number, n?: number, l?: 1 }} */
    const row = { t: record.title ?? key, s: round(record.starisk) };
    if (typeof record.coursera === 'number') row.c = round(record.coursera);
    if (typeof record.reviews === 'number') row.n = record.reviews;
    // Present only when true, the way `scores.json` already writes it.
    if (record.low_sample === true) row.l = 1;

    courses[key] = row;
  }

  const programs = {};

  for (const program of buildGroupings(groupings, scores)) {
    // The badge's program line is the average of the courses we read, so a
    // program with nothing read has no line to draw.
    if (program.scored === 0 || program.average == null) continue;

    programs[program.key] = {
      t: program.title,
      s: round(program.average),
      n: program.scored,
      m: program.total,
    };
  }

  const wanted = [
    ...new Set(
      (requests?.rows ?? [])
        .map((row) => row?.key)
        .filter((key) => typeof key === 'string' && key.length > 0),
    ),
  ];

  return { courses, programs, wanted };
}
