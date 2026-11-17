# One run of the nightly job.
#
# The image is runtimes plus the launcher: Python for the pipeline, git to clone
# and publish, node for `web/scripts/sync-data.mjs`. No application code is baked
# in — the container clones `develop` at run time, so merging a fix to the
# crawler is all it takes to update the job.
#
# The pipeline has no third-party dependencies (see pipeline/pyproject.toml), so
# there is no pip install here.

FROM node:24-slim AS node

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STARISK_CACHE=/state/cache \
    STARISK_LOGS=/state/logs

# libstdc++ / libatomic are what the copied node binary links against.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git \
      ca-certificates \
      libstdc++6 \
      libatomic1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node

# A commit needs a committer identity, which a bare container has none of.
# System-wide so it applies to every git invocation.
RUN git config --system user.name "Starisk Bot" \
 && git config --system user.email "bot@matiasagelvis.com"

COPY ops/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /work
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
