from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def _init(tmp_path, monkeypatch):
    import app.db as db_module
    import app.services.experiment_batches as batches_module
    import app.services.history_resources as history_module
    import app.services.projects as projects_module

    projects = tmp_path / "projects"
    runs = tmp_path / "runs"
    reports = tmp_path / "reports"
    monkeypatch.setattr(db_module, "PROJECTS_DIR", projects)
    monkeypatch.setattr(db_module, "RUNS_DIR", runs)
    monkeypatch.setattr(db_module, "REPORTS_DIR", reports)
    monkeypatch.setattr(projects_module, "PROJECTS_DIR", projects)
    monkeypatch.setattr(batches_module, "RUNS_DIR", runs)
    monkeypatch.setattr(history_module, "RUNS_DIR", runs)
    monkeypatch.setattr(history_module, "REPORTS_DIR", reports)
    db_module.init_db()
    return db_module


def test_walk_forward_freezes_lineage_when_parent_project_is_archived(tmp_path, monkeypatch):
    db_module = _init(tmp_path, monkeypatch)
    from app.services import experiment_batches
    from app.services.history_resources import delete_experiment_batch
    from app.services.projects import create_project, delete_project, list_projects

    project = create_project("immutable-wf", template_key="ema_cross", market="china")
    batch = experiment_batches.create_batch(
        {
            "kind": "optimization",
            "mode": "walk_forward",
            "projectId": project["id"],
            "symbol": "600519",
            "start": "2023-01-01",
            "end": "2024-12-31",
            "trainYears": 1,
            "testYears": 1,
            "validationMonths": 6,
            "parameterGrid": {"fast": [10]},
            "datasetVersion": "dataset:test:v1",
            "universeVersion": "symbols:600519:v1",
            "adjustmentContract": "raw-v1",
            "featurePipelineVersion": "features:test:v1",
        }
    )

    evidence = batch["walkForwardEvidence"]
    assert evidence["lineage_status"] == "complete"
    assert evidence["batchSnapshot"]["configDigest"]
    assert evidence["windows"][0]["projectSnapshot"]["id"] == project["id"]
    assert evidence["windows"][0]["selectionInputs"]["candidateKeys"] == ["fast=10"]

    with pytest.raises(ValueError, match="immutable selection and OOS evidence"):
        delete_experiment_batch(batch["id"])
    deleted = delete_project(project["id"])
    assert deleted == {
        "project": project["id"],
        "archived": True,
        "historyPreserved": True,
        "sourceRemoved": True,
    }
    assert list_projects() == []
    with db_module.db() as connection:
        archived = connection.execute(
            "select archived_at from projects where id=?", (project["id"],)
        ).fetchone()
        lineage = connection.execute(
            "select lineage_status from walk_forward_runs where id=?", (evidence["id"],)
        ).fetchone()
    assert archived["archived_at"]
    assert lineage["lineage_status"] == "complete"


def test_completed_walk_forward_issues_immutable_certificate(tmp_path, monkeypatch):
    db_module = _init(tmp_path, monkeypatch)
    from app.services import experiment_batches
    from app.services.projects import create_project

    project = create_project("certified-wf", template_key="ema_cross", market="china")
    batch = experiment_batches.create_batch(
        {
            "kind": "optimization",
            "mode": "walk_forward",
            "projectId": project["id"],
            "symbol": "600519",
            "start": "2023-01-01",
            "end": "2024-12-31",
            "trainYears": 1,
            "testYears": 1,
            "validationMonths": 6,
            "parameterGrid": {"fast": [10]},
            "datasetVersion": "dataset:test:v1",
            "universeVersion": "symbols:600519:v1",
            "adjustmentContract": "raw-v1",
            "featurePipelineVersion": "features:test:v1",
        }
    )
    window = batch["walkForwardEvidence"]["windows"][0]
    candidate = window["candidates"][0]
    oos_item = next(
        item
        for item in batch["items"]
        if (item["parameters"].get("parameters") or {}).get("experimentPhase") == "oos"
    )
    now = "2026-08-02T00:00:00+00:00"
    with db_module.db() as connection:
        connection.execute(
            """
            insert into parameter_selection_events
                (id,window_id,selected_candidate_id,selection_metric,tie_break_rule,
                 selected_parameters_json,candidate_ranking_json,selection_timestamp,
                 selection_fingerprint)
            values ('selection-cert',?,?,'validationSharpe','candidateKey','{}','[]',?,?)
            """,
            (window["id"], candidate["id"], now, "a" * 64),
        )
        connection.execute(
            """
            insert into oos_evaluations
                (id,window_id,selected_candidate_id,oos_item_id,oos_run_id,input_fingerprint,
                 result_digest,metrics_json,status,created_at,completed_at)
            values ('oos-cert',?,?,?,'oos-run',?,?,'{}','COMPLETED',?,?)
            """,
            (
                window["id"],
                candidate["id"],
                oos_item["id"],
                "b" * 64,
                "c" * 64,
                now,
                now,
            ),
        )
        connection.execute(
            "update walk_forward_runs set status='COMPLETED',completed_at=? where batch_id=?",
            (now, batch["id"]),
        )

    first = experiment_batches.issue_walk_forward_certificate(batch["id"])
    second = experiment_batches.issue_walk_forward_certificate(batch["id"])

    assert first["certificateDigest"] == second["certificateDigest"]
    assert first["certificate"]["windows"][0]["oos"]["runId"] == "oos-run"
    assert first["certificate"]["windows"][0]["leakage"]["decision"] == "ALLOW"


