# The nightly job's only dependency is the repo, mounted at /srv/starisk, so this
# image is just the two runtimes the pipeline and the data copy need.
#
# The pipeline has no third-party dependencies (see pipeline/pyproject.toml), so
# there is no pip install here. Node comes from the official image because
# web/scripts/sync-data.mjs is the only thing that needs it, and using the same
# major the repo pins keeps the container and `mise` interchangeable.

FROM node:24-slim AS node

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# libstdc++ / libatomic are what the copied node binary links against.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git \
      ca-certificates \
      libstdc++6 \
      libatomic1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node

WORKDIR /srv/starisk

# The script itself lives on the mount, like the code it runs. It is absent from
# the image on purpose: updating the job is `git pull`, never a rebuild.
ENTRYPOINT ["/srv/starisk/ops/entrypoint.sh"]
