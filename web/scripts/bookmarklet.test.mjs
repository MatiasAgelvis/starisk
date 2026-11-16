import assert from 'node:assert/strict';
import { test } from 'node:test';

import { bookmarkletSource } from '../src/lib/bookmarklet.js';

// The bookmarklet is a string, so the only honest test is to run it. These are
// the parts of a DOM it touches, and nothing else: if it grows a dependency on
// something not stubbed here, this file fails rather than the badge failing on
// someone else's page.

const ORIGIN = 'https://starisk.example';

const DATA = {
  courses: {
    'learn/known': { t: 'Known', s: 3.3, c: 4.9, n: 19 },
    'learn/low': { t: 'Low', s: 5, c: 3.6, n: 2, l: 1 },
  },
  programs: { 'specializations/known': { t: 'Program', s: 3.4, n: 5, m: 5 } },
  wanted: ['learn/asked'],
};

function makeNode(tag) {
  return {
    tag,
    children: [],
    attributes: {},
    style: {},
    textContent: null,
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    remove() {
      this.removed = true;
    },
    querySelector(selector) {
      if (selector === '[data-starisk]') {
        return this.children.find((child) => child.attributes['data-starisk'] !== undefined) ?? null;
      }
      return null;
    },
    closest() {
      return null;
    },
  };
}

/** Every string a node or its descendants carry, in document order. */
function textOf(node) {
  return [node.textContent ?? '', ...node.children.map(textOf)].join(' ');
}

/** One `<a href><h3>` pair, the shape Coursera's product cards use. */
function card(href) {
  const host = makeNode('div');
  const link = makeNode('a');
  const h3 = makeNode('h3');

  link.getAttribute = () => href;
  link.parentElement = host;
  h3.parentElement = link;
  host.children.push(link);

  return { host, link, h3 };
}

/**
 * Run the bookmarklet against a stubbed page.
 *
 * @param {{ pathname: string, cards?: ReturnType<typeof card>[] }} page
 */
async function run({ pathname, cards = [] }) {
  const appended = [];
  const opened = [];

  const document = {
    body: { appendChild: (node) => appended.push(node) },
    createElement: (tag) => makeNode(tag),
    querySelector: () => null,
    querySelectorAll: (selector) => (selector === 'a[href] > h3' ? cards.map((c) => c.h3) : []),
  };

  const window = {
    open: (url) => opened.push(url),
  };

  const location = { pathname };
  const fetch = () =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(structuredClone(DATA)) });

  class MutationObserver {
    observe() {}
  }

  const source = bookmarkletSource(ORIGIN);
  const run = new Function('window', 'document', 'location', 'fetch', 'MutationObserver', source);
  run(window, document, location, fetch, MutationObserver);

  // One macrotask: the payload arrives in a promise chain.
  await new Promise((resolve) => setTimeout(resolve, 0));

  return { appended, opened, cards, window };
}

test('the source is valid javascript', () => {
  assert.doesNotThrow(() => new Function(bookmarkletSource(ORIGIN)));
});

test('a course page gets a panel with both scores and the gap', async () => {
  const { appended } = await run({ pathname: '/learn/known' });

  assert.equal(appended.length, 1);
  const panel = appended[0];
  assert.equal(panel.attributes['data-starisk-panel'], '');

  const text = textOf(panel);
  assert.match(text, /Coursera 4\.9/);
  assert.match(text, /3\.3/);
  assert.match(text, /gap 1\.6/);
  assert.match(text, /19 reviews read/);
  assert.match(text, /See the reviews/);
});

test('a program page averages the courses read', async () => {
  const { appended } = await run({ pathname: '/specializations/known' });
  const text = textOf(appended[0]);

  assert.match(text, /3\.4/);
  assert.match(text, /5 of 5 courses read/);
});

test('a low-sample course says so', async () => {
  const { appended } = await run({ pathname: '/learn/low' });
  const text = textOf(appended[0]);

  assert.match(text, /Small sample/);
});

test('an unscored course offers a request that opens the same-origin page', async () => {
  const { appended, opened } = await run({ pathname: '/learn/never-seen' });
  const panel = appended[0];
  const button = panel.children.at(-1);

  assert.equal(button.textContent, 'Request a score');
  button.onclick();
  assert.deepEqual(opened, [`${ORIGIN}/request?key=learn%2Fnever-seen`]);
});

test('a course already on the ask list cannot be asked for twice', async () => {
  const { appended } = await run({ pathname: '/learn/asked' });
  const button = appended[0].children.at(-1);

  assert.equal(button.textContent, 'Already on the list');
  assert.equal(button.disabled, true);
});

test('a results page chips the cards we know and counts the page', async () => {
  const cards = [
    card('/learn/known'),
    card('/learn/never-seen'),
    card('/specializations/known'),
    card('/learn/known'), // a second rail pointing at the same course
    card('https://www.coursera.org/about'), // not a product
  ];

  const { appended, cards: rendered } = await run({ pathname: '/search', cards });

  const chips = rendered.flatMap((c) =>
    c.host.children.filter((n) => n.attributes['data-starisk'] !== undefined),
  );
  assert.equal(chips.length, 2, 'one chip per distinct product we know');
  assert.match(textOf(chips[0]), /Starisk 3\.3/);
  assert.match(textOf(chips[0]), /gap 1\.6/);

  assert.equal(appended.length, 1);
  assert.equal(textOf(appended[0]).includes('Starisk has read 2 of these 3'), true);
});

test('a page with no product cards draws nothing at all', async () => {
  const { appended } = await run({ pathname: '/search', cards: [] });

  assert.deepEqual(appended, []);
});

test('clicking it again re-opens a panel that was closed', async () => {
  const { appended, window } = await run({ pathname: '/learn/known' });

  assert.equal(appended.length, 1);
  window.__stariskBadge();
  assert.equal(appended.length, 2);
});

test('a second pass over the same cards does not duplicate chips', async () => {
  const cards = [card('/learn/known')];
  const { window, cards: rendered } = await run({ pathname: '/search', cards });

  window.__stariskBadge();

  const chips = rendered[0].host.children.filter(
    (node) => node.attributes['data-starisk'] !== undefined,
  );
  assert.equal(chips.length, 1);
});
