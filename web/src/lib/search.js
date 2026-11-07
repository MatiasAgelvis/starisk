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
 */
export function buildSearchIndex(scores = {}, teachers = {}) {
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

  return { courses, teachers: people };
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

  for (const item of [...index.courses, ...index.teachers]) {
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

  // A course title should win a tie: visitors are here for courses, and a
  // teacher's page is a second click anyway.
  if (item.kind === 'teacher') points -= 5;

  return points;
}
