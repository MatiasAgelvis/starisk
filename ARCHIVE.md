# Archive

Threads from [`IDEAS.md`](IDEAS.md) whose work is done, or that were rejected.
Kept because the reasoning is reusable; **nothing here is a to-do**.

Anchors are stable, so older notes that link to an idea still resolve.

---

## I1 — The bookmarklet badge — **shipped**

A draggable `javascript:` link. On a Coursera page, clicking it reads
`location.pathname`, fetches the compact lookup, and injects a badge next to
Coursera's headline rating.

**Why it was the right first product:** no store, no manifest, no permissions
prompt, no publish cycle. A bookmarklet is the only distribution channel that
requires zero trust from a stranger, and it survives the MV3 tax entirely.

**What shipped:** `/data/badge.json` — five fields per course instead of the whole
record, against 3.45 MB (800 KB gzipped) for `scores.json`, which stays the dataset
download. `/request` is the same-origin write path (the edge function only answers
its own origin, and a JSON body from another site needs a preflight it doesn't
implement), and `/bookmarklet` keeps its source in `lib/` percent-encoded into the
drag target, exercised by `scripts/bookmarklet.test.mjs` against a stubbed DOM.

**Why it was viable at all:** Coursera sends `content-security-policy:
frame-ancestors 'self'` and nothing else — no `script-src`, no `connect-src`, no meta
CSP — so neither the `javascript:` URL nor a cross-origin fetch is restricted, and
both of our data endpoints answer `access-control-allow-origin: *`.

**Settled since**

- **Batch asks.** `PER_HOUR` was raised from 6 to 24 per visitor: Coursera's results
  page appends cards as you scroll, so one page can legitimately ask for a couple of
  dozen. The site-wide daily cap is the real ceiling on abuse.
- **Discovery.** It lives in the footer as *"The score, on Coursera's own pages."*
  Deliberately quiet: the site's tone is academic, and anything louder reads as
  SaaS. Revisit only if someone says they couldn't find it.

---

## I4 — The scatter — **shipped**

`/findings` is the finding: the histogram of both distributions on one axis
(with the empty low-rated zone boxed, and the share Starisk disagrees on), then
every course plotted on the same scale. That replaced a table of numbers with an
argument, which was the point.

The quadrant view was folded in rather than shipped as its own page: score on x,
spread on y, four named cells, courses under 15 readable reviews left unlabelled,
and the leaderboard filters on the same cells.

---

## I11 — The request queue — **shipped**

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
- **The ask list lives in the repo, not the database.** A couple of rows today; if
  it outgrows git, that's I7's problem.

---

## I12 — Real course thumbnails — **rejected**

Coursera's JSON-LD `image` is the *provider* logo, `og:image` is a generic
placeholder, and the real thumbnails are stock photography with text legible only
at full size. The provider marks (`tile` for tables, `full` for course pages)
carry the identity better, are self-hosted, and cost one download per provider.
For descriptions, we take what `syllabus-description-content` shows before its
"read more".
