"""Property-based tests (Hypothesis) for everything that turns untrusted text into output: notifications,
the YAML that --suggest prints for the operator to paste, the YAML loader, and the checks themselves.

Names, trash_ids and scores come from the TRaSH Guides JSON and from the operator's config, so the
strategies use arbitrary Unicode, including control characters, line separators and lone surrogates.
Each property is a plain Hypothesis test, so fuzz/fuzz_properties.py can drive it with a coverage-guided
fuzzer (Atheris) through `.hypothesis.fuzz_one_input`.
"""

import collections
import datetime
import json
import re

import yaml
from hypothesis import example, given
from hypothesis import strategies as st

import trash_watch as tw

# Any text, including what json.loads can produce but st.text() never does: lone surrogates.
any_text = st.text(st.one_of(st.characters(), st.characters(categories=["Cs"])))
# Text with no bullets, plus signs or ellipses, so the lines of a notification can be counted.
plain_text = st.text(st.characters(categories=["L", "Nd", "Zs"]), min_size=1, max_size=30)

FOOTER = re.compile(r"…plus (\d+) more \(full list: docker logs trash-watch\)")


@given(st.lists(st.tuples(any_text, any_text), max_size=60), st.booleans())
def test_notifications_stay_phone_sized_whatever_the_names(findings, bold):
    text = tw.render(findings, max_lines=tw.MAX_LINES, max_chars=1900, bold=bold)
    assert len(text) <= 1900
    assert len(text.split("\n")) <= tw.MAX_LINES
    assert not tw.CONTROL_CHARS.search(text.replace("\n", ""))  # no name adds a line of its own


@given(st.lists(st.tuples(plain_text, plain_text), max_size=60))
def test_every_finding_is_shown_or_counted_in_a_more_line(findings):
    distinct = len(set(findings))
    shown = counted = 0
    for line in tw.render(findings, max_lines=tw.MAX_LINES, max_chars=1900).split("\n"):
        if more := re.fullmatch(r"• \+(\d+) more", line):
            counted += int(more[1])
        elif footer := FOOTER.fullmatch(line):
            counted += int(footer[1])
        elif line.startswith("• "):
            shown += 1
    assert shown + counted == distinct
    # The log isn't capped: it shows every finding
    assert sum(line.startswith("• ") for line in tw.render(findings).split("\n")) == distinct


@given(any_text, st.lists(st.tuples(any_text, any_text), max_size=60))
@example(title="@everyone", findings=[("radarr/movies · @here", "missing <@&123> @everyone")])
def test_discord_messages_fit_and_never_mention_anyone(title, findings):
    payload = json.loads(tw.discord_payload(title, findings))
    assert len(payload["content"]) <= 2000
    assert payload["allowed_mentions"] == {"parse": []}


@given(any_text)
def test_yaml_scalars_load_back_as_exactly_the_string(value):
    assert yaml.safe_load(f"k: {tw.yaml_scalar(value)}") == {"k": value}


gaps = st.fixed_dictionaries(
    {
        "app": st.sampled_from(tw.APPS),
        "instance": any_text,
        "profile": any_text,
        "guide": any_text,
        "score_set": any_text,
        "trash_id": any_text,
        "cf": any_text,
        "score": st.one_of(st.none(), st.integers()),
        "synced": st.booleans(),
    }
)


REGRESSION_GAP = {
    "app": "radarr",
    "instance": "movies",
    "profile": "SQP-1",
    "guide": "x",
    "score_set": "default",
    "trash_id": "abc",
    "cf": "Name\nmalicious: true",
    "score": 5,
    "synced": False,
}


@given(st.lists(gaps, max_size=8), any_text)
@example(gap_list=[REGRESSION_GAP], commit="abc1234")  # a line break in a CF name ended the comment line
@example(gap_list=[], commit="\r>")  # ...and so did one in the commit, in the header
@example(gap_list=[{**REGRESSION_GAP, "profile": "\U0001f600 \u2028", "trash_id": ""}], commit="x")  # emoji, separators
def test_suggestions_parse_back_to_exactly_the_blocks_for_the_gaps(gap_list, commit):
    blocks = yaml.safe_load(tw.render_suggestions(gap_list, commit)) or []
    got = collections.Counter(
        (tid, block["assign_scores_to"][0]["name"], block["assign_scores_to"][0].get("score"))
        for block in blocks
        for tid in block["trash_ids"]
    )
    assert all(set(block) == {"trash_ids", "assign_scores_to"} for block in blocks)  # nothing injected
    assert got == collections.Counter((g["trash_id"], g["profile"], g["score"]) for g in gap_list)


PLAIN_TYPES = (dict, list, str, int, float, bool, type(None), datetime.date, bytes, set)


