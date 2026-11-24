# TODO

Small, near-term work. The bigger threads — polarization, the dataset, calibration,
the transcript — live in [`IDEAS.md`](IDEAS.md) with their reasoning and an order of
work. This file is the list I actually open.

Current shape: **1064 courses indexed, 881 scored, 372 low-sample, 0 errors, 29
programs, 354 instructors, 12 requests.**

## Next

- **Low-sample shrinkage needs labels, not code.** `w = 1 - e^(-n/k)` with `k = 5`
  moves 89/728 courses and only low-sample ones, but calibration can't judge it: 29
  labelled courses, 2 of them low-sample. Needed: ~10 blind labels on low-sample
  courses. Then `k` stops being a guess.
- **Bookmarklet batch asks.** `PER_HOUR = 6` per visitor, so a results page asking
  for seven courses 429s on the seventh. Per-card asking is what ships today.

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
- **Programs page needs another pass.** The index is seed-driven, not derived from
  the course corpus: 15 programs are committed, a cache-only rebuild produces 29,
  and the sitemap holds 3,399 specialization slugs. A program only appears if its
  page was cached, so the directory depends on which machine built it. Add a
  committed seed/discovery strategy (batched sitemap, demand, or a reliable
  course→program hook) before judging the page.
- **The wanted page looks dead when there are no asks.** Add a “Recently added”
  section with the last 10 courses appended to `scores.json` — the file is
  append-only, so the end is the newest — so the page shows movement even when the
  queue is empty. It is distinct from “Recently fulfilled”, which needs a request.

## Pipeline

- **Alert on repeated `error` records.** Zero today; a run that produces several in
  a row means the markup moved. The nightly already notifies on failure, so this is
  a threshold inside the existing gate, not a new channel.
- **Cache stats and verify.** `python -m starisk.cache stats|verify`: counts by kind,
  size, staleness, then gunzip and re-parse every cached page with the current
  adapter. Zero requests, and it answers "how much of my cache can today's code
  still read" after a selector change. Copying the cache between machines stays
  plain `rsync` — the files are key-named and written atomically, so last write
  wins and nothing needs merging.
- **Optional pagination** (`?page=N`) if we ever want more than the first reviews
  page.
- **Score history over time** — git commits of `scores.json` already form a timeline.
  A query, once I7 exists.

## Coverage

Grow along the two existing edges (`mise run pipeline:expand`), not by sampling the
sitemap: the teacher graph has been the productive one, the specialization lever
much less so. 1537 sources listed against 1064 records — the gap is courses that
were listed but never scored (90 have no reviews at all).

- **Teacher pages are only as good as the corpus.** 121 of 354 teachers have exactly
  one course; the surface gets interesting at 3+ per person, which is a crawl
  problem, not a code one.
- Program aggregate *scoring* is done (groupings + the gap mark); what's missing is
  nothing at this level — see `IDEAS.md` I5 for what a program-level claim would
  need to be defensible.

## V2 / later

- **Classify reviews** (quality vs policy vs praise) — **parked**, `IDEAS.md` I3.
- **SQLite as the pipeline store** — **parked**, `IDEAS.md` I7.
- **Publish the dataset**, **SVG badges**, **compare two courses** — accepted,
  `IDEAS.md` I6, I8, I9.
- **Live lookup is a contradiction** — a Worker can't scrape. The queue is the
  answer, and it shipped: `IDEAS.md` I11.
