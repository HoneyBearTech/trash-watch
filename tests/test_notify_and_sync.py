"""Phone-sized notifications, sending to each target, and syncing the guides clone (from a local git repo)."""

import json
import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import pytest
from conftest import REAL_SYNC_GUIDES

import trash_watch as tw


def many_findings() -> list[tw.Finding]:
    out = [(f"radarr/movies · Profile {p}", f"missing CF {p}{i}") for p in "ABCDEF" for i in range(5)]
    return [*out, ("radarr · changed upstream", "CF Remaster")]


def test_notification_is_capped_for_a_phone() -> None:
    text = tw.render(many_findings(), max_lines=tw.MAX_LINES, max_chars=2000, bold=True)
    lines = text.splitlines()
    assert len(lines) <= tw.MAX_LINES
    assert lines[0] == "**radarr/movies · Profile A**"
    assert lines[1:5] == ["• missing CF A0", "• missing CF A1", "• missing CF A2", "• +2 more"]
    # Each profile takes 5 lines and 19 are available before the footer, so 3 profiles fit; the footer
    # counts the rest: 3 profiles x 5 findings, plus the upstream change
    assert len(lines) == 3 * 5 + 1
    assert lines[-1] == "…plus 16 more (full list: docker logs trash-watch)"


def test_log_gets_everything_with_upstream_changes_last() -> None:
    lines = tw.render(many_findings()).splitlines()
    assert len(lines) == 6 * 6 + 2
    assert lines[-2:] == ["radarr · changed upstream", "• CF Remaster"]


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any, bytes]]:
    """Records each HTTP request instead of sending it; ntfy's fails, to show Discord still goes out."""
    requests = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> None:
        requests.append((request.full_url, request.headers, request.data))
        if "ntfy" in request.full_url:
            msg = "ntfy is down"
            raise OSError(msg)
        assert timeout == 15

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return requests


def test_each_notifier_is_sent_separately(
    sent: list[tuple[str, Any, bytes]], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tw, "NTFY_URL", "https://ntfy.example/topic")
    monkeypatch.setattr(tw, "DISCORD_WEBHOOK", "https://discord.example/api/webhooks/1/x")
    tw.notify("3 item(s)", many_findings()[:3])

    assert [url for url, _, _ in sent] == ["https://ntfy.example/topic", "https://discord.example/api/webhooks/1/x"]
    discord = json.loads(sent[1][2])["content"]
    assert discord.startswith("**3 item(s)**\n**radarr/movies · Profile A**\n• missing CF A0")
    assert sent[0][1]["Title"] == "3 item(s)"
    assert "notify via ntfy failed: ntfy is down" in capsys.readouterr().out


def test_non_http_notifier_urls_are_refused(
    sent: list[tuple[str, Any, bytes]], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tw, "NTFY_URL", "file:///etc/passwd")
    monkeypatch.setattr(tw, "DISCORD_WEBHOOK", None)
    tw.notify("x", text="y")
    assert sent == []
    assert "notify via ntfy skipped: the URL must start with https:// or http://" in capsys.readouterr().out


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_sync_guides_clones_only_the_json_then_follows_upstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
def test_unwritable_data_dir_fails_early_with_the_fix(workspace: Path) -> None:
    data = workspace / "data"
    data.chmod(0o500)  # like a data/ left root-owned by an older, root-running image
    try:
        with pytest.raises(PermissionError, match=r"isn't writable by this container's user .* chown -R \d+:\d+ /data"):
            tw.check_data_writable()
    finally:
        data.chmod(0o700)


@pytest.fixture
def requests_made(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Record (method, URL) for every request instead of sending it."""
    made = []

    def fake_urlopen(request: urllib.request.Request, timeout: float) -> None:
        assert timeout == 15
        made.append((request.get_method(), request.full_url))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return made


HEARTBEAT = "https://kuma.example/api/push/abc?status=up&msg=OK&ping="


def test_a_completed_check_pings_the_heartbeat(
    requests_made: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tw, "HEARTBEAT_URL", HEARTBEAT)
    monkeypatch.setattr(tw, "notify", lambda *_args, **_kwargs: None)
    tw.run_once()
    assert requests_made == [("GET", HEARTBEAT)]


def test_a_failed_check_never_pings(requests_made: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> str:
        msg = "GitHub is down"
        raise OSError(msg)

    monkeypatch.setattr(tw, "HEARTBEAT_URL", HEARTBEAT)
    monkeypatch.setattr(tw, "sync_guides", fail)
    monkeypatch.setattr(tw, "RUN_ONCE", True)
    monkeypatch.setattr(tw, "notify", lambda *_args, **_kwargs: None)
    assert tw.main([]) == 1
    assert requests_made == []


def test_no_heartbeat_url_no_request(requests_made: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tw, "notify", lambda *_args, **_kwargs: None)
    tw.run_once()
    assert requests_made == []


def test_heartbeat_refuses_non_http_urls_and_survives_failures(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tw, "HEARTBEAT_URL", "file:///etc/passwd")
    tw.heartbeat()
    assert "heartbeat skipped: the URL must start with https:// or http://" in capsys.readouterr().out

    def down(*_args: object, **_kwargs: object) -> None:
        msg = "kuma is down"
        raise OSError(msg)

    monkeypatch.setattr(tw, "HEARTBEAT_URL", HEARTBEAT)
    monkeypatch.setattr(urllib.request, "urlopen", down)
    tw.heartbeat()  # doesn't raise
    assert "heartbeat failed: kuma is down" in capsys.readouterr().out
