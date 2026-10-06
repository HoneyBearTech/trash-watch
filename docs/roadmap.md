# Roadmap

What trash-watch intends to do over the next year (to October 2027), and what it deliberately won't do.
Plans change; this file is updated when they do, and larger items get a GitHub issue before work starts.
Suggestions are welcome in [Issues](https://github.com/HoneyBearTech/trash-watch/issues).

## Where it stands

trash-watch checks a Recyclarr config against the TRaSH Guides daily for Radarr and Sonarr: removed or
renamed CFs, CFs a guide profile has that a profile doesn't score, `score_set` and score differences, and
upstream changes that affect the config. It matches renamed profiles (`PROFILE_MAP`, a unique `score_set`),
honours deliberate choices (`IGNORE`), sends phone-sized notifications to Discord and ntfy, and prints
paste-ready fixes with `--suggest`. It has offline tests with a coverage floor and CI with linting and
secret scanning. No release has been tagged yet.

## Over the following year

**Releases and security**

- The first signed release (0.1.0) on GHCR, with SBOM and provenance ([verifying-releases.md](verifying-releases.md)).
- A non-root image, with an upgrade note for existing `data/` directories.
- `RUN_ONCE=1` exiting non-zero when a check fails, so a one-time check can be scripted.
- A scheduled image scan (Trivy) reported to code scanning.
- Type annotations throughout, and ruff's full rule set.

**Security and project health**

- Make the repository public, with branch protection, private vulnerability reporting, and secret scanning
  with push protection turned on.
- The OpenSSF Best Practices badge (Passing, then Silver) and OSPS Baseline Levels 1 and 2.
- A healthy OpenSSF Scorecard: pinned dependencies, signed releases, code review on `main`.

**Checks**

- Recyclarr v8 `custom_format_groups`, so instances that use them get complete "missing" findings instead
  of a warning.
- Template includes from Recyclarr v8's template repository.
- An optional check of the guides' optional CF groups (opt-in, since many are deliberate choices).

**Operations**

- A health signal for monitoring (for example a log line or file a monitoring stack can alert on when no
  check has run for two intervals).
- More notification channels if asked for (for example Gotify or generic webhooks).

**1.0**: stable settings and state format ([interfaces.md](interfaces.md)), with upgrades that need no
manual steps within a major version.

## What trash-watch will not do

- **Change your Recyclarr config, or apply its suggestions.** It reads through a read-only mount and prints
  fixes for you to review; applying them stays a human decision followed by `recyclarr sync --preview`.
- **Talk to Radarr, Sonarr or Recyclarr.** It needs no API keys and doesn't see what's live in the apps.
- **Replace Recyclarr.** Syncing custom formats and profiles is Recyclarr's job; trash-watch only watches
  the gap between your config and the guides.
- **Run as a hosted service or open ports.** It's a sidecar for one operator's own host.
- **Collect data about its users.** It contacts only github.com and the notifiers you configure.
