"""trash-watch: check a Recyclarr config against the current TRaSH Guides JSON.

Reports:
  - trash_ids in your config that no longer exist upstream (removed/renamed CFs)
  - CFs the guide's profile (e.g. an SQP) includes that your profile doesn't score, or that are missing
  - a profile whose score_set differs from the guide profile's
  - scores you set that differ from the guide's score for that profile's score set
  - CFs, profiles and CF groups you use whose definition changed upstream since the last run
Only notifies when the findings change, so it won't spam you daily. Anything listed in IGNORE is skipped;
profiles it can't match to a guide profile are listed in the log on every run.
"""

import argparse
import calendar
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterable

# Parsed JSON and YAML: the guides and the operator's config. Values are checked where they're used.
type JsonValue = Any
type Block = dict[str, JsonValue]  # a custom_formats block, a profile, a guide CF/profile/group, a gap
type Finding = tuple[str, str]  # (heading, item): "radarr/movies · SQP-1", "missing x265 (HD)"
type AppGuides = dict[str, dict[str, Block]]  # "cf" / "qp" / "groups" -> trash_id -> JSON
type Guides = dict[str, AppGuides]  # "radarr" / "sonarr" -> AppGuides
type Instance = tuple[str, str, list[Block], list[Block]]  # app, instance name, CF blocks, profiles

GUIDES_REPO = "https://github.com/TRaSH-Guides/Guides.git"
DATA = Path(os.getenv("DATA_DIR", "/data"))
CACHE = DATA / "guides"
STATE = DATA / "state.json"
CONFIG_ROOT = Path(os.getenv("CONFIG_ROOT", "/config"))  # Recyclarr app-data dir
INTERVAL = int(float(os.getenv("INTERVAL_HOURS", "24")) * 3600)
RUN_ONCE = os.getenv("RUN_ONCE") == "1"
NTFY_URL = os.getenv("NTFY_URL")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
# Optional: pinged after every completed check (Uptime Kuma Push monitor, healthchecks.io, ...)
HEARTBEAT_URL = os.getenv("HEARTBEAT_URL")
# Optional: {"My 4K Profile": "<guide quality-profile trash_id or name>"} for renamed profiles
PROFILE_MAP = json.loads(os.getenv("PROFILE_MAP") or "{}")
# Optional: comma-separated trash_ids (CFs or guide profiles) and profile names you skip on purpose
IGNORE = {s.strip() for s in os.getenv("IGNORE", "").split(",") if s.strip()}
APPS = ("radarr", "sonarr")
# Where Recyclarr keeps the config-templates repo (v8, then v7 layout); only one with includes.json is used
TEMPLATE_REPOS = ("resources/config-templates/git/official", "repositories/config-templates")
# Instance keys that don't affect what's checked; anything else unknown is logged as not understood
KNOWN_KEYS = {
    "custom_format_groups",
    "base_url",
    "api_key",
    "custom_formats",
    "quality_profiles",
    "include",
    "quality_definition",
    "delete_old_custom_formats",
    "replace_existing_custom_formats",
    "media_naming",
    "media_management",
}
STATE_VERSION = 2  # bump when fingerprints change shape: the next run re-baselines instead of alerting
# Line breaks and other control characters (C0, DEL, C1, Unicode line/paragraph separators), plus what YAML
# refuses anywhere in a document (lone surrogates, U+FFFE, U+FFFF)
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\ud800-\udfff\ufffe\uffff]+")
MAX_LINES = 20  # notification body cap, so it reads on a phone; the log always gets everything
PER_GROUP = 3  # items shown per profile in a notification, so one busy profile can't hide the rest
DISCORD_LIMIT = 2000  # characters per Discord message


class Loader(yaml.SafeLoader):
    """SafeLoader that also accepts Recyclarr's !secret and !env_var tags, as their names (never resolved)."""


for _tag in ("!secret", "!env_var"):
    Loader.add_constructor(_tag, lambda _loader, node: str(node.value))


def load_yaml(text: str) -> JsonValue:
    """Parse YAML from the config with the safe loader above."""
    return yaml.load(text, Loader=Loader)  # noqa: S506 - Loader is a SafeLoader subclass (see above)


def git(*args: str, cwd: Path | None = None) -> str:
    """Run git with fixed arguments (no shell) and return its output.

    The only variable parts are this script's own paths and GUIDES_REPO; git is found on PATH, as installed
    in the image.
    """
    command = ["git", *args]
    result = subprocess.run(command, cwd=cwd or CACHE, check=True, capture_output=True, text=True)  # noqa: S603
    return result.stdout.strip()


