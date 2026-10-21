'use strict';

// Turns a saved Coursera reviews page into the plain review objects the engine
// wants: { stars, likes, ageDays }.
//
// Deliberately dependency-free (no DOM parser, no network) so the whole tool
// runs forever on a fixed snapshot. It matches the 2022 Coursera markup and is
// expected to break on a redesign; that is exactly why it is isolated here and
// the engine does not depend on it.

const REVIEW_MARKER = '<div class="_jyhj5r review review-page-review m-b-2">';
const MILLISECONDS_PER_DAY = 1000 * 60 * 60 * 24;

function countMatches(haystack, pattern) {
  return (haystack.match(pattern) || []).length;
}

// The aggregate star rating Coursera shows, e.g. 4.0
function extractCourseraScore(html) {
  const match = html.match(/data-test="number-star-rating">([\d.]+)/);
  return match ? Number.parseFloat(match[1]) : Number.NaN;
}

function extractReviews(html) {
  // Everything before the first review marker is page chrome; drop it so those
  // "Helpful?" buttons don't pollute the first review's like count.
  const blocks = html.split(REVIEW_MARKER).slice(1);

  return blocks.map((block) => {
    const filled = countMatches(block, /<title[^>]*>Filled Star<\/title>/g);
    const half = countMatches(block, /<title[^>]*>Half Star<\/title>/g);

    const likesMatch = block.match(/This is helpful \((\d+)\)/);
    const dateMatch = block.match(/class="dateOfReview[^"]*">([^<]+)</);

    return {
      stars: filled + half / 2,
      likes: likesMatch ? Number.parseInt(likesMatch[1], 10) : 0,
      ageDays: dateMatch ? Date.parse(dateMatch[1]) / MILLISECONDS_PER_DAY : Number.NaN,
    };
  });
}

module.exports = { REVIEW_MARKER, extractCourseraScore, extractReviews };
