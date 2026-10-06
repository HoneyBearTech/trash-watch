# Base image pinned by version and multi-arch digest; Dependabot proposes updates to both.
FROM python:3.14.7-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d

# git fetches the TRaSH Guides. Its version comes from the base image's Debian release (pinned above);
# pinning the apt package as well would break on every Debian point release.
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# An unprivileged user. 1000:1000 is the first user on most Linux hosts, so data/ on the host belongs to
# them; docker-compose.yml can run the container as another uid/gid (TRASH_WATCH_UID / TRASH_WATCH_GID).
RUN groupadd --gid 1000 trash-watch \
    && useradd --uid 1000 --gid 1000 --no-create-home --home-dir /tmp --shell /usr/sbin/nologin trash-watch

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt
COPY trash_watch.py LICENSE ./

# No .pyc files (the root filesystem is read-only in compose); git's HOME is the writable /tmp.
ENV PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
USER 1000:1000
CMD ["python", "-u", "trash_watch.py"]
