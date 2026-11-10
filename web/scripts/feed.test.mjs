import assert from 'node:assert/strict';
import { test } from 'node:test';

import { buildFeed, escapeXml } from '../src/lib/feed.js';

test('escapes the characters XML cares about', () => {
  assert.equal(escapeXml('<a & "b">'), '&lt;a &amp; &quot;b&quot;&gt;');
  assert.equal(escapeXml(null), '');
});

test('an empty feed is still a valid Atom document', () => {
  const xml = buildFeed([], 'https://starisk.example/');

  assert.match(xml, /^<\?xml version="1.0" encoding="utf-8"\?>/);
  assert.match(xml, /<updated>1970-01-01T00:00:00Z<\/updated>/);
  assert.match(xml, /<id>https:\/\/starisk\.example\/wanted<\/id>/);
  assert.equal(xml.match(/<entry>/g), null);
});

test('an empty feed uses the snapshot timestamp when it has one', () => {
  const xml = buildFeed([], 'https://starisk.example', '2026-01-03T00:00:00Z');

  assert.match(xml, /<updated>2026-01-03T00:00:00Z<\/updated>/);
  assert.equal(xml.match(/<entry>/g), null);
});

test('entries carry absolute links, dates and escaped text', () => {
  const xml = buildFeed(
    [
      {
        title: 'A & B',
        added_at: '2026-01-02T10:00:00Z',
        anchor: 'learn-a',
        href: '/learn/a',
        external: false,
        summary: 'Coursera 4.8 → Starisk 3.0',
      },
      {
        title: 'External',
        added_at: '2026-01-01T10:00:00Z',
        anchor: 'learn-b',
        href: 'https://www.coursera.org/learn/b',
        external: true,
        summary: '',
      },
    ],
    'https://starisk.example',
  );

  assert.match(xml, /<title>A &amp; B<\/title>/);
  assert.match(xml, /<link href="https:\/\/starisk\.example\/learn\/a" \/>/);
  assert.match(xml, /<link href="https:\/\/www\.coursera\.org\/learn\/b" \/>/);
  assert.match(xml, /<id>https:\/\/starisk\.example\/wanted#learn-a<\/id>/);
  assert.equal(xml.match(/<entry>/g).length, 2);
});

test('the feed is capped and sorted by the caller', () => {
  const rows = Array.from({ length: 60 }, (_, index) => ({
    title: `Course ${index}`,
    added_at: `2026-01-${String((index % 28) + 1).padStart(2, '0')}T00:00:00Z`,
    anchor: `learn-${index}`,
    href: `/learn/${index}`,
    external: false,
    summary: '',
  }));

  assert.equal(buildFeed(rows, 'https://starisk.example').match(/<entry>/g).length, 50);
});
