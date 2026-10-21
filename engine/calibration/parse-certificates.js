#!/usr/bin/env node
'use strict';

// One-off: turn a Certificates.md into courses.json (the calibration target).
//
//   node engine/calibration/parse-certificates.js /path/to/Certificates.md
//
// Writes engine/calibration/courses.json. Each course gets a `label` field,
// left null for you to fill in with your own gut rating (higher = better).

const fs = require('node:fs');
const path = require('node:path');

const input = process.argv[2];
if (!input) {
  console.error('usage: node engine/calibration/parse-certificates.js <Certificates.md>');
  process.exit(1);
}

const lines = fs.readFileSync(input, 'utf8').split('\n');
const entries = [];
let current = null;

for (const line of lines) {
  const link = line.match(/^\[([^\]]+)\]\(([^)]+)\)/);
  if (link) {
    if (current) entries.push(current);
    current = {
      title: link[1],
      url: link[2],
      issuer: null,
      date: null,
      credentialId: null,
    };
    continue;
  }

  if (!current) continue;

  const authority = line.match(/Issuing [Aa]uthority:\s*(.+?)\s*$/);
  if (authority) current.issuer = authority[1].trim();

  const date = line.match(/Issue Date:?\s*(.+?)\s*$/);
  if (date) current.date = date[1].trim();

  const credential = line.match(/Credential ID:\s*(.+?)\s*$/);
  if (credential) current.credentialId = credential[1].trim();
}
if (current) entries.push(current);

const courses = entries.map((entry) => ({
  ...entry,
  type: /specialization/i.test(entry.title) ? 'specialization' : 'course',
  label: null,
}));

const output = path.join(__dirname, 'courses.json');
fs.writeFileSync(output, JSON.stringify(courses, null, 2) + '\n');

const byIssuer = {};
for (const course of courses) {
  byIssuer[course.issuer] = (byIssuer[course.issuer] || 0) + 1;
}
console.log(`wrote ${courses.length} entries to ${path.relative(process.cwd(), output)}`);
console.log('by issuer:', byIssuer);
