// Copy the pipeline's derived JSON into the site, before dev and before build.
//
// `scores.json` is the course seam (SPEC D7); `groupings.json` is the derived
// program index (programs + their course keys). If a file is missing — a deploy
// that ships only `web/` — keep the committed copy rather than failing.

import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

const files = [
  ['../../pipeline/data/scores.json', '../src/data/scores.json'],
  ['../../pipeline/data/groupings.json', '../src/data/groupings.json'],
];

for (const [from, to] of files) {
  const source = resolve(here, from);
  const target = resolve(here, to);

  if (!existsSync(source)) {
    console.warn(`[sync-data] ${source} not found; keeping the committed copy.`);
    continue;
  }

  mkdirSync(dirname(target), { recursive: true });
  copyFileSync(source, target);
  console.log(`[sync-data] ${from} -> ${to}`);
}