def check_data_writable() -> None:
    """Fail early, with the fix, when the data directory belongs to another user.

    For example root-owned from an older, root-running image, or created by Docker before the first start.
    """
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        probe = DATA / ".write-test"
        probe.touch()
        probe.unlink()
    except OSError as e:
        uid, gid = os.getuid(), os.getgid()
        msg = (
            f"{DATA} isn't writable by this container's user ({uid}:{gid}). Fix it once on the host, in the "
            f'trash-watch directory: docker run --rm -v "$PWD/data:/data" busybox chown -R {uid}:{gid} /data '
            "(see docs/upgrading.md)"
        )
        raise PermissionError(msg) from e


def sync_guides() -> str:
    """Clone or update the sparse, shallow guides checkout (docs/json only); return its short commit."""
    check_data_writable()
    if not (CACHE / ".git").exists():
        clone = ("clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", GUIDES_REPO, str(CACHE))
        git(*clone, cwd=DATA)
        git("sparse-checkout", "set", "docs/json")
    else:
        git("fetch", "-q", "--depth", "1", "origin")
        git("reset", "-q", "--hard", "origin/HEAD")
    return git("rev-parse", "--short", "HEAD")


def load_guides() -> Guides:
    """Load every CF, quality profile and CF group of each app, keyed by trash_id."""
    guides = {}
    for app in APPS:
        base = CACHE / "docs/json" / app
        guides[app] = {
            kind: {d["trash_id"]: d for d in (json.loads(f.read_text()) for f in (base / folder).glob("*.json"))}
            for kind, folder in (("cf", "cf"), ("qp", "quality-profiles"), ("groups", "cf-groups"))
        }
    return guides


def config_files() -> list[Path]:
    """Return the Recyclarr config files: recyclarr.yml or .yaml, then configs/*.yml."""
    files = [p for p in (CONFIG_ROOT / "recyclarr.yml", CONFIG_ROOT / "recyclarr.yaml") if p.exists()]
    configs_dir = CONFIG_ROOT / "configs"
    if configs_dir.is_dir():
        files += sorted(configs_dir.glob("*.y*ml"))
    return files


def template_path(app: str, template_id: str) -> Path | None:
    """Find a template include in includes.json of Recyclarr's config-templates checkout."""
    for repo in TEMPLATE_REPOS:
        index = CONFIG_ROOT / repo / "includes.json"
        if index.exists():
            for entry in json.loads(index.read_text()).get(app) or []:
                if entry.get("id") == template_id:
                    return CONFIG_ROOT / repo / entry["template"]
            return None
    return None


def read_include(app: str, include: Block) -> Block | None:
    """Return the contents of an `include:` entry (local `config:` or `template:`), or None if not found."""
    if "config" in include:
        path = Path(include["config"])
        path = path if path.is_absolute() else CONFIG_ROOT / "includes" / path
    elif "template" in include:
        path = template_path(app, include["template"])
    else:
        return None
    return (load_yaml(path.read_text()) or {}) if path and path.exists() else None


def load_instances(warnings: list[str]) -> list[Instance]:
    """Return every Radarr/Sonarr instance in the config, with local and template includes merged in.

    Anything that can't be read or isn't understood goes to warnings (log only). Profiles that are only
    named in assign_scores_to count as profiles; custom_format_groups sections ride along as marker blocks
    for check() to resolve against the guides.
    """
    instances = []
    for f in config_files():
        doc = load_yaml(f.read_text()) or {}
        for app in APPS:
            for name, settings in (doc.get(app) or {}).items():
                inst = settings or {}
                tag = f"{app}/{name}"
                cfs = list(inst.get("custom_formats") or [])
                qps = list(inst.get("quality_profiles") or [])
                groups = [inst["custom_format_groups"]] if inst.get("custom_format_groups") else []
                for include in inst.get("include") or []:
                    d = read_include(app, include)
                    if d is None:
                        warnings.append(
                            f"{tag}: include {include} not found; CFs it adds aren't counted, "
                            f"so 'missing' findings for this instance may be wrong"
                        )
                        continue
                    cfs += d.get("custom_formats") or []
                    qps += d.get("quality_profiles") or []
                    if d.get("custom_format_groups"):
                        groups.append(d["custom_format_groups"])
                warnings += [
                    f"{tag}: '{key}' isn't understood by trash-watch; findings for this instance may be incomplete"
                    for key in sorted(set(inst) - KNOWN_KEYS)
                ]
                named = {qp.get("name") for qp in qps}
                for block in cfs:
                    for a in block.get("assign_scores_to") or []:
                        if a.get("name") and a["name"] not in named:
                            qps.append({"name": a["name"]})
                            named.add(a["name"])
                cfs += [{"custom_format_groups": g} for g in groups]
                instances.append((app, name, cfs, qps))
    return instances


