# Nightly crawl

One unattended run: read the request queue from Turso, check that Coursera still
parses, crawl, rebuild the derived data, then publish a branch and open a pull
request against `develop`. Production is untouched until you merge.

**The container is stateless.** Every run clones `develop` into its own
filesystem, does the work, publishes, and exits; the clone dies with the
container. Only one volume survives: `starisk-state`, holding the page cache and
the run record. The host supplies three things and nothing else: the image,
`/etc/starisk/env`, and a cron line.

```mermaid
graph TD
    A[cron 03:30] --> B[docker run --rm]
    B --> C[clone --depth 1 develop]
    C --> D[nightly: queue, smoke, crawl, derive, gate]
    D --> E[new branch: data/crawl-STAMP]
    E --> F[git push origin HEAD]
    F --> G[open PR, close older ones]
```

The push is a **create**: the branch is named after the run, so the ref is new
and git has no non-fast-forward case to refuse. No rebase, no `--force`, no lease,
and nothing that depends on what happened to last night's branch. Merging,
squashing or deleting it afterwards changes nothing for the next run.

The corpus is not state: it comes from `develop` with the clone and goes back out
as a branch. The volume holds only the page cache (`STARISK_CACHE`) and the run
record (`STARISK_LOGS`), so losing it costs a night's worth of fetching, not data.

## Try it locally

Same image, same behaviour — only the trigger differs.

```sh
# Config, connectivity and the live pages. Writes nothing, needs no .env.
ops/run.sh --dry-run

# The whole pipeline, no commit, no push.
ops/run.sh --no-git --limit 1

# Throw the accumulated corpus away and start from an empty state.
docker compose -f ops/compose.yml down -v
```

Your working copy is never mounted, so none of this touches it.

## Deploy

```sh
# 1. Somewhere to build from. A clone in your home is fine.
git clone -b develop https://github.com/MatiasAgelvis/starisk.git ~/src/starisk
cd ~/src/starisk

# 2. The secrets. Any path works; --env takes it relative to the repo or absolute.
sudo ./ops/setup.sh --env .env --check
```

That leaves four things on the host — the image, the `starisk-state` volume,
`/etc/starisk/env`, one cron line — and no compose file. The line it installs:

```cron
30 3 * * * docker run --rm --init --env-file /etc/starisk/env -v starisk-state:/state starisk-nightly 2>&1 | logger -t starisk-nightly # starisk-nightly
```

`STARISK_CACHE=/state/cache` and `STARISK_LOGS=/state/logs` come from the image, so
the cron line does not repeat them.

Root is there for the Docker socket, nothing else: it runs that fixed command,
the env file is root-owned `600`, and the image is immutable.

With mise on the box, the same commands are tasks:

```sh
mise run ops:stats                  # what /state holds
mise run ops:dry                    # config + live checks, nothing written
mise run ops:rehearse -- --limit 20 # crawl for real, publish nothing
mise run ops:run                    # the real run: commit, push, PR
mise run ops:last                   # the last run's record
mise run ops:log                    # the last day of journal output
```

Output goes to the journal, which already rotates: `journalctl -t starisk-nightly`.
The pipe hands the exit status to `logger`, so cron never sees a failure — that is
fine, `last-run.json` is the signal. If the box has no `logger`, redirect to a file
and add a logrotate entry for it instead.

`logs/last-run.json` lives in the state volume:

```sh
docker run --rm -v starisk-state:/state --entrypoint cat \
  starisk-nightly /state/logs/last-run.json
```

Cron does not catch up a run missed while the box was off, and it does not need
to: the crawl is staleness-based, so the next run picks up whatever was skipped.
A night with no run is a night with no push, and the next push carries the whole
snapshot anyway.

## Day to day

- **The pull request.** `Nightly crawl`, from `data/crawl-<stamp>` into `develop`.
  One per run; the bot closes the previous one and deletes its branch, so there is
  ever one open. Merge it however you like — squash included — and delete the
  branch. Nothing depends on it afterwards.
- **ntfy.** Silent when nothing changed, a digest when something did, high
  priority on failure. `last-run.json` is written in the silent case too, so a
  dead cron looks different from a quiet week.
