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
| `PROFILE_MAP` | `{}` | JSON object (one line, single-quoted) mapping your profile name to a guide quality profile's `trash_id` or exact name, e.g. `'{"Movies 4K": "<trash_id>"}'`. |
| `IGNORE` | empty | Comma-separated `trash_id`s (CFs or guide profiles) and profile names to skip on purpose, e.g. `dc98083864ea246d05a42df0d05f81cc,My Profile`. No quotes, no comment on the same line. |
| `RUN_ONCE` | unset | `1` = one check, then exit. Pass with `docker compose run -e RUN_ONCE=1`; never put it in `.env`. |

The script also reads `DATA_DIR` (default `/data`) and `CONFIG_ROOT` (default `/config`). They're the
container-side paths the compose mounts use, so don't set them in `.env`.

## Mounts

| Container path | Host | Mode | Contents |
| --- | --- | --- | --- |
| `/config` | `${RECYCLARR_CONFIG_PATH}` | **read-only** | `recyclarr.yml` / `recyclarr.yaml`, `configs/*.yml`, `includes/`, and for `template:` includes `repositories/config-templates/includes.json` (or `resources/config-templates/git/official/`) plus the files it names |
| `/data` | `./data` (gitignored) | read-write | `guides/`: sparse clone of `TRaSH-Guides/Guides` (`docs/json` only); `state.json` |

The container runs as root, so files in `data/` are owned by root on the host.

## Outbound connections

| To | When | What |
| --- | --- | --- |
| `https://github.com/TRaSH-Guides/Guides.git` | every run | `git clone` (first run), then `git fetch --depth 1`. No credentials. |
| `NTFY_URL` | findings changed, or a run failed | HTTP POST, 15 s timeout, `User-Agent: trash-watch/1.0` |
| `DISCORD_WEBHOOK` | same | HTTP POST of `{"content": ...}`, 15 s timeout |

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
| `python -u trash_watch.py --suggest` | Prints Recyclarr YAML for every guide CF a profile doesn't score, then exits. Console only: it sends no notifications, writes no state, and never writes the config. Run it with `docker compose run --rm trash-watch python -u trash_watch.py --suggest` or `make suggest`. |

## Image

Built locally from the [`Dockerfile`](../Dockerfile): `python:3.12-slim` with `git`, `ca-certificates` and
`pyyaml`, running `python -u trash_watch.py`. Nothing is published to a registry.
