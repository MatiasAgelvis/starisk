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
| Financial Markets | 4.8 | 3.0 |
| Neural Networks and Deep Learning | 4.9 | 3.2 |
| Learning How to Learn | 4.8 | 3.7 |

## What it is

- **A score.** `weight = √(1 + likes)`, `score = Σ(stars · weight) / Σ(weight)` —
  every reviewer is one voice, every upvote is worth more but not without limit.
- **The dissent.** Each course page shows the most-upvoted *critical* review, in
  full. Usually that's the honest paragraph buried under five hundred 5★ ones.
- **A leaderboard** of courses, and a lookup box that accepts a course *or* a
  teacher URL.
- **A teacher directory.** Who teaches what, and whether the catalogue holds up —
  the same measurement re-cut by instructor, with the range across their courses.
- **A program directory.** Specializations and Professional Certificates, with the
  courses they contain and the average score of those courses. Complete sets are
  shown by default.
- **A wanted list.** Courses readers asked for but Starisk has not scored yet, what
  came of the ones it has, and an Atom feed for the handful who follow them.
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

The crawler runs on a residential IP, on demand — no server and no cron; the only
database is the request queue (below). It reads Coursera's server-rendered review
cards (`data-e2e` hooks, `aria-label`s) with fallbacks to the page's JSON-LD, and
writes `scores.json`. A second, derived `groupings.json` records which courses
belong to which specialization or Professional Certificate; the site reads both.

## Working on it

