import json
import shutil
import urllib.request
from pathlib import Path

import pytest
from hypothesis import settings

import trash_watch as tw

# pytest --hypothesis-profile=thorough runs 5,000 examples per property instead of 100.
settings.register_profile("thorough", max_examples=5000, deadline=None)

REAL_SYNC_GUIDES = tw.sync_guides  # conftest stubs it per test; test_sync_guides uses the real one
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch):
    """Each test gets its own copy of the fixture guides and config, no settings from the real .env,
    no git and no network."""
    guides = tmp_path / "data" / "guides"
    shutil.copytree(FIXTURES / "guides", guides)
    shutil.copytree(FIXTURES / "config", tmp_path / "config")
    monkeypatch.setattr(tw, "DATA", tmp_path / "data")
    monkeypatch.setattr(tw, "CACHE", guides)
    monkeypatch.setattr(tw, "STATE", tmp_path / "data" / "state.json")
    monkeypatch.setattr(tw, "CONFIG_ROOT", tmp_path / "config")
    monkeypatch.setattr(tw, "PROFILE_MAP", {})
    monkeypatch.setattr(tw, "IGNORE", set())
    monkeypatch.setattr(tw, "sync_guides", lambda: "fixture")

    def no_network(*_args, **_kwargs):
        raise AssertionError("tests must not touch the network")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    return tmp_path


@pytest.fixture
def findings():
    """Runs every check over the fixture config and returns the (group, item) findings."""

    def run():
        guides = tw.load_guides()
        out = []
        for app, inst, cfs, qps in tw.load_instances([]):
            out += tw.check(app, inst, cfs, qps, guides)[0]
        return out

    return run


@pytest.fixture
def notifications(monkeypatch):
    """Captures what run_once would send, instead of sending it."""
    sent = []

    def capture(_title, findings=(), **_kwargs):
        sent.append(list(findings))

    monkeypatch.setattr(tw, "notify", capture)
    return sent


@pytest.fixture
def edit_guide_cf(workspace):
    """Changes one fixture CF's JSON in the test's copy of the guides, as an upstream commit would."""

    def edit(filename, change):
        path = workspace / "data/guides/docs/json/radarr/cf" / filename
        cf = json.loads(path.read_text())
        change(cf)
        path.write_text(json.dumps(cf))

    return edit
