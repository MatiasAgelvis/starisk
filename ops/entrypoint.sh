#!/bin/sh
# The container's whole job: own the clone, bring it up to date, then run.
#
# Nothing on the host is checked out, switched or committed — the clone lives in
# the volume at /srv/starisk. On the first run there is no code in the volume, so
# the clone happens here; after that `starisk.checkout` does the git work, before
# the nightly process starts, so the code it imports is the code just fetched.
set -eu

REPO_DIR=/srv/starisk
REPO_SLUG=${GITHUB_REPO:-MatiasAgelvis/starisk}

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "[entrypoint] cloning https://github.com/$REPO_SLUG.git"
  git clone --branch develop "https://github.com/$REPO_SLUG.git" "$REPO_DIR"
fi

cd "$REPO_DIR/pipeline"
python -m starisk.checkout
exec python -m starisk.nightly "$@"
