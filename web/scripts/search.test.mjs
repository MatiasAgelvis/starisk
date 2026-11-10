import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildSearchIndex, normalize, search } from '../src/lib/search.js';

const scores = {
  'learn/financial-markets': {
    title: 'Financial Markets',
    slug: 'learn/financial-markets',
    starisk: 3.0,
    coursera: 4.8,
    reviews: 20,
  },
  'learn/machine-learning': {
    title: 'Machine Learning',
    slug: 'learn/machine-learning',
    starisk: 4.2,
    coursera: 4.9,
    reviews: 30,
  },
  'learn/learning-how-to-learn': {
    title: 'Learning How to Learn',
    slug: 'learn/learning-how-to-learn',
    starisk: 3.7,
    coursera: 4.8,
    reviews: 25,
  },
  'learn/probabilidad': {
    title: 'Probabilidad y estadística',
    slug: 'learn/probabilidad',
    starisk: 3.5,
    coursera: 4.5,
    reviews: 10,
  },
  'learn/tidyverse': {
    title: 'Data Wrangling in R',
    slug: 'learn/tidyverse',
    starisk: 3.9,
    coursera: 4.7,
    reviews: 15,
  },
  'learn/quiet': {
    title: 'Course Without Reviews',
    slug: 'learn/quiet',
    no_reviews: true,
    reviews: 0,
  },
};

const teachers = {
  'andrew-ng': { name: 'Andrew Ng', page: 'andrew-ng' },
  'barbara-oakley': { name: 'Barbara Oakley', page: 'barbara-oakley' },
};

const index = buildSearchIndex(scores, teachers);
const titles = (query, limit) => search(index, query, limit).map((item) => item.title);

test('normalizes case, accents, and punctuation', () => {
  assert.equal(normalize('  Probabilidad y ESTADÍSTICA '), 'probabilidad y estadistica');
  assert.equal(normalize('C++ for Everyone'), 'c for everyone');
  assert.equal(normalize('machine-learning'), 'machine learning');
});

test('an exact title comes first', () => {
  assert.equal(titles('financial markets')[0], 'Financial Markets');
});

test('a title prefix beats a word-start beats a substring', () => {
  // "Learning How to Learn" starts with the query; "Machine Learning" only has
  // it as a later word.
  assert.deepEqual(titles('learning').slice(0, 2), [
    'Learning How to Learn',
    'Machine Learning',
  ]);

  // A substring deep in the title still matches, but ranks below both.
  assert.equal(titles('markets')[0], 'Financial Markets');
});

test('accents and hyphens do not have to be typed', () => {
  assert.equal(titles('estadistica')[0], 'Probabilidad y estadística');
  assert.equal(titles('machine-learning')[0], 'Machine Learning');
});

test('a slug match is enough when the title does not contain the query', () => {
  assert.equal(titles('tidyverse')[0], 'Data Wrangling in R');
});

test('the provider is searchable', () => {
  const custom = buildSearchIndex({
    'learn/x': {
      title: 'Some Course',
      slug: 'learn/x',
      provider: 'IBM',
      starisk: 3.0,
      reviews: 5,
    },
  });
  assert.equal(search(custom, 'ibm')[0].key, 'learn/x');
});

test('teachers are searchable and labelled', () => {
  const [best] = search(index, 'andrew');
  assert.equal(best.kind, 'teacher');
  assert.equal(best.href, '/instructors/andrew-ng');
  assert.equal(best.title, 'Andrew Ng');
});

test('a course title outranks a teacher on equal text', () => {
  const custom = buildSearchIndex(scores, { x: { name: 'Machine Learning', page: 'x' } });
  const [best] = search(custom, 'machine learning');
  assert.equal(best.kind, 'course');
});

test('a shorter title wins among equal textual matches', () => {
  const custom = buildSearchIndex({
    'learn/a': { title: 'AI in Healthcare', starisk: 3, reviews: 5 },
    'learn/b': {
      title: 'Evaluations of AI Applications in Healthcare',
      starisk: 3,
      reviews: 50,
    },
  });

  assert.equal(search(custom, 'ai healthcare')[0].title, 'AI in Healthcare');
});

test('programs are searchable and carry their average', () => {
  const custom = buildSearchIndex({}, {}, {
    'professional-certificates/ibm-data-science': {
      key: 'professional-certificates/ibm-data-science',
      title: 'IBM Data Science',
      type: 'professional-certificate',
      label: 'Professional Certificate',
      provider: 'IBM',
      average: 3.4,
      scored: 9,
      total: 12,
      reviews: 120,
    },
  });

  const [best] = search(custom, 'ibm data science');
  assert.equal(best.kind, 'program');
  assert.equal(best.href, '/programs/professional-certificates/ibm-data-science');
  assert.equal(best.starisk, 3.4);
  assert.equal(best.label, 'Professional Certificate');
});

test('an exact program title beats a course containing the words', () => {
  const custom = buildSearchIndex(
    {
      'learn/ibm-data-science-capstone': {
        title: 'IBM Data Science Capstone',
        starisk: 3.0,
        reviews: 10,
      },
    },
    {},
    {
      'professional-certificates/ibm-data-science': {
        title: 'IBM Data Science',
        average: 3.4,
        scored: 9,
        total: 12,
        reviews: 100,
      },
    },
  );

  const [best] = search(custom, 'ibm data science');
  assert.equal(best.kind, 'program');
});

test('keeps the score information the dropdown needs', () => {
  const [best] = search(index, 'financial markets');
  assert.equal(best.starisk, 3.0);
  assert.equal(best.coursera, 4.8);

  const [empty] = search(index, 'course without reviews');
  assert.equal(empty.noReviews, true);
  assert.equal(empty.starisk, null);
});

test('one character is not enough to guess', () => {
  assert.deepEqual(search(index, 'm'), []);
});

test('respects the limit and returns nothing for unknown text', () => {
  assert.equal(search(index, 'learning', 1).length, 1);
  assert.deepEqual(search(index, 'quantum basket weaving'), []);
});

test('more-reviewed courses win an otherwise equal match', () => {
  const custom = buildSearchIndex({
    'learn/a': { title: 'Same Title', slug: 'learn/a', starisk: 3.0, reviews: 5 },
    'learn/b': { title: 'Same Title', slug: 'learn/b', starisk: 4.0, reviews: 50 },
  });
  const [best] = search(custom, 'same title');
  assert.equal(best.key, 'learn/b');
});
