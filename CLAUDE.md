# trash-watch

A small Docker sidecar that runs next to the Recyclarr container on the owner's Docker host. Once a day it compares the
Recyclarr config against the TRaSH Guides JSON (`TRaSH-Guides/Guides`, `docs/json/radarr` and
`docs/json/sonarr`) and sends a notification (ntfy and/or Discord) when the config has drifted.

## Goals
- Catch drift that Recyclarr itself won't report: custom formats whose `trash_id` was removed or renamed
  upstream, CFs a guide profile includes that the config is missing, scores that differ from the guide's
  score set, and upstream changes to CFs or profiles the config uses.
- Stay quiet: notify only when the set of findings changes, not every day.
- Observe only. trash-watch reads the Recyclarr config and never changes it, and it doesn't talk to
  Radarr or Sonarr.

## Rules
- **The Recyclarr config is always mounted read-only** (`:ro`). Never remove the flag, and never add a
  second, writable mount of the same directory.
- **Never modify the real Recyclarr config.** Don't write, "fix", reformat or copy over files in the
  Recyclarr app-data directory, on the production host or anywhere else. To experiment, copy the config into a scratch
  directory and point `RECYCLARR_CONFIG_PATH` there.
- **The container stays unprivileged.** It runs as `TRASH_WATCH_UID:TRASH_WATCH_GID` (default 1000:1000) on a
  read-only root filesystem with `cap_drop: [ALL]` and `no-new-privileges`. Don't add `user: root`, capabilities
  or writable mounts; anything that needs to write goes under `/data` or `/tmp`.
- **Names are untrusted.** Anything from the guides or the config that reaches output goes through `one_line()`;
  YAML scalars through `yaml_scalar()`; Discord payloads keep `allowed_mentions: {parse: []}`.
- **Secrets go in `.env`, which is never committed.** That covers the Discord webhook, the ntfy URL and
  anything else that grants access. `.gitignore` covers `.env` and `data/`; extend it rather than work
  around it. Only `.env.example` (placeholders, no real values) is committed.

## This repo is public (or about to be)
- No hostnames, IP addresses, internal domains, paths on the owner's machines, or personal email
  addresses in anything committed: code, docs, examples, tests, commit messages. The production host's
  name, paths and deploy-key details live only in the Chronos notes.
