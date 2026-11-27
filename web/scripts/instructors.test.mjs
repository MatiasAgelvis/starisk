import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { buildInstructors, initials, teacherIndex } from '../src/lib/instructors.js';

// Two shared courses, one solo course, and one record with no score: the four
// cases the directory and the teacher pages have to get right.
const scores = {
  'learn/a': {
    title: 'Course A',
    starisk: 5,
    reviews: 10,
    coursera: 4.9,
    instructors: [
      { slug: 'ada', page: 'ada-lovelace', name: 'Ada Lovelace', courses_taught: 4 },
      { page: 'bob', name: 'Bob Shared' },
    ],
  },
  'learn/b': {
    title: 'Course B',
    starisk: 2,
    reviews: 30,
    instructors: [
      {
        slug: 'ada',
        page: 'ada-lovelace',
        name: 'Ada Lovelace',
        department: 'Mathematics',
        photo: 'ada.jpg',
      },
      { page: 'bob', name: 'Bob Shared' },
    ],
  },
  'learn/c': {
    title: 'Course C',
    starisk: 4,
    reviews: 0,
    instructors: [{ page: 'cy', name: 'Cy Solo', courses_taught: 9 }],
  },
  'learn/unscored': {
    title: 'Never read',
    instructors: [{ page: 'nobody', name: 'Nobody At All' }],
  },
};

const people = buildInstructors(scores);
const byPage = Object.fromEntries(people.map((person) => [person.page, person]));

test('weights the catalogue average by the reviews actually read', () => {
  // 5.0 over 10 reviews and 2.0 over 30 is 2.75, not the plain mean of 3.5.
  assert.equal(byPage['ada-lovelace'].average, 2.75);
  assert.equal(byPage['ada-lovelace'].reviews, 40);
});

test('falls back to the plain mean when no course has reviews', () => {
  assert.equal(byPage.cy.average, 4);
  assert.equal(byPage.cy.reviews, 0);
});

test('keeps the range and orders the courses best first', () => {
  const ada = byPage['ada-lovelace'];
  assert.equal(ada.low, 2);
  assert.equal(ada.high, 5);
  assert.deepEqual(
    ada.courses.map((course) => course.title),
    ['Course A', 'Course B'],
  );
});

test('counts a co-taught course for everyone and names the other teachers', () => {
  const ada = byPage['ada-lovelace'];
  const bob = byPage.bob;

  assert.equal(ada.courses.length, 2);
  assert.equal(bob.courses.length, 2);
  assert.deepEqual(ada.courses[0].co, [{ name: 'Bob Shared', page: 'bob' }]);
  assert.deepEqual(bob.courses[0].co, [{ name: 'Ada Lovelace', page: 'ada-lovelace' }]);
  // A teacher is never their own co-teacher.
  assert.ok(ada.courses[0].co.every((other) => other.page !== ada.page));
});

test('takes the first non-empty value for each profile field', () => {
  const ada = byPage['ada-lovelace'];
  // The first course had no department or photo; the second one did.
  assert.equal(ada.department, 'Mathematics');
  assert.equal(ada.photo, 'ada.jpg');
  assert.equal(ada.name, 'Ada Lovelace');
});

test('directory order is most courses first, then average, then name', () => {
  assert.deepEqual(
    people.map((person) => person.page),
    ['ada-lovelace', 'bob', 'cy'],
  );
});

test('records without a score are left out entirely', () => {
  assert.equal(byPage.nobody, undefined);
  assert.ok(people.every((person) => person.courses.every((course) => typeof course.starisk === 'number')));
});

test('the lookup index is keyed by slug and skips people without one', () => {
  const index = teacherIndex(people);
  assert.deepEqual(index.ada, { page: 'ada-lovelace', name: 'Ada Lovelace' });
  assert.equal(index.bob, undefined);
});

test('publisher labels come from the verified list, not the name', () => {
  const catalog = {
    'learn/x': {
      title: 'X',
      starisk: 4,
      reviews: 1,
      provider: 'SkillUp',
      instructors: [{ page: 'skillup', name: 'SkillUp' }],
    },
    'learn/y': {
      title: 'Y',
      starisk: 4,
      reviews: 1,
      provider: 'IBM',
      instructors: [{ page: 'ibm-skills-network', name: 'IBM Skills Network Team' }],
    },
  };

  // Only skillup is on the list; the name looks like its provider, but looking
  // like a provider is not evidence — the pipeline proposes candidates, a human
  // verifies them, and the site reads the result.
  const pages = Object.fromEntries(
    buildInstructors(catalog, { skillup: 'profile is the partner name' }).map((person) => [
      person.page,
      person,
    ]),
  );

  assert.equal(pages.skillup.publisher, true);
  assert.equal(pages['ibm-skills-network'].publisher, false);
  assert.equal(byPage['ada-lovelace'].publisher, false);
});

test('the verified publisher list is well formed', () => {
  const data = JSON.parse(
    readFileSync(new URL('../src/data/publishers.json', import.meta.url), 'utf8'),
  );
  const slugs = Object.keys(data);

  assert.ok(slugs.length >= 12);
  assert.ok(slugs.includes('professionals-in-the-industry'));
  assert.ok(slugs.every((slug) => /^[a-z0-9~-]+$/.test(slug)));
  assert.ok(slugs.every((slug) => typeof data[slug] === 'string' && data[slug].trim()));
});

test('initials drop titles and credentials', () => {
  assert.equal(initials('Dr. Barbara Oakley'), 'BO');
  assert.equal(initials('Roger D. Peng, PhD'), 'RP');
  assert.equal(initials('Terry'), 'TE');
  assert.equal(initials(''), '');
  assert.equal(initials('李'), '');
});
