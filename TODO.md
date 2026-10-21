# TODO

Ideas and deferred work. Not commitments — just a place so they stop living in my head.

## Front end
- **Logo polarity.** White-on-transparent marks are handled by the shared logo tile +
  alpha drop-shadow in `Logo.astro`. If more edge cases show up, consider a checkerboard
  backing or per-provider overrides.
- **Real course thumbnails.** The JSON-LD `image` is the *provider* logo; `og:image` is a
  generic Coursera placeholder. A real course thumbnail needs another source.
- Decide whether to keep hotlinking Coursera's CDN or download the provider logos.
- **Model choice:** `SIMPLE` vs a size-aware shrinkage model — decide by calibration.
- **Tame the amplification:** try `sqrt(likes)` or a like cap so one review can't own a score.
- Search / filter / sort controls for the leaderboard.

## Pipeline
- **Rename internals** `stellaid` → `starisk` (JSON field and Python package). No user impact.
- Optional pagination (`?page=N`) if we ever want more than the first reviews page.
- Alert when a crawl produces several `error` records in a row (markup changed).
- Score history over time — git commits of `scores.json` already form a timeline.

## Coverage
- Professional Certificates / specializations: score their constituent courses and aggregate
  (landing pages expose `data-e2e="sdp-course-list-link"`).
- Grow the crawl list from `sources.json`; later, from user requests.

## V2 / later
- **Classify reviews** (quality vs policy vs praise) with Jev or a small model. Validate on
  ~50 hand-labeled reviews before trusting it.
- **Live lookup** for non-indexed courses (Cloudflare Worker — not Vercel functions / Deno).
- **"Request this course"** — start with a GitHub issue link; Turso only if it becomes real.
- **Calibration** against the 74 labeled courses in `calibration/courses.json`.
