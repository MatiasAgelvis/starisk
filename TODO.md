# TODO

Small, near-term work. The bigger threads — polarization, the dataset, calibration,
the transcript — live in [`IDEAS.md`](IDEAS.md) with their reasoning and an order of
work. This file is the list I actually open.

Current shape: **1669 courses indexed, 1287 scored, 638 low-sample, 0 errors, 110
programs, 383 instructors, 2 requests.**

## Next

- **Low-sample shrinkage needs labels, not code.** `w = 1 - e^(-n/k)` with `k = 5`
  moves 89/728 courses and only low-sample ones, but calibration can't judge it: 29
  labelled courses, 2 of them low-sample. Needed: ~10 blind labels on low-sample
  courses. Then `k` stops being a guess.
- **Bookmarklet batch asks.** `PER_HOUR = 6` per visitor, so a results page asking
  for seven courses 429s on the seventh. Per-card asking is what ships today.
- **Publisher accounts are inferred, not verified.** The teacher directory marks an
  entry as a publisher when its page or display name matches the provider's name.
  Coursera offers no flag to read: its JSON-LD types every profile — SkillUp, IBM
  Skills Network — as `Person`. The rule catches the 11 obvious ones but misses
  aggregate accounts: "Professionals in the Industry" (491 courses) survives as a
  person. Store the verified set in `pipeline/data/publishers.json` (12 slugs, one
  line of evidence each), keep the name rule as a candidate finder that prints for
  review during `expand --instructors`, and have `buildInstructors` read the file
  instead of guessing at build time.

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
- **Program coverage: 110 of 3,399 sitemap slugs.** Discovery walks the sitemap 20 at
  a time and skips pages already in the cache, so the nightly budget no longer goes
  to pages that fetched but never yielded a course list (15 of them — collections
  such as `specializations/excel`). To go faster, run `--discover-limit 100 --fetch
  --write` **where the cache lives** (the crawl server), not on a laptop: groupings
  is derived, and a rebuild from a partial cache diverges from the server's in hunks
  git cannot merge. Raising `DISCOVER_PER_RUN` only grows a queue the crawl drains
  at 100 a night, so measure queue depth before changing it.

## Pipeline

- **Alert on repeated `error` records.** Zero today; a run that produces several in
  a row means the markup moved. The nightly already notifies on failure, so this is
  a threshold inside the existing gate, not a new channel.
- **A groupings rebuild can regress published stats.** A rebuild from an older
  laptop cache lowered `ratings_total` on 25 published programs and raised none —
  the signature of a stale snapshot, not Coursera recounting. `refuse_reason` only
  protects the program count. Extend it to refuse when an existing program's bundle
  rating or course list changes, unless `--force`.
- **The tests write into the real page cache.** About a dozen `crawl()` calls in
  `tests/test_crawl.py` omit `cache_dir`, so every test run leaves `learn/a`,
  `learn/empty` and friends in `pipeline/data/.cache` — and `cache verify` reports
  them as unparsed pages. Pass a temporary directory everywhere.
- **Optional pagination** (`?page=N`) if we ever want more than the first reviews
  page.
- **Score history over time** — git commits of `scores.json` already form a timeline.
  A query, once I7 exists.

## Coverage

Grow along the two existing edges (`mise run pipeline:expand`), not by sampling the
sitemap: the teacher graph has been the productive one, the specialization lever
much less so. 1818 sources listed against 1669 records — the gap is courses that
were listed but never scored (382 have no reviews at all).

- **Teacher pages are only as good as the corpus.** 133 of 383 teachers have exactly
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