def match_guide_profile(qp: Block, guide_qps: dict[str, Block]) -> tuple[Block | None, str | None]:
    """Find the guide profile for a config profile, and say how it was matched.

    By trash_id (guide-backed), PROFILE_MAP (trash_id or guide name), name (with or without the '[SQP] '
    style prefix), or a score_set only one guide profile uses.
    """
    by_name = {g["name"].lower(): g for g in guide_qps.values()}
    if qp.get("trash_id"):
        return guide_qps.get(qp["trash_id"]), "trash_id"
    mapped = PROFILE_MAP.get(qp.get("name"))
    if mapped:
        return guide_qps.get(mapped) or by_name.get(mapped.lower()), "PROFILE_MAP"
    name = (qp.get("name") or "").lower()
    for gname, g in by_name.items():
        if name and (name == gname or gname.split("] ", 1)[-1] == name):
            return g, "name"
    sets = [g for g in guide_qps.values() if g.get("trash_score_set") == qp.get("score_set")]
    if qp.get("score_set") not in (None, "default") and len(sets) == 1:
        return sets[0], "score_set"
    return None, None


def guide_score(cf: Block | None, score_set: str) -> int | None:
    """Return the guide's score for a CF in a score set, falling back to its default.

    None if it has neither, or if the guide's value isn't an integer (it ends up in notifications and in
    YAML the operator pastes).
    """
    scores = (cf or {}).get("trash_scores", {})
    score = scores.get(score_set, scores.get("default")) if isinstance(scores, dict) else None
    return score if isinstance(score, int) and not isinstance(score, bool) else None


def one_line(text: object) -> str:
    """Return text from the guides or the config as a single line.

    Line breaks and other control characters become spaces, so a name can't add lines to a notification or
    to YAML the operator pastes.
    """
    return CONTROL_CHARS.sub(" ", str(text))


def group_profiles(group: Block) -> set[str]:
    """Return the trash_ids of the guide quality profiles a CF group is meant for (its include list)."""
    include = (group.get("quality_profiles") or {}).get("include") or {}
    return set(include.values()) if isinstance(include, dict) else set()


def group_cfs(group: Block, entry: Block) -> set[str]:
    """Return the CFs Recyclarr syncs for a group entry.

    The required ones, the defaults minus `exclude`, plus `select` (or every optional one with `select_all`).
    """
    members = [c for c in group.get("custom_formats") or [] if isinstance(c, dict) and c.get("trash_id")]
    required = {c["trash_id"] for c in members if c.get("required") is True}
    default = {c["trash_id"] for c in members if c.get("default") is True}
    optional = {c["trash_id"] for c in members} - required
    chosen = required | (default - set(entry.get("exclude") or []))
    return chosen | (optional if entry.get("select_all") is True else set(entry.get("select") or []) & optional)


