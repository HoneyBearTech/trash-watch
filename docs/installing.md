# Installing

trash-watch runs as one container next to Recyclarr, on the Docker host that holds Recyclarr's config
directory. It opens no ports and needs no account anywhere; it only reads the config and fetches the public
TRaSH Guides. For a first look, the [quick start](quick-start.md) is shorter; this page covers the choices.

## What you need

- A Linux host (amd64 or arm64) with Docker and Compose v2.
- Recyclarr's config directory on that host: the directory the Recyclarr container mounts at `/config`.
  Find it with:

  ```sh
  docker inspect recyclarr --format '{{range .Mounts}}{{if eq .Destination "/config"}}{{.Source}}{{end}}{{end}}'
  ```

- Outbound HTTPS to github.com, and to your Discord webhook or ntfy server if you want notifications.

## 1. Get the files

```sh
git clone https://github.com/HoneyBearTech/trash-watch.git && cd trash-watch
git checkout v0.1.0     # optional: a release tag instead of main
```

## 2. Create `.env`

```sh
cp .env.example .env && chmod 600 .env
mkdir -p data
```

`data/` must exist before the first start and belong to the user the container runs as: uid and gid 1000
by default, the first user on most Linux hosts. If `id -u` or `id -g` prints something else, set
`TRASH_WATCH_UID` / `TRASH_WATCH_GID` in `.env`. (If Docker creates `data/` itself, it's owned by root, and
trash-watch stops with the command that fixes it.)

Set `RECYCLARR_CONFIG_PATH` to the directory from above, and `DISCORD_WEBHOOK` and/or `NTFY_URL`. Every
setting is described in [interfaces.md](interfaces.md#settings). `.env` holds secrets: keep it `600`, owned
by the account that runs Docker, and never commit it.

## 3. Choose how to get the image

**Build it from the checkout** (the default; nothing else to set). `docker compose up -d` builds the image
from the `Dockerfile` with its pinned base image and hash-checked packages.

**Or run a signed release image** from GHCR. Add to `.env`:

```sh
TRASH_WATCH_IMAGE=ghcr.io/honeybeartech/trash-watch:0.1.0
TRASH_WATCH_PULL_POLICY=always
```

and [verify its signature](verifying-releases.md) before the first start. Pin a version rather than
`latest`, so upgrades happen when you choose.

## 4. Check once, then start it

```sh
docker compose run --rm -e RUN_ONCE=1 -e DISCORD_WEBHOOK= -e NTFY_URL= trash-watch
```

The output lists each profile and what it was checked against. Map any `NOT CHECKED` profile in
`PROFILE_MAP`, or add it to `IGNORE` if it's your own ([user guide](user-guide/README.md)). Then:

```sh
docker compose up -d
docker compose logs -f trash-watch
```

It checks at start-up and every `INTERVAL_HOURS` (default 24), and notifies only when its findings change.

## Running it securely

- Keep the Recyclarr config mount read-only (`:ro` in `docker-compose.yml`); trash-watch never needs to
  write there.
- Keep `.env` at `600`, and use a Discord webhook (or ntfy topic) dedicated to trash-watch, so it can be
  rotated alone.
- Use an unguessable ntfy topic or ntfy access control: the topic URL is all anyone needs to post to it.
- The container runs as an unprivileged user on a read-only root filesystem, with all Linux capabilities
  dropped and `no-new-privileges`; it writes only to `./data` (and a temporary `/tmp`). Keep those settings
  in `docker-compose.yml`.

More in [security.md](security.md).

## Uninstalling

```sh
docker compose down
cd .. && rm -rf trash-watch     # removes .env and data/ too
```

trash-watch changed nothing in your Recyclarr config, so there is nothing to undo there. Delete the Discord
webhook (or ntfy topic) if you made one for it.
