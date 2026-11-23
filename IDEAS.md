# Ideas

Not commitments. A registry of threads that are worth keeping, with the reasoning
attached so future-me doesn't have to re-derive it.

**Status key**

- **accepted** — I want this; it's a matter of when.
- **parked** — deliberately not now. The reason is written down; revisit if the
  reason stops being true.
- **shipped** — done. Kept for the reasoning, and for what it left unfinished.
- **rejected** — no. Kept here so it doesn't get re-proposed.

The thing that makes all of this interesting is **corpus size**: 1064 courses
indexed, 881 scored, 29 programs, 354 instructors. The patterns below — quadrants,
per-instructor signal, per-subject posts — only earn their space at this scale; at
six courses they were a demo.

## Registry

| # | Idea | Status | Note |
|---|------|--------|------|
| I1 | Bookmarklet badge | shipped | live; batch asks still capped at 6/h |
| I2 | Polarization + quadrants | accepted | the data ships, the surface doesn't |
| I3 | Grievance vs. quality split | parked | the honest escape hatch |
| I4 | The scatter | shipped | `/findings` |
| I5 | Transcript + calibration corpus | partial | `/background` ships, labels stuck at 29 |
| I6 | Publish the dataset | accepted | the part that outlives the site |
| I7 | SQLite as the pipeline store | parked | JSON is correct until it isn't |
| I8 | Embeddable SVG badges | accepted | one file, no JS |
| I9 | Compare two courses | accepted | client-side over scores.json |
| I10 | Rot index | parked | needs I7 |
| I11 | Request queue | shipped | Turso inbox → nightly drain |
| I12 | Course thumbnails | rejected | replaced by provider marks |

---

## A. Where people already are

### I1 — The bookmarklet badge — **shipped**

A draggable `javascript:` link. On a Coursera page, clicking it reads
`location.pathname`, fetches the compact lookup, and injects a badge next to
Coursera's headline rating.

**Why it was the right first product:** no store, no manifest, no permissions
prompt, no publish cycle. A bookmarklet is the only distribution channel that
requires zero trust from a stranger, and it survives the MV3 tax entirely.