def resolve_groups(
    tag: str, cfs: list[Block], qps: list[Block], g: AppGuides
) -> tuple[list[Block], list[Finding], set[str]]:
    """Turn the instance's custom_format_groups (Recyclarr v8) into ordinary CF blocks.

    So the per-profile checks see the CFs groups add. Groups listed under `add` score the profiles in their
    `assign_scores_to`, or else the guide-backed profiles they're meant for; default groups are synced for
    those profiles too unless skipped. Returns the blocks without the group sections plus the resolved
    ones, findings for group references that went stale upstream, and the groups in use.
    """
    groups = g.get("groups") or {}
    sections = [b["custom_format_groups"] for b in cfs if isinstance(b.get("custom_format_groups"), dict)]
    plain = [b for b in cfs if "custom_format_groups" not in b]
    entries = [e for s in sections for e in s.get("add") or [] if isinstance(e, dict)]
    skipped = {gid for s in sections for gid in s.get("skip") or []} | {e.get("trash_id") for e in entries}
    guide_backed = {qp["trash_id"] for qp in qps if qp.get("trash_id")}
    for gid, group in groups.items():
        if str(group.get("default")).lower() == "true" and gid not in skipped and guide_backed & group_profiles(group):
            entries.append({"trash_id": gid})
    blocks, findings, used = [], [], set()
    for entry in entries:
        gid = entry.get("trash_id")
        if gid in IGNORE:
            continue
        group = groups.get(gid)
        if group is None:
            findings.append((tag, f"CF group {gid} removed or renamed upstream"))
            continue
        used.add(gid)
        members = {c.get("trash_id") for c in group.get("custom_formats") or [] if isinstance(c, dict)}
        for key in ("select", "exclude"):
            findings += [
                (tag, f"CF {cid} under {key} is no longer in group {group.get('name', gid)}")
                for cid in entry.get(key) or []
                if cid not in members and cid not in IGNORE
            ]
        targets = entry.get("assign_scores_to") or [
            {"trash_id": t} for t in sorted(guide_backed & group_profiles(group))
        ]
        blocks.append({"trash_ids": sorted(group_cfs(group, entry)), "assign_scores_to": targets})
    return plain + blocks, findings, used


def scored_in(cfs: list[Block], profile_name: str | None) -> dict[str, JsonValue]:
    """Return the CFs a profile scores (the blocks whose assign_scores_to names it), with any explicit score."""
    scored = {}
    for block in cfs:
        for a in block.get("assign_scores_to") or []:
            if a.get("name") == profile_name:
                scored.update(dict.fromkeys(block.get("trash_ids") or [], a.get("score")))
    return scored


def check(  # noqa: C901, PLR0912 - one pass over the profiles, in config order, keeps the log and findings in step
    instance: Instance,
    guides: Guides,
    gaps: list[Block] | None = None,
) -> tuple[list[Finding], set[str], set[str], set[str], list[str], set[str]]:
    """Check one instance against the guides.

    Returns the findings ((heading, item) pairs, the heading being the instance or instance · profile), the
    CFs, guide profiles, score sets and CF groups in use (for fingerprints), and one coverage line per
    profile (log). With a gaps list, also appends one dict per guide CF a profile doesn't score (--suggest).
    """
    app, inst, cfs, qps = instance
    g = guides[app]
    tag = f"{app}/{inst}"
    used_cfs, used_qps, score_sets, coverage = set(), set(), {"default"}, []
    cfs, findings, used_groups = resolve_groups(tag, cfs, qps, g)

    for block in cfs:
        for tid in block.get("trash_ids") or []:
            if tid in IGNORE:
                continue
            used_cfs.add(tid)
            if tid not in g["cf"]:
                findings.append((tag, f"CF {tid} removed or renamed upstream"))

    for qp in qps:
        label = qp.get("name") or qp.get("trash_id")
        gq, how = match_guide_profile(qp, g["qp"])
        if IGNORE & {label, qp.get("trash_id"), gq and gq["trash_id"]}:
            coverage.append(f"{tag} · {label}: ignored (IGNORE)")
            continue
        heading = f"{tag} · {label}"
        if gq and gq["name"] != label:
            heading += f" (guide: {gq['name']})"
        if not gq:
            if qp.get("trash_id"):
                findings.append((heading, "profile trash_id not found upstream"))
            coverage.append(
                f"{tag} · {label}: NOT CHECKED, no guide profile matches "
                f"(add it to PROFILE_MAP, or to IGNORE if it's your own)"
            )
            continue
        coverage.append(f"{tag} · {label}: checked against {gq['name']} (matched by {how})")
        used_qps.add(gq["trash_id"])
        if qp.get("trash_id"):
            continue  # guide-backed profile: Recyclarr syncs its CFs and scores itself
        # Recyclarr scores a profile from its own score_set, not the guide profile's
        score_set = qp.get("score_set") or "default"
        score_sets.add(score_set)
        guide_set = gq.get("trash_score_set", "default")
        if score_set != guide_set:
            findings.append((heading, f"score_set {score_set}, guide uses {guide_set}"))
        scored = scored_in(cfs, qp.get("name"))
        for cf_name, tid in gq.get("formatItems", {}).items():
            if tid in IGNORE or tid in scored:
                continue
            synced = tid in used_cfs
            findings.append(
                (heading, f"{cf_name}: synced, but not scored in this profile" if synced else f"missing {cf_name}")
            )
            if gaps is not None:
                gaps.append(
                    {
                        "app": app,
                        "instance": inst,
                        "profile": qp.get("name"),
                        "guide": gq["name"],
                        "score_set": score_set,
                        "trash_id": tid,
                        "cf": cf_name,
                        "score": guide_score(g["cf"].get(tid), score_set),
                        "synced": synced,
                    }
                )
        for tid, score in scored.items():
            if score is None or tid in IGNORE or tid not in g["cf"]:
                continue
            want = guide_score(g["cf"][tid], score_set)
            if want is not None and want != score:
                findings.append((heading, f"{g['cf'][tid]['name']}: {score}, guide {want}"))
    return findings, used_cfs, used_qps, score_sets, coverage, used_groups


