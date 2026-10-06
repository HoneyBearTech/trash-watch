# Security

trash-watch sits next to a config that controls how Radarr and Sonarr grab media, and it holds webhook
URLs that can post to your phone or Discord. These are the rules it keeps.

## The Recyclarr config is read-only

- The Recyclarr app-data directory is always mounted `:ro`. trash-watch only reads it: it parses YAML with
  a safe loader and never evaluates `!secret` or `!env_var` values.
- Nothing in trash-watch writes to that directory, and nothing should be changed to make it do so. Fixes are
  made by you, in Recyclarr, after `recyclarr sync --preview`.
- To experiment with a different config, copy it into a scratch directory and point `RECYCLARR_CONFIG_PATH`
  there. Never edit the live one to test trash-watch.

## Secrets live in `.env`

- `NTFY_URL` and `DISCORD_WEBHOOK` let anyone who has them post to your topic or channel. Keep them in
  `.env`, which is gitignored and should be `chmod 600`. Only `.env.example`, with placeholders, is
  committed.
- If one leaks: delete and recreate the Discord webhook (or move to a new ntfy topic, or add ntfy access
  control), update `.env`, then run `docker compose up -d`.
- Recyclarr's own secrets (`secrets.yml`, the Radarr/Sonarr API keys) are inside the mounted directory.
  trash-watch doesn't open `secrets.yml`. An API key written inline in a config file gets parsed with the
  rest of that file, but it's never used, logged or sent anywhere.

## What it can reach

- It opens no ports.
- Outbound: GitHub over HTTPS (public guides repo, no token), plus your ntfy and Discord URLs. It refuses
  notifier URLs that don't start with `https://` or `http://`. Notifications contain only custom-format and
  profile names, `trash_id`s, scores and instance names from your config.
- It runs as root inside the container, with `data/` as its only writable mount.

## Trust in the guides

The guides' JSON is parsed as data and never executed. A compromised upstream could at worst produce
misleading findings. trash-watch changes nothing on its own, so acting on any finding is always your
decision.

## Releases

Released images and files are signed keylessly and carry an SBOM and build provenance; tags are signed. Check
them before you run them: [verifying-releases.md](verifying-releases.md).

## What trash-watch does not protect against

- **Anyone who can write to the host**, its Docker daemon, `.env`, the Recyclarr config directory or
  `data/`. Those are trusted inputs: whoever controls them controls what trash-watch reads, reports and
  where it sends it.
- **Wrong guidance.** trash-watch reports differences from the TRaSH Guides as they are; it can't tell
  whether the guides are right for you, or notice if the guides repository itself were compromised.
- **Changes made outside the config.** It doesn't talk to Radarr or Sonarr, so it can't see what's live
  there or whether `recyclarr sync` ran.
- **A leaked notification URL.** Anyone who has it can post to your channel or topic; rotate it as described
  above.
- **Root inside the container.** The process runs as root in its own container namespace (planned:
  non-root, [roadmap](roadmap.md)). The read-only config mount and the single writable `data/` mount limit
  what it can touch on the host.

Why these requirements are met, and the threat model behind them, is in the
[assurance case](assurance-case.md).
