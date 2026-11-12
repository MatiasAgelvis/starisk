#!/bin/sh
# One nightly run. The image holds no code: this script, like the pipeline it
# runs, comes from the mounted clone. Arguments are passed through to
# `starisk.nightly` (`--dry-run`, `--limit 20`, `--no-push`, `--offline`).
set -eu

cd /srv/starisk/pipeline
exec python -m starisk.nightly "$@"
