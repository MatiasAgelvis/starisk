#!/bin/sh
# Run the nightly job from anywhere.
#
# Compose looks for its file in the *current* directory, so `docker compose run`
# from the repo root or from cron's $HOME fails with "no configuration file
# provided". This script is the entry point everywhere: local rehearsal, cron,
# and anything else that should not have to know where ops/ lives.
#
#   ops/run.sh --dry-run
#   ops/run.sh --no-git --limit 1
#   ops/run.sh                      # the real run
set -eu

cd "$(dirname "$0")"
exec docker compose run --rm nightly "$@"
