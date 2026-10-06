# User guide

Day-to-day use of trash-watch once it's [installed](../installing.md): reading what it reports, making it
check every profile, deciding what to fix and what to keep, and applying fixes safely.

## Reading a notification

A notification lists findings under headings: the instance (`radarr/movies`), the instance and profile
(`radarr/movies · HD Bluray + WEB`, with `(guide: <name>)` when the guide calls it something else), or
`<app> · changed upstream`. On a phone it shows at most 3 items per profile and about 20 lines, then
`…plus N more`; the container log always has the full list:

```sh
docker compose logs --tail 100 trash-watch
```

What each kind of finding means is in [How it works](../architecture.md#findings). You're notified again
only when the list of findings changes, so a difference you've decided to keep won't remind you daily.

## Making sure every profile is checked

Every run starts by logging one line per profile:

```
radarr/movies · SQP-1 (1080p): checked against [SQP] SQP-1 (1080p) (matched by name)
sonarr/series · Anime: checked against [Anime] Remux-1080p (matched by score_set)
sonarr/seriesv4 · 2160p Low: ignored (IGNORE)
radarr/movies4k · My Profile: NOT CHECKED, no guide profile matches (add it to PROFILE_MAP, or to IGNORE if it's your own)
```

A `NOT CHECKED` profile produces no findings at all, so deal with each one:

- **It's a guide profile you renamed**: map it in `.env`, by the guide profile's name or `trash_id`:

  ```sh
  PROFILE_MAP='{"My Profile": "[SQP] SQP-3", "WEB-DL (1080p)": "WEB-1080p"}'
  ```

- **It's your own profile**, with no guide equivalent: add its name to `IGNORE` so the log says "ignored"
  instead of "not checked".

The guide profile names are the `name` fields in the guides' `docs/json/radarr/quality-profiles/` and
`docs/json/sonarr/quality-profiles/`.

## Keeping a difference on purpose

Some findings are choices, for example using x265 (no HDR/DV) instead of the guide's x265 (HD). Add the CF's
`trash_id` (from the finding, or the guide JSON) to `IGNORE`:

```sh
IGNORE=dc98083864ea246d05a42df0d05f81cc,2160p Low
```

An ignored `trash_id` is skipped by every check, including upstream changes. `.env` changes apply on the
next start: `docker compose up -d`.

## Fixing what it found

trash-watch never changes your config. To fix a missing CF, have it print the YAML:

```sh
docker compose run --rm trash-watch python -u trash_watch.py --suggest
```

Paste each block under that instance's `custom_formats:` in your Recyclarr config, then:

```sh
recyclarr sync --preview    # see exactly what Recyclarr will change
recyclarr sync
```

For a CF that was removed or renamed upstream, look up its replacement in the guides and swap the
`trash_id`. For a `changed upstream` item, `recyclarr sync --preview` shows what the guide change does to
your setup.

## Hearing about it again

To get the current findings notified again (for example after changing the notifier), delete
`data/state.json` and restart. The next run re-sends the findings and records a new baseline; it can't report
upstream changes on that run.
