#!/usr/bin/env python3
"""
trash-watch: checks a Recyclarr config against the current TRaSH Guides JSON.

Reports:
  - trash_ids in your config that no longer exist upstream (removed/renamed CFs)
  - CFs the guide's profile (e.g. an SQP) includes that your profile doesn't score, or that are missing
  - a profile whose score_set differs from the guide profile's
  - scores you set that differ from the guide's score for that profile's score set
  - CFs/profiles you use whose definition changed upstream since the last run
Only notifies when the findings change, so it won't spam you daily. Anything listed in IGNORE is skipped;
profiles it can't match to a guide profile are listed in the log on every run.
"""

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

import yaml

GUIDES_REPO = "https://github.com/TRaSH-Guides/Guides.git"
DATA = Path(os.getenv("DATA_DIR", "/data"))
CACHE = DATA / "guides"
STATE = DATA / "state.json"
CONFIG_ROOT = Path(os.getenv("CONFIG_ROOT", "/config"))  # Recyclarr app-data dir
INTERVAL = int(float(os.getenv("INTERVAL_HOURS", "24")) * 3600)
RUN_ONCE = os.getenv("RUN_ONCE") == "1"
NTFY_URL = os.getenv("NTFY_URL")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
# Optional: {"My 4K Profile": "<guide quality-profile trash_id or name>"} for renamed profiles
PROFILE_MAP = json.loads(os.getenv("PROFILE_MAP") or "{}")
# Optional: comma-separated trash_ids (CFs or guide profiles) and profile names you skip on purpose
IGNORE = {s.strip() for s in os.getenv("IGNORE", "").split(",") if s.strip()}
APPS = ("radarr", "sonarr")
# Where Recyclarr keeps the config-templates repo (v8, then v7 layout); only one with includes.json is used
TEMPLATE_REPOS = ("resources/config-templates/git/official", "repositories/config-templates")
# Instance keys that don't affect what's checked; anything else unknown is logged as not understood
KNOWN_KEYS = {
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
MAX_LINES = 20  # notification body cap, so it reads on a phone; the log always gets everything
PER_GROUP = 3  # items shown per profile in a notification, so one busy profile can't hide the rest


class Loader(yaml.SafeLoader):
    """SafeLoader that also accepts Recyclarr's !secret and !env_var tags, as their names (never resolved)."""


for _tag in ("!secret", "!env_var"):
    Loader.add_constructor(_tag, lambda _loader, node: str(node.value))


def load_yaml(text):
    return yaml.load(text, Loader=Loader)  # noqa: S506 - Loader is a SafeLoader subclass (see above)


# git runs with fixed arguments (no shell); the only variable parts are this script's own paths and
# GUIDES_REPO. It's found on PATH, as installed in the image.
def git(*args, cwd=None):
    command = ["git", *args]
    result = subprocess.run(command, cwd=cwd or CACHE, check=True, capture_output=True, text=True)  # noqa: S603
    return result.stdout.strip()


def sync_guides():
    if not (CACHE / ".git").exists():
        DATA.mkdir(parents=True, exist_ok=True)
        clone = ("clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", GUIDES_REPO, str(CACHE))
        git(*clone, cwd=DATA)
        git("sparse-checkout", "set", "docs/json")
    else:
        git("fetch", "-q", "--depth", "1", "origin")
        git("reset", "-q", "--hard", "origin/HEAD")
    return git("rev-parse", "--short", "HEAD")


def load_guides():
    guides = {}
    for app in APPS:
        base = CACHE / "docs/json" / app
        guides[app] = {
            kind: {d["trash_id"]: d for d in (json.loads(f.read_text()) for f in (base / folder).glob("*.json"))}
            for kind, folder in (("cf", "cf"), ("qp", "quality-profiles"))
        }
    return guides


def config_files():
    files = [p for p in (CONFIG_ROOT / "recyclarr.yml", CONFIG_ROOT / "recyclarr.yaml") if p.exists()]
    configs_dir = CONFIG_ROOT / "configs"
    if configs_dir.is_dir():
        files += sorted(configs_dir.glob("*.y*ml"))
    return files


def template_path(app, template_id):
    for repo in TEMPLATE_REPOS:
        index = CONFIG_ROOT / repo / "includes.json"
        if index.exists():
            for entry in json.loads(index.read_text()).get(app) or []:
                if entry.get("id") == template_id:
                    return CONFIG_ROOT / repo / entry["template"]
            return None
    return None


def load_instances(warnings):
    """(app, instance, custom_formats, quality_profiles) per instance, with local and template includes
    merged in. Anything that can't be read or isn't understood goes to warnings (log only)."""
    instances = []
    for f in config_files():
        doc = load_yaml(f.read_text()) or {}
        for app in APPS:
            for name, settings in (doc.get(app) or {}).items():
                inst = settings or {}
                tag = f"{app}/{name}"
                cfs = list(inst.get("custom_formats") or [])
                qps = list(inst.get("quality_profiles") or [])
                for inc in inst.get("include") or []:
                    if "config" in inc:
                        p = Path(inc["config"])
                        p = p if p.is_absolute() else CONFIG_ROOT / "includes" / p
                    elif "template" in inc:
                        p = template_path(app, inc["template"])
                    else:
                        p = None
                    if not (p and p.exists()):
                        warnings.append(
                            f"{tag}: include {inc} not found; CFs it adds aren't counted, "
                            f"so 'missing' findings for this instance may be wrong"
                        )
                        continue
                    d = load_yaml(p.read_text()) or {}
                    cfs += d.get("custom_formats") or []
                    qps += d.get("quality_profiles") or []
                for key in sorted(set(inst) - KNOWN_KEYS):
                    warnings.append(
                        f"{tag}: '{key}' isn't understood by trash-watch; findings for this instance may be incomplete"
                    )
                # Profiles that are only scored (defined in the app, not in quality_profiles) count too
                named = {qp.get("name") for qp in qps}
                for block in cfs:
                    for a in block.get("assign_scores_to") or []:
                        if a.get("name") and a["name"] not in named:
                            qps.append({"name": a["name"]})
                            named.add(a["name"])
                instances.append((app, name, cfs, qps))
    return instances


def match_guide_profile(qp, guide_qps):
    """Guide profile for a config profile, and how it was matched: by trash_id (guide-backed), PROFILE_MAP
    (trash_id or guide name), name (with or without the '[SQP] ' style prefix), or a unique score_set."""
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


def guide_score(cf, score_set):
    """The guide's score for a CF in a score set, falling back to its default (None if it has neither)."""
    scores = (cf or {}).get("trash_scores", {})
    return scores.get(score_set, scores.get("default"))


def check(app, inst, cfs, qps, guides, gaps=None):
    """Findings are (group, item) pairs; the group is the instance or instance · profile. Also returns the
    CFs, guide profiles and score sets in use (for fingerprints) and one coverage line per profile (log).
    With a gaps list, also appends one dict per guide CF a profile doesn't score (used by --suggest)."""
    g = guides[app]
    tag = f"{app}/{inst}"
    findings, used_cfs, used_qps, score_sets, coverage = [], set(), set(), {"default"}, []

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
        group = f"{tag} · {label}"
        if gq and gq["name"] != label:
            group += f" (guide: {gq['name']})"
        if not gq:
            if qp.get("trash_id"):
                findings.append((group, "profile trash_id not found upstream"))
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
            findings.append((group, f"score_set {score_set}, guide uses {guide_set}"))
        # The CFs this profile scores are the blocks whose assign_scores_to names it, not the whole instance
        scored = {}  # trash_id -> explicit score, or None for the guide's
        for block in cfs:
            for a in block.get("assign_scores_to") or []:
                if a.get("name") == qp.get("name"):
                    scored.update(dict.fromkeys(block.get("trash_ids") or [], a.get("score")))
        for cf_name, tid in gq.get("formatItems", {}).items():
            if tid in IGNORE or tid in scored:
                continue
            findings.append(
                (
                    group,
                    f"{cf_name}: synced, but not scored in this profile" if tid in used_cfs else f"missing {cf_name}",
                )
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
                        "synced": tid in used_cfs,
                    }
                )
        for tid, score in scored.items():
            if score is None or tid in IGNORE or tid not in g["cf"]:
                continue
            want = guide_score(g["cf"][tid], score_set)
            if want is not None and want != score:
                findings.append((group, f"{g['cf'][tid]['name']}: {score}, guide {want}"))
    return findings, used_cfs, used_qps, score_sets, coverage


