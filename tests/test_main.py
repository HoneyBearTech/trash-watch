"""The command line: exit codes for one-time checks, and the health check the image's HEALTHCHECK runs."""

import json
import time
from typing import Never

import pytest

import trash_watch as tw


def write_state(checked: str) -> None:
    tw.STATE.parent.mkdir(parents=True, exist_ok=True)
    tw.STATE.write_text(json.dumps({"version": tw.STATE_VERSION, "checked": checked}))


def at(seconds_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds_ago))


def test_healthy_after_a_recent_check(capsys: pytest.CaptureFixture[str]) -> None:
    write_state(at(3600))
    assert tw.main(["--health"]) == 0
    assert capsys.readouterr().out.startswith("healthy: last completed check 1.0 h ago")


def test_states_written_before_the_utc_marker_still_count(capsys: pytest.CaptureFixture[str]) -> None:
    write_state(at(1800).rstrip("Z"))  # 0.1.x wrote the container's (UTC) clock without a "Z"
    assert tw.main(["--health"]) == 0
    assert "0.5 h ago" in capsys.readouterr().out


def test_unhealthy_when_no_check_completed_for_two_intervals(capsys: pytest.CaptureFixture[str]) -> None:
    write_state(at(2 * tw.INTERVAL + 3600))
    assert tw.main(["--health"]) == 1
    assert "unhealthy: last completed check" in capsys.readouterr().out


@pytest.mark.parametrize("state", [None, "not json", json.dumps({"version": 2}), json.dumps({"checked": "yesterday"})])
def test_unhealthy_without_a_readable_completed_check(state: str | None) -> None:
    if state is not None:
        tw.STATE.write_text(state)
    ok, message = tw.health()
    assert not ok
    assert message.startswith("unhealthy: no completed check recorded")


def test_one_time_check_exits_0_when_it_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tw, "RUN_ONCE", True)
    monkeypatch.setattr(tw, "run_once", lambda: None)
    assert tw.main([]) == 0


def test_one_time_check_exits_1_and_reports_when_it_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail() -> Never:
        msg = "GitHub is down"
        raise RuntimeError(msg)

    sent = []
    monkeypatch.setattr(tw, "RUN_ONCE", True)
    monkeypatch.setattr(tw, "run_once", fail)
    monkeypatch.setattr(tw, "notify", lambda title, _findings=(), text=None: sent.append((title, text)))
    assert tw.main([]) == 1
    assert sent == [("trash-watch error", "RuntimeError('GitHub is down')")]


def test_suggest_exits_0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tw, "suggest", lambda: None)
    assert tw.main(["--suggest"]) == 0
