# Ideas

Not commitments. A registry of threads that are worth keeping, with the reasoning
attached so future-me doesn't have to re-derive it. Shipped and rejected threads
move to [`ARCHIVE.md`](ARCHIVE.md) once the work is done.

**Status key**

- **accepted** — I want this; it's a matter of when.
- **parked** — deliberately not now. The reason is written down; revisit if the
  reason stops being true.
- **partial** — shipped in part; what is left is named.
- **shipped** — done, and still described here because the reasoning matters.
  Older ones live in `ARCHIVE.md`.
- **rejected** — no. Kept so it doesn't get re-proposed.

The thing that makes all of this interesting is **corpus size**: 1,969 courses
indexed, 1,453 scored, 150 programs, 430 instructors (2026-11-26 — the nightly
moves these; `pipeline/data/stats.json` has the current counts). Quadrants,
per-instructor signal and per-subject posts only earn their space at this scale; at
six courses they were a demo.

## Registry

| # | Idea | Status | Note |
|---|------|--------|------|
| I1 | Bookmarklet badge | shipped | [archived](ARCHIVE.md#i1--the-bookmarklet-badge--shipped); batch asks capped at 24/h |
| I2 | Polarization + quadrants | shipped | folded into `/findings` and the table filters |
| I3 | Grievance vs. quality split | parked | the honest escape hatch |
| I4 | The scatter | shipped | [archived](ARCHIVE.md#i4--the-scatter--shipped); `/findings` |
| I5 | Transcript + calibration corpus | partial | `/background` ships, labels stuck at 29 |
| I6 | Publish the dataset | partial | JSON + `/data` ship; CSV and a citation line left |
| I7 | SQLite as the pipeline store | parked | JSON is correct until it isn't |
| I8 | Embeddable SVG badges | accepted | one file, no JS |
| I9 | Compare two courses | accepted | client-side over scores.json |
| I10 | Rot index | parked | needs I7 |
| I11 | Request queue | shipped | [archived](ARCHIVE.md#i11--the-request-queue--shipped) |
| I12 | Course thumbnails | rejected | [archived](ARCHIVE.md#i12--real-course-thumbnails--rejected) |

---

## A. Making the score honest

### I2 — Polarization, and the honest tierlist — **shipped**

`spread` and `spread_weighted` ship in every record; `/findings` plots the two star
distributions and the same scale side by side, and carries the quadrant view (score
on x, spread on y, four named cells at fixed 3.5 / 1.2 splits, with courses under
15 readable reviews left unlabelled). The leaderboard filters by the same cells, and
each course page says where it lands.

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

## B. The corpus and the story

### I5 — My courses as the corpus, `/background`, and calibration — **partial**

**Shipped:** `/background` lists the credentials (74 entries, 59 Coursera) and
`about` links to it. The corpus exists.

**Data:** `calibration/courses.json` holds 74 entries with a `label` each, **29
labelled**. That's the calibration set, and it is the thing blocking the
low-sample fix: the shrinkage weight `w = 1 - e^(-n/k)` with `k = 5` can't be
judged from 2 low-sample labels.

**Why it still matters:** it solves corpus *and* narrative in one move — the
leaderboard stops being a generic Coursera list and becomes a personal dataset
nobody else has — and the same crawl feeds the Spearman verdict on the premise.

**Measured (2026-10), still the most useful lesson here:** the specialization
lever was smaller than expected — 6 of 7 specializations resolved and only 8 of
their 25 constituent courses were new. The lever that grew the corpus was the
**teacher graph**: instructor profiles linked courses that the umbrellas didn't.
People cluster courses; parent products don't, because Coursera recycles them.

---

## C. The data asset

### I6 — Publish the dataset — **partial**

**Shipped:** `/data` and `/data/dataset.json` — courses with their counts and
identifiers, programs with their members and derived average, a schema table, CC
BY 4.0, about a megabyte. No review text, no logos.

**Left:** a CSV dump for people who don't want JSON, and a "cite this" line with
the version and date. Both are an hour's work and are what make the file usable
outside the site.

**Why it matters:** nobody else has upvote-weighted Coursera review data. This is
the one thing here that outlives the website.

**Constraint:** **excerpts only** for review text. Other people's words, and the
risk/benefit is bad. Aggregates and the single most-upvoted critical excerpt are
enough.

### I7 — SQLite as the pipeline store — **parked (long-term)**

`sqlite3` is stdlib, so this costs no dependency: courses, reviews, crawl runs,
score history. Turso later, if it ever needs to be remote — which it now partly is
(the request inbox).

**Why parked:** JSON plus git is correct until it isn't. The corpus is ~2,000
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
- Cost: ~50–100 commits × a few MB parses. Seconds, once.
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

---

## D. Design notes worth keeping

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

1. **Low-sample labels** — ~10 blind labels on low-sample courses, then `k` stops
   being a guess. Same set as I5's calibration, and only you can do it.
2. **I6 leftovers** — CSV dump and a citation line. An hour, and it makes the
   dataset usable.
3. **I8, I9** — the cheap surfaces, whenever.
4. **I3** — only if the premise gets challenged in public, or calibration comes out
   weak.
5. **I7**, then **I10** — history and rot, once JSON stops being enough.

Program coverage and the corpus edges are day-to-day work, not ideas; they live in
[`TODO.md`](TODO.md).

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
