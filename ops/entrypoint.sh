#!/bin/sh
# One run of the nightly job, from nothing.
#
# The checkout is a build step: cloned here, used, and thrown away with the
# container. The corpus is not carried anywhere either — it comes from `develop`
# with the clone, and goes back out as a branch. Only two things survive, and
# neither is authoritative: the page cache (best effort) and the run record.
set -eu

# Line-buffer stdout even when it is piped to logger: a nightly that looks stuck
# for ten minutes is indistinguishable from one that is fetching.
export PYTHONUNBUFFERED=1

WORK=${STARISK_WORK:-/work}
REPO_SLUG=${GITHUB_REPO:-MatiasAgelvis/starisk}
# The branch to crawl from. `develop` in production; override it to run the
# container against an unmerged branch without merging anything.
BRANCH=${STARISK_BRANCH:-develop}

: "${STARISK_CACHE:=/state/cache}"
: "${STARISK_LOGS:=/state/logs}"
export STARISK_CACHE STARISK_LOGS
mkdir -p "$STARISK_CACHE" "$STARISK_LOGS"

if [ ! -d "$WORK/.git" ]; then
  echo "[entrypoint] cloning https://github.com/$REPO_SLUG.git ($BRANCH)"
  git clone --depth 1 --branch "$BRANCH" "https://github.com/$REPO_SLUG.git" "$WORK"
fi

cd "$WORK/pipeline"
exec python -m starisk.nightly "$@"
