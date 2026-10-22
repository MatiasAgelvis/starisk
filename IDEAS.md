# Ideas

Not commitments. A registry of threads that are worth keeping, with the reasoning
attached so future-me doesn't have to re-derive it.

**Status key**

- **accepted** — I want this; it's a matter of when.
- **parked** — deliberately not now. The reason is written down; revisit if the
  reason stops being true.
- **rejected** — no. Kept here so it doesn't get re-proposed.

The one thing that makes all of this more interesting is **corpus size**. At six
courses the site is a demo; the patterns below (scatter, quadrants) only earn
their space at ~40+. See I5, which is also the corpus the calibration needs.

## Registry

| # | Idea | Status | Cost | Depends on |
|---|------|--------|------|------------|
| I1 | Bookmarklet badge | accepted | hours | `scores.json` served as a static file |
| I2 | Polarization + quadrants | accepted | hours | one new pipeline field |
| I3 | Grievance vs. quality split | parked | — | — |
| I4 | The scatter (Coursera vs. Starisk) | accepted | a weekend | I5 |
| I5 | My 84 courses as the corpus + `/transcript` | accepted | a weekend | slug mapping |
| I6 | Publish the dataset | accepted | hours | I5 |
| I7 | SQLite as the pipeline store | parked (long-term) | — | dataset growth |
| I11 | Request queue: Turso + local drain | accepted (gated) | a weekend | a second requestor |
| I8 | Embeddable SVG badges | accepted | hours | — |
| I9 | Compare two courses | accepted | hours | — |
| I10 | Rot index | accepted (later) | — | score history |

---

## A. Where people already are

### I1 — The bookmarklet badge (the extension's ghost)

A draggable `javascript:` link. On a Coursera course page, clicking it reads
`location.pathname`, fetches `scores.json` from the deployed site, and injects a
small badge next to Coursera's headline rating.

**Why:** this is the original product, with the MV3 tax removed. No store, no
manifest, no permissions prompt, no publish cycle. A bookmarklet is the only
distribution channel that requires zero trust from a stranger.

**Sketch**

```js
// ~40 lines: match /learn/<slug>, fetch, insert a div, done.
const m = location.pathname.match(/^\/(learn|specializations)\/([^/]+)/);
```

**Requires**

- `scores.json` at a **stable URL**. Today it's imported at build time from
  `web/src/data/scores.json`, so it is *not* fetchable. `build.sh` must also copy
  it to `web/public/data/scores.json` (and the page can then be generated from
  the same file).
- CORS: **already solved on both hosts.** GitHub Pages and Cloudflare Pages
  both send `access-control-allow-origin: *` (verified with `curl -I`), so no
  `_headers` file is needed. The remaining blocker is Coursera's CSP.
- **A 5-minute CSP spike.** If Coursera's `connect-src` blocks a cross-origin
  fetch from a bookmarklet, this idea is dead on arrival. Test before building.

**Risk:** bookmarklets are niche and iOS Safari can't run them. Fine — this is a
love letter to the one power user who was ever going to install the extension.

---

## B. Making the score honest

### I2 — Polarization, and the honest tierlist

Compute the **weighted standard deviation** of stars at crawl time, store it next
to the score, and plot courses on two axes: score (x), disagreement (y).

|  | low disagreement | high disagreement |
|---|---|---|
| **high score** | Beloved | Hype vs. backlash |
| **low score** | Everyone agrees it's mediocre | **Contested** |

**Why:** this is the tierlist the original project wanted, done in a way that
can be defended. It turns the model's worst weakness — one 663-like review
owning a score — into a measured quantity instead of a hidden failure. The
"contested" quadrant is precisely the 5★-course-with-a-lynched-top-review
phenomenon that started all of this.

**Sketch:** `weighted_variance = Σ w·(stars − score)² / Σ w`, reported as a
standard deviation in stars. Then a quadrant label derived from two thresholds.

**Caveats**

- Noisy at 20 reviews. Label it as a vibe, not a statistic.
- Uses the *same* weights as the score, so a single dominant review inflates
  both. Worth reporting the unweighted std-dev alongside it as a sanity check.

### I3 — Grievance vs. quality split — **parked**

Two numbers per course: the course, and the platform (access, pricing,
certificates, refunds). Would directly answer "your score measures complaints
about the paywall, not the teaching" — the strongest critique of this project.

**Why parked:** too much complication for now (a lexicon, a validation set, a
second column, a second story). Revisit the moment the premise gets challenged
in public, or if calibration comes out weak. It's the honest escape hatch, not
the next feature.

---

## C. The corpus and the story

### I4 — The scatter

Coursera rating on x, Starisk on y, one dot per course, biggest gaps labeled.
*"The 5-star illusion, in one chart."*

**Why:** a portfolio piece needs a **finding**, not a feature. This is the
finding: at N courses, the official rating barely separates the courses the
reviews love from the ones they don't.

**Note:** a scatter of six points proves nothing. This lands at 40+.

### I5 — My 84 courses as the corpus + `/transcript`

Crawl **my own** courses instead of "popular" ones, and publish a page:
*"I took 84 courses in 18 months. Here's what my own tool says about them now —
and where I disagree with it."*

