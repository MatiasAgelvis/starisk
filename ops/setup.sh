#!/bin/sh
# One-shot setup for the box. Run as root from the repo:
#
#   sudo ./ops/setup.sh            # build the image, install env + cron
#   sudo ./ops/setup.sh --check    # ...then run a dry run
#   sudo ./ops/setup.sh --force    # overwrite an existing /etc/starisk/env
#
# Idempotent: rebuilds the image, keeps an existing env file, and replaces only
# its own cron line. Nothing else on the host is touched: the clone, cache,
# logs and commits live in the volume.
#
# What root is for: the Docker socket. After this script, root runs one fixed
# `docker run` at 03:30 and nothing user-writable is in that path — the env file
# is root-owned 600 and the image is immutable.
set -eu

REPO=$(cd "$(dirname "$0")/.." && pwd)
IMAGE=starisk-nightly
VOLUME=starisk
ENV_FILE=/etc/starisk/env
MARK="# starisk-nightly"
SCHEDULE=${STARISK_SCHEDULE:-"30 3 * * *"}

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
}

force=0
check=0
for arg in "$@"; do
  case "$arg" in
    --force) force=1 ;;
    --check) check=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root: sudo $0" >&2
  exit 1
fi

command -v docker >/dev/null 2>&1 || {
  echo "docker is not installed" >&2
  exit 1
}
command -v logger >/dev/null 2>&1 ||
  echo "[setup] warning: logger not found; the cron line will fail to write its log" >&2

echo "[setup] building $IMAGE from $REPO"
docker build -f "$REPO/ops/Dockerfile" -t "$IMAGE" "$REPO"

mkdir -p /etc/starisk
chmod 700 /etc/starisk
if [ -f "$ENV_FILE" ] && [ "$force" -eq 0 ]; then
  echo "[setup] keeping existing $ENV_FILE (--force to replace)"
elif [ -f "$REPO/ops/.env" ]; then
  cp "$REPO/ops/.env" "$ENV_FILE"
  chown root:root "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "[setup] installed $ENV_FILE"
else
  echo "[setup] no ops/.env to install; create $ENV_FILE by hand" >&2
fi

if [ -f "$ENV_FILE" ]; then
  for key in TURSO_DATABASE_URL TURSO_AUTH_TOKEN GITHUB_TOKEN; do
    grep -q "^$key=" "$ENV_FILE" || echo "[setup] warning: $key is missing from $ENV_FILE" >&2
  done
fi

LINE="$SCHEDULE docker run --rm --env-file $ENV_FILE -v $VOLUME:/srv/starisk $IMAGE 2>&1 | logger -t starisk-nightly $MARK"
{
  crontab -l 2>/dev/null | grep -vF "$MARK" || true
  echo "$LINE"
} | crontab -
echo "[setup] cron installed:"
echo "        $LINE"

if [ "$check" -eq 1 ]; then
  echo "[setup] dry run"
  docker run --rm --env-file "$ENV_FILE" -v "$VOLUME:/srv/starisk" "$IMAGE" --dry-run
fi

echo "[setup] done. Journal: journalctl -t starisk-nightly"
