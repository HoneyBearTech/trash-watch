"""Recyclarr v8 custom_format_groups: which CFs a group adds, which profiles score them, and stale references."""

import json

import pytest

import trash_watch as tw

SQP1 = "radarr/movies · SQP-1 (1080p) (guide: [SQP] SQP-1 (1080p))"
X265_HD, REPACK, BR_DISK = (f"a000000000000000000000000000000{n}" for n in (1, 2, 3))
OPTIONAL, DEFAULTS = "c0000000000000000000000000000001", "c0000000000000000000000000000002"
SQP1_GUIDE = "b0000000000000000000000000000001"
SELECT_X265 = f"    custom_format_groups:\n      add:\n        - trash_id: {OPTIONAL}\n          select: [{X265_HD}]\n"


def add_groups(workspace, yaml_block):
    path = workspace / "config/recyclarr.yml"
    path.write_text(path.read_text().replace("    quality_profiles:", yaml_block + "    quality_profiles:", 1))


def test_a_selected_group_cf_scored_in_the_profile_is_not_missing(workspace, findings):
    add_groups(
        workspace,
        f"    custom_format_groups:\n      add:\n        - trash_id: {OPTIONAL}\n          select: [{X265_HD}]\n"
        "          assign_scores_to:\n            - name: SQP-1 (1080p)\n",
    )
    warnings = []
    tw.load_instances(warnings)
    assert warnings == []  # custom_format_groups is understood now
    assert (SQP1, "missing x265 (HD)") not in findings()


def test_a_group_without_assign_scores_to_only_syncs_its_cfs_for_a_named_profile(workspace, findings):
    add_groups(workspace, SELECT_X265)
    assert (SQP1, "x265 (HD): synced, but not scored in this profile") in findings()


def test_stale_group_references_are_reported(workspace, findings):
    gone = "c" * 32
    add_groups(
        workspace,
        f"    custom_format_groups:\n      add:\n        - trash_id: {gone}\n        - trash_id: {OPTIONAL}\n"
        f"          select: [{'d' * 32}]\n          exclude: [{REPACK}]\n",
    )
    result = findings()
    assert ("radarr/movies", f"CF group {gone} removed or renamed upstream") in result
    assert ("radarr/movies", f"CF {'d' * 32} under select is no longer in group [Optional] Fixture x265") in result
    assert ("radarr/movies", f"CF {REPACK} under exclude is no longer in group [Optional] Fixture x265") in result


def test_ignored_groups_are_skipped(workspace, findings, monkeypatch):
    add_groups(workspace, f"    custom_format_groups:\n      add:\n        - trash_id: {'c' * 32}\n")
    monkeypatch.setattr(tw, "IGNORE", {"c" * 32})
    assert not [f for f in findings() if "CF group" in f[1]]


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ({}, {BR_DISK}),  # required only
        ({"select": [X265_HD]}, {BR_DISK, X265_HD}),
        ({"exclude": [BR_DISK]}, {BR_DISK}),  # required CFs can't be excluded
        ({"select_all": True}, {BR_DISK, X265_HD}),
        ({"select": ["not-a-member"]}, {BR_DISK}),
    ],
)
def test_group_cfs_follows_recyclarrs_selection_rules(entry, expected):
    group = tw.load_guides()["radarr"]["groups"][OPTIONAL]
    assert tw.group_cfs(group, entry) == expected


def test_default_groups_sync_for_guide_backed_profiles_unless_skipped():
    g = tw.load_guides()["radarr"]
    qps = [{"trash_id": SQP1_GUIDE}]
    blocks, findings, used = tw.resolve_groups("radarr/movies", [], qps, g)
    assert findings == []
    assert used == {DEFAULTS}
    assert blocks == [{"trash_ids": [REPACK], "assign_scores_to": [{"trash_id": SQP1_GUIDE}]}]

    skip = [{"custom_format_groups": {"skip": [DEFAULTS]}}]
    assert tw.resolve_groups("radarr/movies", skip, qps, g) == ([], [], set())
    # ...and named profiles never get default groups
    assert tw.resolve_groups("radarr/movies", [], [{"name": "Mine"}], g) == ([], [], set())


def test_a_group_changed_upstream_is_reported_between_runs(workspace, notifications):
    add_groups(workspace, SELECT_X265)
    tw.run_once()
    path = workspace / "data/guides/docs/json/radarr/cf-groups/optional-x265.json"
    group = json.loads(path.read_text())
    group["custom_formats"].append({"name": "Repack/Proper", "trash_id": REPACK, "required": True})
    path.write_text(json.dumps(group))
    tw.run_once()
    assert ("radarr · changed upstream", "CF group [Optional] Fixture x265") in notifications[-1]
