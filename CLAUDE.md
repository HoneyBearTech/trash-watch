# trash-watch

A small Docker sidecar that runs on Atlas next to the Recyclarr container. Once a day it compares the
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
  Recyclarr app-data directory, on Atlas or anywhere else. To experiment, copy the config into a scratch
  directory and point `RECYCLARR_CONFIG_PATH` there.
- **Secrets go in `.env`, which is never committed.** That covers the Discord webhook, the ntfy URL and
  anything else that grants access. `.gitignore` covers `.env` and `data/`; extend it rather than work
  around it. Only `.env.example` (placeholders, no real values) is committed.

## Before making structural changes
Read the project notes. They live outside this repo, in the owner's Obsidian vault **Chronos** at
`~/Chronos/Projects/trash-watch/` (every file is prefixed `trash-watch-`):
- `trash-watch-roadmap.md`: open questions and what's in scope now vs. later
- `trash-watch-Architecture.md`: how the check works, deployment on Atlas, current state
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
- `Dockerfile`: `python:3.12-slim` + `git` + `requirements.txt` (pinned PyYAML); runs `trash_watch.py`
  unbuffered. `requirements-dev.txt` adds pytest.
- `tests/`: pytest, no network. `tests/fixtures/guides/docs/json/radarr/` is a tiny fake guides tree (three
  CFs, one SQP profile) and `tests/fixtures/config/recyclarr.yml` a fake config built so that each check
  produces exactly one known finding. `conftest.py` points the module's paths at a per-test copy, blanks
  `PROFILE_MAP`/`IGNORE`, stubs `sync_guides` and makes `urlopen` fail. New check or bug fix → add a case;
  keep `test_exactly_the_expected_findings` exact.
- `Makefile`: `make test` (builds `.venv`, runs pytest), `make build`, `make run-once`.
- `docker-compose.yml`: the one service, built locally. It reads settings from `.env` (`env_file`) and
  mounts `${RECYCLARR_CONFIG_PATH}` at `/config:ro` and `./data` at `/data`.
- `.env.example`: template for `.env`, listing every setting.
- `data/` (gitignored, created at runtime): `guides/` (the clone) and `state.json` (fingerprints of the
  CFs/profiles in use, a hash of the last report, guides commit, time of last check).
- `docs/`: user documentation (quick start, how it works, interfaces, security). `CHANGELOG.md`: add to
  "Unreleased" with every user-visible change. Update the docs in the same change as the behaviour they
  describe.

Config the watcher reads (under `/config`): `recyclarr.yml` or `recyclarr.yaml`, `configs/*.yml`, and
local `include: - config:` files (relative paths resolve under `includes/`), and `template:` includes via
the `includes.json` in Recyclarr's config-templates checkout (`resources/config-templates/git/official` or
`repositories/config-templates`). The `!secret` and `!env_var` tags are accepted and their values ignored.
Renamed profiles are matched with `PROFILE_MAP` (or a unique `score_set`); deliberate skips go in `IGNORE`.
Every run logs which guide profile each config profile was checked against. Check that output after a
change: a profile marked "NOT CHECKED" is silently missing from the findings.

## Commands
```sh
make test       # unit tests against the fixtures (no network, no Docker, no real config)
make build      # docker compose build
make run-once   # build, then one check against the real config in .env (notifies if findings changed)
```

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
