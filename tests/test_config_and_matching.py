"""How the Recyclarr config is read (includes, templates, unknown keys) and how profiles match the guide."""

import json

import trash_watch as tw

SQP1_ID = "b0000000000000000000000000000001"
X265_HD = "a0000000000000000000000000000001"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def write_config(workspace, text):
    write(workspace / "config/recyclarr.yml", text)


def coverage_lines():
    guides, lines = tw.load_guides(), []
    for app, inst, cfs, qps in tw.load_instances([]):
        lines += tw.check(app, inst, cfs, qps, guides)[4]
    return lines


def test_local_and_template_includes_are_merged(workspace, findings):
    # x265 (HD) comes from a template include, so the SQP profile no longer misses it
    write(
        workspace / "config/repositories/config-templates/includes.json",
        json.dumps({"radarr": [{"id": "x265-block", "template": "radarr/includes/x265.yml"}]}),
    )
    write(
        workspace / "config/repositories/config-templates/radarr/includes/x265.yml",
        f"custom_formats:\n  - trash_ids: [{X265_HD}]\n    assign_scores_to:\n      - name: SQP-1 (1080p)\n",
    )
    write(workspace / "config/includes/extra.yml", "quality_profiles:\n  - name: Extra profile\n")
    text = (workspace / "config/recyclarr.yml").read_text()
    write_config(
        workspace,
        text.replace(
            "    quality_profiles:",
            "    include:\n      - template: x265-block\n      - config: extra.yml\n    quality_profiles:",
        ),
    )

    warnings = []
    [(_, _, cfs, qps)] = tw.load_instances(warnings)
    assert warnings == []
    assert any(X265_HD in (b.get("trash_ids") or []) for b in cfs)
    assert "Extra profile" in [qp.get("name") for qp in qps]
    assert not [f for f in findings() if "x265" in f[1]]


def test_missing_include_and_unknown_key_are_warned(workspace):
    text = (workspace / "config/recyclarr.yml").read_text()
    write_config(
        workspace,
        text.replace(
            "    quality_profiles:",
            "    include:\n      - template: no-such-template\n    custom_format_groups: {}\n    quality_profiles:",
        ),
    )
    warnings = []
    tw.load_instances(warnings)
    assert any("include {'template': 'no-such-template'} not found" in w for w in warnings)
    assert any("'custom_format_groups' isn't understood" in w for w in warnings)


def test_configs_dir_and_scored_only_profiles_are_read(workspace):
    write(
        workspace / "config/configs/sonarr.yml",
        "sonarr:\n  series:\n    custom_formats:\n      - trash_ids: []\n"
        "        assign_scores_to:\n          - name: Only Scored Here\n",
    )
    instances = {(app, inst): qps for app, inst, _, qps in tw.load_instances([])}
    assert ("sonarr", "series") in instances
    assert instances["sonarr", "series"] == [{"name": "Only Scored Here"}]


def guide_qps():
    return tw.load_guides()["radarr"]["qp"]


def test_profile_map_by_trash_id_or_guide_name(monkeypatch):
    monkeypatch.setattr(tw, "PROFILE_MAP", {"Mine": SQP1_ID, "Also mine": "[SQP] SQP-1 (1080p)"})
    assert tw.match_guide_profile({"name": "Mine"}, guide_qps())[1] == "PROFILE_MAP"
    assert tw.match_guide_profile({"name": "Also mine"}, guide_qps())[0]["trash_id"] == SQP1_ID


def test_unique_score_set_matches_but_never_guesses(workspace):
    gq, how = tw.match_guide_profile({"name": "Renamed", "score_set": "sqp-1-1080p"}, guide_qps())
    assert (gq["trash_id"], how) == (SQP1_ID, "score_set")

    # A second guide profile with the same score set makes it ambiguous: no match
    second = json.loads((workspace / "data/guides/docs/json/radarr/quality-profiles/sqp-1-1080p.json").read_text())
    second.update(trash_id="b0000000000000000000000000000002", name="[SQP] SQP-1 WEB (1080p)")
    write(workspace / "data/guides/docs/json/radarr/quality-profiles/second.json", json.dumps(second))
    assert tw.match_guide_profile({"name": "Renamed", "score_set": "sqp-1-1080p"}, guide_qps()) == (None, None)
    assert tw.match_guide_profile({"name": "Renamed", "score_set": "default"}, guide_qps()) == (None, None)


def test_unmatched_and_ignored_profiles_are_logged_not_silently_skipped(workspace, monkeypatch):
    text = (workspace / "config/recyclarr.yml").read_text()
    write_config(
        workspace,
        text.replace("    quality_profiles:", "    quality_profiles:\n      - name: My Own\n      - name: Skip Me"),
    )
    monkeypatch.setattr(tw, "IGNORE", {"Skip Me"})
    lines = coverage_lines()
    assert "radarr/movies · My Own: NOT CHECKED, no guide profile matches" in "\n".join(lines)
    assert "radarr/movies · Skip Me: ignored (IGNORE)" in lines
    assert "radarr/movies · SQP-1 (1080p): checked against [SQP] SQP-1 (1080p) (matched by name)" in lines


def test_score_set_mismatch_and_dead_guide_backed_profile(workspace, findings):
    text = (workspace / "config/recyclarr.yml").read_text()
    text = text.replace("score_set: sqp-1-1080p", "score_set: default")
    text = text.replace(
        "    quality_profiles:",
        "    quality_profiles:\n      - trash_id: ffffffffffffffffffffffffffffffff\n        name: Gone From The Guide",
    )
    write_config(workspace, text)
    result = findings()
    assert (
        "radarr/movies · SQP-1 (1080p) (guide: [SQP] SQP-1 (1080p))",
        "score_set default, guide uses sqp-1-1080p",
    ) in result
    assert ("radarr/movies · Gone From The Guide", "profile trash_id not found upstream") in result
