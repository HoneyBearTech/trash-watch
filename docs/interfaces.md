# Interfaces

Everything trash-watch reads, writes and connects to. It listens on no ports.

## Settings

Set in `.env` (template: [`.env.example`](../.env.example)). Compose uses `RECYCLARR_CONFIG_PATH` for the mount
and passes every line into the container.

| Setting | Default | What |
| --- | --- | --- |
| `RECYCLARR_CONFIG_PATH` | none (required) | Host path of Recyclarr's app-data directory, mounted at `/config` read-only. Compose refuses to start without it. |
| `INTERVAL_HOURS` | `24` | Hours between checks. Decimals allowed. |
| `NTFY_URL` | unset | Full ntfy topic URL. The report is POSTed as the body with a `Title` header. **Secret.** |
| `DISCORD_WEBHOOK` | unset | Discord webhook URL. **Secret.** |
| `HEARTBEAT_URL` | unset | Requested (GET, 15 s timeout) after every check that completed and saved its state; never after a failed one. For a dead man's switch: an Uptime Kuma Push monitor, healthchecks.io and the like. Only `http(s)://`. **Secret** (it carries a token). |
| `PROFILE_MAP` | `{}` | JSON object (one line, single-quoted) mapping your profile name to a guide quality profile's `trash_id` or exact name, e.g. `'{"Movies 4K": "<trash_id>"}'`. |
| `IGNORE` | empty | Comma-separated `trash_id`s (CFs or guide profiles) and profile names to skip on purpose, e.g. `dc98083864ea246d05a42df0d05f81cc,My Profile`. No quotes, no comment on the same line. |
| `RUN_ONCE` | unset | `1` = one check, then exit: exit code 0 if it completed, 1 if it failed (after the error notification). Pass with `docker compose run -e RUN_ONCE=1`; never put it in `.env`. |
| `TRASH_WATCH_IMAGE` | `trash-watch:local` | Compose only: the image to run. Leave unset to build from the checkout, or set a release such as `ghcr.io/honeybeartech/trash-watch:0.2.0` ([verifying-releases.md](verifying-releases.md)). |
| `TRASH_WATCH_UID` / `TRASH_WATCH_GID` | `1000` | Compose only: the user and group the container runs as. They must own `./data` on the host. |
| `TRASH_WATCH_PULL_POLICY` | `build` | Compose only: `build` builds from the checkout on every start; `always` pulls `TRASH_WATCH_IMAGE` instead. |

The script also reads `DATA_DIR` (default `/data`) and `CONFIG_ROOT` (default `/config`). They're the
container-side paths the compose mounts use, so don't set them in `.env`.

## Mounts

| Container path | Host | Mode | Contents |
| --- | --- | --- | --- |
| `/config` | `${RECYCLARR_CONFIG_PATH}` | **read-only** | `recyclarr.yml` / `recyclarr.yaml`, `configs/*.yml`, `includes/`, and for `template:` includes `repositories/config-templates/includes.json` (or `resources/config-templates/git/official/`) plus the files it names |
| `/data` | `./data` (gitignored) | read-write | `guides/`: sparse clone of `TRaSH-Guides/Guides` (`docs/json` only); `state.json` |

The container runs as `TRASH_WATCH_UID:TRASH_WATCH_GID` (1000:1000 by default), which must own `./data`. Its root
filesystem is read-only; `/tmp` is a tmpfs (git's `HOME`). If `/data` isn't writable, the run stops with an error
that names the fix ([upgrading.md](upgrading.md#from-a-root-running-version-before-the-non-root-image)).

## Outbound connections

| To | When | What |
| --- | --- | --- |
| `https://github.com/TRaSH-Guides/Guides.git` | every run | `git clone` (first run), then `git fetch --depth 1`. No credentials. |
| `NTFY_URL` | findings changed, or a run failed | HTTP POST, 15 s timeout, `User-Agent: trash-watch/1.0` |
| `DISCORD_WEBHOOK` | same | HTTP POST of `{"content": ...}`, 15 s timeout |
| `HEARTBEAT_URL` | after every completed check | HTTP GET, 15 s timeout; a failure is logged and changes nothing else |

Both get the phone-sized message described in [How it works](architecture.md#when-youre-notified). A
failed notification is logged as `notify via <target> failed: ...` and doesn't stop the loop or the
other target.

## Output

Everything is also printed to stdout (`docker compose logs trash-watch`): `OK — ...`, `No new findings
...`, or the full report under `== <title>`.

## Command line

| Command | What it does |
| --- | --- |
| `python -u trash_watch.py` | The image's default: check, notify on change, save state, sleep `INTERVAL_HOURS`, repeat (once with `RUN_ONCE=1`) |
| `python -u trash_watch.py --health` | Exits 0 if a check completed within two intervals (plus ten minutes), 1 otherwise, and prints how long ago it was. The image's `HEALTHCHECK` runs it every 5 minutes (after a 15-minute start period), so `docker ps` and monitoring tools see `healthy` / `unhealthy`. |
| `python -u trash_watch.py --suggest` | Prints Recyclarr YAML for every guide CF a profile doesn't score, then exits. Console only: it sends no notifications, writes no state, and never writes the config. Run it with `docker compose run --rm trash-watch python -u trash_watch.py --suggest` or `make suggest`. |

## Image

Built from the [`Dockerfile`](../Dockerfile): `python:3.14-slim` (pinned by version and digest) with `git`
and `ca-certificates` (with Debian's security updates applied at build time), PyYAML installed from the
hash-pinned [`requirements.txt`](../requirements.txt) (pip is removed afterwards), and
`trash_watch.py` and `LICENSE` in `/app`; it runs `python -u trash_watch.py` as the unprivileged user `trash-watch`
(uid/gid 1000). By default compose builds it
from the checkout. Releases publish it for linux/amd64 and linux/arm64 as `ghcr.io/honeybeartech/trash-watch`,
tagged with the version (`0.2.0`), major.minor (`0.2`) and `latest`, signed and with an SBOM and provenance
([verifying-releases.md](verifying-releases.md)).
