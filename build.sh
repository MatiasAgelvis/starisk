#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

# The pipeline writes scores.json; the site renders a copy of it at build time.
cp pipeline/data/scores.json web/src/data/scores.json

cd web
npm run build
