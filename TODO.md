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
- **Course requests.** Shipped: the landing page's miss state writes to Turso
  through `web/src/lib/course-requests.js` (served by `web/api/course-request.js`).
  `pipeline:demand` reads that inbox, turns `status='new'` rows into crawl work,
  verifies new keys and merges them into `sources.json` plus the local
  `requests.json`; `/wanted` and `/feed.xml` derive waiting/fulfilled by joining
  that list against `scores.json` / `groupings.json`. Next: reconcile `planned` →
  `done` (`done_at`), then export a queue snapshot for `/wanted` and the request
  feed. Moderation still means editing `status` by hand.

## Homelab

A clone of the repo in a container, on a schedule. The box has the residential
IP the crawl wants and the notification channel the repo cannot own. With the
repo checked out and `.env.prod` mounted (not baked into the image):
`python -m starisk.demand --env-file .env.prod --write`, then `pipeline:crawl`.
The write step verifies links and updates `data/requests.json`; the crawl
supplies the scores and titles the site derives from.

- **Nightly queue read.** Query `course_requests` and send one `ntfy` digest
  through the existing health check: new asks (`first_seen` since the last run),
  what was added today, and anything left for a human (`name/*` rows, gone
  links, failed program/instructor pages). Silent when nothing changed. A local
  watermark file is enough for one box; a `notified_at` column only if a second
  consumer appears.
- **Gate before crawling.** `pipeline:demand --dry-run` is the test: if every
  row reports `add`, run `--write` then `pipeline:crawl --limit N`. Anything
  `manual` / `gone` / `waiting` goes into the notification instead of the run.
- **Close the loop.** After the crawl, reconcile `planned` keys against
  `scores.json` / `groupings.json`, export the snapshot, commit and push so the
  site and feed rebuild. Non-zero exit and 403/429 are high-priority alerts;
  send a heartbeat on success so the existing health check catches a dead cron.
- **Secrets live on the box:** `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, a deploy
  key for the push, and the `ntfy` topic. No repo secrets are needed.
- **Never automate `name/*` rows.** They cannot be resolved to a slug without a
  human, so the run should count them and stop.
- Keep the container's data volume on `pipeline/data/` and the cache directory so
  freshness and `--offline` keep working across runs.

## Front end
- **Brand theme: navy + gold.** The logo is `#111827` with `#fbbf24`, and the
  `theme-color` meta already matches the navy, but the site still runs on daisyUI's
  stock `light` / `dark`. Not in scope for `feat/findings` — it deserves its own
  branch, since it changes every page at once. Sketch: a `@plugin "daisyui/theme"`
  block in `global.css` defining both schemes, using `--color-neutral: #111827`
  and `--color-primary: #fbbf24`.
  - **Gold is a bad text colour** — `#fbbf24` on white is ~1.9:1. Keep it for fills
    and highlights, and use a darker amber (~`#b45309`) for `text-primary` links,
    or every link on the site becomes unreadable.
  - The logo chips in `Logo.astro` and `ScoreTable.svelte` are literal `bg-white`
    on purpose: the marks are dark artwork drawn for light backgrounds. A dark
    theme should keep those chips light rather than tokenising them.
  - The charts already fit: grey for Coursera, `primary` for Starisk. Under a
    gold theme our bars turn gold without touching either page.
  - Everything else uses semantic tokens (`bg-base-200`, `text-primary`,
    `fill-primary/80`, `stroke-base-content/25`), so expect one file plus a
    contrast pass, not a rewrite.
- **Logo polarity.** White-on-transparent marks are handled by the shared logo tile +
  alpha drop-shadow in `Logo.astro`. If more edge cases show up, consider a checkerboard
  backing or per-provider overrides.
- **Real course thumbnails.** The JSON-LD `image` is the *provider* logo; `og:image` is a
  generic Coursera placeholder. A real course thumbnail needs another source.
- **OG image.** Shared links render a bare text card. Needs a raster (satori/resvg at
  build, or one hand-made PNG) — the pipeline can draw SVG, but social platforms
  don't accept SVG.
- **Size-aware shrinkage** — the model choice itself is settled (`CALIBRATED`); whether
  to shrink small samples is still open, and should be decided by calibration.
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
  (landing pages expose `data-e2e="sdp-course-list-link"`). The **expansion** side is done
  (D25); aggregate *scoring* of the program is still open.
- Grow the crawl list along the two existing edges (`mise run pipeline:expand`), not by
  sampling the sitemap. 454 sources as of the latest pass.
- **Teacher pages are only as good as the corpus.** 49 of 151 teachers have exactly one
  course; the surface gets interesting at 3+ per person, which is a crawl problem, not a
  code one.

## V2 / later
- **Classify reviews** (quality vs policy vs praise) — **parked**, see `IDEAS.md` I3.
  Too much complication for now; it is the honest escape hatch if the premise gets
  challenged, and needs validation on ~50 hand-labeled reviews before any trust.
- **Live lookup** is a contradiction — a Worker can't scrape (datacenter IP, D6).
  Enqueue instead: `IDEAS.md` I11.
- **"Request this course"** — shipped as the Turso queue behind `/wanted` and
  `/feed.xml`. Remaining work is operational (homelab nightly), not the write
  path; design sketch in `IDEAS.md` I11.
- **Calibration** against the 74 labeled courses in `calibration/courses.json`.