**Why:** solves corpus *and* narrative in one move. The leaderboard stops being
a generic Coursera list and becomes a personal dataset nobody else has. It is
also the calibration corpus — `calibration/courses.json` already holds the
credential list and an empty `label` per entry, so the same crawl feeds
**both** the site and the Spearman verdict on the premise.

**Friction (real)**

- Certificates are **credential** URLs, not course URLs. Slugs must be mapped.
  Test cheaply whether a credential page exposes the course link (or an
  `og:url`) before assuming this is a weekend.
- `calibration/courses.json`: 74 entries — 59 Coursera (52 single courses,
  7 specializations), 15 non-Coursera (SoloLearn 6, Santa Fe 5, Udemy 1, Stepik
  1, edX 1). Only the Coursera singles are crawlable today (D17).
- Specializations are the gap between 52 and the ~84 I actually took. Their
  constituent courses are the SPEC's open question; the `sdp-course-list-link`
  hook is the way in.

---

## D. The data asset

### I6 — Publish the dataset

A page for `scores.json` + aggregates, with a "cite this" line and a CSV dump.

**Why:** nobody else has upvote-weighted Coursera review data. This is the one
thing here that outlives the website, and it costs almost nothing.

**Constraint:** **excerpts only** for review text. Other people's words, and
the risk/benefit is bad. Aggregates and the single most-upvoted critical
excerpt are enough.

### I7 — SQLite as the pipeline store — **parked (long-term)**

`sqlite3` is in the Python stdlib, so this costs no dependency: courses,
reviews, crawl runs, score history. Later Turso, if it ever needs to be remote.

**Why parked:** the dataset is six courses. JSON is correct until it isn't.

**Constraint that must not drift:** SQLite stays a **pipeline-internal store**;
`scores.json` remains the published artifact and the seam (D7/D8). The front
never reads a database — the build reads the exported JSON. If SQLite starts
leaking into the site build, the seam is gone and the static property with it.

**Payoff when it's worth it:** score history becomes per-crawl rows instead of
git archaeology, and "courses that moved most" becomes one query.

### I11 — The request queue: Turso + local drain — **accepted, gated**

A visitor asks for a course that isn't indexed. The row is a **job**; the local
crawler drains it on its next run. Nothing scrapes from a server, ever.

**Why:** it's the only version of "live lookup" that survives D6 — a Worker (or
the browser) enqueues, the laptop crawls. A request is also the one piece of
state a static site provably cannot hold.

**Shape**

```
requests(slug, requested_at, status, crawled_at)
status: queued → crawled | failed | rejected
```

The crawler drains N rows per run with the throttle it already has, then flips
the status. The site can render a `/requests` page from the same table.

**Gates before building any of it**

1. **Cheapest is a mailto or a form, not an issue tracker.** A GitHub issue
 tracker is developer-speak for someone browsing Coursera, and it needs a
 **public, unarchived** repo — this one was archived, so the link 404'd. A
 `mailto:` with a prefilled subject/body costs nothing; Tally/Formspree have
 free tiers and work for anyone. One setting lives in `web/src/lib/config.js`,
 and with it null the page simply says the course isn't indexed.
2. **A public write needs a Worker in front.** A token held in the browser can't
 be rate-limited or validated, so: URL-shape check (`^/(learn|specializations)/`),
 dedupe by slug, per-IP cap. Otherwise the queue is someone else's spam cannon.
3. **Email notification is the expensive part — legally, not technically.** In
 the EU, collecting an address means a legal basis, a privacy notice, a deletion
 path, and a processor (Resend/Postmark) plus another secret. A public
 `/requests` page saying "queued 3 days ago" needs none of that. **Skip email
 until someone asks for it.**

**Trigger:** a second person requesting a course. Not before. Until then the
queue is a table with one row in it, which is I7's problem, not this one.

---

## E. Cheap wins, any time

### I8 — Embeddable SVG badges

`/badge/learn/machine-learning.svg`, generated at build. A course's score, one
file, no JS. Drop straight into my certificate mural.

### I9 — Compare two courses

Client-side over `scores.json`: pick two, see scores and dissents side by side.
No build explosion, no new data.

### I10 — Rot index

Courses that vanished or stopped updating. `error` records already hint at it,
and "most of my 2020 courses didn't survive" is a real observation from the
last crawl. Needs history (I7) to be a trend rather than a snapshot.

---

**LLM Q&A over the reviews.** : maybe with a small local sllm? A lightweight LLM could parse
review text to answer questions like "Why did this course get 5 stars?" or "What do people
complain about the platform?" without exposing raw excerpts. This would add
intelligence to the dataset while keeping the privacy constraint (excerpts only)
intact.

**Track course teachers.** Add instructor names and ratings to the dataset. This would
allow analysis of whether certain educators consistently produce high-quality content
across different platforms, and help users identify trusted voices in online education.

---

## Order of work

1. **CSP spike** for I1 (5 minutes, kills or greenlights the bookmarklet).
2. **I1** — copy `scores.json` to `public/`, `_headers`, bookmarklet. Small, and
   it makes the site feel alive.
3. **I2** — polarization in the pipeline, quadrants on the landing page.
4. **I5 spike** — do credential pages give up course slugs? This decides whether
   the corpus is a weekend or a grind.
5. **I5** — crawl, `/transcript`.
6. **I4** — the scatter, once there are 40+ courses.
7. **I6, I8, I9** — the cheap ones, whenever.
