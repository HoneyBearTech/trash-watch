# Changelog

All notable changes to trash-watch are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- A health check: `trash_watch.py --health` (the image's `HEALTHCHECK`, every 5 minutes) reports the container
  unhealthy when no check has completed for two intervals, so monitoring notices a watcher that crashed, hangs
  or keeps failing.

### Changed

- A one-time check (`RUN_ONCE=1`) exits with code 1 when it fails, so it can be scripted.
- `state.json` records the time of the last completed check in UTC (with a trailing `Z`).

## [0.1.1] - 2026-10-06

A security release for the image; trash-watch itself is unchanged.

### Security

- The image applies Debian's security updates when it's built and no longer contains pip, which fixes 11
  HIGH-severity vulnerabilities in the 0.1.0 image: OpenSSL (CVE-2026-75804, CVE-2026-84782) and PCRE2
  (CVE-2026-103111), plus urllib3, msgpack and setuptools' `pkg_resources` vendored inside pip (never run
  by trash-watch). Upgrade by pulling the new image.
- A weekly image scan (Trivy) of the image built from `main` and of the latest release, reported to code
  scanning (`scan.yml`).

## [0.1.0] - 2026-10-06

The first release.

### Added

- `--suggest` (`make suggest`): prints paste-ready Recyclarr YAML (trash_ids plus `assign_scores_to` with
  the guide's score) for every guide CF a profile doesn't score, grouped by profile. Console only: it never
  writes the config, notifies or saves state.
- The watcher (`trash_watch.py`), its `Dockerfile` and `docker-compose.yml`: a daily check of a Recyclarr
  config against the TRaSH Guides JSON for Radarr and Sonarr, with ntfy and Discord notifications sent
  only when the findings change.
- Settings and secrets come from a gitignored `.env` (template: `.env.example`); the Recyclarr config
  directory is set with `RECYCLARR_CONFIG_PATH` and always mounted read-only.
- Documentation in `docs/`.
- `IGNORE` in `.env`: trash_ids and profile names you skip on purpose.
- Tests (`tests/`, pytest, offline fixtures) for dead trash_ids, missing CFs, score mismatches, upstream
  changes between runs and Recyclarr's `!secret`/`!env_var` tags; `requirements.txt` (pinned PyYAML, now
  used by the image), `requirements-dev.txt` and a `Makefile` (`test`, `build`, `run-once`).
- Signed releases: on a version tag, a multi-arch image on GHCR signed keylessly with
  cosign, with an SBOM and SLSA provenance, and a GitHub Release with a source archive and signed checksums
  ([docs/verifying-releases.md](docs/verifying-releases.md)). `TRASH_WATCH_IMAGE` and
  `TRASH_WATCH_PULL_POLICY` in `.env` run a release image instead of building from the checkout.
- Project policies (`SECURITY.md`, `CONTRIBUTING.md`, `GOVERNANCE.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`)
  and docs for installing, upgrading, the user guide, the assurance case, dependencies and the roadmap.
- CI: ruff, yamllint, actionlint, hadolint, gitleaks over the history, tests with a 90 % coverage floor, an
  image build; CodeQL, OpenSSF Scorecard, dependency review, a DCO check and Dependabot. `make lint`.

### Changed

- Notifications are sized for a phone: findings grouped by instance and profile, at most 3 items per
  profile, about 20 lines in all, then a "plus N more" footer. The container log still has the full list.
- ntfy and Discord are sent separately, so a failure on one no longer skips the other.
- Profiles are checked against the CFs scored in that profile, not the whole instance; a guide CF that's in
  the instance but not scored in the profile is reported as "synced, but not scored".
- A profile whose `score_set` differs from its guide profile's is reported.
- Renamed profiles match a guide profile by a `score_set` only one guide profile uses; `PROFILE_MAP` accepts
  guide profile names as well as trash_ids, and an empty `PROFILE_MAP` no longer stops the watcher.
- Every run logs which guide profile each profile was checked against, and which weren't checked.
- `template:` includes are read (from Recyclarr's config-templates checkout) instead of skipped; unknown
  includes and instance keys are logged as warnings.
- Upstream-change fingerprints cover only what affects you (conditions, rename flag, scores in your score
  sets). The first run after upgrading re-baselines instead of reporting every CF as changed.
- The image's base is pinned by version and digest, PyYAML is installed with `--require-hashes`, and the
  image now includes `LICENSE`.
- The image runs Python 3.14 (was 3.12); CI tests on the same version.

### Security

- Notifier URLs that don't start with `https://` or `http://` are refused, so a mistyped `.env` value
  can't make trash-watch open a `file:` or other URL.
- The container runs as an unprivileged user (uid/gid 1000, or `TRASH_WATCH_UID`/`TRASH_WATCH_GID`) on a
  read-only root filesystem, with all Linux capabilities dropped and `no-new-privileges`.
- Names from the guides and the config are flattened to one line before they reach a notification or the YAML
  `--suggest` prints, so a line break in a custom format's name can no longer add keys to YAML you paste;
  profile names and trash_ids are quoted by PyYAML's emitter; guide scores must be integers. Discord messages
  no longer mention anyone (a name like `@everyone` stays text).
- Property-based tests (Hypothesis) and coverage-guided fuzzing (Atheris, `fuzz.yml`) of that code.

### Upgrading

- From a version that ran as root: `data/` is owned by root, so make it the container user's once, in the
  trash-watch directory, before starting the new version:
  `docker run --rm -v "$PWD/data:/data" busybox chown -R 1000:1000 /data` ([docs/upgrading.md](docs/upgrading.md)).
  Without it, trash-watch stops with an error that names this command.

[Unreleased]: https://github.com/HoneyBearTech/trash-watch/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/HoneyBearTech/trash-watch/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/HoneyBearTech/trash-watch/releases/tag/v0.1.0
