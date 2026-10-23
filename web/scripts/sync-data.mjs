// Copy the pipeline's scores.json into the site, before dev and before build.
//
// The seam is `pipeline/data/scores.json` (SPEC D7); the site imports a copy at
// `src/data/scores.json`. That copy used to be refreshed only by `build.sh`, so
// `npm run dev` and Vercel's `npm run build` could serve month-old data — which
// is exactly what happened. Running this as `predev`/`prebuild` makes the copy
// impossible to forget.
//
// If the pipeline file is missing (a deploy that ships only `web/`), keep the
// committed copy rather than failing the build.

import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, '../../pipeline/data/scores.json');
const target = resolve(here, '../src/data/scores.json');

if (!existsSync(source)) {
  console.warn(`[sync-data] ${source} not found; keeping the committed copy.`);
  process.exit(0);
}

mkdirSync(dirname(target), { recursive: true });
copyFileSync(source, target);
console.log('[sync-data] pipeline/data/scores.json -> src/data/scores.json');
