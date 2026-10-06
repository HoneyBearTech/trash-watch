"""Phone-sized notifications, sending to each target, and syncing the guides clone (from a local git repo)."""

import json
import os
import subprocess
import urllib.request

import pytest
from conftest import REAL_SYNC_GUIDES

import trash_watch as tw


def many_findings():
    out = [(f"radarr/movies · Profile {p}", f"missing CF {p}{i}") for p in "ABCDEF" for i in range(5)]
    return [*out, ("radarr · changed upstream", "CF Remaster")]


def test_notification_is_capped_for_a_phone():
    text = tw.render(many_findings(), max_lines=tw.MAX_LINES, max_chars=2000, bold=True)
    lines = text.splitlines()
    assert len(lines) <= tw.MAX_LINES
    assert lines[0] == "**radarr/movies · Profile A**"
    assert lines[1:5] == ["• missing CF A0", "• missing CF A1", "• missing CF A2", "• +2 more"]
    # Each profile takes 5 lines and 19 are available before the footer, so 3 profiles fit; the footer
    # counts the rest: 3 profiles x 5 findings, plus the upstream change
    assert len(lines) == 3 * 5 + 1
    assert lines[-1] == "…plus 16 more (full list: docker logs trash-watch)"


def test_log_gets_everything_with_upstream_changes_last():
    lines = tw.render(many_findings()).splitlines()
    assert len(lines) == 6 * 6 + 2
    assert lines[-2:] == ["radarr · changed upstream", "• CF Remaster"]


@pytest.fixture
def sent(monkeypatch):
    """Records each HTTP request instead of sending it; ntfy's fails, to show Discord still goes out."""
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request.full_url, request.headers, request.data))
        if "ntfy" in request.full_url:
            raise OSError("ntfy is down")
        assert timeout == 15

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return requests


def test_each_notifier_is_sent_separately(sent, monkeypatch, capsys):
    monkeypatch.setattr(tw, "NTFY_URL", "https://ntfy.example/topic")
    monkeypatch.setattr(tw, "DISCORD_WEBHOOK", "https://discord.example/api/webhooks/1/x")
    tw.notify("3 item(s)", many_findings()[:3])

    assert [url for url, _, _ in sent] == ["https://ntfy.example/topic", "https://discord.example/api/webhooks/1/x"]
    discord = json.loads(sent[1][2])["content"]
    assert discord.startswith("**3 item(s)**\n**radarr/movies · Profile A**\n• missing CF A0")
    assert sent[0][1]["Title"] == "3 item(s)"
    assert "notify via ntfy failed: ntfy is down" in capsys.readouterr().out


def test_non_http_notifier_urls_are_refused(sent, monkeypatch, capsys):
    monkeypatch.setattr(tw, "NTFY_URL", "file:///etc/passwd")
    monkeypatch.setattr(tw, "DISCORD_WEBHOOK", None)
    tw.notify("x", text="y")
    assert sent == []
    assert "notify via ntfy skipped: the URL must start with https:// or http://" in capsys.readouterr().out


def git(cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_sync_guides_clones_only_the_json_then_follows_upstream(tmp_path, monkeypatch):
    upstream = tmp_path / "upstream"
    (upstream / "docs/json/radarr/cf").mkdir(parents=True)
    (upstream / "docs/json/radarr/cf/a.json").write_text("{}")
    (upstream / "docs/Radarr").mkdir(parents=True)
    (upstream / "docs/Radarr/guide.md").write_text("not needed")
    git(upstream, "init", "-q", "-b", "master")
    git(upstream, "add", "-A")
    git(upstream, "commit", "-q", "-m", "one")
    monkeypatch.setattr(tw, "GUIDES_REPO", f"file://{upstream}")
    monkeypatch.setattr(tw, "DATA", tmp_path / "sync-data")
    monkeypatch.setattr(tw, "CACHE", tmp_path / "sync-data/guides")

    first = REAL_SYNC_GUIDES()
    assert (tmp_path / "sync-data/guides/docs/json/radarr/cf/a.json").exists()
    assert not (tmp_path / "sync-data/guides/docs/Radarr").exists()  # sparse: docs/json only

    (upstream / "docs/json/radarr/cf/b.json").write_text("{}")
    git(upstream, "add", "-A")
    git(upstream, "commit", "-q", "-m", "two")
    second = REAL_SYNC_GUIDES()

    assert second != first
    assert second == git(upstream, "rev-parse", "--short", "HEAD")
    assert (tmp_path / "sync-data/guides/docs/json/radarr/cf/b.json").exists()


@pytest.mark.skipif(os.getuid() == 0, reason="root can write anywhere")
def test_unwritable_data_dir_fails_early_with_the_fix(workspace):
    data = workspace / "data"
    data.chmod(0o500)  # like a data/ left root-owned by an older, root-running image
    try:
        with pytest.raises(PermissionError, match=r"isn't writable by this container's user .* chown -R \d+:\d+ /data"):
            tw.check_data_writable()
    finally:
        data.chmod(0o700)