def cf_fingerprint(cf: Block, score_sets: Iterable[str]) -> str:
    """Fingerprint what a CF does for you: its conditions, rename flag, and its scores in the sets you use.

    Upstream edits to descriptions, links or other languages' score sets don't count as a change.
    """
    scores = cf.get("trash_scores", {})
    return digest(
        {
            "specifications": cf.get("specifications"),
            "includeCustomFormatWhenRenaming": cf.get("includeCustomFormatWhenRenaming"),
            "scores": {s: scores.get(s, scores.get("default")) for s in sorted(score_sets)},
        }
    )


def qp_fingerprint(qp: Block) -> str:
    """Fingerprint a guide profile or CF group: everything but its description and grouping."""
    return digest({k: v for k, v in qp.items() if k not in {"trash_description", "trash_url", "group"}})


def digest(obj: JsonValue) -> str:
    """Return a short SHA-256 of a JSON-serialisable value."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def render(
    findings: Iterable[Finding],
    *,
    max_lines: int | None = None,
    max_chars: int | None = None,
    bold: bool = False,
) -> str:
    """Render findings grouped by instance/profile: a heading per group, then one bullet per item.

    Upstream changes come last. With max_lines (a notification), each group shows PER_GROUP items, whole
    groups are added while they fit, and a 'plus N more' footer covers the rest.
    """
    groups = {}
    for group, item in sorted({(one_line(g), one_line(i)) for g, i in findings}):
        groups.setdefault(group, []).append(item)
    order = sorted(groups, key=lambda g: (g.endswith("changed upstream"), g))
    lines = []
    for n, group in enumerate(order):
        items = groups[group]
        shown = items[:PER_GROUP] if max_lines else items
        block = [f"**{group}**" if bold else group] + [f"• {i}" for i in shown]
        if len(items) > len(shown):
            block.append(f"• +{len(items) - len(shown)} more")
        if (
            (max_lines and len(lines) + len(block) > max_lines - 1)  # keep a line for the footer
            or (max_chars and len("\n".join(lines + block)) > max_chars - 80)
        ):
            hidden = sum(len(groups[g]) for g in order[n:])
            lines.append(f"…plus {hidden} more (full list: docker logs trash-watch)")
            break
        lines += block
    return "\n".join(lines)


def send(label: str, url: str, data: bytes | None, headers: dict[str, str]) -> None:
    """Request a URL (POST with data, GET without); log failures instead of raising.

    So one target can't stop another or the loop. Only http(s) URLs are opened: no file: or other schemes
    from a typo'd .env.
    """
    if not url.lower().startswith(("https://", "http://")):
        print(f"{label} skipped: the URL must start with https:// or http://", flush=True)
        return
    request = urllib.request.Request(url, data=data, headers={"User-Agent": "trash-watch/1.0", **headers})  # noqa: S310 - scheme checked above
    try:
        urllib.request.urlopen(request, timeout=15)  # noqa: S310 - scheme checked above
    except Exception as e:  # noqa: BLE001 - never let a failed request kill the loop, or skip the next target
        print(f"{label} failed: {e}", flush=True)


def post(name: str, url: str, data: bytes, headers: dict[str, str]) -> None:
    """POST a notification to one target."""
    send(f"notify via {name}", url, data, headers)


def heartbeat() -> None:
    """Ping HEARTBEAT_URL after a completed check, if it's set.

    A dead man's switch for a monitor such as an Uptime Kuma Push monitor or healthchecks.io: the pings stop
    when trash-watch crashes, hangs or keeps failing, and the monitor alerts.
    """
    if HEARTBEAT_URL:
        send("heartbeat", HEARTBEAT_URL, None, {})


def notify(title: str, findings: Iterable[Finding] = (), text: str | None = None) -> None:
    """Log everything; send ntfy/Discord the phone-sized version (MAX_LINES, Discord's 2,000 characters)."""
    findings = list(findings)
    print(f"== {title}\n{text or render(findings)}\n", flush=True)
    if NTFY_URL:
        post("ntfy", NTFY_URL, (text or render(findings, max_lines=MAX_LINES)).encode(), {"Title": title})
    if DISCORD_WEBHOOK:
        post("Discord", DISCORD_WEBHOOK, discord_payload(title, findings, text), {"Content-Type": "application/json"})


def discord_payload(title: str, findings: Iterable[Finding] = (), text: str | None = None) -> bytes:
    """Build a Discord message: at most 2,000 characters, and no mentions.

    A name such as "@everyone" in the guides or the config is shown as text and never pings anyone.
    """
    head = f"**{one_line(title)}**\n"
    body = text or render(findings, max_lines=MAX_LINES, max_chars=DISCORD_LIMIT - len(head), bold=True)
    return json.dumps({"content": (head + body)[:DISCORD_LIMIT], "allowed_mentions": {"parse": []}}).encode()


def yaml_scalar(value: str) -> str:
    """Return a string as a YAML scalar that loads back as exactly that string.

    Plain when that round-trips, otherwise double-quoted by PyYAML's own emitter.
    """
    try:
        if yaml.safe_load(f"k: {value}") == {"k": value}:
            return value
    except yaml.YAMLError:
        pass
    return yaml.safe_dump(value, default_style='"', allow_unicode=True, width=float("inf")).rstrip("\n")


def render_suggestions(gaps: Iterable[Block], commit: str) -> str:
    """Render Recyclarr custom_formats blocks for the gaps, one per profile and guide score.

    Indented to paste under an instance's custom_formats: list. Text only; the caller prints it.
    """
    out = [
        one_line(f"# trash-watch --suggest @ TRaSH Guides {commit}. Nothing has been written to your config."),
        "# Review each block, paste it into that instance's custom_formats: list, then run",
        "# `recyclarr sync --preview` before `recyclarr sync`.",
    ]
    gaps = list(gaps)
    if not gaps:
        return "\n".join([*out, "#", "# Nothing to suggest: every checked profile scores all its guide CFs."])
    profiles = {}
    for gap in sorted(gaps, key=lambda x: (x["app"], x["instance"], x["profile"], x["cf"])):
        profiles.setdefault((gap["app"], gap["instance"], gap["profile"]), []).append(gap)
    for (app, inst, profile), items in profiles.items():
        first = items[0]
        out += [
            "",
            one_line(f"# {app}/{inst} · {profile} (guide: {first['guide']}, score_set {first['score_set']})"),
            one_line(f"# paste under:  {app}: > {inst}: > custom_formats:"),
        ]
        by_score = {}
        for gap in items:
            by_score.setdefault(gap["score"], []).append(gap)
        for score, block in by_score.items():
            out.append("      - trash_ids:")
            for gap in block:
                note = " (already synced, not scored in this profile)" if gap["synced"] else ""
                out.append(f"          - {yaml_scalar(str(gap['trash_id']))} # {one_line(gap['cf'])}{note}")
            out += ["        assign_scores_to:", f"          - name: {yaml_scalar(str(profile))}"]
            if score is not None:  # without a score, Recyclarr uses the guide's (or 0); guide_score() is int-only
                out.append(f"            score: {score}")
    return "\n".join(out)


def suggest() -> None:
    """Print paste-ready blocks for every missing or unscored guide CF (--suggest).

    Prints only: no state, no notifications, and the config stays read-only.
    """
    commit = sync_guides()
    guides = load_guides()
    warnings, gaps = [], []
    for instance in load_instances(warnings):
        check(instance, guides, gaps)
    print(render_suggestions(gaps, commit), flush=True)
    for w in warnings:
        print(f"# warning: {w}", flush=True)


def upstream_changes(
    used: dict[str, dict[str, set[str]]], guides: Guides, old_fp: dict[str, str]
) -> tuple[dict[str, str], list[Finding]]:
    """Fingerprint the CFs, profiles and CF groups in use; report those that changed since the last run."""
    fp = {}
    for app, u in used.items():
        for tid in u["cf"] & guides[app]["cf"].keys():
            fp[f"{app}:cf:{tid}"] = cf_fingerprint(guides[app]["cf"][tid], u["sets"])
        for tid in u["qp"]:
            fp[f"{app}:qp:{tid}"] = qp_fingerprint(guides[app]["qp"][tid])
        for tid in u["groups"]:
            fp[f"{app}:groups:{tid}"] = qp_fingerprint(guides[app]["groups"][tid])
    changes = []
    for key, h in fp.items():
        if key in old_fp and old_fp[key] != h:
            app, kind, tid = key.split(":")
            label = {"cf": "CF", "qp": "Profile", "groups": "CF group"}[kind]
            changes.append((f"{app} · changed upstream", f"{label} {guides[app][kind][tid]['name']}"))
    return fp, changes


def run_once() -> None:
    """Run one check: sync the guides, check every instance, notify if the findings changed, save state, ping."""
    commit = sync_guides()
    guides = load_guides()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    old_fp = state.get("fingerprints", {}) if state.get("version") == STATE_VERSION else {}
    if state and state.get("version") != STATE_VERSION:
        print("Fingerprint format changed: re-baselining, so no upstream changes are reported this run", flush=True)
    findings, warnings = [], []
    used = {app: {"cf": set(), "qp": set(), "sets": set(), "groups": set()} for app in APPS}

    for instance in load_instances(warnings):
        app = instance[0]
        f, used_cfs, used_qps, score_sets, coverage, used_groups = check(instance, guides)
        findings += f
        used[app]["cf"] |= used_cfs
        used[app]["qp"] |= used_qps
        used[app]["sets"] |= score_sets
        used[app]["groups"] |= used_groups
        print("\n".join(coverage), flush=True)
    for w in warnings:
        print(f"warning: {w}", flush=True)

    fp, changes = upstream_changes(used, guides, old_fp)
    findings += changes

    report = render(findings)
    if not findings:
        print(f"OK — config matches TRaSH Guides @ {commit}", flush=True)
    elif digest(report) != state.get("last_report"):
        notify(f"Recyclarr vs TRaSH Guides @ {commit}: {len(set(findings))} item(s)", findings)
    else:
        print(f"No new findings @ {commit} ({len(set(findings))} unchanged)", flush=True)

    STATE.write_text(
        json.dumps(
            {
                "version": STATE_VERSION,
                "fingerprints": fp,
                "last_report": digest(report) if findings else None,
                "commit": commit,
                "checked": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            },
            indent=2,
        )
    )
    heartbeat()  # only after a check that completed and saved its state


def health(now: float | None = None) -> tuple[bool, str]:
    """Say whether the last successful check finished within two intervals (plus ten minutes).

    `--health`, used by the image's HEALTHCHECK, so monitoring notices a watcher that stopped checking,
    whether it crashed, hangs, or every check fails (a failed check doesn't update state.json).
    """
    try:
        # UTC; states written before 0.2 have no "Z", but the container clock they came from was UTC too
        stamp = json.loads(STATE.read_text())["checked"].rstrip("Z")
        checked = calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%S"))
    except (OSError, ValueError, KeyError, TypeError) as e:
        return False, f"unhealthy: no completed check recorded in {STATE} ({type(e).__name__})"
    age = (time.time() if now is None else now) - checked
    limit = 2 * INTERVAL + 600
    if age > limit:
        return False, f"unhealthy: last completed check {age / 3600:.1f} h ago (limit {limit / 3600:.1f} h)"
    return True, f"healthy: last completed check {age / 3600:.1f} h ago"


def main(argv: list[str] | None = None) -> int:
    """Run the command line; return the exit code."""
    parser = argparse.ArgumentParser(description="Check a Recyclarr config against the TRaSH Guides.")
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="print Recyclarr YAML for each missing CF, grouped by profile, and exit "
        "(console only: no notifications, no state, never writes the config)",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="exit 0 if a check completed within two intervals, 1 otherwise (the image's HEALTHCHECK)",
    )
    args = parser.parse_args(argv)
    if args.health:
        ok, message = health()
        print(message, flush=True)
        return 0 if ok else 1
    if args.suggest:
        suggest()
        return 0
    while True:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001 - report any failure, then try again next interval
            notify("trash-watch error", text=repr(e))
            if RUN_ONCE:
                return 1  # a one-time check that failed fails, so it can be scripted
        if RUN_ONCE:
            return 0
        time.sleep(INTERVAL)


if __name__ == "__main__":
    raise SystemExit(main())
