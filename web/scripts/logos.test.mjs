import assert from 'node:assert/strict';
import { test } from 'node:test';

import { logoFull, logoKey, logoTile } from '../src/lib/logos.js';

test('reads the provider stem out of any logo path', () => {
  assert.equal(logoKey('/logos/tile/deeplearning-ai.png'), 'deeplearning-ai');
  assert.equal(logoKey('/logos/full/deep-learning-solutions.jpg'), 'deep-learning-solutions');
  assert.equal(logoKey('/logos/the-linux-foundation.png'), 'the-linux-foundation');
  assert.equal(logoKey(''), '');
  assert.equal(logoKey(null), '');
});

test('a course resolves to the sizes the pipeline generated', () => {
  // `image` points at the tile file after pruning; the stem still resolves.
  assert.equal(logoTile('/logos/tile/ibm.png'), '/logos/tile/ibm.png');
  assert.equal(logoFull('/logos/tile/ibm.png'), '/logos/full/ibm.png');
  assert.equal(logoFull('/logos/ibm.png'), '/logos/full/ibm.png');
});

test('an unknown logo falls back to whatever image holds', () => {
  const remote = 'https://cdn.example.com/x.png';
  assert.equal(logoTile(remote), remote);
  assert.equal(logoFull(remote), remote);
  assert.equal(logoTile(undefined), null);
});

test('the tile is the fallback when no full render exists', () => {
  // Providers whose page has no header mark never get a `full` entry.
  assert.equal(logoTile('/logos/the-linux-foundation.png'), '/logos/tile/the-linux-foundation.png');
});
