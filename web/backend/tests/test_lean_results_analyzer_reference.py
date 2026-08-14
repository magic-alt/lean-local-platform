import json
import zipfile

import pytest


def _rows(start: str, end: str):
    return [
        {
            "date": start,
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100",
            "volume": "1000",
        },
        {
            "date": end,
            "open": "110",
            "high": "111",
            "low": "109",
            "close": "110",
            "volume": "1200",
        },
    ]


def _configure_data_dir(tmp_path, monkeypatch):
    import app.lean_engine.data_paths as data_paths
    import app.lean_engine.data_writers as data_writers

    data_dir = tmp_path / "Data"
    monkeypatch.setattr(data_paths, "DATA_DIR", data_dir)
    monkeypatch.setattr(data_paths, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(data_writers, "REPO_ROOT", tmp_path)
    return data_dir


def test_results_analyzer_reference_refreshes_stale_spy_cache(tmp_path, monkeypatch):
    data_dir = _configure_data_dir(tmp_path, monkeypatch)
    import app.services.lean_cache as lean_cache

    calls = []

    def fake_fetch(symbol, start, end):
        calls.append((symbol, start, end))
        return _rows("1993-01-29", "2026-07-13")

    monkeypatch.setattr(lean_cache, "fetch_yahoo_rows", fake_fetch)

    result = lean_cache.ensure_lean_results_analyzer_reference_data("2024-01-01", "2026-07-13")

    assert result["refreshed"] is True
    assert result["coverage"]["lastDate"] == "2026-07-13"
    assert calls == [("SPY", "1993-01-29", "2026-07-15")]
    factor_path = data_dir / "equity" / "usa" / "factor_files" / "spy.csv"
    assert factor_path.read_text(encoding="utf-8").splitlines() == [
        "19930129,1,1,0",
        "20501231,1,1,0",
    ]


def test_results_analyzer_reference_reuses_covering_spy_cache(tmp_path, monkeypatch):
    data_dir = _configure_data_dir(tmp_path, monkeypatch)
    import app.services.lean_cache as lean_cache
    from app.lean_engine.data_writers import write_lean_daily_zip

    write_lean_daily_zip("SPY", _rows("2023-12-20", "2026-07-13"), "test", overwrite=True, market="usa")

    market_hours = json.loads(
        (data_dir / "market-hours" / "market-hours-database.json").read_text(encoding="utf-8")
    )
    assert "Equity-usa-[*]" in market_hours["entries"]

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("covering cache should not fetch")

    monkeypatch.setattr(lean_cache, "fetch_yahoo_rows", unexpected_fetch)

    result = lean_cache.ensure_lean_results_analyzer_reference_data("2024-01-01", "2026-07-13")

    assert result["refreshed"] is False
    with zipfile.ZipFile(data_dir / "equity" / "usa" / "daily" / "spy.zip") as archive:
        assert archive.namelist() == ["spy.csv"]


def test_results_analyzer_reference_accepts_friday_for_weekend_end(tmp_path, monkeypatch):
    data_dir = _configure_data_dir(tmp_path, monkeypatch)
    import app.services.lean_cache as lean_cache
    from app.lean_engine.data_writers import write_lean_daily_zip

    write_lean_daily_zip("SPY", _rows("2023-12-20", "2026-07-24"), "test", overwrite=True, market="usa")

    def unexpected_fetch(*args, **kwargs):
        raise AssertionError("Friday coverage should satisfy a Saturday request")

    monkeypatch.setattr(lean_cache, "fetch_yahoo_rows", unexpected_fetch)

    result = lean_cache.ensure_lean_results_analyzer_reference_data("2024-01-01", "2026-07-25")

    assert result["refreshed"] is False
    assert result["market"] == "usa"
    assert result["requestedEndDate"] == "2026-07-25"
    assert result["expectedLastTradeDate"] == "2026-07-24"
    assert result["coverage"]["lastDate"] == "2026-07-24"
    assert (data_dir / "equity" / "usa" / "daily" / "spy.zip").is_file()


def test_results_analyzer_reference_accepts_prior_session_for_us_holiday(tmp_path, monkeypatch):
    _configure_data_dir(tmp_path, monkeypatch)
    import app.services.lean_cache as lean_cache
    from app.lean_engine.data_writers import write_lean_daily_zip

    write_lean_daily_zip("SPY", _rows("2023-12-20", "2026-07-02"), "test", overwrite=True, market="usa")
    monkeypatch.setattr(
        lean_cache,
        "fetch_yahoo_rows",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("holiday coverage should reuse cache")),
    )

    result = lean_cache.ensure_lean_results_analyzer_reference_data("2024-01-01", "2026-07-03")

    assert result["expectedLastTradeDate"] == "2026-07-02"


def test_results_analyzer_reference_rejects_missing_expected_us_session(tmp_path, monkeypatch):
    _configure_data_dir(tmp_path, monkeypatch)
    from app.lean_engine.errors import LeanPlatformError
    import app.services.lean_cache as lean_cache

    monkeypatch.setattr(
        lean_cache,
        "fetch_yahoo_rows",
        lambda symbol, start, end: _rows("1993-01-29", "2026-07-23"),
    )

    with pytest.raises(
        LeanPlatformError,
        match=r"market=usa.*expectedLastTradeDate=2026-07-24",
    ):
        lean_cache.ensure_lean_results_analyzer_reference_data("2024-01-01", "2026-07-25")
