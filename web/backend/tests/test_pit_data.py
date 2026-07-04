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


def test_financial_factors_as_of_excludes_future_announcements(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services.pit_data import financial_factors_as_of, import_financial_statements

    import_financial_statements(
        [
            {
                "symbol": "600519",
                "statement_type": "metrics",
                "report_date": "2023-12-31",
                "announce_date": "2024-04-30",
                "fields": {"eps": 10.0, "roe": 0.31},
            },
            {
                "symbol": "600519",
                "statement_type": "metrics",
                "report_date": "2024-03-31",
                "announce_date": "2024-04-20",
                "fields": {"eps": 3.0, "roe": 0.08},
            },
        ],
        source="unit",
    )

    assert financial_factors_as_of(["600519"], "2024-04-01", ["eps"])["600519"] == {}
    snapshot = financial_factors_as_of(["600519"], "2024-04-25", ["eps"])["600519"]["eps"]
    assert snapshot["value"] == 3.0
    assert snapshot["report_date"] == "2024-03-31"
    assert snapshot["announce_date"] == "2024-04-20"


def test_index_members_as_of_respects_effective_date(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services.ashare_repository import universe_as_of
    from app.services.pit_data import import_index_members

    import_index_members(
        [
            {
                "universe_code": "CSI300",
                "symbol": "600519",
                "start_date": "2024-01-01",
                "announce_date": "2023-12-15",
                "effective_date": "2024-01-01",
                "industry": "Consumer",
            },
            {
                "universe_code": "CSI300",
                "symbol": "000001",
                "start_date": "2024-06-01",
                "announce_date": "2024-05-15",
                "effective_date": "2024-06-01",
                "industry": "Bank",
            },
        ],
        source="unit",
    )

    assert [item["symbol"] for item in universe_as_of("CSI300", "2024-05-20")] == ["600519"]
    assert [item["symbol"] for item in universe_as_of("CSI300", "2024-06-01")] == ["000001", "600519"]