[mise](https://mise.jdx.dev/) pins the toolchains and coordinates the tasks:

```sh
mise trust && mise install    # node 24, python 3.13
mise run setup                # install web dependencies
mise run pipeline:lint        # ruff
mise run pipeline:test        # python unit tests (stdlib only)
mise run pipeline:groupings   # rebuild the program index
mise run pipeline:seed-programs  # fetch seeded program pages, then rebuild
mise run web:dev              # astro dev server
mise run check                # lint + tests + a full site build
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
stalest-first so `--limit` always makes progress. Each course is **two**
requests — the reviews page and the landing page (the whole teaching team,
categories) — and both are cached, so `--offline` re-parses without touching the
network. The landing page's data blob carries every instructor, not just the ones
the hero links, so teachers cost no extra request. If Coursera rate-limits a run
(403/429), it **stops** instead of retrying — the next run resumes at the same
course.

### Growing the list

The list grows along edges that already exist, not by sampling the sitemap:

```sh
mise run pipeline:expand              # report both levers, writes nothing
mise run pipeline:expand -- --write   # extend sources.json
mise run pipeline:expand -- --instructors --limit 10
```

- **specializations** — my certificate specializations, resolved from Coursera's
  sitemap and confirmed by `og:title`, then expanded into their constituent
  courses (`data-e2e="sdp-course-list-link"`).
- **instructors** — every teacher already in `scores.json`, read from their
  Coursera profile (`data-e2e="course-card"`).

Both cost one cached request per parent page. Language variants (`-fr`, `-de`, …)
are dropped; a separately-created translation with its own slug is not (only one
so far — the landing page carries `inLanguage` if it ever matters).

Professional Certificates are not in the calibration file, so they are seeded
explicitly in `pipeline/data/programs.json`:

```sh
mise run pipeline:seed-programs   # fetch missing seeds, then rebuild groupings.json
```

To add specific courses by hand:

```sh
mise run pipeline:add -- https://www.coursera.org/learn/some-course
mise run pipeline:add -- learn/one learn/two three
mise run pipeline:add -- --from links.txt            # one per line, # comments
mise run pipeline:add -- --from - < links.txt        # or stdin
mise run pipeline:add -- --check learn/one learn/two # ask Coursera first
mise run pipeline:add -- --dry-run ...               # show, don't write
```

It accepts a full URL (including `/reviews`), `/learn/x`, or a bare slug,
dedupes against the list, and rejects anything that is not a course. Arguments and
`--from` can be combined in one call. The added courses are scored by the next
`pipeline:crawl`; nothing is fetched by `add` unless you pass `--check`.

### Demand queue

The landing page writes a missed course to Turso when someone asks for it. Turso
is only the inbox; the durable ask list is `pipeline/data/requests.json`, which
the site reads.

```sh
cd pipeline
python -m starisk.demand --env-file .env.prod            # dry run: what would change
python -m starisk.demand --env-file .env.prod --write    # verify, add to crawl list, update asks
```

`--write` reads the inbox, checks each new `learn/*` link, captures its advertised
title from the same page, appends it to `data/sources.json` (or seeds a
program/instructor), and merges the ask into `data/requests.json` with `added_at`.
It never updates Turso — the inbox stays read-only from the pipeline's side. Run
`mise run web:sync` to copy the ask list into `web/src/data/` without a full build;
`web:dev` and `web:build` do it automatically.

Everything after that is derived from files the site already ships:

- **waiting** — asks in `requests.json` that are not in `scores.json` /
  `groupings.json`
- **fulfilled** — asks that are; score and final title come from those files

The ask-list `title` is only the pre-crawl display name captured during
verification. It is not written back to Turso.
- **feed** — fulfilled asks at `/feed.xml`, newest `added_at` first (50 max)

A key already in `requests.json` is not processed again. `name/*` stays in the
inbox and is printed for a human; it never reaches the public list. Courses
Coursera no longer serves are reported and left for the next run. Useful flags:
`--offline` (no link checks or program fetches), `--limit N`, `--min-requests N`.

`--env-file` is any file holding `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN`; the
explicit file wins over an exported variable, so a dev shell cannot silently
read production. A relative path is looked up in the current directory first,
then at the repository root — so `mise run pipeline:demand -- --env-file .env.prod`
finds a file kept at the top of the repo, with no copy inside `pipeline/`.
Without `--write`, nothing on disk changes (`--dry-run` says so explicitly).

Vercel's **Sensitive** variables cannot be pulled — `vercel env pull` writes the
literal `{SENSITIVE}`. For this file, mint a dedicated token instead:
`turso db show <db> --url` and `turso db tokens create <db>`.

- `learn/*` — checked against Coursera, then appended to `data/sources.json`.
- `instructor/*` — the profile is fetched and the courses it lists are added.
- `specializations/*`, `professional-certificates/*` — seeded in
  `data/programs.json`, the program page is fetched, and its courses are added.
- `name/*` — cannot become a slug without a Coursera search; printed for a human.

The intended cadence is one nightly run from a homelab container: `--write`, then
`pipeline:crawl` (see `TODO.md`). The crawl writes the scores and titles that
`/wanted` and the feed join against; there is no second reconciliation step.

For a throwaway database, `turso dev --db-file .turso/dev.db` serves the same
HTTP API on `127.0.0.1:8080`. Point `pipeline/.env.dev` at it:

```sh
turso dev --db-file .turso/dev.db          # terminal 1
```

```sh
# .env.dev, at the repository root
TURSO_DATABASE_URL=http://127.0.0.1:8080
TURSO_AUTH_TOKEN=dev
```

### Calibration

```sh
mise run pipeline:calibration                 # Spearman between my labels and the model
python -m starisk.calibration --label         # rate the mapped courses, one by one
```

The label prompt is **blind**: it never shows the model's score, because seeing it
would anchor the answer and turn calibration into confirmation.

### Deploying

The site is static files in `web/dist`. Any static host works; the settings are
root `web`, build `npm run build`, output `dist`. `npm run build` and
`npm run dev` first run `scripts/sync-data.mjs`, which copies
`pipeline/data/scores.json`, `pipeline/data/groupings.json` and
`pipeline/data/requests.json` into `web/src/data/` — so a fresh clone and a deploy
always reflect the last crawl and queue export, without anyone remembering to run
`build.sh`. If a pipeline file is absent (a deploy that ships only `web/`), the
committed copy is kept.

- **Vercel:** two setups work, but the **dashboard must match the config file**
  you are relying on — Vercel's Project Settings override `vercel.json`:

  | Root Directory | config read | dashboard fields |
  |---|---|---|
  | repo root | `/vercel.json` (install `npm ci --prefix web`, output `web/dist`) | all empty |
  | `web` | `web/vercel.json` (install `npm ci`, output `dist`) | all empty |

  The failing signature `npm ci can only install with an existing
  package-lock.json` with the command `npm ci --prefix web` means the build ran
  **inside `web/`** (Root Directory = `web`) while the dashboard still carried a
  `--prefix web` Install Command, so npm looked for `web/web/package-lock.json`.
  Clear **Install Command**, **Build Command** and **Output Directory**, then
  redeploy. There is no repo change that can outvote a dashboard command.

  Set `SITE_URL` in the project's environment to the deployment origin.

  The request queue (below) adds `web/api/course-request.js`, which only Vercel
  picks up when the Root Directory is `web`. Rooted at the repository instead,
  move that file to `api/course-request.js` — nothing else changes.
- **Cloudflare Pages:** root `web`, build `npm run build`, output `dist`. The
  static site works, but there is no Functions adapter, so the request button
  reports the queue as unavailable.
- **GitHub Pages:** a *project* site serves from `/starisk/`, so absolute links
  (`/learn/...`, `/logos/...`) would break. Use a custom domain, or set `base`
  and route internal links through `import.meta.env.BASE_URL` first.

- `SITE_URL=https://your.domain` sets the canonical/Open Graph origin
  (default: `https://starisk.pages.dev`).
- `/data/scores.json` is published as a file — the whole dataset, CORS `*`.
- Provider logos are committed in `web/public/logos/`, so no download runs at
  build time. `mise run pipeline:logos` fetches any that are missing and derives
  the `tile/` and `full/` sizes the tables and course pages draw. `--prune` drops
  the 160px lockup once a provider has both; the crawl keeps local logo paths, so
  neither step is needed *after* a crawl to keep `scores.json` honest.
- `web/public/_headers` sets caching for Cloudflare Pages (ignored elsewhere).

### Course requests

The landing page's lookup runs in the browser. When it misses, the result offers
**Request this course**, which `POST`s to `/api/course-request` — a Vercel Edge
Function in `web/api/`, with the logic in `web/src/lib/course-requests.js`. It is
the only server-side code in the project: it validates the name and writes it to
Turso over the HTTP API, with no driver and no Node built-ins.

The function lives under `web/`, so the Vercel project's **Root Directory must be
`web`**, the same directory the static build uses. If the project is rooted at the
repository instead, add `api/course-request.js` there with the same three lines,
importing `../web/src/lib/course-requests.js`.

Set three variables in the Vercel project (Production, Preview and Development):

| Variable | Value |
|---|---|
| `TURSO_DATABASE_URL` | `libsql://<database>-<org>.turso.io` |
| `TURSO_AUTH_TOKEN` | from `turso db tokens create <database>` |
| `REQUEST_SALT` | any random string; visitor IPs are hashed with it |

The function creates its own tables on first use:

- `course_requests` — one row per request (`key` unique, plus `query` and `kind`),
  with `requests` as the demand count and the first/last seen timestamps. This is
  an inbox, not a workflow: the pipeline reads it and never writes to it.
- `request_hits` — hashed visitor and window, which caps the pace at 6 requests
  per visitor per hour and 400 per day site-wide.

Read the inbox with:

```sh
turso db shell starisk \
  "select key, requests from course_requests order by requests desc"
```

Validation is shared with the browser (`web/src/lib/requests.js`): Coursera course
links, instructor profiles and typed names, with a length cap, control-character
stripping, a small unambiguous profanity list, and a refusal to store programs.
The function re-runs every check, because the browser is not a security boundary.
A link is stored as the key it produced (`learn/…`, `instructor/…`), not the URL
it was pasted from, so tracking parameters never reach the table.

`astro dev` does not serve functions. `mise run web:dev:api` runs `vercel dev`
instead, which serves the site and `/api/*` together; pull the variables first
with `vercel env pull .env.local`. For offline work, `turso dev --db-file
.turso/dev.db` exposes the same HTTP API on `127.0.0.1:8080`.

Edge Functions receive their environment at build time, so changing the Turso
token or the salt means a redeploy.

On a static-only host (Cloudflare Pages, GitHub Pages) the button says the list is
unavailable and everything else keeps working; wrapping the same
`handleCourseRequest` in that host's function format is the only change needed.

### Layout

```
pipeline/      Python — crawler, scoring engine, calibration
  starisk/     engine, adapter, fetch, crawl, rank, calibration, groupings
  data/        sources.json (what to crawl), scores.json (the seam),
               groupings.json (derived program index), programs.json (program seeds),
               requests.json (exported request queue)
  tests/       unittest, zero installs
web/           Astro + Svelte islands + Tailwind + daisyUI
  public/logos/  provider logos: tile/ and full/ marks, plus a lockup fallback
  src/pages/instructors/  the teacher directory (a derived view, not a crawl unit)
  src/pages/programs/     the program directory (derived from groupings.json)
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
