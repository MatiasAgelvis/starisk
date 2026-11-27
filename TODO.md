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

Grow along the edges that already exist (`mise run pipeline:expand`): the teacher
graph has been the productive one, and program discovery adds the directory.
2,261 sources listed against 2,089 records — the gap is courses that were listed but
never scored (554 have no written reviews at all).

- **Program memberships drift slowly, and no program page is ever re-read.**
  Coursera usually replaces a course or ships a new program (which discovery finds),
  so real additions are rare. But neither `groupings --fetch` (it only fills *missing*
  pages) nor `expand --programs` re-reads an existing page, so once a bundle is
  fetched its membership is frozen. A full yearly refresh needs either a `--refetch`
  flag on `groupings` (re-download published program pages, with the movement guard
  still refusing widespread change) or clearing `cache/pages/specializations/*` and
  re-running `pipeline:seed-programs` (one night of requests).

- **Program coverage: ~200 of ~3,600 specializations and ~300 Professional
  Certificates.** Discovery samples both sitemaps 20 a night (one shared budget,
  taken round-robin; stable hash order so it spreads across each catalogue instead
  of stopping at `advanced-*`) and skips pages already in the cache, so the budget
  no longer goes to pages that fetched but never yielded a course list. Localized
  alias slugs (`.../analytique-des-donnees-google`) redirect to the canonical page;
  its JSON-LD `url` lets the build drop the duplicate. To go faster, run
  `--discover-limit 100 --fetch --write` **where the cache lives** (the crawl
  server), not on a laptop: groupings is derived, and a rebuild from a partial
  cache diverges from the server's in hunks git cannot merge. Raising
  `DISCOVER_PER_RUN` only grows a queue the crawl drains at 100 a night, so measure
  queue depth before changing it.
- **Teacher pages are only as good as the corpus.** 147 of 430 teachers have exactly
  one course; the surface gets interesting at 3+ per person, which is a crawl
  problem, not a code one.
- Program aggregate *scoring* is done (groupings + the gap mark); what's missing is
  nothing at this level — see `IDEAS.md` I5 for what a program-level claim would
  need to be defensible.

## Product types

Coursera's sitemap index names every product family. What the corpus reads today,
and the gap to "all of them":

| Type | Path | Rough count | Status |
|---|---|---|---|
| Courses | `learn/*` | ~23k | **in** — scored from written reviews |
| Specializations | `specializations/*` | ~3.6k | **in** — discovered, expanded to members |
| Professional Certificates | `professional-certificates/*` | ~300 | **in** — second sitemap, aliases deduped |
| Guided Projects | `projects/*` | ~2,188 | **out** — scoreable, not pipelined yet |
| MasterTrack | `mastertrack/*` | ~31 | **out** — no course-list hook |
| Degrees | `degrees/*` | ~64 | **out** — no course list or reviews |

Not products: `collections/*` (editorial groupings, ~412), `browse` / `explore` /
`eqp` (catalog and query pages), `about` / `articles` / `partners` / `instructors` /
`resources` / `enterprise` (site information).

- **Guided Projects are the biggest gap (2,188).** Single, short products rather
  than bundles, but `/projects/<slug>/reviews` renders the same `review-table-card`
  hooks as a course, so they are scoreable. The open question is presentation, not
  data: keep them separate from courses (see the plan below).
- **MasterTrack and Degrees are a different model.** No course list to expand and no
  written reviews to score, so they would need their own fields (institution,
  tuition, format) rather than the course pipeline.

### Implementation plan (open)

Order: Guided Projects first (scoreable today), then the two directory families.

**Guided Projects — a new crawl type, never mixed with courses.**

They are 1–2 hour products, not courses; a mixed leaderboard would rank
incomparable things. Leaning: separate type, separate listing.

1. **Crawler:** accept `projects/{slug}` in `normalize_source` / `_TYPES` /
   `reviews_url`, with `/projects/{slug}/reviews` (same `review-table-card` hooks —
   verified 20 cards on `getting-started-in-google-analytics`).
2. **Discovery:** `guided-projects.xml` (~2,188) into `sources.json`. Budget it like
   program discovery (N/night) or run it as a one-off; it competes with the course
   queue, so the pace is a decision.
3. **Data:** `scores.json` gains `projects/*` records with the same score model.
4. **Site:** pages already render via `[type]/[slug]`, but `index.astro` currently
   maps every scored key. Split by type: courses stay on the home table, projects
   get their own index (or a product filter). `/coverage` already counts the family.

Open: separate `/projects` leaderboard vs a product filter on the home table;
and whether project reviews join the calibration sample or stay a separate
population (they are short and may rate differently).

**MasterTrack — separate from programs.**

No course list on the page and no written reviews; it is a graduate bundle.
Options: (a) rate from member courses if the page ever exposes them — it does not
today; (b) show only Coursera's pooled bundle rating; (c) directory entry, no
score. Needs its own type, not `groupings.json` programs.

Open: (a)/(b)/(c). Leaning (b) if the pooled rating is readable, else (c).

**Degrees — a different model.**

Institution, tuition, format, admissions; no reviews and no course list. At most a
directory entry with its own fields, not part of the scored corpus.

Open: include them at all? If yes, define the fields before coding.

**Settle first, then code**

- Add a `product` field to every record, so the front never infers the family from
  the key prefix.
- Decide the leaderboard shape for multi-product data (separate pages vs a filter).
- Decide whether `/coverage` shows `listed` vs `scored` per family (courses already
  carry both).

## V2 / later

- **Classify reviews** (quality vs policy vs praise) — **parked**, `IDEAS.md` I3.
- **SQLite as the pipeline store** — **parked**, `IDEAS.md` I7; the rot index
  (I10) waits on it.
- **SVG badges**, **compare two courses** — accepted, `IDEAS.md` I8, I9.
