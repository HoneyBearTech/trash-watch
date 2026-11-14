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

Stop the service before snapshotting state so no check writes during the copy. Skip the state-copy
command if no check has completed successfully yet and `data/state.json` does not exist. Keep `.env`
backups confidential, with the same restricted permissions as `.env`.

```sh
docker compose stop trash-watch
cp .env .env.backup
cp data/state.json data/state.json.backup
```

## From a root-running version (before the non-root image)

Older versions ran as root, so their `data/` is owned by root, and the new unprivileged container can't write
to it: it stops with an error that names this fix. Run it once, in the trash-watch directory, before
starting the new version (no sudo needed; Docker does it):

```sh
docker run --rm -v "$PWD/data:/data" busybox chown -R 1000:1000 /data
```

Use your `TRASH_WATCH_UID:TRASH_WATCH_GID` instead of `1000:1000` if you set them. The saved state is kept.

## From a checkout (building the image)

The tag below is the existing `0.2.0` example, not a claim about the newest release.

```sh
git fetch --tags && git checkout v0.2.0   # or: git pull, to follow main
docker compose up -d                      # rebuilds the image and restarts the container
docker compose logs -f trash-watch        # the per-profile lines, then OK / findings
```

## From a release image

Set `TRASH_WATCH_IMAGE` in `.env` to the chosen release image, for example
`ghcr.io/honeybeartech/trash-watch:0.2.0` (an example, not a claim about the newest release),
[verify it](verifying-releases.md), then `git pull` (the compose file and `.env.example` can
change between releases) and `docker compose up -d`.

## Rolling back

Stop the service before restoring state. Check out the previous tag (or set the previous
`TRASH_WATCH_IMAGE`), restore the backups, and run
`docker compose up -d`:

```sh
docker compose stop trash-watch
cp .env.backup .env
sudo cp data/state.json.backup data/state.json
```

Rolling back past the non-root change is fine: a root-running container can write to a `data/` owned by
uid 1000. Without the backup, delete `data/state.json` instead: the next run notifies the current findings again and
starts a new baseline. trash-watch never changed your Recyclarr config, so there's nothing to roll back
there.
