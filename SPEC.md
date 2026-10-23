# Starisk — Spec

> Formerly Stellaid (the 2021 browser extension). The name is new; the thesis is
> the same.

> A living document. The north star, the goals, and the decisions — so future-me
> remembers *why*, not just *what*.

## 1. Mission

**Give Coursera courses an honest rating.** Paste a course link, see Coursera's
advertised score next to what students actually think — the signal hiding under
the inflated number.

One line: *"The true signal, under the rating."*

## 2. Context / origin

This revives a 2021 browser extension (Manifest v2) that never found users. The
extension is dead (MV2, and it scraped a DOM that has since rotted), but its
**thesis survives** and is still true:

> Official ratings are inflated — mass default-5★ reviews hide the honest,
> critical minority that other students upvoted. The "helpful" votes are the
> signal.

The new form is **not** an extension. It's a website + a data pipeline, and the
by-product (rating history over time) is a data asset nobody else has.

## 3. Goals

- **G1 — An honest score.** Compute a course score from its reviews, with a
  documented, defensible model.
- **G2 — The website.** Paste a Coursera link → get the score. This is the
  deliverable.
- **G3 — A leaderboard / tierlist.** Browse and sort popular courses.
- **G4 — Portfolio quality.** Presentation matters; it should look deliberate.
- **G5 — A renewable pipeline.** Local, on-demand crawl that can accumulate
  `scores.json` history over time.

## 4. Non-goals (explicitly out of scope)

- ❌ A browser extension.
- ❌ A commercial product / accounts / monetization. This is a portfolio piece.
- ❌ Real-time live scoring in v1 (server deferred).
- ❌ Scraping all of Coursera. Curated list first.
- ❌ Other platforms (Amazon, Reddit, Udemy…) for now. **Coursera only.**
- ❌ The homelab / any always-on server. Decided out of scope — the box ate
  5h and still isn't set up, and it is **not** a prerequisite for this project.

## 5. Architecture

Front and back are **separate**, joined by one file: `scores.json`.

```
   [ Python pipeline ]                    [ static site ]
   fetch → parse → score    ──scores.json──▶   Astro + Svelte islands
   (run locally, on demand)      (the seam)     (deploy to a static host)
```

- **Read path** = static. The site reads `scores.json`; no server, no DB.
- **No server, at all.** Not a homelab, not a monolith — v1 is pure static files.
  The crawler runs on my laptop, on demand; that is the only "server" involved.
- **Write path** ("request this course") is **deferred**. A static site can't
  write to a DB without *some* server-side trust anchor, so when this becomes
  real the options are: a GitHub-issue / mailto link (v1, zero infra), a
  **scoped Turso token used from the browser** (later), or a small serverless
  function. Seen from the crawler's side it is simply **a queue**: a row is a
  job, and the local pipeline drains it. That is the one genuinely tricky later
  decision; don't solve it now. (Design sketch: `IDEAS.md` I11.)

## 6. Decisions (the log)

