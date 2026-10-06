# trash-watch

[![CI](https://github.com/HoneyBearTech/trash-watch/actions/workflows/ci.yml/badge.svg)](https://github.com/HoneyBearTech/trash-watch/actions/workflows/ci.yml)
[![CodeQL](https://github.com/HoneyBearTech/trash-watch/actions/workflows/codeql.yml/badge.svg)](https://github.com/HoneyBearTech/trash-watch/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/HoneyBearTech/trash-watch/badge)](https://scorecard.dev/viewer/?uri=github.com/HoneyBearTech/trash-watch)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15256/badge)](https://www.bestpractices.dev/projects/15256)
[![OpenSSF Baseline](https://www.bestpractices.dev/projects/15256/baseline)](https://www.bestpractices.dev/projects/15256)

A small Docker sidecar for [Recyclarr](https://recyclarr.dev). Once a day it compares your Recyclarr
config with the current [TRaSH Guides](https://github.com/TRaSH-Guides/Guides) JSON for Radarr and Sonarr.
When your config has drifted from the guides, it sends a notification to Discord and/or ntfy.

It only reads. Your Recyclarr config is mounted read-only, and trash-watch never talks to Radarr, Sonarr
or Recyclarr.

## Why

Recyclarr keeps the custom formats *you list* in sync with the guides: their conditions, their names, and
the guide's scores. It does what your config says, and it can't tell you what your config leaves out:

- **A CF the guide added to your profile.** When TRaSH adds a CF to an SQP or other profile, Recyclarr
  doesn't add it to your config. Your profile quietly stops matching the guide.
- **A CF that was removed or renamed upstream.** Its `trash_id` lingers in your config, and Recyclarr can
  no longer sync it.
- **A score you overrode.** An explicit `score:` keeps winning after the guide changes its
  recommendation.
- **A guide change that alters what you grab.** Recyclarr applies it on the next sync, but nothing tells
  you it happened or why.

trash-watch reports each of these, groups them by profile, and stays quiet until something changes.

## What it checks

For every Radarr and Sonarr instance in your config:

| Finding | Meaning |
| --- | --- |
| `CF <trash_id> removed or renamed upstream` | A `trash_id` in your config no longer exists in the guides |
| `missing <CF>` | The guide's version of your profile has a CF that's nowhere in this instance |
| `<CF>: synced, but not scored in this profile` | The CF exists in the instance, but none of this profile's `assign_scores_to` blocks lists it |
| `score_set X, guide uses Y` | Your profile takes its scores from a different score set than the guide's profile |
| `<CF>: N, guide M` | A score you set differs from the guide's score in your profile's score set |
| `changed upstream: CF/Profile <name>` | A CF or profile you use changed in a way that affects you (its conditions, or its scores in your score sets) since the last check |

Each profile in your config is matched to a guide profile by:
1. its `trash_id`;
2. `PROFILE_MAP`;
3. its name, with or without a prefix such as `[SQP] `;
4. its `score_set`, when only one guide profile uses that set.

Every run logs what each profile was checked against, so a profile that matched nothing doesn't go
unnoticed.

## Setup

You need a Docker host with Compose v2, running Recyclarr (v7 or v8) or with its config directory on disk.

**1. Find Recyclarr's config directory.** This is the host path your Recyclarr container mounts at
`/config`:

```sh
docker inspect recyclarr --format '{{range .Mounts}}{{if eq .Destination "/config"}}{{.Source}}{{end}}{{end}}'
```

**2. Get trash-watch and create `.env`.**

```sh
git clone https://github.com/HoneyBearTech/trash-watch.git && cd trash-watch
cp .env.example .env && chmod 600 .env
mkdir -p data      # created by you, so it belongs to your user (uid 1000 by default)
```

In `.env`, set `RECYCLARR_CONFIG_PATH` to the path from step 1 and add a Discord webhook or ntfy URL.
`.env` holds secrets and is gitignored; never commit it.

**3. Run one check.** It prints the result and exits:

```sh
make run-once        # or: docker compose run --rm --build -e RUN_ONCE=1 trash-watch
```

Read the per-profile lines at the top of the output. Add any profile marked `NOT CHECKED` to
`PROFILE_MAP`, or to `IGNORE` if it's your own, then run again. Put any finding you're keeping on purpose
in `IGNORE`.

**4. Leave it running.**

```sh
docker compose up -d --build
docker compose logs -f trash-watch
```

It checks at start-up and then every `INTERVAL_HOURS`. To update it: `git pull && docker compose up -d --build`.

## Settings (`.env`)

| Setting | Default | What it does |
| --- | --- | --- |
| `RECYCLARR_CONFIG_PATH` | required | Host path of Recyclarr's config directory, mounted read-only at `/config`. Compose won't start without it. |
| `INTERVAL_HOURS` | `24` | Hours between checks. Decimals are fine. |
| `DISCORD_WEBHOOK` | empty | Discord webhook URL for notifications. **Secret.** |
| `NTFY_URL` | empty | Full ntfy topic URL for notifications. **Secret.** With neither notifier set, findings only go to the log. |
| `PROFILE_MAP` | `{}` | One line of JSON in single quotes, mapping your profile names to guide profiles by `trash_id` or exact guide name. Use it for renamed profiles: `'{"SQP-3 Remux\|IMAX-E\|2160p": "[SQP] SQP-3"}'` |
| `IGNORE` | empty | Comma-separated `trash_id`s (CFs or guide profiles) and profile names you skip on purpose. No quotes, and no comment on the same line. Example: `IGNORE=dc98083864ea246d05a42df0d05f81cc,2160p Low` |
| `TRASH_WATCH_IMAGE` | `trash-watch:local` | The image compose runs. Leave unset to build from the checkout; set a signed release such as `ghcr.io/honeybeartech/trash-watch:0.1.0` to run that instead ([verify it first](docs/verifying-releases.md)). |
| `TRASH_WATCH_UID` / `TRASH_WATCH_GID` | `1000` | The unprivileged user and group the container runs as. They must own `data/` on the host; change them if your host user isn't 1000 (`id -u`, `id -g`). |
| `TRASH_WATCH_PULL_POLICY` | `build` | `build` builds from the checkout on every start; set `always` together with a release `TRASH_WATCH_IMAGE`. |

`RUN_ONCE=1` (one check, then exit) is for `docker compose run -e RUN_ONCE=1` only. Don't put it in `.env`:
with `restart: unless-stopped`, the container would start again straight after every exit.

## Example output

The log lists every profile, then the findings:

```
radarr/movies · SQP-1 (1080p): checked against [SQP] SQP-1 (1080p) (matched by name)
radarr/movies4k · SQP-3 Remux|IMAX-E|2160p: checked against [SQP] SQP-3 (matched by PROFILE_MAP)
sonarr/series · Anime: checked against [Anime] Remux-1080p (matched by score_set)
sonarr/seriesv4 · 2160p Low: ignored (IGNORE)
== Recyclarr vs TRaSH Guides @ e7c97a6: 3 item(s)
radarr/movies · SQP-1 (1080p) (guide: [SQP] SQP-1 (1080p))
• Repack/Proper: 99, guide 6
• missing x265 (HD)
sonarr/series · Anime (guide: [Anime] Remux-1080p)
• missing VOSTFR
```

A Discord message has the same layout, with bold headings. It shows at most 3 items per profile and
about 20 lines in total, then `…plus N more (full list: docker logs trash-watch)`. A run with nothing to
report logs `OK — config matches TRaSH Guides @ <commit>`; a run whose findings haven't changed logs
`No new findings` and sends nothing.

## Suggested fixes (`--suggest`)

To fix what it found, have trash-watch print the Recyclarr YAML for every guide CF a profile doesn't score.
The snippets are grouped by profile, with the guide's score for that profile's `score_set`:

```sh
make suggest     # or: docker compose run --rm --build trash-watch python -u trash_watch.py --suggest
```

```yaml
# sonarr/series · Anime (guide: [Anime] Remux-1080p, score_set anime-sonarr)
# paste under:  sonarr: > series: > custom_formats:
      - trash_ids:
          - 07a32f77690263bb9fda1842db7e273f # VOSTFR
        assign_scores_to:
          - name: Anime
            score: -10000
```

It only prints to the console. It never writes to your config (which is mounted read-only anyway), sends no
notifications, and doesn't touch `data/state.json`, so the daily report isn't affected. CFs in `IGNORE`
are left out. Each snippet is indented to paste directly under that instance's `custom_formats:` list. Run
`recyclarr sync --preview` before you sync.

## Limitations

- **It checks the guide's core list for each profile, not every optional CF.** A guide profile's JSON
  lists the CFs that profile needs. The optional extras in the guide's pages and in Recyclarr's templates
  aren't checked.
- **Guide-backed profiles (with a `trash_id`) are only checked to exist.** Recyclarr syncs their CFs and
  scores from the guide itself.
- **v8 `custom_format_groups` aren't understood yet.** trash-watch logs a warning when an instance uses
  them, because "missing" findings for that instance may then be wrong.
- **Template includes are resolved through `includes.json` in Recyclarr's config-templates checkout.**
  Current v8 template repos don't have one, so such includes are logged as not found.
- **Renamed profiles need a hint.** A profile whose name and `score_set` don't identify a guide profile
  isn't checked until you add it to `PROFILE_MAP`. trash-watch doesn't guess.
- **Scores are compared only where you set one explicitly.** Scores left to the guide are Recyclarr's job.
- **It doesn't see what's live in Radarr or Sonarr.** It can't tell whether `recyclarr sync` ran or
  succeeded, or what someone changed in the UI.
- **Upstream changes need a previous run.** They show up in the one report after they happen. The first
  run, or the first one after `data/state.json` is deleted, only records a baseline.
- **Radarr and Sonarr only.** Lidarr, Readarr and others aren't checked.
- **It needs HTTPS access to github.com.** The container runs as an unprivileged user (uid 1000 by default), so
  `data/` must belong to that uid on the host.

## Running it securely

- Keep the Recyclarr config mount read-only (`:ro`); trash-watch never needs to write there. The container runs
  unprivileged, on a read-only root filesystem, with no Linux capabilities; keep those settings in
  `docker-compose.yml`.
- Keep `.env` at `chmod 600` and out of git. Use a Discord webhook or ntfy topic dedicated to trash-watch,
  so it can be rotated on its own; anyone with the URL can post to it.
- If you run a release image, [verify its signature](docs/verifying-releases.md) and pin the version.
- What trash-watch protects and what it doesn't: [docs/security.md](docs/security.md).

## Documentation

- [Quick start](docs/quick-start.md) and [Installing](docs/installing.md): setup, release images, running
  it securely, uninstalling
- [User guide](docs/user-guide/README.md): reading notifications, `PROFILE_MAP`, `IGNORE`, applying fixes
- [How it works](docs/architecture.md): each run, every finding, when you're notified
- [Interfaces](docs/interfaces.md): every setting, mount, file, command and connection
- [Upgrading](docs/upgrading.md) and [Verifying releases](docs/verifying-releases.md)
- [Security requirements](docs/security.md), [Assurance case](docs/assurance-case.md) and
  [Dependencies](docs/dependencies.md)
- [Roadmap](docs/roadmap.md), including what trash-watch won't do
- Project policies: [CONTRIBUTING.md](CONTRIBUTING.md), [GOVERNANCE.md](GOVERNANCE.md),
  [SECURITY.md](SECURITY.md), [SUPPORT.md](SUPPORT.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and
  [CHANGELOG.md](CHANGELOG.md)

## Development

```sh
make test       # pytest with coverage against small fixtures in tests/ (no network, no Docker, no real config)
make lint       # ruff, ruff format, yamllint
make build      # docker compose build
make run-once   # build, then one check against the config in .env
make suggest    # build, then print paste-ready YAML for missing CFs (console only)
```

`make` isn't installed on every Docker host. Each target is a single `docker compose` command, so you can
copy it from the [Makefile](Makefile). How to contribute is in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE).
