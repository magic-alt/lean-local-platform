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


def test_pit_api_maps_000300_to_csi300(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.pit_data import import_index_members

    import_index_members(
        [
            {
                "universe_code": "CSI300",
                "symbol": "600519",
                "start_date": "2024-01-01",
                "announce_date": "2023-12-15",
                "effective_date": "2024-01-01",
            }
        ],
        source="unit",
    )

    client = TestClient(app)
    response = client.get("/api/pit/index-members/000300/as-of/2024-02-01")

    assert response.status_code == 200
    payload = response.json()
    assert payload["universe"] == "CSI300"
    assert payload["requestedUniverse"] == "000300"
    assert [item["symbol"] for item in payload["items"]] == ["600519"]


def test_csi300_pit_api_returns_gap_before_official_coverage_start(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.pit_data import import_index_members

    import_index_members(
        [
            {
                "universe_code": "CSI300",
                "symbol": "600519",
                "start_date": "2006-01-01",
                "announce_date": "2005-12-15",
                "effective_date": "2006-01-01",
            }
        ],
        source="manual-unverified",
    )

    client = TestClient(app)
    response = client.get("/api/pit/index-members/000300/as-of/2006-02-01")

    assert response.status_code == 200
    payload = response.json()
    assert payload["universe"] == "CSI300"
    assert payload["coverageStatus"] == "coverage_gap"
    assert payload["coverageStart"] == "2017-12-08"
    assert payload["count"] == 0
    assert payload["items"] == []


def test_ashare_universe_interfaces_return_gap_before_csi300_official_coverage(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.pit_data import import_index_members

    import_index_members(
        [
            {
                "universe_code": "CSI300",
                "symbol": "600519",
                "start_date": "2006-01-01",
                "announce_date": "2005-12-15",
                "effective_date": "2006-01-01",
            }
        ],
        source="manual-unverified",
    )

    client = TestClient(app)
    universe = client.get("/api/ashare/universe/CSI300", params={"date": "2006-02-01"})
    tradable = client.get("/api/ashare/universe/CSI300/tradable", params={"date": "2006-02-01"})

    assert universe.status_code == 200
    assert tradable.status_code == 200
    assert universe.json()["coverageStatus"] == "coverage_gap"
    assert universe.json()["count"] == 0
    assert tradable.json()["coverageStatus"] == "coverage_gap"
    assert tradable.json()["count"] == 0
