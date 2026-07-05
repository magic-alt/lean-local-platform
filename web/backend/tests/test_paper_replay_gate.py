from app.db import json_dump


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
    return db_module


def import_rows():
    from app.services.data import import_ashare_research_data

    rows = [
        {"date": "2024-01-02", "open": "10", "high": "10.5", "low": "9.8", "close": "10", "volume": "100000"},
        {"date": "2024-01-03", "open": "10.1", "high": "10.6", "low": "10.0", "close": "10.2", "volume": "100000"},
        {"date": "2024-01-04", "open": "10.2", "high": "10.8", "low": "10.1", "close": "10.4", "volume": "100000"},
    ]
    return import_ashare_research_data(
        symbol="600519",
        provider="unit",
        market="china",
        rows=rows,
        source="unit",
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


def test_paper_replay_runs_daily_loop(tmp_path, monkeypatch):
    configure_temp_platform(tmp_path, monkeypatch)
    import_rows()

    from app.services.paper import create_session, run_replay

    session = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000, "fast": 1, "slow": 2})
    result = run_replay(session["id"], "2024-01-02", "2024-01-04")

    assert result["tradingDays"] == 3
    assert len(result["snapshots"]) == 3
    assert result["finalSession"]["status"] == "paused"


def test_paper_match_rejects_when_quality_gate_is_critical(tmp_path, monkeypatch):
    db_module = configure_temp_platform(tmp_path, monkeypatch)
    import_rows()
    with db_module.db() as connection:
        connection.execute(
            """
            insert into data_quality_reports
                (id, report_type, asset_class, market, symbol, start_date, end_date,
                 sources_json, severity, result_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "qa-1",
                "ashare_daily_multisource",
                "equity",
                "china",
                "600519",
                "2024-01-03",
                "2024-01-03",
                json_dump(["akshare", "baostock"]),
                "critical",
                json_dump({"severity": "critical"}),
                "now",
            ),
        )

    from app.services.paper import create_session, create_signal, match_daily_orders

    session = create_session({"symbol": "600519", "assetClass": "equity", "market": "china", "cash": 100000})
    create_signal(session["id"], trade_date="2024-01-02", side="buy", target_percent=1)
    result = match_daily_orders(session["id"], "2024-01-03", auto_signal=False)

    assert result["orders"][0]["status"] == "rejected"
    assert result["orders"][0]["reason"] == "qa_failed:qa-1"
