"""Coverage-guided fuzzing (Atheris) of the Hypothesis properties in tests/test_properties.py.

libFuzzer feeds each property's `.hypothesis.fuzz_one_input`, so a fuzzer finding is a failing property.

Atheris only has Linux x86_64 wheels, so this runs in CI (.github/workflows/fuzz.yml) or an amd64 container:

    pip install --require-hashes --no-deps -r requirements-dev.txt -r requirements-fuzz.txt
    python fuzz/fuzz_properties.py <target> [libFuzzer flags]      # e.g. -max_total_time=60
    python fuzz/fuzz_properties.py <target> <crash-file>           # replay a finding
"""

import sys
from pathlib import Path

import atheris
from hypothesis import settings

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

# Registered before the properties are imported so their settings inherit it: the fuzzer owns the inputs
# and the time budget, so there's no example database and no deadline.
settings.register_profile("fuzz", deadline=None, database=None)
settings.load_profile("fuzz")

TARGETS = {
    "notifications": "test_notifications_stay_phone_sized_whatever_the_names",
    "notification_counts": "test_every_finding_is_shown_or_counted_in_a_more_line",
    "discord": "test_discord_messages_fit_and_never_mention_anyone",
    "yaml_scalar": "test_yaml_scalars_load_back_as_exactly_the_string",
    "suggestions": "test_suggestions_parse_back_to_exactly_the_blocks_for_the_gaps",
    "load_yaml": "test_loading_config_text_only_ever_builds_plain_data",
    "checks": "test_checks_never_crash_on_well_formed_configs_and_guides",
}


def main() -> None:
    """Fuzz the target named on the command line; libFuzzer takes the remaining arguments."""
    if sys.argv[1:2] == [] or sys.argv[1] not in TARGETS:
        sys.exit(f"usage: {sys.argv[0]} <target> [libFuzzer flags]\ntargets: {', '.join(TARGETS)}")
    target = sys.argv.pop(1)

    # PyYAML is guidance too: with only trash_watch instrumented, the fuzzer can't tell one document from another.
    with atheris.instrument_imports(include=["trash_watch", "yaml"]):
        import test_properties  # noqa: PLC0415 - imported inside the block so it gets instrumented

    prop = getattr(test_properties, TARGETS[target])
    atheris.Setup(sys.argv, prop.hypothesis.fuzz_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
