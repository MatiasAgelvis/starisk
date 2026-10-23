# TODO

Ideas and deferred work. Not commitments — just a place so they stop living in my head.

Bigger threads (the bookmarklet, polarization, the corpus, the dataset) live in
[`IDEAS.md`](IDEAS.md) with their reasoning and an order of work. This file is
for the small, near-term stuff.

## Next
- **I1 — bookmarklet.** First: the 5-minute CSP spike (CORS is already fine —
  both GH Pages and CF Pages send `Access-Control-Allow-Origin: *`). Then copy
  `scores.json` to `web/public/data/`: it is only imported at build time today, so
  it isn't fetchable.
- **I2 — polarization.** Add the weighted standard deviation to the crawl output,
  then the quadrant view.
- **I5 spike.** Do Coursera credential pages expose the course slug? Decides how
  expensive the personal corpus is.

## Front end
- **Logo polarity.** White-on-transparent marks are handled by the shared logo tile +
  alpha drop-shadow in `Logo.astro`. If more edge cases show up, consider a checkerboard
  backing or per-provider overrides.
- **Real course thumbnails.** The JSON-LD `image` is the *provider* logo; `og:image` is a
  generic Coursera placeholder. A real course thumbnail needs another source.
- **OG image.** Shared links render a bare text card. Needs a raster (satori/resvg at
  build, or one hand-made PNG) — the pipeline can draw SVG, but social platforms
  don't accept SVG.
- Decide whether to keep hotlinking Coursera's CDN or download the provider logos.
- **Model choice:** `SIMPLE` vs a size-aware shrinkage model — decide by calibration.
- **Tame the amplification:** try `sqrt(likes)` or a like cap so one review can't own a score.
- Search / filter / sort controls for the leaderboard.
- **Teacher photos** are remote and lazy, like course thumbnails (SPEC D24). If
  hotlinking becomes a privacy or breakage problem, localize them the way provider
  logos are: one file per person, downloaded during the crawl.
- Find where to add the copy '5 stars... would not reccomend'

## Pipeline
- Optional pagination (`?page=N`) if we ever want more than the first reviews page.
- Alert when a crawl produces several `error` records in a row (markup changed).
- Score history over time — git commits of `scores.json` already form a timeline.

## Coverage
- Professional Certificates / specializations: score their constituent courses and aggregate
  (landing pages expose `data-e2e="sdp-course-list-link"`).
- Grow the crawl list from `sources.json`; later, from user requests.
- **Teacher pages are only as good as the corpus.** 17 of 30 teachers have exactly one
  course; the surface gets interesting at 3+ per person, which is a crawl problem, not a
  code one.

## V2 / later
- **Classify reviews** (quality vs policy vs praise) — **parked**, see `IDEAS.md` I3.
  Too much complication for now; it is the honest escape hatch if the premise gets
  challenged, and needs validation on ~50 hand-labeled reviews before any trust.
- **Live lookup** is a contradiction — a Worker can't scrape (datacenter IP, D6).
  Enqueue instead: `IDEAS.md` I11.
- **"Request this course"** — a GitHub issue link first (the issue *is* a queue and a
  notification, with no PII). Turso only if it becomes real; design sketch in
  `IDEAS.md` I11.
- **Calibration** against the 74 labeled courses in `calibration/courses.json`.