- Commit as `31805425+HoneyBearTech@users.noreply.github.com` (set as this repo's `user.email`), with
  `git commit -s` for the DCO sign-off; commits and tags are SSH-signed.
- No secrets: gitleaks runs over the whole history in CI, and push protection is on.
- The old in-repo vault path `.obsidian-docs/` stays gitignored; notes never go into this repo.
- Keep the repo on track for OpenSSF Baseline Levels 1 and 2 and the Best Practices Passing and Silver
  badges. If a change would break a met criterion (for example unpinning a dependency, adding a workflow
  without `permissions:`, or dropping the coverage floor), say so before making it.

## Stack
- Python 3.14 (one script, standard library plus PyYAML), git, Docker Compose. No web UI, no HTTP API.
- Tooling: ruff with every rule family (`select = ["ALL"]`, exceptions in `pyproject.toml`; per-line `noqa`
  with a reason) and `ruff format`; everything type-annotated (aliases `Block`, `Finding`, `Guides`, `Instance`
  in `trash_watch.py`; `RunChecks`, `EditGuideCf` in `tests/conftest.py`), yamllint, pytest + coverage (90 % branch floor), Hypothesis (property tests),
  Atheris (coverage-guided fuzzing, Linux x86_64 only), pip-tools for the hash-pinned requirements. CI-only: actionlint, hadolint, gitleaks, CodeQL, Scorecard, dependency review.
- Releases: signed multi-arch images on GHCR (cosign keyless), SBOM, SLSA provenance, signed checksums.

## Before making structural changes
Read the project notes. They live outside this repo, in the owner's Obsidian vault **Chronos** at
`~/Chronos/Projects/trash-watch/` (every file is prefixed `trash-watch-`):
- `trash-watch-roadmap.md`: open questions and what's in scope now vs. later
- `trash-watch-Architecture.md`: how the check works, the production deployment (host, paths, deploy key), current state
- `trash-watch-Security-Considerations.md`: secrets, mounts, exposure checklist
- `trash-watch-Decisions-Log.md`: why decisions were made (entries marked **Proposed** still need the
  owner's call)
- `trash-watch-Pass-Map.md`: delivery log; add a row when a pass ships

Keep those notes current: new decisions get a dated entry in the Decisions Log, and roadmap checkboxes get
ticked as work lands. **The notes never go into this repo.** Chronos is versioned in its own private repo;
only commit or push it when the owner asks.

## Layout
- `trash_watch.py`: the whole watcher. Each run it syncs a sparse, shallow clone of the guides
  (`docs/json` only), loads the Recyclarr config, checks each Radarr/Sonarr instance, compares against
  the last state and notifies on change. Then it sleeps `INTERVAL_HOURS`, or exits when `RUN_ONCE=1`.
- `Dockerfile`: `python:3.14-slim` pinned by version and digest, + `git`, PyYAML from the hash-pinned
  `requirements.txt` (`--require-hashes`), `trash_watch.py` and `LICENSE`; runs `trash_watch.py` unbuffered.
  `requirements.in` / `requirements-dev.in` are the sources; regenerate the `.txt` files with
  `pip-compile --generate-hashes --strip-extras <file>.in`.
- `tests/test_properties.py`: Hypothesis properties over arbitrary Unicode for every name-to-output path
  (notification caps and counts, Discord payload, `yaml_scalar`, `--suggest` YAML round trip, `load_yaml`,
  `check()` on well-formed but arbitrary configs and guides). Bugs they find get an `@example`.
  `pytest --hypothesis-profile=thorough` = 5,000 examples each. `fuzz/fuzz_properties.py` drives the same
  properties with Atheris; `requirements-fuzz.in/.txt` pins it (compile in a linux/amd64 container).
- `pyproject.toml`: ruff rules, pytest options (warnings are errors), coverage floor. `.yamllint.yml`.
- `.github/`: `ci.yml` (one job, "Checks + tests", the required check: ruff, yamllint, actionlint, hadolint,
  gitleaks over the history, pytest + coverage, image build/start, compose config), `codeql.yml`,
  `scorecard.yml`, `dependency-review.yml`, `dco.yml`, `scan.yml` (weekly Trivy scan of the `main` build and the latest GHCR release → code scanning), `fuzz.yml` (Atheris per target: 60 s on PRs touching the
  code, 10 min weekly; not a required check), `release.yml` (on a `v*.*.*` tag: multi-arch image to
  GHCR, cosign keyless, SBOM + provenance, GitHub Release from the tag's `CHANGELOG.md` section, signed
  `SHA256SUMS`); `dependabot.yml`; issue/PR templates; `CODEOWNERS`; `allowed_signers` (tag-signing key).
  Actions pinned by full SHA; every workflow has top-level `permissions:`; untrusted input only via `env:`.
- Root policies: `SECURITY.md`, `CONTRIBUTING.md`, `GOVERNANCE.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`.
- `tests/`: pytest, no network. `tests/fixtures/guides/docs/json/radarr/` is a tiny fake guides tree (three
  CFs, one SQP profile) and `tests/fixtures/config/recyclarr.yml` a fake config built so that each check
  produces exactly one known finding. `conftest.py` points the module's paths at a per-test copy, blanks
  `PROFILE_MAP`/`IGNORE`, stubs `sync_guides` and makes `urlopen` fail. New check or bug fix → add a case;
  keep `test_exactly_the_expected_findings` exact.
- `Makefile`: `make test` (builds `.venv`, runs pytest), `make build`, `make run-once`, `make suggest`.
  The production host has no `make`; run the target's `docker compose` line there.
- `--suggest` (`suggest()` / `render_suggestions()`): prints paste-ready `custom_formats` blocks for the gaps
  `check(instance, guides, gaps)` collects. **Console only, by design:** it must never write the config (or anywhere else),
  notify, or save state. Never add an option that applies the suggestions.
- `docker-compose.yml`: the one service. Builds from the checkout by default (`TRASH_WATCH_IMAGE` /
  `TRASH_WATCH_PULL_POLICY` switch it to a release image). It reads settings from `.env` (`env_file`) and
  mounts `${RECYCLARR_CONFIG_PATH}` at `/config:ro` and `./data` at `/data`.
- `.env.example`: template for `.env`, listing every setting.
- `data/` (gitignored, created at runtime): `guides/` (the clone) and `state.json` (fingerprints of the
  CFs/profiles in use, a hash of the last report, guides commit, time of last check).
- `docs/`: quick start, installing, user guide, how it works (`architecture.md`), interfaces, upgrading,
  verifying releases, security requirements, assurance case, dependencies, roadmap. `CHANGELOG.md`: add to
  "Unreleased" with every user-visible change. Update the docs in the same change as the behaviour they
  describe; mark anything not built yet as "Planned".

Config the watcher reads (under `/config`): `recyclarr.yml` or `recyclarr.yaml`, `configs/*.yml`, and
local `include: - config:` files (relative paths resolve under `includes/`), and `template:` includes via
the `includes.json` in Recyclarr's config-templates checkout (`resources/config-templates/git/official` or
`repositories/config-templates`). The `!secret` and `!env_var` tags are accepted and their values ignored.
Recyclarr v8 `custom_format_groups` (also from includes) ride through `load_instances()` as marker blocks and
`resolve_groups()` turns them into ordinary CF blocks using the guides' `cf-groups/` (required + defaults −
exclude + select/select_all; `assign_scores_to`, else the guide-backed profiles in the group's include list;
default groups for those unless skipped). Renamed profiles are matched with `PROFILE_MAP` (or a unique `score_set`); deliberate skips go in `IGNORE`.
Every run logs which guide profile each config profile was checked against. Check that output after a
change: a profile marked "NOT CHECKED" is silently missing from the findings.

