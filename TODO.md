# TODO

Small, near-term work. The bigger threads — polarization, the dataset, calibration,
the transcript — live in [`IDEAS.md`](IDEAS.md) with their reasoning and an order of
work. Shipped and rejected threads live in [`ARCHIVE.md`](ARCHIVE.md).

Current shape (2026-11-27): **2,089 courses indexed, 1,535 scored, 554 with no
written reviews, 0 errors, 200 programs, 169 queued, 2 requests.** The nightly
moves these; `pipeline/data/stats.json` has the counts it wrote.

## Next

- **Low-sample shrinkage needs labels, not code.** `w = 1 - e^(-n/k)` with `k = 5`
  moves only low-sample courses, but calibration can't judge it: 29 labelled
  courses, 2 of them low-sample. Needed: ~10 blind labels on low-sample courses.
  Then `k` stops being a guess.

## Front end

- **Teacher photos** are remote and lazy. If hotlinking becomes a privacy or
  breakage problem, localize them the way provider logos are: one file per person,
  downloaded during the crawl.
- **The dissent as a pull quote.** Typographic upgrade to the course page's
  blockquote: hanging gold quotation mark, thin rule, review larger than body copy,
  source and upvotes under it. See `IDEAS.md`, design notes.
- **Search** is the newest surface and the least settled: partial matching shows top
  results as you type, but the ranking is plain substring plus sort order. Worth a
  pass once there's evidence people use it.
- **Dataset page leftovers.** `/data` now shows a "Data as of <date>" line (newest
  review read; also `asOf` in the JSON) with a link to request a re-read. What's
  left is a CSV dump and a copy-paste "cite this" line (version + date). An hour,
  per `IDEAS.md` I6.

## Pipeline

- **Alert on repeated `error` records.** Zero today; a run that produces several in
  a row means the markup moved. The nightly already notifies on failure, so this is
  a threshold inside the existing gate, not a new channel.
- **Optional pagination** (`?page=N`) if we ever want more than the first reviews
  page.
- **Score history over time** — git commits of `scores.json` already form a timeline.
  A query, once I7 exists.

## Coverage

Grow along the two existing edges (`mise run pipeline:expand`), not by sampling the
sitemap: the teacher graph has been the productive one, the specialization lever
much less so. 2,261 sources listed against 2,089 records — the gap is courses that
were listed but never scored (554 have no written reviews at all).

- **Program memberships drift slowly, and no program page is ever re-read.**
  Coursera usually replaces a course or ships a new program (which discovery finds),
  so real additions are rare. But neither `groupings --fetch` (it only fills *missing*
  pages) nor `expand --programs` re-reads an existing page, so once a bundle is
  fetched its membership is frozen. A full yearly refresh needs either a `--refetch`
  flag on `groupings` (re-download published program pages, with the movement guard
  still refusing widespread change) or clearing `cache/pages/specializations/*` and
  re-running `pipeline:seed-programs` (one night of requests). The calibration-cert
  lever (`expand --specializations`) only ever covered my own certificates, not the
  published directory; it no longer runs in the nightly.

- **Program coverage: 200 of ~3,604 sitemap slugs.** Discovery samples the sitemap
  20 a night (stable hash order, so it spreads across the catalogue instead of
  stopping at `advanced-*`) and skips pages already in the cache, so the budget no
  longer goes to pages that fetched but never yielded a course list (15 collections
  such as `specializations/excel`). To go faster, run `--discover-limit 100 --fetch
  --write` **where the cache lives** (the crawl server), not on a laptop: groupings
  is derived, and a rebuild from a partial cache diverges from the server's in hunks
  git cannot merge. Raising `DISCOVER_PER_RUN` only grows a queue the crawl drains
  at 100 a night, so measure queue depth before changing it.
- **Teacher pages are only as good as the corpus.** 147 of 430 teachers have exactly
  one course; the surface gets interesting at 3+ per person, which is a crawl
  problem, not a code one.
- Program aggregate *scoring* is done (groupings + the gap mark); what's missing is
  nothing at this level — see `IDEAS.md` I5 for what a program-level claim would
  need to be defensible.

## V2 / later

- **Classify reviews** (quality vs policy vs praise) — **parked**, `IDEAS.md` I3.
- **SQLite as the pipeline store** — **parked**, `IDEAS.md` I7; the rot index
  (I10) waits on it.
- **SVG badges**, **compare two courses** — accepted, `IDEAS.md` I8, I9.
