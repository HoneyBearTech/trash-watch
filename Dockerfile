# Base image pinned by version and multi-arch digest; Dependabot proposes updates to both.
FROM python:3.12.15-slim@sha256:05cda9777409a9c3ffddd94a4c476b79f0769a0b4857f0c7ed9226b6800b0d6f

# git fetches the TRaSH Guides. Its version comes from the base image's Debian release (pinned above);
# pinning the apt package as well would break on every Debian point release.
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.txt
COPY trash_watch.py LICENSE ./
CMD ["python", "-u", "trash_watch.py"]
