#!/bin/sh
# Install the nightly job on this box: image, state volume, secrets, cron.
#
#   sudo ./ops/setup.sh --env .env.prod            # install or update
#   sudo ./ops/setup.sh --env .env.prod --check    # ...then run a dry run
#   sudo ./ops/setup.sh --env .env.prod --force    # replace the installed env
#
# Safe to re-run: the image is rebuilt, an existing corpus is kept, an existing
# env file is kept unless --force, and only this script's cron line is replaced.
# Root is needed for the Docker socket and nothing else.
#
# Overrides: STARISK_ENV_FILE (installed path, default /etc/starisk/env),
# STARISK_SCHEDULE (default "30 3 * * *").
set -eu

REPO=$(cd "$(dirname "$0")/.." && pwd)
IMAGE=starisk-nightly
VOLUME=starisk-state
ENV_FILE=${STARISK_ENV_FILE:-/etc/starisk/env}
SCHEDULE=${STARISK_SCHEDULE:-"30 3 * * *"}
MARK="# starisk-nightly"

usage() {
  sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'
}

force=0
check=0
env_source=
while [ $# -gt 0 ]; do
  case "$1" in
    --force) force=1 ;;
    --check) check=1 ;;
    --env)
      shift
      env_source=${1:?--env needs a path}
      ;;
    --env=*) env_source=${1#--env=} ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo $0 --env <path>" >&2; exit 1; }
[ -n "$env_source" ] || { echo "missing --env: e.g. --env .env" >&2; exit 2; }
case "$env_source" in
  /*) ENV_SOURCE=$env_source ;;
  *) ENV_SOURCE=$REPO/$env_source ;;
esac

command -v docker >/dev/null 2>&1 || { echo "docker is not installed" >&2; exit 1; }
command -v logger >/dev/null 2>&1 ||
  echo "[setup] warning: logger not found; cron will fail to write its log" >&2

echo "[setup] building $IMAGE"
docker build -f "$REPO/ops/Dockerfile" -t "$IMAGE" "$REPO"
docker volume create "$VOLUME" >/dev/null

if [ -f "$ENV_FILE" ] && [ "$force" -eq 0 ]; then
  echo "[setup] keeping $ENV_FILE (--force to replace)"
else
  [ -f "$ENV_SOURCE" ] || { echo "[setup] no such env file: $ENV_SOURCE" >&2; exit 1; }
  mkdir -p "$(dirname "$ENV_FILE")"
  cp "$ENV_SOURCE" "$ENV_FILE"
  chown root:root "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "[setup] installed $ENV_FILE from $ENV_SOURCE"
fi

for key in TURSO_DATABASE_URL TURSO_AUTH_TOKEN GITHUB_TOKEN; do
  grep -q "^$key=" "$ENV_FILE" || echo "[setup] warning: $key missing from $ENV_FILE" >&2
done
grep -q '^NTFY_URL=' "$ENV_FILE" ||
  echo "[setup] note: no NTFY_URL, so failures only reach the journal" >&2

LINE="$SCHEDULE docker run --rm --init --env-file $ENV_FILE -v $VOLUME:/state $IMAGE 2>&1 | logger -t starisk-nightly $MARK"
{
  crontab -l 2>/dev/null | grep -vF "$MARK" || true
  echo "$LINE"
} | crontab -
echo "[setup] cron: $LINE"

if [ "$check" -eq 1 ]; then
  echo "[setup] dry run"
  docker run --rm --init --env-file "$ENV_FILE" -v "$VOLUME:/state" "$IMAGE" --dry-run
fi
