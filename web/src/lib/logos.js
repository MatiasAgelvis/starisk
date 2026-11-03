// Resolve a course's `image` to the variant that belongs in that context.
//
// `logo-sizes.json` is keyed by provider stem, not by path: the pipeline repoints
// `image` at the tile file once it can prune the 160px lockup, so the path itself
// is not stable. Anything unknown falls back to whatever `image` holds, which is
// the lockup `logos.py` downloaded.
import sizes from '../data/logo-sizes.json' with { type: 'json' };

/** @type {Record<string, { tile?: string, full?: string }>} */
const variants = /** @type {any} */ (sizes);

/** `/logos/tile/deeplearning-ai.png` -> `deeplearning-ai` */
export function logoKey(src) {
  if (!src) return '';
  const file = String(src).split('/').pop() ?? '';
  return file.replace(/\.[^.]+$/, '');
}

/** The mark for a table cell: ~36px, so the small render is plenty. */
export function logoTile(src) {
  return variants[logoKey(src)]?.tile ?? src ?? null;
}

/** The mark for the single-course view, falling back to the tile. */
export function logoFull(src) {
  const entry = variants[logoKey(src)];
  return entry?.full ?? entry?.tile ?? src ?? null;
}
