#!/usr/bin/env node
'use strict';

// Check a model against your own ranking.
//
//   node engine/calibration/calibrate.js
//
// Reads two files next to this script:
//   courses.json  -- the course list; fill each `label` with your gut score
//                    (a number, higher = better; leave null to skip)
//   scores.json   -- { "<url or title>": <model score> }, produced by scoring
//                    each course's saved reviews page with engine/score.js
//
// Reports Spearman rank correlation between your labels and the model.

const fs = require('node:fs');
const path = require('node:path');
const { spearman } = require('../rank.js');

const dir = __dirname;
const courses = JSON.parse(fs.readFileSync(path.join(dir, 'courses.json'), 'utf8'));

const scoresPath = path.join(dir, 'scores.json');
const scores = fs.existsSync(scoresPath)
  ? JSON.parse(fs.readFileSync(scoresPath, 'utf8'))
  : {};

function scoreFor(course) {
  if (scores[course.url] !== undefined) return scores[course.url];
  if (scores[course.title] !== undefined) return scores[course.title];
  return undefined;
}

const labeled = courses.filter((course) => course.label !== null && course.label !== undefined);

if (labeled.length === 0) {
  console.log(`No labels yet. Open ${path.relative(process.cwd(), path.join(dir, 'courses.json'))}`);
  console.log('and fill `label` on the courses you remember (higher = better).');
  process.exit(0);
}

const pairs = labeled
  .map((course) => ({ course, score: scoreFor(course) }))
  .filter((pair) => typeof pair.score === 'number' && pair.score >= 0);

if (pairs.length === 0) {
  console.log(`${labeled.length} labeled course(s), but no scores found.`);
  console.log('Add scores.json by running engine/score.js on each course\'s saved reviews page.');
  console.log('(This is the missing half: labels are yours, review data has to be collected.)');
  process.exit(0);
}

const correlation = spearman(
  pairs.map((pair) => pair.course.label),
  pairs.map((pair) => pair.score),
);

console.log(`labeled courses with scores: ${pairs.length}`);
console.log(`Spearman correlation (your ranking vs model): ${correlation.toFixed(3)}`);

const rows = pairs
  .map((pair) => ({ ...pair.course, score: pair.score }))
  .sort((a, b) => b.label - a.label);
console.log('\nby your label:');
for (const row of rows) {
  console.log(`  label ${String(row.label).padStart(3)}  model ${row.score.toFixed(1).padStart(4)}  ${row.title}`);
}
