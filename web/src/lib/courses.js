// The one place the shape of `scores.json` is described.
//
// The file is a union of a dozen literal shapes (scored, no_reviews, error…), and
// TypeScript narrows a *value*, not an index lookup: `scores[key].starisk` stays an
// error even behind a `typeof` check, because the property genuinely does not exist
// on every member of the union. Importing `courses` here re-types the whole file
// once, so pages get a single `Course` shape and the narrowing helpers below.

import scores from '../data/scores.json';

/**
 * @typedef {Object} TopReview
 * @property {string} text
 * @property {number} likes
 * @property {number} stars
 * @property {string} [kind]
 */

/**
 * @typedef {Object} Course
 * @property {string} [title]
 * @property {string} [slug]
 * @property {string} [provider]
 * @property {string} [description]
 * @property {string} [image]
 * @property {string[]} [categories]
 * @property {{ name: string, page: string }[]} [instructors]
 * @property {number|null} [coursera]
 * @property {number} [starisk]
 * @property {number} [reviews]
 * @property {number} [ratings_total]
 * @property {Record<string, number>} [rating_counts]
 * @property {Record<string, number>} [review_counts]
 * @property {boolean} [low_sample]
 * @property {string} [source]
 * @property {string} [scrapedAt]
 * @property {string} [level]
 * @property {number} [enrollment]
 * @property {TopReview} [top_review]
 */

/** A course we read reviews from. */
/** @typedef {Course & { starisk: number }} Scored */
/** A course that also has a Coursera headline rating to compare against. */
/** @typedef {Course & { starisk: number, coursera: number }} Rated */

/** @type {Record<string, Course>} */
export const courses = /** @type {any} */ (scores);

/** @param {Course} course @returns {course is Scored} */
export function isScored(course) {
  return typeof course.starisk === 'number';
}

/** @param {Course} course @returns {course is Rated} */
export function isRated(course) {
  return typeof course.starisk === 'number' && typeof course.coursera === 'number';
}

// `filter` only narrows through a predicate on the element, and the element is the
// [key, course] pair — so the entry needs its own predicate.
/** @param {[string, Course]} entry @returns {entry is [string, Scored]} */
export function isScoredEntry(entry) {
  return isScored(entry[1]);
}
