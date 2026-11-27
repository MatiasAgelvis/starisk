#!/bin/sh
# The only launcher baked into the image.
#
# Everything else — the cache paths, the flags, the run itself — lives in
# `ops/entrypoint.sh` inside the cloned checkout. That means an ops change ships
# through a merge like any other code; rebuilding the image is only for the base
# image or the runtimes.
#
# Keep this file boring: it is the one thing a rebuild is required to change.
set -eu

WORK=${STARISK_WORK:-/work}
REPO_SLUG=${GITHUB_REPO:-MatiasAgelvis/starisk}
BRANCH=${STARISK_BRANCH:-develop}

if [ ! -d "$WORK/.git" ]; then
  echo "[bootstrap] cloning https://github.com/$REPO_SLUG.git ($BRANCH)"
  git clone --depth 1 --branch "$BRANCH" "https://github.com/$REPO_SLUG.git" "$WORK"
fi

exec sh "$WORK/ops/entrypoint.sh" "$@"