def test_paper_certification_cohort_is_durable_and_fail_closed(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    from app.services import paper_accounts, paper_certification
    from app.services.history_resources import delete_paper_session

    first = paper_accounts.create_account(
        {"name": "cert-a", "initialCash": "1000000", "metadata": {"purpose": "certification"}}
    )
    second = paper_accounts.create_account(
        {"name": "cert-b", "initialCash": "3000000", "metadata": {"purpose": "certification"}}
    )
    cohort = paper_certification.create_cohort(
        name="Level 5 Paper acceptance",
        account_ids=[first["id"], second["id"]],
    )

    assert cohort["status"] == "collecting"
    assert cohort["required_sessions"] == 21
    assert len(cohort["members"]) == 2
    assert all(member["evidence"]["checks"]["deploymentExists"] is False for member in cohort["members"])
    with pytest.raises(ValueError, match="immutable certification evidence"):
        paper_accounts.delete_account(first["id"])
    with pytest.raises(ValueError, match="shadow sessions are protected facts"):
        delete_paper_session(first["shadow_session_id"])


def test_domain_reconciler_converges_ownerless_research_and_quarantines_ready_job(tmp_path, monkeypatch):
    db_module = _init(tmp_path, monkeypatch)
    from app.services import run_reconciler

    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with db_module.db() as connection:
        connection.execute(
            """
            insert into research_runs
                (id,task_id,template_key,name,status,scope_json,parameters_json,
                 cancel_requested,created_at,started_at)
            values ('research-orphan',null,'data-quality','orphan','running','{}','{}',0,?,?)
            """,
            (stale, stale),
        )
        connection.execute(
            """
            insert into research_run_items
                (id,run_id,item_index,item_key,status,parameters_json,created_at,started_at)
            values ('research-item','research-orphan',0,'data-quality','running','{}',?,?)
            """,
            (stale, stale),
        )
        connection.execute(
            """
            insert into paper_daily_jobs
                (id,session_id,trade_date,state,attempt,max_attempts,version,correlation_id,
                 scheduled_at,updated_at)
            values ('paper-orphan','missing-session','2026-08-01','READY',0,3,1,
                    'paper:missing-session:2026-08-01',?,?)
            """,
            (stale, stale),
        )

    result = run_reconciler.reconcile_domain_runs(stale_seconds=60)

    assert result["research"]["count"] == 1
    assert result["paper"]["paperJobs"] == ["paper-orphan"]
    with db_module.db() as connection:
        research = connection.execute(
            "select status,recovery_reason from research_runs where id='research-orphan'"
        ).fetchone()
        job = connection.execute(
            "select state,quarantined_at,quarantine_reason from paper_daily_jobs where id='paper-orphan'"
        ).fetchone()
    assert dict(research) == {"status": "failed", "recovery_reason": "owner_task_missing"}
    assert job["state"] == "MANUAL_INTERVENTION_REQUIRED"
    assert job["quarantined_at"]
    assert job["quarantine_reason"] == "parent_session_missing"
