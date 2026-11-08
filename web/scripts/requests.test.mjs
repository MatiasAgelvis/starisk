import assert from 'node:assert/strict';
import { test } from 'node:test';

import { MAX_INPUT, MAX_QUERY, validateQuery } from '../src/lib/requests.js';

test('accepts the forms the lookup already accepts', () => {
  const url = validateQuery('https://www.coursera.org/learn/machine-learning/reviews?foo=bar');
  assert.deepEqual(url, {
    ok: true,
    kind: 'slug',
    key: 'learn/machine-learning',
    query: 'https://www.coursera.org/learn/machine-learning/reviews?foo=bar',
  });

  assert.equal(validateQuery('/learn/machine-learning/').key, 'learn/machine-learning');
  assert.equal(validateQuery('learn/machine-learning').key, 'learn/machine-learning');
  assert.equal(validateQuery('machine-learning').key, 'learn/machine-learning');
  assert.equal(validateQuery('LEARN/Machine-Learning').key, 'learn/machine-learning');
});

test('the same course in different shapes gets one key', () => {
  const forms = [
    'https://www.coursera.org/learn/calculus-through-data-and-modeling',
    'https://coursera.org/learn/calculus-through-data-and-modeling/',
    'learn/calculus-through-data-and-modeling',
    'Calculus-Through-Data-And-Modeling',
  ];
  const keys = new Set(forms.map((form) => validateQuery(form).key));
  assert.deepEqual([...keys], ['learn/calculus-through-data-and-modeling']);
});

test('a typed name is stored as a name, not a fake slug', () => {
  const name = validateQuery('Machine Learning by Andrew Ng');
  assert.equal(name.ok, true);
  assert.equal(name.kind, 'name');
  assert.equal(name.key, 'name/machine-learning-by-andrew-ng');
  assert.equal(name.query, 'Machine Learning by Andrew Ng');
});

test('names may use other scripts and the punctuation course names use', () => {
  assert.equal(validateQuery('Probabilidad y estadística').key, 'name/probabilidad-y-estadistica');
  assert.equal(validateQuery('C# Programming').key, 'name/c-programming');
  assert.equal(validateQuery('C++ for Everyone').key, 'name/c-for-everyone');
});

test('rejects links that are not Coursera courses', () => {
  assert.equal(validateQuery('https://www.coursera.com/learn/bad-name').reason, 'url');
  assert.equal(validateQuery('example.com/learn/something').reason, 'url');
  assert.equal(validateQuery('https://www.coursera.org/instructor/andrew-ng').reason, 'not_a_course');
  assert.equal(validateQuery('https://www.coursera.org/specializations/deep-learning').reason, 'program');
  assert.equal(validateQuery('specializations/deep-learning').reason, 'program');
});

test('rejects profanity in a slug, a name, and leetspeak', () => {
  assert.equal(validateQuery('learn/fuck-you').reason, 'language');
  assert.equal(validateQuery('learn/sh1t-course').reason, 'language');
  assert.equal(validateQuery('some very fucked up course').reason, 'language');
});

test('leaves real words alone', () => {
  assert.equal(validateQuery('analysis').ok, true);
  assert.equal(validateQuery('class').ok, true);
  assert.equal(validateQuery('assessment methods').ok, true);
  assert.equal(validateQuery('Dickens and the Victorian Novel').ok, true);
});

test('rejects markup, repeated characters, and empty input', () => {
  assert.equal(validateQuery('').reason, 'empty');
  assert.equal(validateQuery('   ').reason, 'empty');
  assert.equal(validateQuery(null).reason, 'empty');
  assert.equal(validateQuery('hello <b>world</b>').reason, 'characters');
  assert.equal(validateQuery('aaaaaaaa').reason, 'repetitive');
  assert.equal(validateQuery('learn/foo--bar').reason, 'not_a_course');
});

test('a link may be longer than a name: only its slug matters', () => {
  const result = validateQuery(
    'https://www.coursera.org/learn/ai-transformation-advisory-package' +
      '?specialization=ibm-enterprise-ai-transformation-and-consulting',
  );

  assert.equal(result.ok, true);
  assert.equal(result.kind, 'slug');
  assert.equal(result.key, 'learn/ai-transformation-advisory-package');
});

test('caps a typed name and a pasted link separately', () => {
  const longName = `${'a'.repeat(MAX_QUERY - 10)} ${'b'.repeat(20)}`;
  assert.equal(validateQuery(longName).reason, 'too_long');
  assert.equal(validateQuery('x'.repeat(MAX_INPUT + 1)).reason, 'too_long');
  assert.equal(validateQuery(`learn/${'x'.repeat(100)}`).reason, 'too_long');
});

test('strips invisible characters instead of storing them', () => {
  const result = validateQuery('\u200blearn/machine-learning\u202e');
  assert.equal(result.ok, true);
  assert.equal(result.key, 'learn/machine-learning');
});
