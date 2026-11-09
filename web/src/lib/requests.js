// Turning a failed lookup into a demand signal: "this course isn't indexed —
// here is how to ask for it".
//
// The rules live here rather than in the island because the same check has to
// run twice: in the browser for instant feedback, and in the server function
// because the browser is not a security boundary. Nothing in this module touches
// the DOM, the network, or `crypto`, so it runs unchanged in Svelte, in a Worker,
// and under `node --test`.

export const MAX_QUERY = 120;

// A pasted link is not a name: the query string can carry a specialization,
// utm_* and friends, and only the slug inside it matters. The bound exists to
// keep the body small, not to judge the link.
export const MAX_INPUT = 1024;

// A bare Coursera slug, which is what a URL or a pasted path becomes.
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const MAX_SLUG = 80;

// Instructor profiles are either name-based (`andrewng`) or an opaque
// `~<number>` (79 of the 211 in the corpus).
const INSTRUCTOR_SLUG = /^~?[a-z0-9][a-z0-9-]*$/;

// The two program URL types. Both are crawlable units that expand into courses.
export const PROGRAM_TYPES = ['specializations', 'professional-certificates'];

// What a course *name* may contain. Anything outside this is a link, markup, or
// someone testing the input — none of which belong in a crawl queue. `#` and `+`
// are here for C# and C++, and the dashes for names that were typed, not pasted.
const NAME_CHARS = /^[\p{L}\p{N}\s'’‘&.,():+!?#–—“”\-]+$/u;

// "aaaaaaaa" is not a course.
const REPEATED = /(.)\1{5,}/;

// Profanity that is never also a course name. Deliberately short: `sex`, `rape`,
// `ass` and friends are real subjects, and a false positive on a real course is
// worse than a false negative I can see in the table and reject by hand.
const BLOCKED_TOKENS = [
  'fuck',
  'shit',
  'bitch',
  'cunt',
  'dick',
  'cock',
  'pussy',
  'bastard',
  'whore',
  'slut',
  'nigg',
  'fagg',
  'retard',
  'tranny',
];

// The subset unambiguous enough to match inside a run of letters, which is how
// leetspeak and hyphen-smuggled spellings survive tokenisation. `dick` is not
// here on purpose — Dickens is a course.
const BLOCKED_INSIDE = ['fuck', 'shit', 'bitch', 'cunt', 'fagg', 'nigg', 'tranny'];

export const REASON_MESSAGES = {
  empty: 'Type a course name or link first.',
  too_long: 'That is too long to be a course name or link.',
  too_short: 'That is too short to be a course name.',
  url: 'Only Coursera course links are accepted.',
  not_a_course: 'That link is not a course.',
  language: 'That does not look like a course name.',
  repetitive: 'That does not look like a course name.',
  characters: 'That does not look like a course name.',
};

/**
 * @typedef {{ ok: true, query: string, kind: 'slug' | 'name' | 'teacher' | 'program', key: string }
 *   | { ok: false, reason: keyof typeof REASON_MESSAGES }} Validation
 */

/**
 * @param {unknown} raw
 * @returns {Validation}
 */
export function validateQuery(raw) {
  const query = clean(raw);
  if (!query) return { ok: false, reason: 'empty' };
  if (query.length > MAX_INPUT) return { ok: false, reason: 'too_long' };

  const classified = classify(query);
  if (!classified.ok) return classified;

  // A link is stored as the key it produced, not as the URL it was pasted from:
  // `?specialization=…` and `utm_*` are not part of the request. A typed name is
  // already the thing a human needs to read.
  return {
    ...classified,
    query: classified.kind === 'name' ? query : classified.key,
  };
}

/**
 * @param {unknown} raw
 * @returns {string}
 */
function clean(raw) {
  return String(raw ?? '')
    .normalize('NFKC')
    // Zero-width and bidi characters are invisible in a table and are pure
    // smuggling material.
    .replace(/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u2064\ufeff]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * @param {string} text
 * @returns {{ ok: true, kind: 'slug' | 'name' | 'teacher' | 'program', key: string } | { ok: false, reason: string }}
 */
function classify(text) {
  const link = parseLink(text);
  if (link) return fromLink(link);

  // `learn/x` and `learn/x/` without a host, the same forms the lookup accepts.
  const path = text.match(
    /^\/?(learn|specializations|professional-certificates|instructor)\/([^/?#\s]+)\/?$/i,
  );
  if (path) return fromPath(path[1], path[2]);

  // A single token is a slug, matching `normalizeCourseKey`'s v1 rule; anything
  // with a space is a name someone typed. A bare slug that is actually a name
  // (`python`) still lands on the right course.
  if (!/\s/.test(text)) return slugOf(text);
  return nameOf(text);
}

/**
 * @param {string} text
 * @returns {string | null} the link, normalised to something `new URL` parses
 */
function parseLink(text) {
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(text)) return text;

  // No scheme: `coursera.org/learn/x` and `www.coursera.org/learn/x` still read
  // as links, and must be validated as such rather than as course names.
  if (/^(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)+\//i.test(text)) return `https://${text}`;
  return null;
}

/**
 * @param {string} link
 * @returns {{ ok: true, kind: 'slug' | 'name' | 'teacher' | 'program', key: string } | { ok: false, reason: string }}
 */
function fromLink(link) {
  let parsed;
  try {
    parsed = new URL(link);
  } catch {
    return { ok: false, reason: 'url' };
  }

  const parts = parsed.pathname.split('/').filter(Boolean);
  const [type, slug] = parts;

  // Only Coursera is a course source here. `www.coursera.com` is a typo or a
  // phish, and either way it is not something to crawl.
  const host = parsed.hostname.toLowerCase();
  if (host !== 'coursera.org' && !host.endsWith('.coursera.org')) {
    return { ok: false, reason: 'url' };
  }
  if (!type) return { ok: false, reason: 'not_a_course' };

  return fromPath(type, slug);
}

/**
 * @param {string} type
 * @param {string | undefined} slug
 */
function fromPath(type, slug) {
  const kind = type.toLowerCase();
  if (kind === 'instructor') return instructorOf(slug);
  if (PROGRAM_TYPES.includes(kind)) return programOf(kind, slug);
  if (kind !== 'learn') return { ok: false, reason: 'not_a_course' };
  return slugOf(slug);
}

/**
 * @param {string} kind
 * @param {string | undefined} value
 * @returns {{ ok: true, kind: 'program', key: string } | { ok: false, reason: string }}
 */
function programOf(kind, value) {
  if (!value) return { ok: false, reason: 'not_a_course' };

  let slug;
  try {
    slug = decodeURIComponent(value);
  } catch {
    return { ok: false, reason: 'not_a_course' };
  }

  slug = slug.toLowerCase().replace(/\/+$/, '');

  if (slug.length < 2) return { ok: false, reason: 'too_short' };
  if (slug.length > MAX_SLUG) return { ok: false, reason: 'too_long' };
  if (!SLUG.test(slug)) return { ok: false, reason: 'not_a_course' };
  if (REPEATED.test(slug.replace(/-/g, ''))) return { ok: false, reason: 'repetitive' };
  if (isProfane(slug)) return { ok: false, reason: 'language' };

  return { ok: true, kind: 'program', key: `${kind}/${slug}` };
}

/**
 * @param {string | undefined} value
 * @returns {{ ok: true, kind: 'slug', key: string } | { ok: false, reason: string }}
 */
function slugOf(value) {
  if (!value) return { ok: false, reason: 'not_a_course' };

  let slug;
  try {
    slug = decodeURIComponent(value);
  } catch {
    return { ok: false, reason: 'not_a_course' };
  }

  slug = slug.toLowerCase().replace(/\/+$/, '');

  if (slug.length < 2) return { ok: false, reason: 'too_short' };
  if (slug.length > MAX_SLUG) return { ok: false, reason: 'too_long' };
  if (!SLUG.test(slug)) return { ok: false, reason: 'not_a_course' };
  if (REPEATED.test(slug.replace(/-/g, ''))) return { ok: false, reason: 'repetitive' };
  if (isProfane(slug)) return { ok: false, reason: 'language' };

  return { ok: true, kind: 'slug', key: `learn/${slug}` };
}

/**
 * @param {string | undefined} value
 * @returns {{ ok: true, kind: 'teacher', key: string } | { ok: false, reason: string }}
 */
function instructorOf(value) {
  if (!value) return { ok: false, reason: 'not_a_course' };

  let slug;
  try {
    slug = decodeURIComponent(value);
  } catch {
    return { ok: false, reason: 'not_a_course' };
  }

  slug = slug.toLowerCase().replace(/\/+$/, '');

  if (slug.length < 2) return { ok: false, reason: 'too_short' };
  if (slug.length > MAX_SLUG) return { ok: false, reason: 'too_long' };
  if (!INSTRUCTOR_SLUG.test(slug)) return { ok: false, reason: 'not_a_course' };
  if (isProfane(slug)) return { ok: false, reason: 'language' };

  return { ok: true, kind: 'teacher', key: `instructor/${slug}` };
}

/**
 * @param {string} value
 * @returns {{ ok: true, kind: 'name', key: string } | { ok: false, reason: string }}
 */
function nameOf(value) {
  if (value.length < 3) return { ok: false, reason: 'too_short' };
  if (value.length > MAX_QUERY) return { ok: false, reason: 'too_long' };
  if (countLetters(value) < 2) return { ok: false, reason: 'too_short' };
  if (!NAME_CHARS.test(value)) return { ok: false, reason: 'characters' };
  if (REPEATED.test(value)) return { ok: false, reason: 'repetitive' };
  if (isProfane(value)) return { ok: false, reason: 'language' };

  return { ok: true, kind: 'name', key: `name/${slugify(value) || value.toLowerCase()}` };
}

const countLetters = (text) => (text.match(/\p{L}/gu) ?? []).length;

/**
 * ASCII for the key, so the table reads well. Scripts without ASCII letters fall
 * back to the name itself rather than collapsing every one of them to one key.
 */
function slugify(name) {
  return name
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_SLUG);
}

// Leetspeak is the cheapest bypass, so fold the obvious substitutions before
// both the token check and the inside-a-word check.
const fold = (text) =>
  text
    .toLowerCase()
    .replace(/[4@]/g, 'a')
    .replace(/3/g, 'e')
    .replace(/[1!|]/g, 'i')
    .replace(/0/g, 'o')
    .replace(/[5$]/g, 's')
    .replace(/7/g, 't');

/**
 * @param {string} text
 * @returns {boolean}
 */
function isProfane(text) {
  const folded = fold(text);
  const tokens = folded.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
  if (tokens.some((token) => BLOCKED_TOKENS.includes(token))) return true;

  const letters = folded.replace(/[^\p{L}]/gu, '');
  return BLOCKED_INSIDE.some((word) => letters.includes(word));
}