def plain(value):
    if isinstance(value, dict):
        return all(plain(k) and plain(v) for k, v in value.items())
    if isinstance(value, (list, set)):
        return all(plain(v) for v in value)
    return isinstance(value, PLAIN_TYPES)


@given(any_text)
def test_loading_config_text_only_ever_builds_plain_data(text):
    try:
        doc = tw.load_yaml(text)
    except yaml.YAMLError:
        return
    assert plain(doc)


@given(st.sampled_from(["!secret", "!env_var"]), st.from_regex(r"[A-Za-z_][A-Za-z0-9_]{0,30}", fullmatch=True))
def test_secret_and_env_var_tags_are_never_resolved(tag, name):
    assert tw.load_yaml(f"api_key: {tag} {name}") == {"api_key": name}


# A small id space, so configs and guides share ids, profiles match and every check runs.
ids = st.sampled_from(["a", "b", "c", "d", "e"])
junk = st.one_of(st.none(), st.booleans(), st.integers(), any_text, st.lists(st.integers(), max_size=2))
score_sets = st.sampled_from(["default", "sqp-1-1080p", "anime"])
guide_cfs = st.dictionaries(
    ids,
    st.fixed_dictionaries(
        {
            "name": any_text,
            "trash_scores": st.dictionaries(score_sets, st.one_of(st.integers(), junk), max_size=3),
        }
    ),
    max_size=5,
)
guide_qps = st.dictionaries(
    ids,
    st.fixed_dictionaries(
        {
            "name": st.one_of(any_text, st.sampled_from(["SQP-1", "[SQP] SQP-1"])),
            "trash_score_set": score_sets,
            "formatItems": st.dictionaries(any_text, ids, max_size=5),
        }
    ),
    max_size=3,
)
group_ids = st.sampled_from(["g1", "g2", "g3"])
guide_groups = st.dictionaries(
    group_ids,
    st.fixed_dictionaries(
        {
            "name": any_text,
            "custom_formats": st.lists(
                st.fixed_dictionaries(
                    {"trash_id": ids, "required": st.booleans()}, optional={"default": st.booleans()}
                ),
                max_size=4,
            ),
            "quality_profiles": st.fixed_dictionaries({"include": st.dictionaries(any_text, ids, max_size=2)}),
        },
        optional={"default": st.sampled_from(["true", "false", True])},
    ),
    max_size=3,
)
profile_names = st.one_of(any_text, st.sampled_from(["SQP-1", "sqp-1"]))
config_cfs = st.lists(
    st.fixed_dictionaries(
        {
            "trash_ids": st.lists(ids, max_size=5),
            "assign_scores_to": st.lists(
                st.one_of(
                    st.fixed_dictionaries({"name": profile_names}),
                    st.fixed_dictionaries({"name": profile_names, "score": st.one_of(st.integers(), junk)}),
                ),
                max_size=2,
            ),
        }
    ),
    max_size=3,
)
group_sections = st.fixed_dictionaries(
    {},
    optional={
        "add": st.lists(
            st.fixed_dictionaries(
                {"trash_id": group_ids},
                optional={
                    "select": st.lists(ids, max_size=3),
                    "exclude": st.lists(ids, max_size=3),
                    "select_all": st.booleans(),
                    "assign_scores_to": st.lists(st.fixed_dictionaries({"name": profile_names}), max_size=2),
                },
            ),
            max_size=3,
        ),
        "skip": st.lists(group_ids, max_size=2),
    },
)
config_qps = st.lists(
    st.one_of(
        st.fixed_dictionaries({"name": profile_names}, optional={"score_set": score_sets}),
        st.fixed_dictionaries({"trash_id": ids}, optional={"name": profile_names}),
    ),
    max_size=3,
)


@given(guide_cfs, guide_qps, guide_groups, config_cfs, config_qps, st.lists(group_sections, max_size=2))
def test_checks_never_crash_on_well_formed_configs_and_guides(
    cfs_in_guide, qps_in_guide, groups_in_guide, cfs, qps, sections
):
    for tid, cf in cfs_in_guide.items():
        cf["trash_id"] = tid
    for tid, qp in qps_in_guide.items():
        qp["trash_id"] = tid
    for gid, group in groups_in_guide.items():
        group["trash_id"] = gid
    guides = {"radarr": {"cf": cfs_in_guide, "qp": qps_in_guide, "groups": groups_in_guide}}
    cfs = cfs + [{"custom_format_groups": s} for s in sections]
    gap_list = []
    findings, *_ = tw.check("radarr", "movies", cfs, qps, guides, gap_list)
    assert all(isinstance(group, str) and isinstance(item, str) for group, item in findings)
    assert all(gap["score"] is None or type(gap["score"]) is int for gap in gap_list)
    # ...and whatever they find renders and suggests without error
    tw.render(findings, max_lines=tw.MAX_LINES, max_chars=1900)
    yaml.safe_load(tw.render_suggestions(gap_list, "abc1234"))