## Commands
```sh
make test       # unit tests + coverage floor against the fixtures (no network, no Docker, no real config)
make lint       # ruff check, ruff format --check, yamllint --strict
make build      # docker compose build
make run-once   # build, then one check against the real config in .env (notifies if findings changed)
make suggest    # build, then print Recyclarr YAML for missing CFs (console only)
```
`main()` returns the exit code: `RUN_ONCE=1` → 0 or 1; `--health` → 0 if a check completed within two
intervals (the image's `HEALTHCHECK`), else 1.

One-time test by hand (no daemon; prints the result and exits):
```sh
cp .env.example .env && chmod 600 .env   # set RECYCLARR_CONFIG_PATH (and a notifier if you want one)
docker compose build
docker compose run --rm -e RUN_ONCE=1 trash-watch
# keep it to the log only, with no notifications sent:
docker compose run --rm -e RUN_ONCE=1 -e NTFY_URL= -e DISCORD_WEBHOOK= trash-watch
```
A clean config prints `OK — config matches TRaSH Guides @ <commit>`; otherwise the findings are printed
under `== Recyclarr vs TRaSH Guides @ <commit>: N item(s)`. The run writes `data/state.json`, so the daemon
won't re-send those same findings later; delete `data/state.json` to get them notified again.

Run it for real:
```sh
docker compose up -d --build
docker compose logs -f trash-watch
```

Never put `RUN_ONCE=1` in `.env`: with `restart: unless-stopped` the container would start again straight
after every exit.

Release (the owner does this): add a `## [x.y.z] - date` section to `CHANGELOG.md`, then
`git tag -s vX.Y.Z -m vX.Y.Z && git push origin vX.Y.Z`; `release.yml` does the rest.
