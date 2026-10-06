# Quick start

Run trash-watch next to Recyclarr on the same host. You need Docker with Compose v2 and the path of
Recyclarr's app-data directory: the host directory your Recyclarr container mounts as `/config`.

## 1. Configure

```sh
cp .env.example .env && chmod 600 .env
```

Edit `.env`:

- `RECYCLARR_CONFIG_PATH`: the Recyclarr app-data directory on the host. It's mounted read-only.
- `NTFY_URL` (a full topic URL, e.g. `https://ntfy.example/recyclarr`) and/or `DISCORD_WEBHOOK`. With
  neither set, findings only go to the container log.
- `INTERVAL_HOURS` if you want something other than daily.
- `PROFILE_MAP` if you've renamed guide profiles, and `IGNORE` for anything you skip on purpose; see
  [Interfaces](interfaces.md#settings). The one-time check below tells you which profiles need a mapping.

`.env` holds secrets and is gitignored. Never commit it.

## 2. Run a one-time check

```sh
docker compose build
docker compose run --rm -e RUN_ONCE=1 -e NTFY_URL= -e DISCORD_WEBHOOK= trash-watch
```

The blank `NTFY_URL`/`DISCORD_WEBHOOK` keep this first run to your terminal. The first run clones the
guides' JSON into `data/guides/`, which takes a few seconds. It then logs one line per profile:
`checked against <guide profile>`, `ignored`, or `NOT CHECKED`. Map each `NOT CHECKED` profile in
`PROFILE_MAP`, or add it to `IGNORE` if it's your own, and run again. After that you'll see one of:

- `OK — config matches TRaSH Guides @ <commit>`: nothing to report.
- `== Recyclarr vs TRaSH Guides @ <commit>: N item(s)` followed by the findings, grouped by profile, for
  example a heading `radarr/movies · HD Bluray + WEB` with `• missing x265 (HD)` under it.
  [How it works](architecture.md#findings) explains each kind of finding. The log always has the full
  list; notifications are cut to about 20 lines.
- `== trash-watch error` with an exception: usually a wrong `RECYCLARR_CONFIG_PATH`, invalid `PROFILE_MAP`
  JSON, or no route to GitHub.

To check that notifications arrive, run it again without the blank overrides. Because the first run saved
its findings in `data/state.json`, delete that file first, or nothing new will be sent.

## 3. Leave it running

```sh
docker compose up -d --build
docker compose logs -f trash-watch
```

It checks at start-up and then every `INTERVAL_HOURS`. Don't add `RUN_ONCE=1` to `.env`: with
`restart: unless-stopped` the container would start again straight after every exit.

## Acting on a finding

trash-watch only reports. Fix the config the way you normally would, then run
`recyclarr sync --preview` to see what Recyclarr will change before syncing for real. A score you've
changed on purpose will keep showing up in the list, but it won't notify you again until the findings
change.
