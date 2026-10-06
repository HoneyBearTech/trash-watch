# Changelog

All notable changes to trash-watch are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

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
