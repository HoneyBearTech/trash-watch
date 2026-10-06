# How it works

trash-watch is one Python script (`trash_watch.py`) in one container. It doesn't talk to Radarr, Sonarr
or Recyclarr. It reads Recyclarr's config files and the TRaSH Guides JSON, and compares the two.

```
TRaSH-Guides/Guides (GitHub) ──git fetch──▶ data/guides/docs/json ─┐
                                                                   ├─▶ check ─▶ data/state.json
Recyclarr app-data dir ──read-only mount──▶ /config ───────────────┘      │
                                                                          └─▶ ntfy / Discord (on change)
```

## Each run

1. **Sync the guides.** The first run makes a shallow, sparse clone of `TRaSH-Guides/Guides` that holds
   only `docs/json`. Later runs fetch and hard-reset it to the latest upstream commit. That clone is the
   only thing trash-watch writes besides `state.json`.
2. **Load the guides.** For `radarr` and `sonarr`: every custom format (`cf/*.json`) and quality profile
   (`quality-profiles/*.json`), keyed by `trash_id`.
3. **Load the config.** It reads `recyclarr.yml` or `recyclarr.yaml` and `configs/*.yml` under `/config`.
   For each Radarr and Sonarr instance it collects `custom_formats` and `quality_profiles`, including those
   from includes: local `include: - config:` files (relative paths resolve under `includes/`) and
   `include: - template:` ones, looked up in the `includes.json` of Recyclarr's copy of the
   config-templates repo. A profile that's only named in `assign_scores_to` counts as a profile too.
   Recyclarr's `!secret` and `!env_var` tags are accepted, and their values are never used.
4. **Check each instance** (below). The log gets one line per profile saying what it was checked against,
   that it was ignored, or that it matched nothing and was **not checked**, plus a `warning:` for an
   include it couldn't find or an instance key it doesn't understand (such as `custom_format_groups`).
5. **Compare with the last run** and notify if the findings changed. Then it saves `data/state.json`.

Then it sleeps for `INTERVAL_HOURS`, or exits if `RUN_ONCE=1`. If a run fails, it sends a
`trash-watch error` notification and tries again at the next interval.

## Matching your profiles to the guide

A profile in your config is matched to a guide quality profile:

1. by its `trash_id`, if it has one (a guide-backed profile);
2. otherwise by `PROFILE_MAP`, which maps your profile name to a guide profile's `trash_id` or name;
3. otherwise by name, case-insensitively, with or without the guide's `[Tag] ` prefix;
4. otherwise by its `score_set`, if exactly one guide profile uses it (`sqp-2` → `[SQP] SQP-2`, but not
   `sqp-3`, which two guide profiles share).

A profile that matches nothing isn't checked, and the log says so on every run. Map it in `PROFILE_MAP`,
or put it in `IGNORE` if it's your own.

## Ignoring things on purpose

`IGNORE` in `.env` is a comma-separated list. A `trash_id` there (a CF or a guide profile) is left out of
every check, including upstream changes; a profile name skips that profile. Use it for deliberate choices,
such as using x265 (no HDR/DV) instead of x265 (HD), so they stop showing up as findings.

## Findings

Findings are grouped under a heading: the instance (`radarr/movies`), the instance and profile
(`radarr/movies · HD Bluray + WEB`, plus `(guide: <name>)` when the guide profile is named differently), or
`<app> · changed upstream`.

| Heading | Item | Meaning |
| --- | --- | --- |
| instance | `CF <id> removed or renamed upstream` | A `trash_id` in your `custom_formats` isn't upstream any more. Recyclarr can't sync it. |
| profile | `profile trash_id not found upstream` | A guide-backed profile's `trash_id` is gone. |
| profile | `missing <CF>` | The guide's profile has a CF that's nowhere in this instance. |
| profile | `<CF>: synced, but not scored in this profile` | The CF is in the instance, but no block that's assigned to this profile lists it, so the profile scores it 0. |
| profile | `score_set X, guide uses Y` | Your profile takes its scores from a different score set than the guide profile it matches. |
| profile | `<CF>: N, guide M` | A score in `assign_scores_to` differs from the guide's score in your profile's `score_set` (falling back to `default`). Ignore it if it's intentional. |
| `<app> · changed upstream` | `CF <name>` / `Profile <name>` | The JSON of a CF or profile you use changed since the last run. Run `recyclarr sync --preview` to see what that does to your setup. |

Guide-backed profiles (those with a `trash_id`) only get the first two checks: Recyclarr syncs their CFs
and scores from the guide itself.

## When you're notified

All findings go into one report. If it's empty, the run logs `OK` and nothing is sent. If its hash
matches the last report in `state.json`, it logs "No new findings" and nothing is sent. Otherwise:

- **The log** gets the full report: every heading and every item.
- **ntfy and Discord** get a phone-sized version: at most 3 items per heading (then `• +N more`), whole
  headings added while they fit in 20 lines (and Discord's 2,000 characters), then
  `…plus N more (full list: docker logs trash-watch)`. Upstream changes come last. On Discord the headings
  are bold.

```
**radarr/movies · HD Bluray + WEB (guide: [SQP] SQP-1 (1080p))**
• missing <CF>
• missing <CF>
• missing <CF>
• +9 more
**sonarr/series · WEB-1080p**
• <CF>: 10, guide 15
…plus 4 more (full list: docker logs trash-watch)
```

Each target is sent separately, so a failure on one doesn't stop the other.

"Changed upstream" findings appear once: on the next run the stored fingerprint matches again. So a
report that loses only those lines counts as changed and is sent again.

## Suggest mode

`--suggest` runs the same sync and checks, then prints a Recyclarr `custom_formats` block for each
`missing` or `synced, but not scored` finding instead of reporting. Blocks are grouped by profile, with one
block per guide score: `assign_scores_to` names the profile and sets the guide's score for the profile's
`score_set` (falling back to `default`, and left out when the guide has no score). Profile names are quoted
only when YAML needs it. The output parses as YAML, and it's indented to paste under an instance's
`custom_formats:` list. Nothing else happens: no notification, no `state.json`, and no write to the
config.

## State

`data/state.json` holds a 16-character SHA-256 fingerprint of each guide CF and profile your config uses,
a hash of the last report, the guides commit, the time of the last completed check (UTC; `--health` reads it)
and a format version. A CF's
fingerprint covers only what affects you: its conditions, its rename flag, and its scores in the score
sets your profiles use. So a new language's score set or a reworded description isn't a "change". A
profile's covers everything but its description and group.

Deleting `state.json` is safe: the next run notifies the current findings again and starts fingerprinting
from scratch. It can't report upstream changes on that first run. The same happens once, on purpose, when
the fingerprint format changes.
