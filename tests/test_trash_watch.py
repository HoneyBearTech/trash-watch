import pytest
import yaml

import trash_watch as tw

SQP1 = "radarr/movies · SQP-1 (1080p) (guide: [SQP] SQP-1 (1080p))"
X265_HD = "a0000000000000000000000000000001"


def test_dead_trash_id(findings):
    assert ("radarr/movies", "CF deadbeefdeadbeefdeadbeefdeadbeef removed or renamed upstream") in findings()


def test_missing_cf_for_sqp_profile(findings):
    result = findings()
    assert (SQP1, "missing x265 (HD)") in result
    # CFs the profile does score aren't reported as missing
    assert not [item for group, item in result if "BR-DISK" in item or "missing Repack" in item]


def test_score_mismatch_uses_the_profiles_score_set(findings):
    # The guide's default score is 5, but the profile's score_set is sqp-1-1080p, where it's 6
    assert (SQP1, "Repack/Proper: 99, guide 6") in findings()


def test_exactly_the_expected_findings(findings):
    assert sorted(findings()) == sorted([
        ("radarr/movies", "CF deadbeefdeadbeefdeadbeefdeadbeef removed or renamed upstream"),
        (SQP1, "missing x265 (HD)"),
        (SQP1, "Repack/Proper: 99, guide 6"),
    ])


def test_ignore_skips_a_deliberately_missing_cf(findings, monkeypatch):
    monkeypatch.setattr(tw, "IGNORE", {X265_HD})
    assert (SQP1, "missing x265 (HD)") not in findings()


def test_upstream_change_detected_between_two_runs(notifications, edit_guide_cf):
    tw.run_once()  # first run: baseline fingerprints, no upstream changes possible
    assert not [f for f in notifications[0] if "changed upstream" in f[0]]

    edit_guide_cf("br-disk.json", lambda cf: cf["specifications"][0]["fields"].update(value="ISO"))
    tw.run_once()

    assert ("radarr · changed upstream", "CF BR-DISK") in notifications[1]


def test_unrelated_upstream_edit_is_not_a_change(notifications, edit_guide_cf):
    tw.run_once()
    # A score set no profile here uses, and the description link, don't affect this config
    edit_guide_cf("br-disk.json", lambda cf: cf.update(trash_scores={**cf["trash_scores"], "french-vostfr": -5},
                                                       trash_regex="https://example.invalid"))
    tw.run_once()

    assert len(notifications) == 1  # findings unchanged, so the second run sent nothing


def test_secret_and_env_var_tags_load_without_being_resolved(workspace, findings):
    text = (workspace / "config/recyclarr.yml").read_text()
    with pytest.raises(yaml.constructor.ConstructorError):
        yaml.safe_load(text)  # plain YAML rejects Recyclarr's custom tags

    doc = yaml.load(text, Loader=tw.Loader)
    movies = doc["radarr"]["movies"]
    assert movies["api_key"] == "radarr_api_key"  # the secret's name, never its value
    assert movies["base_url"] == "RADARR_URL"
    assert len(tw.load_instances([])) == 1
    assert findings()  # and the checks run on that config


def test_suggest_prints_paste_ready_yaml_for_missing_cf(capsys):
    tw.suggest()
    out = capsys.readouterr().out

    assert "# radarr/movies · SQP-1 (1080p) (guide: [SQP] SQP-1 (1080p), score_set sqp-1-1080p)" in out
    assert "# paste under:  radarr: > movies: > custom_formats:" in out
    # The output is valid YAML: exactly the block to add, scored with the guide's score for the profile
    assert yaml.safe_load(out) == [{
        "trash_ids": [X265_HD],
        "assign_scores_to": [{"name": "SQP-1 (1080p)", "score": -10000}],
    }]


def test_suggest_only_prints(workspace, notifications, capsys):
    config = {p: p.read_bytes() for p in (workspace / "config").rglob("*") if p.is_file()}
    tw.suggest()

    assert {p: p.read_bytes() for p in (workspace / "config").rglob("*") if p.is_file()} == config
    assert not tw.STATE.exists()  # no state written, so the daemon's next report isn't affected
    assert notifications == []
    assert "Nothing has been written to your config" in capsys.readouterr().out


def test_suggest_respects_ignore(capsys, monkeypatch):
    monkeypatch.setattr(tw, "IGNORE", {X265_HD})
    tw.suggest()
    out = capsys.readouterr().out
    assert "Nothing to suggest" in out
    assert yaml.safe_load(out) is None


def test_suggestions_grouped_by_profile_and_score():
    def gap(profile, tid, cf, score, synced=False):
        return {"app": "sonarr", "instance": "series", "profile": profile, "guide": "WEB-1080p",
                "score_set": "default", "trash_id": tid, "cf": cf, "score": score, "synced": synced}

    text = tw.render_suggestions([
        gap("WEB: 1080p", "c1" * 16, "AV1", -10000),
        gap("WEB: 1080p", "c2" * 16, "BR-DISK", -10000, synced=True),
        gap("WEB: 1080p", "c3" * 16, "Repack/Proper", 5),
        gap("Anime", "c4" * 16, "VOSTFR", None),
    ], "abc1234")

    assert yaml.safe_load(text) == [
        {"trash_ids": ["c4" * 16], "assign_scores_to": [{"name": "Anime"}]},  # no guide score: none set
        {"trash_ids": ["c1" * 16, "c2" * 16], "assign_scores_to": [{"name": "WEB: 1080p", "score": -10000}]},
        {"trash_ids": ["c3" * 16], "assign_scores_to": [{"name": "WEB: 1080p", "score": 5}]},
    ]
    assert "already synced, not scored in this profile" in text
    assert text.count("# sonarr/series · ") == 2


def test_yaml_scalar_quotes_only_when_needed():
    for name in ("SQP-3 Remux|IMAX-E|2160p", "WEB-DL (1080p)", "a: b", "#tag", "123", "yes", "- x"):
        assert yaml.safe_load(f"k: {tw.yaml_scalar(name)}") == {"k": name}
    assert tw.yaml_scalar("SQP-3 Remux|IMAX-E|2160p") == "SQP-3 Remux|IMAX-E|2160p"
