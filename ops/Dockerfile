# The nightly job's dependencies are the repo, cloned into a volume at run time,
# and the two runtimes it needs. Nothing is baked in: the image is upgraded by
# changing the runtimes, the job by merging to `develop`.
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

# The launcher has to live in the image: on a fresh volume there is no clone yet,
# so nothing can be read from /srv/starisk. It is the only script that is baked.
COPY ops/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /srv/starisk
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
