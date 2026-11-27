#!/bin/sh
# One run of the nightly job.
#
# This file is cloned at runtime, so changes here — cache paths, flags, defaults —
# take effect on the next run. Only `ops/bootstrap.sh` and the Dockerfile need an
# image rebuild.
#
# The checkout is a build step: cloned by the bootstrap, used, and thrown away
# with the container. The corpus is not carried anywhere either — it comes from
# the branch with the clone, and goes back out as a branch. Only two things
# survive, and neither is authoritative: the page cache and the run record.
set -eu

# Line-buffer stdout even when it is piped to logger: a nightly that looks stuck
# for ten minutes is indistinguishable from one that is fetching.
export PYTHONUNBUFFERED=1

WORK=${STARISK_WORK:-/work}

# The image may or may not set these. Setting them here means a stale image can
# still find the persistent volume; an env file still overrides both.
: "${STARISK_CACHE:=/state/cache}"
: "${STARISK_LOGS:=/state/logs}"
export STARISK_CACHE STARISK_LOGS
mkdir -p "$STARISK_CACHE" "$STARISK_LOGS"

# A cold cache is not fatal, but a cold cache every night is: print it once, at
# the top, so a mis-mounted volume is visible before the run spends its budget.
pages=$(ls "$STARISK_CACHE/pages" 2>/dev/null | wc -l | tr -d ' ')
echo "[entrypoint] cache $STARISK_CACHE ($pages page(s))"

cd "$WORK/pipeline"
exec python -m starisk.nightly "$@"