**What shipped:** `/data/badge.json` — five fields per course instead of the whole
record, 881 courses and 26 programs in **105 KB raw / 26 KB gzipped**, against
3.45 MB (800 KB gzipped) for `scores.json`, which stays the dataset download.
`/request` is the same-origin write path (the edge function only answers its own
origin, and a JSON body from another site needs a preflight it doesn't implement),
and `/bookmarklet` keeps its source in `lib/` percent-encoded into the drag target,
exercised by `scripts/bookmarklet.test.mjs` against a stubbed DOM.

**Why it was viable at all:** Coursera sends `content-security-policy:
frame-ancestors 'self'` and nothing else — no `script-src`, no `connect-src`, no meta
CSP — so neither the `javascript:` URL nor a cross-origin fetch is restricted, and
both of our data endpoints answer `access-control-allow-origin: *`.

**Still open**

- **Batch asks.** `PER_HOUR = 6` per visitor, so "ask for these 7" from a results
  page would 429 on the seventh. Per-card asking is what ships.
- **Discovery.** It lives in the footer as *"The score, on Coursera's own pages."*
  Deliberately quiet: the site's tone is academic, and anything louder reads as
  SaaS. Revisit only if someone says they couldn't find it.

---

## B. Making the score honest

### I2 — Polarization, and the honest tierlist — **shipped**

`spread` and `spread_weighted` ship in every record now; `/findings` plots the two
star distributions and the same scale side by side. `/contested` is the quadrant
view: score on x, spread on y, four named cells at fixed 3.5 / 1.2 splits.

**Why:** it turns the model's worst weakness (one upvoted review owning a score)
into a measured quantity instead of a hidden failure. The "contested" cell is
precisely the phenomenon that started all of this.

**Caveats, measured**

- Noisy at 20 reviews. Label it a vibe, not a statistic.
- **The weighted spread is a trap.** Weighting by likes drags the mean onto the
  dominant review, so weighted std-dev *shrinks* when one review owns the score
  (measured: 1.63 → 0.44 sd after giving a 1★ review 100 likes). A bitterly
  contested course would look unanimous. Use the **unweighted** `spread` as the
  contention axis; keep `spread_weighted` as a curiosity.
- **The population confirms the thesis.** Every course page carries
  `rating_counts` (all ratings ever). Financial Markets: 32,334 ratings, of which
  **1.2%** are 1–2★, while the 20 reviews we read scatter with 1.84 sd. The
  upvoted minority really is ~1% of the population.

### I3 — Grievance vs. quality split — **parked**

Two numbers per course: the course, and the platform (access, pricing,
certificates, refunds). It would answer "your score measures complaints about the
paywall, not the teaching" — the strongest critique of this project.

**Why parked:** a lexicon, a validation set, a second column and a second story.
Revisit the moment the premise gets challenged in public, or if calibration comes
out weak. It's the honest escape hatch, not the next feature.

**Concrete use case, measured:** 5 of the first 34 courses had no critical review
*with text* — every 1–3★ review was a bare rating — so the page fell back to a 5★
review (`kind: consensus`). Some of those contain real criticism after a "but".
Finding that sentence inside praise is exactly what this would buy.

---

## C. The corpus and the story

### I4 — The scatter — **shipped**

`/findings` is the finding: the histogram of both distributions on one axis
(with the empty low-rated zone boxed, and the share Starisk disagrees on), then
every course plotted on the same scale. That replaced a table of numbers with an
argument, which was the point.

### I5 — My courses as the corpus, `/background`, and calibration — **partial**

**Shipped:** `/background` lists the credentials (74 entries, 59 Coursera) and
`about` links to it. The corpus exists.

**Data:** `calibration/courses.json` holds 74 entries with a `label` each, **29
labelled**. That's the calibration set, and it is the thing blocking the
low-sample fix.

**Why it still matters:** it solves corpus *and* narrative in one move — the
leaderboard stops being a generic Coursera list and becomes a personal dataset
nobody else has — and the same crawl feeds the Spearman verdict on the premise.

**Measured (2026-10), still the most useful lesson here:** the specialization
lever was smaller than expected — 6 of 7 specializations resolved and only 8 of
their 25 constituent courses were new. The lever that grew the corpus was the
**teacher graph**: instructor profiles linked courses that the umbrellas didn't.
People cluster courses; parent products don't, because Coursera recycles them.

---

## D. The data asset

### I6 — Publish the dataset — **accepted**

A page for `scores.json` plus aggregates, a "cite this" line, and a CSV dump.

**Why:** nobody else has upvote-weighted Coursera review data. This is the one
thing here that outlives the website, and it costs almost nothing.

**Constraint:** **excerpts only** for review text. Other people's words, and the
risk/benefit is bad. Aggregates and the single most-upvoted critical excerpt are
enough.

### I7 — SQLite as the pipeline store — **parked (long-term)**

`sqlite3` is stdlib, so this costs no dependency: courses, reviews, crawl runs,
score history. Turso later, if it ever needs to be remote — which it now partly is
(the request inbox).

**Why parked:** JSON plus git is correct until it isn't. The corpus is 1064
records and the diffs are still readable.

**Constraint that must not drift:** SQLite stays a **pipeline-internal store**;
`scores.json` remains the published artifact and the seam. The front never reads a
database — the build reads the exported JSON. If SQLite leaks into the site build,
the static property goes with it.

**Payoff when it's worth it:** score history becomes rows instead of git
archaeology, and "courses that moved most" becomes one query (see I10).

**The migration also pays for the one field `scores.json` never stored.** Arrival
time is already in git: the file is append-only, so the first commit in which a key
appears *is* its arrival date.

- Walk `git log --format=%H -- pipeline/data/scores.json` **oldest → newest**, parse
  each blob with `git show <sha>:pipeline/data/scores.json`, and assign a date only
  when the key is still unset. First appearance wins, and the walk can stop as soon
  as every key is assigned. (Newest → oldest, overwriting while the key is present,
  gives the same answer with more writes.)
- Cost: ~50–100 commits × 3.4 MB parses. Seconds, once.
- **Call it `added_at`, meaning "indexed at".** Nothing exists before the first
  commit, so the earliest cohort all share that date. Nothing may claim to be a
  crawl date.
- **Abort on a rewrite.** A commit whose key count is unchanged but whose keys
  changed is a reordering, not an append — every date would collapse onto it.
- **Prefer the request rows where they overlap:** `data/requests.json` already
  carries a real `added_at` from the moment a request was validated.
- The same pass yields `last_seen` per key, which is I10's other column.

### I8 — Embeddable SVG badges — **accepted**

`/badge/learn/machine-learning.svg`, generated at build: a course's score, one
file, no JS. Distinct from the bookmarklet's JSON lookup — this is for other
people's pages.

### I9 — Compare two courses — **accepted**

Client-side over `scores.json`: pick two, see scores and dissents side by side.
No build explosion, no new data.

### I10 — Rot index — **parked**

Courses that vanished or stopped updating. `error` records hint at it, and "most
of my 2020 courses didn't survive" is a real observation from a crawl. Needs I7 to
be a trend rather than a snapshot — the same git walk that backfills `added_at`
yields `last_seen` per key, which is the other column this needs.

### I11 — The request queue — **shipped**

A visitor asks for a course that isn't indexed; the row is a job; the nightly
drain resolves it. Nothing scrapes from a server, ever.

**Shape, as built:** Turso holds only the inbox, and the pipeline never writes back
to it. `pipeline:demand` reads pending rows, verifies each link against Coursera,
resolves instructors to their course lists and programs to their members, appends
new keys to `sources.json` / `programs.json`, and merges the ask into
`data/requests.json` with `added_at`. `/wanted` and `/feed.xml` derive state by
joining that list against `scores.json` / `groupings.json`: a score means
fulfilled, no score means waiting. No status machine, no `crawled_at`.

**Decisions worth keeping**

- **No email.** Collecting an address means a legal basis, a privacy notice, a
  deletion path and a processor. `/wanted` plus a feed needs none of that.
- **No moderation, so no realtime.** The queue is a nightly batch for exactly this
  reason.
- **The ask list lives in the repo, not the database.** 12 rows today; if it
  outgrows git, that's I7's problem.

### I12 — Real course thumbnails — **rejected**

Coursera's JSON-LD `image` is the *provider* logo, `og:image` is a generic
placeholder, and the real thumbnails are stock photography with text legible only
at full size. The provider marks (`tile` for tables, `full` for course pages)
carry the identity better, are self-hosted, and cost one download per provider.
For descriptions, we take what `syllabus-description-content` shows before its
"read more".

---

## E. Design notes worth keeping

### The dissent as a pull quote

The course page renders the most-upvoted critical review as a plain `blockquote`.
The upgrade is typographic, not structural: hanging gold quotation mark, thin gold
rule, review text larger than body copy, source and upvotes under it. Unique to
Starisk in a way a theme colour cannot be.

### Chart identity

Keep the slate/gold series, standardize the language: thin axes, mono labels, no
default chart chrome, annotate "the gap" on the scatter. `/findings` is the
reference implementation — the rest of the site should look like it was drawn by
the same hand.

---

**LLM Q&A over the reviews — parked.** A small local model answering "why did this
course get 5 stars" or "what do people complain about" without exposing excerpts.
Interesting, and still the wrong order: it needs the dataset (I6) to be worth
anything.

---

## Order of work

1. **I2 quadrants** — the data is already in `scores.json`; only the surface is
   missing, and it pairs with the low-sample story.
2. **Low-sample labels** — ~10 blind labels on low-sample courses, then `k` stops
   being a guess. Same set as I5's calibration.
3. **I6** — publish the dataset. Outlives the site, costs hours.
4. **I8, I9** — the cheap ones, whenever.
5. **I10** — only after I7.

---

## Blog

- Short posts about groups of courses on one subject: "best R courses on
  Coursera", "Python for data science".
- Where I took the course, compare my experience with the official rating —
  "what I learned vs. what the stars say".
- Highlight the most contested courses (high spread, low score) and analyse why.
- Profile instructors off `/instructors`: who consistently teaches well?
- Discuss the limits of upvote-weighted reviews and how to read them.
- Feature the popular-and-well-rated courses and say what makes them stand out.
