# Starisk

**The true signal, under the rating.**

Coursera's ratings cluster between 4.5 and 4.9 stars. Almost nothing is bad, so
the headline number barely distinguishes a course worth a month of your life from
one that isn't. But the reviews underneath disagree with it: the reviews other
learners actually upvoted are often critical, and those upvotes are a signal the
star average throws away.

Starisk reads a course's most helpful reviews, weights each one by its upvotes,
and puts the result next to Coursera's number.

| Course | Coursera | Starisk |
|---|---:|---:|
| Financial Markets | 4.8 | 2.5 |
| Neural Networks and Deep Learning | 4.9 | 2.9 |
| Learning How to Learn | 4.8 | 3.6 |

## What it is

- **A score.** `weight = 1 + likes`, `score = Σ(stars · weight) / Σ(weight)` —
  every reviewer is one voice, every upvote is one more voice.
- **The dissent.** Each course page shows the most-upvoted *critical* review, in
  full. Usually that's the honest paragraph buried under five hundred 5★ ones.
- **A leaderboard** of courses, and a lookup box for a course link.
- **Not** a browser extension, not a product with accounts, not a claim about
  objective quality.

## What the score actually measures

**What the most-endorsed reviews say — not "true quality."** Read this as *how
contested a course is*, not as a verdict on the teaching. Upvoted reviews are
sometimes platform grievances (paywall, lost access, certificates) rather than
judgments about the course, and one review with 600 likes can move a score by
more than a point. This is a documented weakness, not a hidden one.

The site says this out loud on every page, because a score that pretends to be
neutral is the thing this project exists to argue against.

## The pipeline

```
  [ pipeline/ — Python ]                  [ web/ — Astro ]
  fetch → parse → score   ──scores.json──▶  static site, zero JS by default
  (run locally, on demand)    (the seam)    (deploy anywhere static)
```

The crawler runs on a residential IP, on demand — no server, no cron, no
database. It reads Coursera's server-rendered review cards (`data-e2e` hooks,
`aria-label`s) with fallbacks to the page's JSON-LD, and writes one JSON file.
Everything the site shows comes from that file.

## Working on it

[mise](https://mise.jdx.dev/) pins the toolchains and coordinates the tasks:

```sh
mise trust && mise install    # node 24, python 3.13
mise run setup                # install web dependencies
mise run pipeline:test        # python unit tests (stdlib only)
mise run web:dev              # astro dev server
mise run check                # tests + a full site build
```

Without mise, it's still plain: `python -m unittest discover -s pipeline/tests`
(inside `pipeline/`), `npm ci --prefix web`, and `./build.sh`.

### Crawling

```sh
mise run pipeline:crawl                # anything not scraped in the last 30 days
mise run pipeline:crawl -- --limit 10  # budget: at most 10 requests this run
mise run pipeline:crawl -- --force     # ignore freshness, refetch everything
```

Sources are normalised (`learn/x`, `/learn/x/`, a full URL and a bare slug are
one course), fresh records are skipped without a request, and work is ordered
stalest-first so `--limit` always makes progress. If Coursera rate-limits a run
(403/429), it **stops** instead of retrying — the next run resumes at the same
course.

### Deploying

The site is static files in `web/dist`. Any static host works; the settings are
root `web`, build `npm run build`, output `dist` (`build.sh` only adds the data
copy, which is already committed, so hosts can skip it).

- `SITE_URL=https://your.domain` sets the canonical/Open Graph origin
  (default: `https://starisk.pages.dev`).
- `/data/scores.json` is published as a file — the whole dataset, CORS `*`.
- Provider logos are committed in `web/public/logos/`, so no download runs at
  build time. `mise run pipeline:logos` fetches any that are missing.
- `web/public/_headers` sets caching for Cloudflare Pages (ignored elsewhere).

### Layout

```
pipeline/      Python — crawler, scoring engine, calibration
  starisk/     engine, adapter, fetch, crawl, rank, calibration
  data/        sources.json (what to crawl), scores.json (the seam)
  tests/       unittest, zero installs
web/           Astro + Svelte islands + Tailwind + daisyUI
  public/logos/  provider logos, downloaded once by the pipeline
calibration/   my own 74 credentials, for measuring the model
samples/       scratch space for live HTML snapshots (gitignored)
SPEC.md        the why: mission, non-goals, decision log
IDEAS.md       the registry of larger ideas, with reasoning
```

## History

This started as a 2021 Manifest v2 browser extension that never found a user and
could not be migrated to v3. The extension is archived at the tag
`legacy-mv2-extension` — `git show legacy-mv2-extension:source/content.js` — and
the thesis is the same one it had back then.

## License

Apache 2.0. See [LICENSE.txt](LICENSE.txt).
