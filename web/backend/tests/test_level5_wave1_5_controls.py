from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def test_wave5_openapi_has_single_canonical_routes():
    from app.main import app

    paths = TestClient(app).get("/openapi.json").json()["paths"]

    assert "/api/backtests/{run_id}/result" in paths
    assert "/api/backtests/{run_id}/results" not in paths
    assert "/api/insights/ashare-tech/reports" in paths
    assert not any(path.startswith("/api/ashare-tech-insights") for path in paths)
    assert not any(
        path.endswith("/{project_id}/")
        or path.endswith("/{task_id}/")
        or path.endswith("/{strategy_id}/")
        for path in paths
    )


def test_legacy_routes_redirect_without_remaining_in_openapi():
    from app.main import app

    client = TestClient(app, follow_redirects=False)
    result_alias = client.get("/api/backtests/example/results")
    insight_alias = client.get("/api/ashare-tech-insights/capabilities")

    assert result_alias.status_code == 308
    assert result_alias.headers["location"] == "/api/backtests/example/result"
    assert insight_alias.status_code == 308
    assert insight_alias.headers["location"] == "/api/insights/ashare-tech/capabilities"


def test_report_export_rejects_existing_file_outside_approved_roots(
    tmp_path,
    monkeypatch,
):
    from app import db as db_module
    from app.api import reports

    allowed_runs = tmp_path / "runs"
    allowed_reports = tmp_path / "reports"
    outside = tmp_path / "outside.html"
    outside.write_text("not an approved report", encoding="utf-8")
    monkeypatch.setattr(db_module, "RUNS_DIR", allowed_runs)
    monkeypatch.setattr(db_module, "REPORTS_DIR", allowed_reports)

    with pytest.raises(HTTPException) as exc:
        reports._report_file_path(outside)

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "REPORT_PATH_FORBIDDEN"


def test_new_run_fingerprint_uses_camel_case_top_level_with_nested_legacy_aliases(
    tmp_path,
    monkeypatch,
):
    from app.services import run_fingerprint

    monkeypatch.setattr(
        run_fingerprint,
        "git_state",
        lambda: {"commit": "abc", "statusHash": None, "dirty": False},
    )
    monkeypatch.setattr(
        run_fingerprint,
        "data_fingerprint",
        lambda parameters: {
            "scope": {
                "source": "tushare",
                "assetClass": "equity",
                "market": "china",
                "venue": "china",
            },
            "marketDailyBars": {},
            "tradeStatus": {},
            "benchmark": {},
            "parquetFiles": [],
        },
    )
    monkeypatch.setattr(
        run_fingerprint,
        "source_certification",
        lambda *args, **kwargs: {
            "source": "tushare",
            "datasetVersion": "dataset-v1",
            "isCertified": True,
        },
    )
    monkeypatch.setattr(
        run_fingerprint,
        "docker_image_digest",
        lambda image: {"image": image, "digest": "sha256:test"},
    )
    strategy = tmp_path / "main.py"
    strategy.write_text("pass\n", encoding="utf-8")
    fingerprint = run_fingerprint.build_run_fingerprint(
        run_id="run-1",
        parameters={"ticker": "600519", "start": "2024-01-01", "end": "2024-01-02"},
        docker_image="lean:test",
        lean_cache={},
        strategy_path=strategy,
    )

    canonical = {
        "parametersHash",
        "inputFingerprint",
        "strategyFileHash",
        "configFileHash",
        "datasetVersion",
    }
    legacy = {
        "parameters_sha256",
        "input_fingerprint",
        "strategy_file_sha256",
        "config_file_sha256",
        "dataset_version",
    }
    assert canonical <= fingerprint.keys()
    assert legacy.isdisjoint(fingerprint.keys())
    assert legacy == fingerprint["legacyAliases"].keys()


def test_paper_checkpoint_and_ledger_sequences_are_both_unique():
    from app.db import connect, init_db

    init_db()
    connection = connect()
    try:
        def unique_columns(table: str) -> set[tuple[str, ...]]:
            output = set()
            for index in connection.execute(f"pragma index_list('{table}')").fetchall():
                if int(index["unique"]) != 1:
                    continue
                columns = connection.execute(
                    f"pragma index_info('{index['name']}')"
                ).fetchall()
                output.add(tuple(str(item["name"]) for item in columns))
            return output

        ledger_indexes = unique_columns("paper_ledger_entries")
        checkpoint_indexes = unique_columns("paper_account_checkpoints")
    finally:
        connection.close()

    assert (
        "paper_account_id",
        "account_generation",
        "ledger_sequence",
    ) in ledger_indexes
    assert (
        "paper_account_id",
        "generation",
        "source_ledger_sequence",
    ) in checkpoint_indexes


def test_object_store_index_table_is_connected_to_stored_objects(tmp_path, monkeypatch):
    from app import db as db_module
    from app.services import object_store

    monkeypatch.setattr(db_module, "OBJECT_STORE_DIR", tmp_path / "object-store")
    monkeypatch.setattr(object_store, "OBJECT_STORE_DIR", tmp_path / "object-store")
    db_module.init_db()

    created = object_store.put_item("wave5/example.txt", b"wave5")
    listed = object_store.list_items()

    assert created["stored_object_id"]
    assert listed[0]["stored_object_id"] == created["stored_object_id"]
    assert Path(created["file_path"]).is_file()
