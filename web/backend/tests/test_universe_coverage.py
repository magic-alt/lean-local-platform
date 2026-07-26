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


def test_offered_universe_coverage_is_explicitly_missing(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services.universe_coverage import universe_coverage_overview

    overview = universe_coverage_overview()

    assert {item["universeCode"] for item in overview["items"]} == {
        "CSI300",
        "CSI500",
        "CSI1000",
        "SSE50",
        "STAR50",
        "ALL_A",
    }
    assert overview["passed"] is False
    assert all(item["coverage_status"] == "missing" for item in overview["items"])


def test_untrusted_source_cannot_certify_complete_universe(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services.pit_data import import_index_members
    from app.services.universe_coverage import record_universe_coverage

    import_index_members(
        [
            {
                "universe_code": "SSE50",
                "symbol": "600000",
                "start_date": "2004-01-02",
                "announce_date": "2004-01-02",
            }
        ],
        source="manual",
    )
    coverage = record_universe_coverage(
        "SSE50",
        coverage_start="2004-01-02",
        coverage_end="2026-07-26",
        status="complete",
        source="manual",
    )

    assert coverage["coverage_status"] == "failed"
    assert coverage["validation"]["trustedSource"] is False


def test_tushare_snapshot_builder_requires_full_snapshot_counts(monkeypatch):
    import pytest

    from app.services import tushare_index_pit

    original = tushare_index_pit.universe_spec
    monkeypatch.setattr(
        tushare_index_pit,
        "universe_spec",
        lambda code: {**original(code), "expectedMembers": 2},
    )
    with pytest.raises(Exception, match="snapshot membership counts are incomplete"):
        tushare_index_pit.build_snapshot_intervals(
            "STAR50",
            [{"trade_date": "2024-01-01", "symbol": "688001", "weight": 100}],
        )


def test_tushare_snapshot_builder_creates_non_overlapping_intervals(monkeypatch):
    from app.services import tushare_index_pit

    original = tushare_index_pit.universe_spec
    monkeypatch.setattr(
        tushare_index_pit,
        "universe_spec",
        lambda code: {**original(code), "expectedMembers": 2},
    )
    monkeypatch.setattr(
        tushare_index_pit,
        "previous_trade_date",
        lambda value: "2024-01-31" if value == "2024-02-01" else value,
    )
    built = tushare_index_pit.build_snapshot_intervals(
        "STAR50",
        [
            {"trade_date": "2024-01-01", "symbol": "688001", "weight": 50},
            {"trade_date": "2024-01-01", "symbol": "688002", "weight": 50},
            {"trade_date": "2024-02-01", "symbol": "688002", "weight": 40},
            {"trade_date": "2024-02-01", "symbol": "688003", "weight": 60},
        ],
    )

    first = [item for item in built["intervals"] if item["start_date"] == "2024-01-01"]
    second = [item for item in built["intervals"] if item["start_date"] == "2024-02-01"]
    assert {item["end_date"] for item in first} == {"2024-01-31"}
    assert {item["end_date"] for item in second} == {None}
    assert built["snapshotCounts"] == [
        {"date": "2024-01-01", "count": 2},
        {"date": "2024-02-01", "count": 2},
    ]


def test_complete_certification_is_not_claimed_outside_covered_dates(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services.pit_data import import_index_members
    from app.services.universe_coverage import coverage_gap, record_universe_coverage

    import_index_members(
        [
            {
                "universe_code": "CSI500",
                "symbol": "600000",
                "start_date": "2007-01-15",
                "announce_date": "2007-01-15",
            }
        ],
        source="tushare:index_weight",
    )
    stored = record_universe_coverage(
        "CSI500",
        coverage_start="2007-01-15",
        coverage_end="2026-07-26",
        status="complete",
        source="tushare:index_weight",
    )
    gap = coverage_gap("CSI500", "2006-12-31")

    assert stored["coverage_status"] == "complete"
    assert gap["isOfficialHistoryComplete"] is False
    assert gap["coverageCertification"] == "partial"
    assert gap["storedCoverageCertification"] == "complete"
