import json
from pathlib import Path

import pytest


def configure_temp_platform(tmp_path, monkeypatch):
    import app.db as db_module
    import app.domain.assets as assets_module
    import app.lean as lean_module

    data_dir = tmp_path / "Data"
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(lean_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(lean_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(assets_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(assets_module, "REPO_ROOT", tmp_path)
    db_module.init_db()
    return data_dir


def sample_ashare_rows():
    return [
        {"date": "2024-01-02", "open": "10.00", "high": "10.20", "low": "9.90", "close": "10.00", "volume": "100000"},
        {"date": "2024-01-03", "open": "10.50", "high": "11.00", "low": "10.50", "close": "11.00", "volume": "120000"},
        {"date": "2024-01-04", "open": "11.00", "high": "11.10", "low": "10.90", "close": "11.00", "volume": "0"},
    ]


def import_sample_ashare(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services.data import import_ashare_research_data

    return import_ashare_research_data(
        symbol="600519",
        provider="test",
        market="china",
        rows=sample_ashare_rows(),
        source="test",
        overwrite=True,
        adjust="raw",
        outputsize="",
        asset_class="equity",
        venue="china",
        resolution="daily",
        data_type="trade",
        start_date=None,
        end_date=None,
    )


def test_ashare_import_writes_research_tables_and_restores_asof_universe(tmp_path, monkeypatch):
    asset = import_sample_ashare(tmp_path, monkeypatch)

    from app.services.ashare_repository import is_tradeable, universe_as_of

    assert asset["batch_id"]
    assert asset["qa_report"]["passed"] is True
    assert Path(tmp_path / "Data" / "equity" / "china" / "daily" / "600519.zip").exists()
    universe = universe_as_of("ALL_A", "2024-01-04")
    assert [item["symbol"] for item in universe] == ["600519"]
    can_buy, reason = is_tradeable("600519", "2024-01-03", "buy")
    assert can_buy is False
    assert reason == "blocked_buy"
    can_sell, reason = is_tradeable("600519", "2024-01-04", "sell")
    assert can_sell is False
    assert reason == "suspended"


def test_ashare_quality_report_blocks_duplicate_dates(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    from app.services.data import import_ashare_research_data
    from app.services.data_quality import DataQualityError
    from app.services.ashare_repository import list_import_batches

    rows = sample_ashare_rows()
    rows.append({**rows[-1]})
    with pytest.raises(DataQualityError):
        import_ashare_research_data(
            symbol="600519",
            provider="test",
            market="china",
            rows=rows,
            source="test",
            overwrite=True,
            adjust="raw",
            outputsize="",
            asset_class="equity",
            venue="china",
            resolution="daily",
            data_type="trade",
            start_date=None,
            end_date=None,
        )

    latest = list_import_batches()[0]
    assert latest["status"] == "failed"
    assert latest["qa_report"]["passed"] is False
    assert "duplicate_dates" in ";".join(latest["qa_report"]["errors"])


def test_backtest_creation_injects_ashare_rules_after_preflight(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    import app.services.backtest_service as backtest_service
    import app.services.tasks as task_service

    monkeypatch.setattr(backtest_service, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(task_service, "RUNS_DIR", tmp_path / "runs")

    job = backtest_service.create_backtest_job(
        {
            "symbol": "600519",
            "assetClass": "equity",
            "market": "china",
            "start": "2024-01-02",
            "end": "2024-01-04",
            "cash": 100000,
            "fast": 1,
            "slow": 2,
        }
    )

    assert job["parameters"]["ashareRules"] is True
    assert job["parameters"]["lotSize"] == 100
    assert job["parameters"]["ashareStatusFile"] == "/Lean/Run/ashare_trade_status.json"


def test_ashare_execution_artifacts_include_status_payload(tmp_path, monkeypatch):
    import_sample_ashare(tmp_path, monkeypatch)

    from app.services.ashare_execution import write_ashare_execution_artifacts

    artifacts = write_ashare_execution_artifacts(
        tmp_path / "runs" / "job-1",
        {
            "ashareRules": True,
            "ticker": "600519",
            "start": "2024-01-02",
            "end": "2024-01-04",
        },
    )

    assert artifacts is not None
    status_path = Path(artifacts["status"])
    helper_path = Path(artifacts["helper"])
    assert "AShareExecutionHelper" in helper_path.read_text(encoding="utf-8")
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert payload["600519"]["2024-01-03"]["can_buy"] is False
