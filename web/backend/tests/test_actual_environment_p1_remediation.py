from __future__ import annotations

import json
from pathlib import Path


def _init_temp_db(tmp_path, monkeypatch):
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


def _release(db_module) -> dict:
    from app.services.dataset_releases import certify_parquet_dataset

    with db_module.db() as connection:
        connection.execute(
            """
            insert into parquet_datasets
                (id,dataset_key,asset_class,market,venue,resolution,data_type,adjust,source,
                 root_path,start_date,end_date,row_count,file_count,metadata_json,created_at,updated_at,
                 dataset_version,environment,is_production,is_certified,certified_at,certified_by,
                 coverage_start,coverage_end,qa_status,qa_report_id)
            values ('parquet-p1','daily-p1','equity','china','china','daily','trade','raw','tushare',
                    '/tmp/parquet','2026-01-01','2026-01-02',2,1,'{}','now','now',
                    'tushare-parquet-p1-manifest','production',1,1,'now','test',
                    '2026-01-01','2026-01-02','ok','qa-p1')
            """
        )
        connection.execute(
            """
            insert into parquet_files
                (id,dataset_id,file_path,partition_json,row_count,sha256,size,created_at)
            values ('file-p1','parquet-p1','equity/2026.parquet','{}',2,?,128,'now')
            """,
            ("a" * 64,),
        )
    return certify_parquet_dataset(
        "parquet-p1",
        dataset_version="tushare-parquet-p1-manifest",
        manifest_sha256="b" * 64,
        qa_report_id="qa-p1",
    )


def test_dataset_release_is_single_authority_for_parquet_and_run_versions(tmp_path, monkeypatch):
    db_module = _init_temp_db(tmp_path, monkeypatch)
    release = _release(db_module)
    from app.services.dataset_releases import certify_parquet_dataset

    same = certify_parquet_dataset(
        "parquet-p1",
        dataset_version="tushare-parquet-p1-manifest",
        manifest_sha256="b" * 64,
        qa_report_id="qa-p1",
    )
    with db_module.db() as connection:
        parquet = connection.execute(
            "select dataset_release_id from parquet_datasets where id='parquet-p1'"
        ).fetchone()
        count = connection.execute(
            "select count(*) as count from dataset_releases where status='active'"
        ).fetchone()["count"]
    assert same["id"] == release["id"] == parquet["dataset_release_id"]
    assert count == 1


def test_paper_trust_is_bound_to_live_account_generation_release_and_ttl(tmp_path, monkeypatch):
    db_module = _init_temp_db(tmp_path, monkeypatch)
    release = _release(db_module)
    from app.services import paper_accounts

    account = paper_accounts.create_account(
        {"name": "P1 account", "initialCash": "100000", "benchmarkSymbol": "000300"}
    )
    trust = paper_accounts.mark_projection_history_trusted(
        {
            "passed": True,
            "accountId": account["id"],
            "generation": account["current_generation"],
            "datasetReleaseId": release["id"],
            "checkpoints": 1,
            "reports": 0,
        }
    )
    assert trust["valuationTrusted"] is True
    with db_module.db() as connection:
        connection.execute("update paper_accounts set status='archived' where id=?", (account["id"],))
    assert paper_accounts._data_trust(account["id"])["valuationTrusted"] is False
    assert paper_accounts.list_accounts()["dataTrust"]["valuationTrusted"] is False


