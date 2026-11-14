# Nightly crawl

One unattended run: read the request queue from Turso, check that Coursera still
parses, crawl, rebuild the derived data, then commit on a bot branch and keep a
pull request open against `develop`. Production is untouched until you merge.

The box is the right place for this because it has the residential IP and the
notification channel; nothing here needs to run on the site's host.

The image contains **no code**: everything it runs is the clone mounted at
`/srv/starisk`, including `ops/entrypoint.sh`. So `build` is a one-time step (or
one per runtime bump) and updating the job is `git pull`.

## Try it locally first

Same image, same command, same behaviour — the mount just points at your clone.
Everything goes through `ops/run.sh`, which changes into `ops/` first: Compose
looks for its file in the current directory, and that is the difference between
a working command and `no configuration file provided: not found` from the repo
root or from cron.

```sh
# Config, connectivity and the live pages. Writes nothing, needs no .env.
ops/run.sh --dry-run

# The whole pipeline on the current checkout: no branch, no commit, no push.
# It rewrites data/ in the working tree, so undo with git checkout afterwards.
ops/run.sh --no-git --limit 1
```

For a rehearsal of the real thing — branch prep, commit, push — use a scratch
clone and point `STARISK_REPO` at it, so the bot never touches your dev tree:

```sh
git clone -b develop https://github.com/MatiasAgelvis/starisk.git /tmp/starisk-test
STARISK_REPO=/tmp/starisk-test ops/run.sh --limit 1
```

`STARISK_REPO` defaults to the repo this compose file lives in, which is why the
plain commands above need no path. The image builds on first use; run
`docker compose build` in `ops/` (or add `--build`) after changing the Dockerfile.

## Deploy

```sh
# 1. The clone the job owns. Not your dev checkout.
git clone -b develop https://github.com/MatiasAgelvis/starisk.git /srv/starisk

# 2. The secrets.
cd /srv/starisk/ops
cp .env.example .env
$EDITOR .env            # Turso, GitHub token, ntfy topic, PUID/PGID

# 3. A rehearsal: config, connectivity, the live pages. Builds the image too.
/srv/starisk/ops/run.sh --dry-run

# 4. Cron (the user must be in the docker group).
crontab -e
```

```cron
30 3 * * * mkdir -p /srv/starisk/logs && /srv/starisk/ops/run.sh >> /srv/starisk/logs/nightly.log 2>&1
```

Cron does not catch up a run missed while the box was off, and it does not need
to: the crawl is staleness-based, so the next run picks up whatever was skipped.
`logs/nightly.log` grows by a page or so per run; rotate it or let it be.

## Day to day

- **The pull request.** `Nightly crawl`, from `data/crawl` into `develop`. It is
  updated (not recreated) every night and its body carries that run's counts.
  Merge it whenever; the next night starts a new one. **Merge or fast-forward it —
  never squash.** The branch is rebased nightly, so it recognises already-merged
  commits and drops them; a squash rewrites them, and the next rebase replays
  every historical run on top of `develop` and conflicts.
- **`logs/last-run.json`.** Status, timestamps, counts, commit, PR. This is the
  durable record; a health check can read it:

  ```sh
  jq -e '(.finished | fromdateiso8601) > (now - 129600)' /srv/starisk/logs/last-run.json
  ```

- **ntfy.** Silent when nothing changed, a digest when something did, high
  priority on failure. `last-run.json` is still written in the silent case, so a
  dead cron looks different from a quiet week.

## Exit codes

| Code | Status | What it means |
|---|---|---|
| 0 | ok | Committed (or dry run passed) |
| 10 | nothing | Ran, changed nothing, no commit, no notification |
| 20 | refused | A gate tripped; read `reason` in `last-run.json` |
| 30 | partial | Committed, but Coursera rate-limited the crawl |
| 40 | git | Dirty tree, diverged branch, or a failed push |
| 50 | smoke | A live page stopped parsing — nothing was crawled |
| 60 | config | A required variable is missing |
| 70 | failed | Anything unexpected |

## Flags

```sh
nightly                 # the real run
nightly --dry-run       # config + smoke only, writes nothing
nightly --no-git        # the pipeline on the current checkout, no commit
nightly --limit 20      # smaller valve for one night
nightly --limit 0       # uncapped
nightly --no-push       # commit on the branch, stop before push/PR
nightly --offline       # re-parse the cache, no requests
```

`--offline` is for adapter fixes: after changing a selector, re-score the cached
pages instead of re-fetching the corpus from the one residential IP.

## First run on a fresh clone

The page cache is gitignored, so a new box starts with none. The run fetches the
program pages it needs back before rebuilding the index (`groupings --fetch`),
which is why the first night makes ~25 extra requests and later nights make none.
If the cache is ever incomplete, the index write is refused rather than replacing
26 programs with a shorter list — that is the guard, not a failure to fix.

## When something goes wrong

**`40 git`** — the clone has local changes, or `data/crawl` no longer rebases
onto `develop`. The usual cause is a hand edit on the box. The run leaves the
branch alone rather than resolving data conflicts by guessing:

```sh
cd /srv/starisk && git status && git stash   # or commit the edit properly
```

**`20 refused`** — the run produced something it did not trust: courses
disappeared, the scored count dropped by more than five, three or more records
gained errors, or a file outside `pipeline/data` and `web/src/data` changed.
Look at `git status` on the box before merging anything.

**`50 smoke`** — a Coursera page stopped parsing. Each run checks a normal
course, a low-sample course, and a program page before crawling, so this fires
early instead of after an hour of cache writes. Reproduce with:

```sh
cd /srv/starisk/pipeline && STARISK_LIVE=1 python3 -m unittest tests.test_live
```

**`30 partial`** — Coursera rate-limited us partway through. The commit is
valid, the next run resumes at the stalest course. Two partials in a row with
almost no progress usually means the IP is being throttled harder.

**Login prompt / `could not read Username`** — `GITHUB_TOKEN` is missing or
expired. The token is read from `ops/.env` at push time and is never written to
the clone's `.git/config`.