def cf_fingerprint(cf, score_sets):
    """What a CF does for you: its conditions, rename flag, and its scores in the sets you use. Upstream
    edits to descriptions, links or other languages' score sets don't count as a change."""
    scores = cf.get("trash_scores", {})
    return digest(
        {
            "specifications": cf.get("specifications"),
            "includeCustomFormatWhenRenaming": cf.get("includeCustomFormatWhenRenaming"),
            "scores": {s: scores.get(s, scores.get("default")) for s in sorted(score_sets)},
        }
    )


def qp_fingerprint(qp):
    return digest({k: v for k, v in qp.items() if k not in ("trash_description", "trash_url", "group")})


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]


def render(findings, max_lines=None, max_chars=None, bold=False):
    """Findings grouped by instance/profile: a heading per group, then one bullet per item,
    upstream changes last. With max_lines (a notification), each group shows PER_GROUP items,
    whole groups are added while they fit, and a 'plus N more' footer covers the rest."""
    groups = {}
    for group, item in sorted(set(findings)):
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


def post(name, url, data, headers):
    if not url.lower().startswith(("https://", "http://")):  # no file: or other schemes from a typo'd .env
        print(f"notify via {name} skipped: the URL must start with https:// or http://", flush=True)
        return
    request = urllib.request.Request(url, data=data, headers={"User-Agent": "trash-watch/1.0", **headers})  # noqa: S310 - scheme checked above
    try:
        urllib.request.urlopen(request, timeout=15)  # noqa: S310 - scheme checked above
    except Exception as e:  # noqa: BLE001 - never let a notify failure kill the loop, or skip the other target
        print(f"notify via {name} failed: {e}", flush=True)