def test_list_summaries_drop_embedded_snapshots_and_enforce_hard_budget(tmp_path, monkeypatch):
    db_module = _init_temp_db(tmp_path, monkeypatch)
    from app.services.backtest_service import query_backtests
    from app.services.tasks import create_task, list_tasks

    huge = "x" * 1_000_000
    with db_module.db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id,symbol,parameters_json,status,docker_image,results_dir,created_at,
                 fingerprint_json,validation_json,experiment_json)
            values ('run-p1','600519',?,'success','lean:test','/tmp/run','now',?,?,?)
            """,
            (
                json.dumps({"ticker": "600519", "start": "2026-01-01", "universeSchedule": huge}),
                json.dumps({"snapshot": huge}),
                json.dumps({"passed": True, "severity": "ok", "detail": huge}),
                json.dumps({"snapshot": huge}),
            ),
        )
    create_task("unit", "large task", {"small": "ok", "schedule": [huge]})
    runs = query_backtests()
    tasks = list_tasks()
    assert runs[0]["parameters"] == {"ticker": "600519", "start": "2026-01-01"}
    assert runs[0]["validation"] == {"passed": True, "severity": "ok"}
    assert tasks[0]["parameters"] == {"small": "ok"}
    assert len(json.dumps({"runs": runs, "tasks": tasks})) < 200_000


def test_asset_capabilities_distinguish_metadata_data_and_execution(tmp_path, monkeypatch):
    db_module = _init_temp_db(tmp_path, monkeypatch)
    from app.services.asset_capabilities import capability_for_scope

    empty = capability_for_scope(
        asset_class="future", market="china", venue="china", resolution="daily", data_type="trade"
    )
    assert empty["state"] == "unavailable"
    with db_module.db() as connection:
        connection.execute(
            """
            insert into futures_contracts
                (contract_code,product,exchange,source,updated_at)
            values ('IF2608','IF','CFFEX','unit','now')
            """
        )
    metadata = capability_for_scope(
        asset_class="future", market="china", venue="china", resolution="daily", data_type="trade"
    )
    assert metadata["state"] == "metadata_only"
    with db_module.db() as connection:
        connection.execute(
            """
            insert into futures_daily_bars
                (contract_code,trade_date,close,source,created_at)
            values ('IF2608','2026-08-01',4000,'unit','now')
            """
        )
    ready = capability_for_scope(
        asset_class="future", market="china", venue="china", resolution="daily", data_type="trade"
    )
    assert ready["state"] == "data_ready"
    assert ready["executable_reason"] == "execution_adapter_not_certified"


def test_maintenance_uses_one_active_run_with_visible_resume_checkpoint(tmp_path, monkeypatch):
    db_module = _init_temp_db(tmp_path, monkeypatch)
    from app.services import derived_maintenance

    first = derived_maintenance.create_maintenance_run(layers=["parquet"])
    duplicate = derived_maintenance.create_maintenance_run(layers=["parquet"])
    assert duplicate["id"] == first["id"]
    with db_module.db() as connection:
        columns = {row["name"] for row in connection.execute("pragma table_info(derived_maintenance_runs)")}
    assert {"attempt_count", "checkpoint_json", "next_retry_at", "heartbeat_at", "lease_owner"} <= columns


def test_reproducibility_certificates_form_fetchable_golden_pair(tmp_path, monkeypatch):
    db_module = _init_temp_db(tmp_path, monkeypatch)
    release = _release(db_module)
    from app.services import reproducibility

    paths: dict[str, Path] = {}
    result = {
        "orders": {"1": {"id": 1, "status": "filled", "quantity": 10, "price": 10}},
        "charts": {"Strategy Equity": {"series": {"Equity": {"values": [[1, 100000], [2, 100100]]}}}},
        "statistics": {"End Equity": "100100"},
    }
    for run_id in ("golden-a", "golden-b"):
        result_dir = tmp_path / run_id
        result_dir.mkdir()
        path = result_dir / "result.json"
        path.write_text(json.dumps(result), encoding="utf-8")
        paths[run_id] = path
        fingerprint = {
            "inputFingerprint": "c" * 64,
            "datasetReleaseId": release["id"],
            "canonicalResultSha256": "d" * 64,
            "docker_image_digest": "sha256:image",
            "strategyFileHash": "e" * 64,
            "configFileHash": "f" * 64,
            "lean_zip_sha256": "1" * 64,
            "factor_file_sha256": "2" * 64,
        }
        with db_module.db() as connection:
            connection.execute(
                """
                insert into backtest_runs
                    (id,symbol,parameters_json,status,docker_image,results_dir,result_json_path,
                     created_at,fingerprint_json,dataset_release_id)
                values (?,'600519','{}','success','lean:test',?,?, 'now',?,?)
                """,
                (run_id, str(result_dir), str(path), json.dumps(fingerprint), release["id"]),
            )
    monkeypatch.setattr(reproducibility, "run_file", lambda run_id, *_args: paths[run_id])
    reproducibility.issue_certificate("golden-a")
    second = reproducibility.issue_certificate("golden-b")
    fetched = reproducibility.certificate_for_run("golden-a")
    assert second["goldenPair"] is True
    assert fetched and fetched["goldenPair"] is True
    assert fetched["stored_object_id"]
    assert set(fetched["matchingRunIds"]) == {"golden-a", "golden-b"}
