# Nightly crawl on the homelab box

One unattended run: read the request queue from Turso, check that Coursera still
parses, crawl, rebuild the derived data, then commit on a bot branch and keep a
pull request open against `develop`. Production is untouched until you merge.

The box is the right place for this because it has the residential IP and the
notification channel; nothing here needs to run on the site's host.

## One-time setup

```sh
# 1. The clone the job owns. Not your dev checkout.
git clone -b develop https://github.com/MatiasAgelvis/starisk.git /srv/starisk

# 2. The secrets.
cd /srv/starisk/ops
cp .env.example .env
$EDITOR .env            # Turso, GitHub token, ntfy topic

# 3. The image. It contains no code, so this is a one-time step.
docker compose build

# 4. A rehearsal: config, connectivity, the live pages. Writes nothing.
docker compose run --rm nightly --dry-run

# 5. The timer.
sudo cp systemd/starisk-nightly.service systemd/starisk-nightly.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now starisk-nightly.timer
```

`ops/.env` is gitignored (`.env*`), so it never enters the repository.

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
  dead timer looks different from a quiet week.

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
docker compose run --rm nightly                 # the real run
docker compose run --rm nightly --dry-run       # config + smoke only
docker compose run --rm nightly --limit 20      # smaller valve for one night
docker compose run --rm nightly --limit 0       # uncapped
docker compose run --rm nightly --no-push       # commit on the branch, stop
docker compose run --rm nightly --offline       # re-parse the cache, no requests
```

`--offline` is for adapter fixes: after changing a selector, re-score the cached
pages instead of re-fetching the corpus from the one residential IP.

## Why systemd and not cron

Both can run a command on a schedule; the differences that matter here are:

- **Catch-up.** A cron job missed while the box was off is simply missed.
  `Persistent=true` runs it once when the box comes back, which is what you want
  for a crawl that tracks staleness.
- **Logs.** `journalctl -u starisk-nightly` keeps a run's output, its exit code
  and when it happened, without a `>>` redirect and a rotation rule.
- **State.** `systemctl status` tells you the last result and the next run time.
  With cron, "did it run?" is a grep through mail and syslog.
- **Overlap.** `Type=oneshot` plus the job's own lock file means a slow night
  cannot start a second copy.

If you would rather keep cron, this is the equivalent line:

```cron
30 3 * * * cd /srv/starisk/ops && /usr/bin/docker compose run --rm nightly >/dev/null 2>&1
```

## When something goes wrong

**`40 git`** — the clone has local changes, or `data/crawl` no longer rebases
onto `develop`. The usual cause is a hand edit on the box. The run leaves the
branch alone rather than resolving data conflicts by guessing:

```sh
cd /srv/starisk && git status && git stash   # or commit the edit properly
```

If the rebase itself conflicts, the same applies: resolve it by hand once, then
let the timer continue.

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