- **Failures.** Every failed fetch or parse is one line in the journal, with the
  course key and the message. The exit code says *whether* something broke; the
  journal says *what*.
- **Retired courses.** Coursera retires courses and the slug then answers 404
  forever. The crawl records that in `pipeline/data/retired.json` and stops
  asking, so a dead course cannot keep consuming the nightly budget; deleting an
  entry is how you ask for the course to be tried again. A course we already
  scored keeps its record — the score was true on the day it was measured.
  Retired slugs never trip the gate, and `expand` will not re-add them from a
  profile that still lists them.
- **Updating the job.** Merge to `develop`. The next run clones it, so the code
  that runs is the code you merged. Rebuild the image only when the entrypoint or
  runtimes change: `sudo ./ops/setup.sh --env .env`, or
  `docker build -f ops/Dockerfile -t starisk-nightly .`.

## Exit codes

| Code | Status | What it means |
|---|---|---|
| 0 | ok | Committed and published (or dry run passed) |
| 10 | nothing | Ran, changed nothing, no commit, no notification |
| 20 | refused | A gate tripped; read `reason` in `last-run.json` |
| 30 | partial | Committed, but with a caveat: Coursera rate-limited the crawl, a few records failed, or the push did not land |
| 40 | git | Clone, commit or push failed — the message names which |
| 50 | smoke | A live page stopped parsing — nothing was crawled |
| 60 | config | A required variable is missing |
| 70 | failed | Anything unexpected |

## Flags

```sh
nightly                       # the real run
nightly --dry-run             # config + smoke only, writes nothing
nightly --no-git              # the pipeline, no commit and no push
nightly --limit 20            # smaller valve for one night
nightly --limit 0             # uncapped
nightly --no-push             # commit on the branch, stop before push/PR
nightly --offline             # re-parse the cache, no requests
nightly --env-file .env         # host runs: read a dotenv instead of exporting it
```

The container gets its environment from `--env-file` — `/etc/starisk/env` on the
box, `ops/.env` for the local compose path — so `--env-file` is for running the
module directly on the host:

```sh
mise run pipeline:nightly -- --env-file .env --dry-run
```

## First run on a fresh volume

Nothing to seed: the corpus comes from `develop` with the clone. Only the page
cache is empty, so the first run refetches the program pages the index needs —
roughly 25 requests, once.

## When something goes wrong

**`40 git`** — the clone, the commit or the push failed in a way that left nothing
published. There is no rebase and no force, so there is nothing half-applied to
repair. The clone is gone, so the crawl's work is lost: the journal has the error
line that names the cause, and the next run re-crawls from the stalest course.

**`20 refused`** — the run produced something it did not trust: courses
disappeared, the scored count dropped by more than five, more than a fifth of the
fetched records failed, or a file outside `pipeline/data` and `web/src/data`
changed. The clone is discarded with the container, so the refused data is gone
too — the journal lines are the record. Courses that answer 404/410 are *not*
refusals: they are retired (see below).

**`50 smoke`** — a Coursera page stopped parsing. Each run checks a normal
course, a low-sample course, and a program page before crawling, so this fires
early instead of after an hour of cache writes. Reproduce with:

```sh
cd pipeline && STARISK_LIVE=1 python3 -m unittest tests.test_live
```

**`30 partial`** — Coursera rate-limited us partway through, a few records failed
(fetch or parse), or the push failed. A handful of failures is weather, not a
broken adapter, so the good data is published and the failures are listed one per
line in the journal. The crawl is cumulative: the next run picks up whatever was
skipped.

**Login prompt / `could not read Username`** — `GITHUB_TOKEN` is missing or
expired. The token is read from the environment at push time and is never written
to the clone's `.git/config`.

## Migrating from the volume-clone layout

The old job kept a clone in the `starisk` volume and rebased `data/crawl` every
night. Nothing in it is reused: delete the volume and the branch.

```sh
docker volume rm starisk
git push origin --delete data/crawl     # if it still exists
```

Nothing has to be carried over: the corpus is in git. The first crawl after the
switch just refetches what it needs, because the cache is not.
