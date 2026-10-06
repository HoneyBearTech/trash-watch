# Upgrading

Only the latest release and `main` get fixes ([SUPPORT.md](../SUPPORT.md)), so upgrade when a new one
comes out. Every release's notes (and [CHANGELOG.md](../CHANGELOG.md)) list what changed and, under
**Upgrading**, anything you need to do first.

## What's kept

trash-watch has very little state, all of it on the host:

- `.env`: your settings and secrets. Upgrades never change it; compare it with the new `.env.example` for
  new settings.
- `data/state.json`: fingerprints of the CFs and profiles you use, a hash of the last report, the guides
  commit and the time of the last check. It decides what counts as "changed upstream" and whether a report
  is new.
- `data/guides/`: a cache of the TRaSH Guides JSON, re-fetched every run. Safe to delete.

When a release changes the `state.json` format, the first run after the upgrade says so and starts again
from a fresh baseline instead of reporting everything as changed. It can't report upstream changes on that
run.

## Back up first

```sh
cp .env .env.backup
sudo cp data/state.json data/state.json.backup      # data/ is owned by root (the container's user)
```

## From a checkout (building the image)

```sh
git fetch --tags && git checkout v0.1.0   # or: git pull, to follow main
docker compose up -d                      # rebuilds the image and restarts the container
docker compose logs -f trash-watch        # the per-profile lines, then OK / findings
```

## From a release image

Set the new version in `.env` (`TRASH_WATCH_IMAGE=ghcr.io/honeybeartech/trash-watch:0.1.1`),
optionally [verify it](verifying-releases.md), then `git pull` (the compose file and `.env.example` can
change between releases) and `docker compose up -d`.

## Rolling back

Check out the previous tag (or set the previous `TRASH_WATCH_IMAGE`), restore the backups, and run
`docker compose up -d`:

```sh
cp .env.backup .env
sudo cp data/state.json.backup data/state.json
```

Without the backup, delete `data/state.json` instead: the next run notifies the current findings again and
starts a new baseline. trash-watch never changed your Recyclarr config, so there's nothing to roll back
there.
