#!/bin/sh
# One run of the nightly job, from nothing.
#
# The clone is a build step, not state: it is made here, used, and thrown away
# with the container. The only thing that survives is the state volume, which the
# pipeline reads and writes through STARISK_DATA — the JSON corpus and the page
# cache. Updating the crawler is therefore free: the next run clones whatever is
# on `develop`.
set -eu

WORK=${STARISK_WORK:-/work}
REPO_SLUG=${GITHUB_REPO:-MatiasAgelvis/starisk}
# The branch under test. `develop` in production; override it to run the container
# against an unmerged branch without merging anything.
BRANCH=${STARISK_BRANCH:-develop}

: "${STARISK_DATA:=/state}"
: "${STARISK_LOGS:=/state/logs}"
export STARISK_DATA STARISK_LOGS
mkdir -p "$STARISK_DATA" "$STARISK_LOGS"

if [ ! -d "$WORK/.git" ]; then
  echo "[entrypoint] cloning https://github.com/$REPO_SLUG.git ($BRANCH)"
  git clone --depth 1 --branch "$BRANCH" "https://github.com/$REPO_SLUG.git" "$WORK"
fi

cd "$WORK/pipeline"
exec python -m starisk.nightly "$@"
