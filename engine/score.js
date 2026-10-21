#!/usr/bin/env node
'use strict';

// Stellaid CLI: score saved Coursera pages.
//
//   node engine/score.js test/pages/coursera/*.html
//
// Prints Coursera's rating next to Stellaid's, under both the original and the
// simplified model. No network, no browser, no extension.

const fs = require('node:fs');
const path = require('node:path');
const { extractCourseraScore, extractReviews } = require('./adapter.js');
const { courseScore, DEFAULTS, SIMPLE } = require('./engine.js');

function cell(value) {
  return (value < 0 ? 'n/a' : value.toFixed(1)).padStart(8);
}

function main() {
  const files = process.argv.slice(2);
  if (files.length === 0) {
    console.error('usage: node engine/score.js <saved-page.html> [...]');
    process.exit(1);
  }

  console.log('page'.padEnd(32) + 'Coursera   reviews  original    simple');
  for (const file of files) {
    const html = fs.readFileSync(file, 'utf8');
    const courseraScore = extractCourseraScore(html);
    const reviews = extractReviews(html);

    const original = courseScore({ reviews, courseraScore }, DEFAULTS);
    const simple = courseScore({ reviews, courseraScore }, SIMPLE);

    console.log(
      path.basename(file).padEnd(32)
      + (Number.isNaN(courseraScore) ? '     n/a' : courseraScore.toFixed(1).padStart(8))
      + String(reviews.length).padStart(9)
      + cell(original)
      + cell(simple),
    );
  }
}

main();
