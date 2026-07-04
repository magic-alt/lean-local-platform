import pytest

from app.domain.backtest_job import duration_seconds, is_terminal, normalize_status


def test_normalize_legacy_statuses():
    assert normalize_status("succeeded") == "success"
    assert normalize_status("interrupted") == "failed"


def test_terminal_statuses():
    assert is_terminal("success")
    assert is_terminal("failed")
    assert is_terminal("cancelled")
    assert not is_terminal("running")


def test_invalid_status_is_rejected():
    with pytest.raises(ValueError):
        normalize_status("paused")


def test_duration_seconds():
    assert duration_seconds("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:03.250000+00:00") == 3.25
