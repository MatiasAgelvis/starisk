// Type-ahead over the lookup payload.
//
// 553 scored courses and ~620 teachers is small enough to score on every
// keystroke: no index to build, no debounce, no dependency. The ranking is
// deliberately readable — exact beats prefix beats word-start beats substring —
// because a fuzzy score nobody can explain is hard to tune when the result a
// visitor expected does not show up.

/** @typedef {'course' | 'teacher'} Kind */

const MIN_QUERY = 2;
export const MAX_RESULTS = 6;

/** Lower-case, accent-free, punctuation collapsed to single spaces. */
export function normalize(text) {
  return String(text ?? '')
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, ' ')
    .trim();
}

/**
 * @param {Record<string, any>} scores the lookup payload
 * @param {Record<string, { name?: string, page?: string }>} teachers
 * @param {Record<string, any>} programs the program lookup payload
 */
export function buildSearchIndex(scores = {}, teachers = {}, programs = {}) {
  const courses = Object.entries(scores).map(([key, record]) => {
    const title = record.title ?? key;
    const slug = record.slug ?? key;
    const provider = record.provider ?? null;
    const normalized = normalize(title);

    return {
      kind: /** @type {const} */ ('course'),
      key,
      slug,
      href: `/${slug}`,
      title,
      provider,
      normalized,
      haystack: `${normalized} ${normalize(slug)} ${normalize(provider)}`,
      starisk: typeof record.starisk === 'number' ? record.starisk : null,
      coursera: typeof record.coursera === 'number' ? record.coursera : null,
      reviews: record.reviews ?? 0,
      noReviews: record.no_reviews === true,
    };
  });

  const people = Object.entries(teachers).map(([slug, person]) => {
    const title = person?.name ?? person?.page ?? slug;
    const normalized = normalize(title);

    return {
      kind: /** @type {const} */ ('teacher'),
      key: `instructor/${slug}`,
      slug,
      href: `/instructors/${person?.page ?? slug}`,
      title,
      provider: null,
      normalized,
      haystack: normalized,
      starisk: null,
      coursera: null,
      reviews: 0,
      noReviews: false,
    };
  });

  const programRows = Object.entries(programs).map(([key, program]) => {
    const title = program?.title ?? key;
    const provider = program?.provider ?? null;
    const normalized = normalize(title);

    return {
      kind: /** @type {const} */ ('program'),
      key,
      href: `/programs/${key}`,
      title,
      provider,
      normalized,
      haystack: `${normalized} ${normalize(key)} ${normalize(provider)}`,
      starisk: typeof program?.average === 'number' ? program.average : null,
      coursera: null,
      reviews: program?.reviews ?? 0,
      noReviews: false,
      label: program?.label ?? 'Program',
      scored: program?.scored ?? 0,
      total: program?.total ?? 0,
    };
  });

  return { courses, teachers: people, programs: programRows };
}

/**
 * @param {{ courses: any[], teachers: any[] }} index
 * @param {string} raw
 * @param {number} limit
 * @returns {any[]} best matches, most relevant first
 */
export function search(index, raw, limit = MAX_RESULTS) {
  const query = normalize(raw);
  if (query.length < MIN_QUERY) return [];

  const tokens = query.split(' ');
  const found = [];

  for (const item of [...index.courses, ...index.teachers, ...(index.programs ?? [])]) {
    const points = score(item, query, tokens);
    if (points > 0) found.push({ item, points });
  }

  return found
    .sort(
      (a, b) =>
        b.points - a.points ||
        b.item.reviews - a.item.reviews ||
        a.item.title.localeCompare(b.item.title),
    )
    .slice(0, limit)
    .map(({ item }) => item);
}

function score(item, query, tokens) {
  if (!tokens.every((token) => item.haystack.includes(token))) return 0;

  let points = 20; // every token is in the title or the slug
  if (item.normalized === query) points += 80;
  else if (item.normalized.startsWith(query)) points += 60;
  else if (item.normalized.split(' ').some((word) => word.startsWith(query))) points += 40;
  else if (item.normalized.includes(query)) points += 20;

  // Among equally textual matches, the shorter title is the more specific one:
  // `AI in Healthcare` should beat `Evaluations of AI Applications in Healthcare`.
  const extra = Math.max(0, item.normalized.split(' ').length - tokens.length);
  points -= Math.min(extra, 10) * 0.5;

  // Courses are the atomic thing; a program is a bundle. Prefer courses in a
  // tie, and teachers behind both.
  if (item.kind === 'teacher') points -= 5;
  else if (item.kind === 'program') points -= 3;

  return points;
}
