import sys

from fastapi.testclient import TestClient


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


def test_source_gate_rejects_research_source_by_default(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.main import app
    from app.services.source_gate import require_source_allowed, resolve_effective_data_source

    assert require_source_allowed(None) == "tushare"
    assert require_source_allowed("akshare") == "akshare"
    assert resolve_effective_data_source("jqdata", start_date="2025-04-01", end_date="2026-04-01")["effectiveSource"] == "jqdata"
    fallback = resolve_effective_data_source("jqdata", start_date="2026-06-01", end_date="2026-06-30")
    assert fallback["effectiveSource"] == "tushare"
    assert fallback["fallbackReason"] == "jqdata_entitlement_window_exceeded"
    try:
        require_source_allowed("test")
    except ValueError as exc:
        assert "source_not_certified:test" in str(exc)
    else:
        raise AssertionError("test source should be rejected by default")

    client = TestClient(app)
    rejected = client.get(
        "/api/data/query",
        params={"symbol": "600519", "assetClass": "equity", "market": "china", "source": "database", "providerSource": "test"},
    )
    assert rejected.status_code == 400
    allowed = client.get(
        "/api/data/query",
        params={
            "symbol": "600519",
            "assetClass": "equity",
            "market": "china",
            "source": "database",
            "providerSource": "test",
            "allowResearchSource": True,
        },
    )
    assert allowed.status_code == 200


def test_instrument_identifier_backfill_and_coverage(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services.instrument_identity import identifier_coverage, identifiers_for_symbol, upsert_instrument_identifiers

    result = upsert_instrument_identifiers(symbols=["600519", "000001", "300750", "000300"], dry_run=False)
    assert result["identifiers"] >= 20
    coverage = identifier_coverage(["600519", "000001", "300750", "000300"])
    assert coverage["missing"] == 0
    identifiers = identifiers_for_symbol("600519")
    types = {item["identifier_type"] for item in identifiers["items"]}
    assert {"raw_symbol", "exchange_symbol", "ts_code", "lean_symbol", "provider_symbol"} <= types


def test_coverage_api_exposes_source_and_severity(tmp_path, monkeypatch):
    configure_temp_db(tmp_path, monkeypatch)

    from app.main import app

    response = TestClient(app).get(
        "/api/data/coverage/symbol/600519",
        params={"source": "akshare", "startDate": "2026-06-01", "endDate": "2026-06-30"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "akshare"
    assert payload["severity"] in {"ok", "warning", "critical"}
    assert "dailyBars" in payload


def test_level3_scripts_support_dry_run(monkeypatch, capsys):
    from scripts import run_daily_shadow_pipeline, run_level3_shadow_audit, run_paper_constraints_acceptance

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_daily_shadow_pipeline.py",
            "--symbols",
            "600519,000001,300750",
            "--benchmark",
            "000300",
            "--source",
            "akshare",
            "--start-date",
            "2026-06-01",
            "--end-date",
            "2026-06-30",
            "--dry-run",
            "--json",
        ],
    )
    assert run_daily_shadow_pipeline.main() == 0
    assert "planned" in capsys.readouterr().out

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_paper_constraints_acceptance.py",
            "--symbols",
            "600519,000001,300750",
            "--dry-run",
            "--json",
        ],
    )
    assert run_paper_constraints_acceptance.main() == 0
    assert "requiredRejectReasons" in capsys.readouterr().out

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_level3_shadow_audit.py",
            "--symbols",
            "600519,000001,300750",
            "--start-date",
            "2026-06-01",
            "--end-date",
            "2026-06-30",
            "--dry-run",
            "--json",
        ],
    )
    assert run_level3_shadow_audit.main() == 0
    assert "LEVEL3_CANDIDATE" in capsys.readouterr().out


def test_cleanup_report_artifacts_dry_run_does_not_delete(tmp_path, monkeypatch, capsys):
    configure_temp_db(tmp_path, monkeypatch)

    from app.services.db_object_store import get_object, put_bytes
    from scripts import cleanup_report_artifacts

    item = put_bytes("backtest-results", "old-run/result.json", b"{}")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanup_report_artifacts.py",
            "--days",
            "0",
            "--dry-run",
            "--json",
        ],
    )

    assert cleanup_report_artifacts.main() == 0
    assert "wouldDelete" in capsys.readouterr().out
    assert get_object(item["id"]) is not None
