def configure_temp_db(tmp_path, monkeypatch):
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.sqlite3")
    monkeypatch.setattr(db_module, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(db_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(db_module, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(db_module, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(db_module, "RESEARCH_DIR", tmp_path / "research")
    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(db_module, "REPORTS_DIR", tmp_path / "reports")
    db_module.init_db()
    return db_module


def insert_ashare_bar(connection, symbol, trade_date, close, volume, source):
    connection.execute(
        """
        insert into ashare_daily_bars
            (symbol, trade_date, open, high, low, close, volume, adjust, source, batch_id, created_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (symbol, trade_date, close - 1, close + 1, close - 2, close, volume, "raw", source, "batch-1", "now"),
    )


def test_compare_ashare_daily_sources_persists_warning_report(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    with db_module.db() as connection:
        insert_ashare_bar(connection, "600519", "2026-07-01", 100.00, 1000, "akshare")
        insert_ashare_bar(connection, "600519", "2026-07-02", 101.00, 1000, "akshare")
        insert_ashare_bar(connection, "600519", "2026-07-01", 100.01, 1001, "baostock")
        insert_ashare_bar(connection, "600519", "2026-07-02", 105.00, 2000, "baostock")

    from app.services.ashare_multisource import compare_ashare_daily_sources, list_quality_reports

    report = compare_ashare_daily_sources(
        symbol="600519",
        sources=["akshare", "baostock"],
        start_date="2026-07-01",
        end_date="2026-07-02",
        persist=True,
    )

    assert report["severity"] == "warning"
    assert report["passed"] is False
    assert report["priceMismatchCount"] == 1
    assert report["volumeMismatchCount"] == 1
    assert report["reportId"]

    saved = list_quality_reports()
    assert len(saved) == 1
    assert saved[0]["report_type"] == "ashare_daily_multisource"
    assert saved[0]["sources"] == ["akshare", "baostock"]
    assert saved[0]["result"]["symbol"] == "600519"


def test_compare_ashare_daily_sources_batch_persists_critical_acceptance_report(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    with db_module.db() as connection:
        insert_ashare_bar(connection, "600519", "2026-07-01", 100.00, 1000, "akshare")
        insert_ashare_bar(connection, "600519", "2026-07-01", 100.00, 1000, "baostock")
        insert_ashare_bar(connection, "000001", "2026-07-01", 10.00, 1000, "baostock")

    from app.services.ashare_multisource import compare_ashare_daily_sources_batch, list_quality_reports

    report = compare_ashare_daily_sources_batch(
        symbols=["600519", "000001"],
        sources=["akshare", "baostock"],
        start_date="2026-07-01",
        end_date="2026-07-01",
        persist=True,
        persist_symbol_reports=True,
    )

    assert report["severity"] == "critical"
    assert report["passed"] is False
    assert report["criticalSymbols"] == ["000001"]
    assert report["criticalCount"] == 1

    saved = list_quality_reports(limit=10)
    batch = next(item for item in saved if item["report_type"] == "ashare_daily_multisource_batch")
    assert batch["severity"] == "critical"
    assert batch["result"]["criticalSymbols"] == ["000001"]


def test_compare_ashare_daily_sources_batch_api(tmp_path, monkeypatch):
    db_module = configure_temp_db(tmp_path, monkeypatch)
    with db_module.db() as connection:
        insert_ashare_bar(connection, "600519", "2026-07-01", 100.00, 1000, "akshare")
        insert_ashare_bar(connection, "600519", "2026-07-01", 100.00, 1000, "baostock")

    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.post(
        "/api/data/quality/ashare/daily/compare-batch",
        json={
            "symbols": ["600519"],
            "sources": ["akshare", "baostock"],
            "startDate": "2026-07-01",
            "endDate": "2026-07-01",
            "persist": False,
            "persistSymbolReports": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["severity"] == "ok"
    assert payload["symbolCount"] == 1
