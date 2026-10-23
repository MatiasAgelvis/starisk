#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

# The deploy entry point. The data copy lives in web/package.json's `prebuild`
# (scripts/sync-data.mjs), so any `npm run build` — here, on Vercel, in CI —
# picks up the current pipeline/data/scores.json without a second mechanism.
cd web
npm run build
