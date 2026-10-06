# Base image pinned by version and multi-arch digest; Dependabot proposes updates to both.
FROM python:3.14.7-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d

# Debian's security updates for the base image's packages (the Python image can lag behind them, as it did
# for OpenSSL at 0.1.0), then git, which fetches the TRaSH Guides. Package versions come from the base image's
# Debian release (pinned above); pinning them as well would break on every Debian point release.
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# An unprivileged user. 1000:1000 is the first user on most Linux hosts, so data/ on the host belongs to
# them; docker-compose.yml can run the container as another uid/gid (TRASH_WATCH_UID / TRASH_WATCH_GID).
RUN groupadd --gid 1000 trash-watch \
    && useradd --uid 1000 --gid 1000 --no-create-home --home-dir /tmp --shell /usr/sbin/nologin trash-watch

WORKDIR /app
COPY requirements.txt .
# pip is only needed to install PyYAML; removing it drops its vendored packages (urllib3, msgpack, ...) and
# their vulnerabilities from the image.
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt \
    && python -m pip uninstall -y pip
COPY trash_watch.py LICENSE ./

# No .pyc files (the root filesystem is read-only in compose); git's HOME is the writable /tmp.
ENV PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
USER 1000:1000
CMD ["python", "-u", "trash_watch.py"]
