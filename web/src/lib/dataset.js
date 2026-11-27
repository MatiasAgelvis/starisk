// The published dataset (IDEAS.md I6).
//
// Built from the same imports as every page, and deliberately narrower than
// `scores.json`: LICENSING.md puts reviewed prose, course descriptions and
// provider marks in the third-party tier, so none of it is here. What remains is
// measurements and identifiers — what someone would cite, join or plot.
//
// Courses are an array, not a map keyed by slug, so a data tool can read this
// without knowing the site's key format.

import { buildGroupings } from './groupings.js';

const SITE = 'https://starisk.matiasagelvis.com';
const SOURCE = 'https://github.com/MatiasAgelvis/starisk';
const COURSERA = 'https://www.coursera.org';

/** Two decimals is more than any page renders, and less than the raw float. */
const round = (value) => Math.round(value * 100) / 100;

function courseRow(key, record) {
  const row = {
    key,
    type: record.type ?? (key.startsWith('projects/') ? 'project' : 'course'),
    title: record.title ?? key,
    provider: record.provider ?? null,
  };

  if (record.categories?.length) row.categories = record.categories;
  if (record.level) row.level = record.level;

  // Coursera's own population: every star rating, and its shape.
  if (typeof record.coursera === 'number') row.coursera = record.coursera;
  if (typeof record.ratings_total === 'number') row.ratings = record.ratings_total;
  if (record.rating_counts) row.ratingCounts = record.rating_counts;

  // Ours: the written reviews we read, and what they came to.
  if (typeof record.starisk === 'number') row.starisk = record.starisk;
  if (typeof record.spread === 'number') row.spread = record.spread;
  if (typeof record.reviews === 'number') row.reviewsRead = record.reviews;
  if (typeof record.reviews_total === 'number') row.reviewsTotal = record.reviews_total;
  if (record.review_counts) row.reviewCounts = record.review_counts;
  if (record.low_sample === true) row.lowSample = true;
  if (record.no_reviews === true) row.noReviews = true;
  if (record.scrapedAt) row.scrapedAt = record.scrapedAt;

  const instructors = (record.instructors ?? [])
    .filter((person) => person?.name)
    .map((person) => {
      const profile =
        person.url ?? (person.page ? `${COURSERA}/instructor/${person.page}` : null);
      return profile ? { name: person.name, profile } : { name: person.name };
    });
  if (instructors.length) row.instructors = instructors;

  return row;
}

function programRow(program) {
  const row = {
    key: program.key,
    type: program.type,
    title: program.title,
    provider: program.provider ?? null,
    url: program.url,
    courses: program.courses.map((course) => course.key),
  };

  if (typeof program.coursera === 'number') row.coursera = program.coursera;
  if (typeof program.ratings === 'number') row.ratings = program.ratings;
  if (program.ratingCounts) row.ratingCounts = program.ratingCounts;
  if (typeof program.average === 'number') row.average = round(program.average);
  row.scored = program.scored;
  row.total = program.total;

  return row;
}

/**
 * @param {Record<string, any>} scores
 * @param {Record<string, any>} groupings
 * @param {string} generatedAt ISO timestamp, passed in so a build is reproducible
 */
export function buildDataset(scores, groupings, generatedAt) {
  const courses = Object.entries(scores).map(([key, record]) => courseRow(key, record));
  const programs = buildGroupings(groupings, scores).map(programRow);

  // The corpus's "manufactured on" date: the newest review read, not the build
  // time. `generatedAt` changes every build; this only moves when the crawl does.
  const asOf =
    courses
      .map((course) => course.scrapedAt)
      .filter(Boolean)
      .sort()
      .pop() ?? null;

  return {
    schema: 1,
    generatedAt,
    asOf,
    site: SITE,
    source: SOURCE,
    license: {
      data: 'CC BY 4.0',
      code: 'Apache-2.0',
      attribution: `Starisk — ${SITE}`,
      excludes: [
        'review text',
        'course descriptions',
        'provider logos',
        'instructor photos',
      ],
    },
    method: {
      score:
        'sum(stars × √(1 + likes)) / sum(√(1 + likes)) over the most-helpful written reviews of one page (~20 per course)',
      calibration: 'weights calibrated against 29 courses I rated myself',
      ratings:
        'coursera and ratingCounts are the whole population Coursera publishes; starisk and reviewCounts are the written-review sample',
      programs:
        'a program has no written reviews of its own; average is the review-weighted mean of its courses, null when none are scored',
    },
    counts: {
      courses: courses.filter((course) => course.type === 'course').length,
      projects: courses.filter((course) => course.type === 'project').length,
      scored: courses.filter((course) => typeof course.starisk === 'number').length,
      noReviews: courses.filter((course) => course.noReviews === true).length,
      reviewsRead: courses.reduce((total, course) => total + (course.reviewsRead ?? 0), 0),
      programs: programs.length,
    },
    courses,
    programs,
  };
}