def notify(title, findings=(), text=None):
    """Logs everything; ntfy/Discord get the phone-sized version (MAX_LINES, Discord's 2000 chars)."""
    print(f"== {title}\n{text or render(findings)}\n", flush=True)
    if NTFY_URL:
        post("ntfy", NTFY_URL, (text or render(findings, MAX_LINES)).encode(), {"Title": title})
    if DISCORD_WEBHOOK:
        head = f"**{title}**\n"
        body = text or render(findings, MAX_LINES, 2000 - len(head), bold=True)
        post(
            "Discord",
            DISCORD_WEBHOOK,
            json.dumps({"content": (head + body)[:2000]}).encode(),
            {"Content-Type": "application/json"},
        )


def yaml_scalar(value):
    """A profile name as YAML: plain when that round-trips, otherwise double-quoted."""
    try:
        if yaml.safe_load(f"k: {value}") == {"k": value}:
            return value
    except yaml.YAMLError:
        pass
    return json.dumps(value)


def render_suggestions(gaps, commit):
    """Recyclarr custom_formats blocks for the gaps, one per profile and guide score, indented to paste
    under an instance's custom_formats: list. Text only; the caller prints it."""
    out = [
        f"# trash-watch --suggest @ TRaSH Guides {commit}. Nothing has been written to your config.",
        "# Review each block, paste it into that instance's custom_formats: list, then run",
        "# `recyclarr sync --preview` before `recyclarr sync`.",
    ]
    if not gaps:
        return "\n".join([*out, "#", "# Nothing to suggest: every checked profile scores all its guide CFs."])
    profiles = {}
    for gap in sorted(gaps, key=lambda x: (x["app"], x["instance"], x["profile"], x["cf"])):
        profiles.setdefault((gap["app"], gap["instance"], gap["profile"]), []).append(gap)
    for (app, inst, profile), items in profiles.items():
        first = items[0]
        out += [
            "",
            f"# {app}/{inst} · {profile} (guide: {first['guide']}, score_set {first['score_set']})",
            f"# paste under:  {app}: > {inst}: > custom_formats:",
        ]
        by_score = {}
        for gap in items:
            by_score.setdefault(gap["score"], []).append(gap)
        for score, block in by_score.items():
            out.append("      - trash_ids:")
            for gap in block:
                note = " (already synced, not scored in this profile)" if gap["synced"] else ""
                out.append(f"          - {gap['trash_id']} # {gap['cf']}{note}")
            out += ["        assign_scores_to:", f"          - name: {yaml_scalar(profile)}"]
            if score is not None:  # without a score, Recyclarr uses the guide's (or 0)
                out.append(f"            score: {score}")
    return "\n".join(out)


def suggest():
    """--suggest: print paste-ready blocks for every missing or unscored guide CF. Prints only: no state,
    no notifications, and the config stays read-only."""
    commit = sync_guides()
    guides = load_guides()
    warnings, gaps = [], []
    for app, inst, cfs, qps in load_instances(warnings):
        check(app, inst, cfs, qps, guides, gaps)
    print(render_suggestions(gaps, commit), flush=True)
    for w in warnings:
        print(f"# warning: {w}", flush=True)


def run_once():
    commit = sync_guides()
    guides = load_guides()
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    old_fp = state.get("fingerprints", {}) if state.get("version") == STATE_VERSION else {}
    if state and state.get("version") != STATE_VERSION:
        print("Fingerprint format changed: re-baselining, so no upstream changes are reported this run", flush=True)
    findings, fp, warnings = [], {}, []
    used = {app: {"cf": set(), "qp": set(), "sets": set()} for app in APPS}

    for app, inst, cfs, qps in load_instances(warnings):
        f, used_cfs, used_qps, score_sets, coverage = check(app, inst, cfs, qps, guides)
        findings += f
        used[app]["cf"] |= used_cfs
        used[app]["qp"] |= used_qps
        used[app]["sets"] |= score_sets
        print("\n".join(coverage), flush=True)
    for w in warnings:
        print(f"warning: {w}", flush=True)

    for app, u in used.items():
        for tid in u["cf"] & guides[app]["cf"].keys():
            fp[f"{app}:cf:{tid}"] = cf_fingerprint(guides[app]["cf"][tid], u["sets"])
        for tid in u["qp"]:
            fp[f"{app}:qp:{tid}"] = qp_fingerprint(guides[app]["qp"][tid])

    for key, h in fp.items():
        if key in old_fp and old_fp[key] != h:
            app, kind, tid = key.split(":")
            name = guides[app][kind][tid]["name"]
            findings.append((f"{app} · changed upstream", f"{'CF' if kind == 'cf' else 'Profile'} {name}"))

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
                "checked": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check a Recyclarr config against the TRaSH Guides.")
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="print Recyclarr YAML for each missing CF, grouped by profile, and exit "
        "(console only: no notifications, no state, never writes the config)",
    )
    if parser.parse_args().suggest:
        suggest()
        raise SystemExit(0)
    while True:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001 - report any failure, then try again next interval
            notify("trash-watch error", text=repr(e))
        if RUN_ONCE:
            break
        time.sleep(INTERVAL)