| # | Decision | Why |
|---|----------|-----|
| D1 | Backend/pipeline in **Python** | The pipeline is a *data* job (fetch → parse → analyze); Python is the data language, and it's what I'm fluent in. Fluency × correctness point the same way. |
| D2 | Frontend in **Astro + Svelte islands + Tailwind 4 + daisyUI 5** | Content-first: static pages ship **zero JS**; only islands ship any. Component reuse for presentation. Svelte for the interactive bits. |
| D3 | **No Deno** | Announced Oct 2026: team → Cloudflare, ~1 year of support then development ends; Deploy shuts down in 6 months. Betting a new project on it would repeat the MV2 mistake. |
| D4 | **Static site**, not a monolith server (v1) | Read path needs no server; static is cheapest, most durable, best distribution. |
| D5 | Two toolchains in one repo is fine | Python for the pipeline, Node to build the site. Prior art: the docx→cards project already does Python + SvelteKit. |
| D6 | Crawl **locally, on demand** | Residential IP dodges Cloudflare's bot-challenge for free. Not nightly CI (datacenter IP risk). |
| D7 | `scores.json` is **the seam** | Keeps pipeline and site decoupled in code even though they ship together. |
| D8 | Reads from **static JSON**; writes (user data) to a **DB later** (Turso) | Keep user writes off the read path. |
| D9 | **Fail-safe crawl** | Atomic write; never overwrite good data with a broken parse; flag `stale`; alert when N parses in a row yield 0 reviews (adapter is stale). |
| D10 | Port the scoring **faithfully**; the 16 JS tests (tag `legacy-mv2-extension`) are the port spec | Don't silently change behavior. Keep the original model for reference; `SIMPLE` (`1 + likes`) as the default candidate. |
| D11 | Simplify the model where it doesn't earn its keep | Drop the inert time term; keep one real knob. Decide final model by *calibration*, not taste. |
| D12 | Parse Coursera's **semantic hooks** (`data-e2e`, `data-testid`, `aria-label`) + **JSON-LD fallback** | Verified on 8 live snapshots: server-rendered review cards carry **stars, likes and dates**; JSON-LD carries stars/dates but **no likes**. No DOM library needed; a repair is a selector change. |
| D16 | **DOM cards first, JSON-LD fallback** | Likes exist only in the review cards; some pages publish reviews only as JSON-LD. The fallback keeps them usable, at the cost of no likes (every weight collapses to 1). |
| D17 | **Single courses are the v1 unit** | Professional Certificate / specialization pages are inconsistent (some have no JSON-LD, some no reviews). Digging into their constituent courses is a later feature. |
| D18 | **Two requests per course**: the reviews page, then the landing page | Verified: `?page=2` and `?page=3` return **identical HTML** to page 1 — the param is ignored server-side, and paging is client-side. So the reviews page is the only one available without the internal API or a browser; it is sorted "Most Helpful" and the model weights by likes, so it *is* the signal. The landing page is the only place with `instructor` and `domains` (category); it is cached separately and throttled like everything else. |
| D13 | Calibrate against my own labeled courses (Spearman) | ~74 credentials parsed locally (`calibration/courses.json`); my gut ranking is the ground truth. |
| D14 | Deployment is **static-only**; no always-on server | Homelab detour cost 5h and still isn't up. Static is cheaper, more durable, and has no uptime/security/DDNS burden. The pipeline runs locally on demand. |
| D19 | **Root has no build system.** Node lives only in `web/`, Python only in `pipeline/`; mise coordinates tasks, `build.sh` is the deploy entry point | One lockfile, one toolchain per side, no root `package.json` to rot. mise is a convenience for humans, so a CI runner or static host needs only node + python. The 2021 extension toolchain (Parcel, jest, puppeteer, `xo`, 454 MB of `node_modules`) was archived at tag `legacy-mv2-extension` and deleted. |
| D20 | Provider logos are **self-hosted**: the pipeline downloads one file per provider into `web/public/logos/`, **no transcoding** | Hotlinking Coursera's image proxy leaks every visitor's IP to them, breaks all logos at once if the URL changes, and gives us no cache control. Measured: 4 unique logos for 6 courses, 33 KB total, ~160×60 PNGs shown at 56×32. Re-encoding buys nothing and would drag a non-stdlib encoder into a stdlib-only pipeline. Fail-safe: a logo that cannot be fetched keeps its remote URL. |
| D21 | Crawls are **incremental and polite**: sources normalised and deduped, records younger than `--max-age` (30 days) skipped without a request, work ordered stalest-first, `--limit` as a per-run budget | A growing list must not mean re-fetching everything, and the residential IP is the asset the project depends on. 403/429 raises `RateLimited` and **stops the run** instead of retrying; the next run resumes at the stalest course, so nothing is repeated and nothing is skipped. 404 is never retried — a retired course stays retired. |
| D15 | Write path **deferred** until there are real users | A static site can't write to a DB without a trust anchor; don't build an API for a feature nobody has used yet. Start with a mailto/GitHub-issue link if needed. |

## 7. The scoring model

Weights are the whole idea: **likes = evidence of engagement**, so a review the
crowd upvoted counts for more.

- **Faithful (original 2021):** `weight = (2 + likes)² · ageDays^0.3`,
  `score = 0.8·peer + 0.2·coursera`.
- **Simplified:** `weight = 1 + likes`,
  `score = Σ(stars·weight) / Σ(weight)`.
  *"Everyone is one voice; every upvote is one more voice."*
- **Calibrated (2026-10, the default):** `weight = √(1 + likes)`, same sum.
  Upvotes still matter — 80 likes counts about 5× a review with 2 — but one
  review can no longer own a course.

**Why sqrt:** on 29 courses I rated myself, Spearman against my gut was
**0.62** for `1 + likes`, **0.57** for the 2021 model, and **0.68–0.70** for
anything that compresses likes (sqrt, log, cap-at-10, or even ignoring votes).
Bootstrap: sqrt beats linear in 79% of resamples with overlapping CIs —
*suggestive, not proven*. The decision rests on the failure mode it removes
(one 663-like review owning a score), not on the point estimate.

On the sample fixture (`review.html`): Coursera **4.0** → original **1.9** /
simple **1.7**. The most-liked review is a 1★ takedown (`This is helpful (102)`).

Open: the final model may use size-aware shrinkage / effective sample size
(a course with 3,000 reviews isn't 3,000 independent opinions). **Decide by
calibration against my labels, not aesthetics.**

## 8. Data contract

`pipeline/data/sources.json` — the crawl list:
```json
["learn/machine-learning", "specializations/deep-learning"]
```

`scores.json` — the built artifact the site serves, keyed by `type/slug`:
```json
{
  "learn/machine-learning": {
    "slug": "learn/machine-learning",
    "title": "Supervised Machine Learning: Regression and Classification",
    "provider": "DeepLearning.AI",
    "coursera": 4.9,
    "starisk": 3.1,
    "spread": 1.63,
    "spread_weighted": 1.75,
    "reviews": 19,
    "reviews_total": 6214,
    "ratings_total": 32982,
    "rating_counts": { "1": 122, "2": 56, "3": 226, "4": 2391, "5": 30187 },
    "model": "simple",
    "scrapedAt": "2026-10-20T03:00:00Z"
  }
}
```

- `reviews` — cards we actually read (one page, ~20).
- `reviews_total` / `ratings_total` — the population, so the sampling is explicit.
- `rating_counts` — Coursera's full star distribution, from the embedded page data.
- `review_counts` — the same for the ~20 sampled reviews only.
- `spread` — unweighted std-dev of the sampled stars (contention).
- `spread_weighted` — the same with like weights; it *collapses* when one review
  dominates, which is informative but not a contention measure.
- Optional: `level`, `enrollment`, `low_sample`, `source: "jsonld"`, `error`.

## 9. Repo layout (target)

```
starisk/
  SPEC.md                     # this file
  pipeline/                   # Python — the back
    pyproject.toml
    starisk/
      __init__.py
      engine.py               # scoring (ported; DEFAULTS + SIMPLE)
      adapter.py              # HTML → reviews (2022 regex; BS4 in Phase 2)
      rank.py                 # Spearman
      calibration.py          # parse Certificates.md → labels; correlate
      fetch.py                # (Phase 2) http + throttle + retries
      crawl.py                # (Phase 2) sources.json → scores.json
    tests/                    # unittest, zero installs
    data/
      sources.json
      scores.json             # ← the seam
  calibration/
    courses.json              # 74 credentials; `label` = my gut score
  web/                        # Astro + Svelte + daisyUI — the front
    src/pages/
    src/components/
    src/layouts/
    public/data/scores.json   # scores.json copied here at build
    package.json
```

## 10. Roadmap

- **Phase 0 — Spec.** (this file)
- **Phase 1 — Port the core to Python.** ✅ Done: engine + adapter + rank +
  calibration; 16 tests green (`unittest`, zero installs); same numbers as the
  JS reference (4.0 → 1.9 original / 1.7 simple).
- **Phase 2 — Local crawl.** ✅ Adapter rewritten against live markup, plus
  `fetch.py` (stdlib HTTP, retries) and `crawl.py` (throttled, fail-safe merge,
  atomic write). 24 tests green.
- **Phase 3 — The site.** Astro: static leaderboard (build-time data) + lookup
  island (Svelte) + daisyUI presentation.
- **Phase 4 — Deploy.** Static host (Cloudflare Pages or GitHub Pages).
- **Phase 5 — Later.** "Request a course": a **mailto / form link** first (the
  audience isn't developers, and a GitHub issue link 404s on an archived repo —
  `web/src/lib/config.js` holds the one setting); a Turso request queue (browser
  with a scoped token, or through a small Cloudflare Worker) once someone other
  than me asks. Score history / trends.
- **Phase 6 — Optional.** Python notebooks over the history (the data asset).

## 11. Open questions

- Final model: `SIMPLE` vs shrinkage — decide by calibration.
- Static host: Cloudflare Pages vs GitHub Pages.
- Write path (deferred): none vs Turso-from-browser (scoped token) vs a small
  serverless function.
- **Live lookup: a Worker cannot scrape.** Its datacenter IP is exactly what D6
  avoids. If wanted, a Worker enqueues the slug and the local crawler picks it up
  on its next run — queued lookup, not live lookup.
- Professional Certificates / specializations: score their constituent courses
  and aggregate? (Landing pages expose `data-e2e="sdp-course-list-link"`.)
- Where course **slugs** come from (my certificates are credential URLs, not
  course URLs — the crawl list needs real slugs).
- Size and source of the initial crawl list.

## 12. Risks

- **Coursera markup fragility.** The adapter matches one DOM; it *will* break.
  Isolate it, test it, alert on breakage, verify against a live page early.
- **Bot-blocking.** Mitigated by residential IP + throttling.
- **ToS / copyright.** Portfolio/educational use; don't hammer; identify the UA.
- **Distribution** — the recurring bottleneck. The site + the story *are* the
  distribution. Plan the launch/writeup as part of the build, not after.

## 13. Principles (the north)

1. **Don't build on things that rot.** MV2. Deno. Prefer durable, simple
   foundations.
2. **Distribution is the bottleneck, not capability.** Choose paths where the
   artifact distributes itself.
3. **Finish small.** A working artifact beats a grand unfinished one.
4. **One source of truth.** Never implement the scoring in two languages.
5. **Keep the seam.** `scores.json` is the boundary; keep it clean, and the two
   halves can evolve or split later.
6. **Don't overthink the framework.** It isn't where the value is.
