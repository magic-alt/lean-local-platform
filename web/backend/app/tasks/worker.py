import json
import logging
import os
from pathlib import Path
from typing import Any

from .celery_app import celery_app
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta, timezone
from ..core.config import DEFAULT_DOCKER_IMAGE, REPORTS_DIR, RUNS_DIR
from ..db import DatabaseUnavailableError, database_backend, db, json_dump, row_to_dict, utc_now
from ..lean_engine.errors import LeanPlatformError
from ..lean_engine.reports import render_report
from ..lean_engine.research import run_detached_research
from ..lean_engine.results import extract_statistics
from ..observability.metrics import BACKTEST_STATUS, TASK_STATUS
from ..domain.backtest_job import CANCELLED
from ..repositories.backtest_repository import get_backtest, update_backtest
from ..runners.lean_runner import LeanRunner
from ..services.data import fetch_and_import_symbol
from ..services import market_lake
from ..services.ashare_multisource import quality_gate_range
from ..services.ashare_repository import assert_ashare_ready, assert_benchmark_ready
from ..services.backtest_validation import build_backtest_validation, build_experiment_record
from ..services.backtest_service import failure_metadata
from ..services.backtest_execution_validation import (
    audit_backtest_execution,
    execution_failure_message,
    merge_execution_validation,
)
from ..services.experiments import record_experiment_versions
from ..services.projects import get_project
from ..services.result_service import persist_result
from ..services.lean_cache import ensure_ashare_lean_cache, ensure_lean_results_analyzer_reference_data
from ..services.run_fingerprint import build_run_fingerprint
from ..services.reproducibility import issue_certificate
from ..services.scheduler import acquire_scheduler_lease, release_scheduler_lease
from ..services.settings import get_settings
from ..services.source_gate import DEFAULT_PRODUCTION_SOURCE
from ..services.tasks import append_log, create_task, get_task, update_task
from ..services import ashare_tech_insights
from ..services import ashare_tech_agents
from ..services import paper as paper_service
from ..services.trading_calendar import next_trade_date
from ..services import paper_accounts
from ..services import paper_scheduler
from ..services import data_sync
from ..services import tushare_lineage
from ..services import ml_data_preparation
from ..services import ml_research
from ..services import research_runs
from ..services import run_reconciler
from ..services import derived_maintenance
from ..services import mysql_backup
from ..services import resource_pressure
from ..services.alerts import emit_alert, redeliver_open_alerts, resolve_open_alert
from ..services.source_gate import source_certification
from ..core.config import ASHARE_TECH_RETRY_MINUTES


logger = logging.getLogger(__name__)


def _emit_operational_alert(event_type: str, **kwargs: Any) -> None:
    try:
        emit_alert(event_type, **kwargs)
    except Exception:
        logger.exception("Failed to persist or dispatch operational alert %s", event_type)


def _record_task_metric(kind: str, status: str) -> None:
    if TASK_STATUS is not None:
        TASK_STATUS.labels(kind, status).inc()


def _record_backtest_metric(status: str) -> None:
    if BACKTEST_STATUS is not None:
        BACKTEST_STATUS.labels(status).inc()


@celery_app.task(name="lean_web.reconcile_domain_runs")
def reconcile_domain_runs_task():
    return run_reconciler.reconcile_domain_runs()


@celery_app.task(name="lean_web.monitor_operational_resources")
def monitor_operational_resources_task():
    return resource_pressure.monitor_operational_resources()


@celery_app.task(name="lean_web.redeliver_open_alerts")
def redeliver_open_alerts_task():
    return redeliver_open_alerts()


@celery_app.task(name="lean_web.backup_mysql")
def backup_mysql_task():
    try:
        return mysql_backup.create_backup()
    except Exception as exc:
        _emit_operational_alert(
            "mysql_backup_failed",
            severity="critical",
            title="Scheduled MySQL backup failed",
            message=str(exc),
            source="mysql_backup",
            details={"error": str(exc)},
            dedupe_key="mysql_backup_failed:scheduled",
        )
        raise


@celery_app.task(name="lean_web.generate_ashare_tech_report", bind=True, max_retries=2)
def generate_ashare_tech_report_task(self, task_id: str, report_id: str):
    try:
        result = ashare_tech_insights.run_report(task_id, report_id, attempt=self.request.retries)
        _record_task_metric("ashare_tech_report", "success")
        return result
    except ashare_tech_insights.ReportDataNotReady as exc:
        update_task(task_id, status="queued", error=str(exc))
        raise self.retry(exc=exc, countdown=ASHARE_TECH_RETRY_MINUTES * 60)
    except Exception as exc:
        ashare_tech_insights.fail_report(report_id, str(exc))
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        _emit_operational_alert(
            "scheduled_report_failed",
            severity="critical",
            title="Scheduled A-share report failed",
            message=str(exc),
            source="ashare_tech_scheduler",
            related_id=report_id,
            details={"reportId": report_id, "taskId": task_id, "error": str(exc)},
            dedupe_key=f"scheduled_report_failed:{report_id}",
        )
        _record_task_metric("ashare_tech_report", "failed")
        raise


@celery_app.task(name="lean_web.schedule_ashare_tech_report")
def schedule_ashare_tech_report_task():
    requested_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    report = ashare_tech_insights.create_report(requested_date)
    if report.get("status") == "success":
        return {"id": report["id"], "status": "success", "reused": True}
    task = create_task(
        "ashare_tech_report", f"A股科技股日报 {requested_date}",
        {"requestedDate": requested_date, "scheduled": True}, related_id=report["id"],
    )
    ashare_tech_insights.attach_task(report["id"], task["id"])
    result = generate_ashare_tech_report_task.apply_async(args=[task["id"], report["id"]])
    update_task(task["id"], celery_task_id=result.id)
    return {"id": report["id"], "taskId": task["id"], "status": "queued"}


@celery_app.task(name="lean_web.refresh_ashare_tech_evaluations")
def refresh_ashare_tech_evaluations_task(task_id: str | None = None):
    if task_id:
        update_task(task_id, status="running", started_at=utc_now(), error=None)
        append_log(task_id, "Refreshing matured A-share technology Agent predictions.")
    try:
        result = ashare_tech_agents.refresh_evaluations()
        if task_id:
            update_task(
                task_id,
                status="success",
                artifacts_json=["ashare-tech-evaluations"],
                finished_at=utc_now(),
                error=None,
            )
            append_log(task_id, f"Completed prediction refresh: {json.dumps(result, ensure_ascii=False)}")
        _record_task_metric("ashare_tech_evaluation", "success")
        return result
    except Exception as exc:
        if task_id:
            update_task(task_id, status="failed", finished_at=utc_now(), error=str(exc))
            append_log(task_id, f"Prediction refresh failed: {exc}")
        _record_task_metric("ashare_tech_evaluation", "failed")
        raise


@celery_app.task(name="lean_web.mark_paper_walkforward_running")
def mark_paper_walkforward_running_task(paper_run_id: str):
    paper_service.mark_walkforward_running(paper_run_id)
    return {"paperRunId": paper_run_id, "status": "running"}


@celery_app.task(
    name="lean_web.finalize_paper_walkforward",
    acks_late=True,
    reject_on_worker_lost=True,
)
def finalize_paper_walkforward_task(paper_run_id: str):
    result = paper_service.finalize_walkforward_run(paper_run_id)
    job = paper_scheduler.job_for_date(
        str(result.get("session_id") or ""),
        str(result.get("trade_date") or ""),
    )
    if job and result.get("status") == "success":
        paper_scheduler.transition_job(
            str(job["id"]),
            "COMPLETED",
            event_type="paper_run_completed",
            payload={"paperRunId": paper_run_id},
            expected_states={"RUNNING", "RETRYING"},
            paper_run_id=paper_run_id,
            task_id=str(result.get("task_id") or "") or None,
        )
    elif job:
        paper_scheduler.transition_job(
            str(job["id"]),
            "FAILED",
            event_type="paper_run_failed",
            payload={"paperRunId": paper_run_id, "error": str(result.get("failure") or "finalize_failed")},
            expected_states={"RUNNING", "RETRYING"},
        )
    return result


@celery_app.task(name="lean_web.recover_paper_finalizations")
def recover_paper_finalizations_task(
    paper_run_id: str | None = None,
    stale_seconds: int | None = None,
):
    configured = int(
        stale_seconds
        if stale_seconds is not None
        else os.environ.get("LEAN_PAPER_FINALIZE_STALE_SECONDS", "120")
    )
    candidates = paper_service.recoverable_walkforward_finalizations(
        stale_seconds=max(0, configured),
        paper_run_id=paper_run_id,
    )
    recovered = []
    for item in candidates:
        run_id = str(item["id"])
        job = paper_scheduler.job_for_date(
            str(item["session_id"]),
            str(item["trade_date"]),
        )
        if job and job.get("state") == "RUNNING":
            job = paper_scheduler.transition_job(
                str(job["id"]),
                "RETRYING",
                event_type="finalization_worker_loss_recovered",
                payload={"paperRunId": run_id},
                expected_states={"RUNNING"},
            )
        if job and job.get("state") == "RETRYING":
            paper_scheduler.transition_job(
                str(job["id"]),
                "RUNNING",
                event_type="replacement_finalization_dispatched",
                payload={"paperRunId": run_id},
                expected_states={"RETRYING"},
                paper_run_id=run_id,
            )
        dispatched = finalize_paper_walkforward_task.apply_async(args=[run_id])
        recovered.append(
            {
                "paperRunId": run_id,
                "taskId": dispatched.id,
            }
        )
    return {"recovered": recovered, "staleSeconds": max(0, configured)}


@celery_app.task(name="lean_web.fail_paper_walkforward")
def fail_paper_walkforward_task(request, exc, traceback, paper_run_id: str):  # pragma: no cover - Celery errback
    failed = paper_service.fail_walkforward_run(paper_run_id, str(exc))
    job = paper_scheduler.job_for_date(
        str(failed.get("session_id") or ""),
        str(failed.get("trade_date") or ""),
    )
    if job and job.get("state") in {"RUNNING", "RETRYING"}:
        paper_scheduler.transition_job(
            str(job["id"]),
            "FAILED",
            event_type="worker_error",
            payload={"paperRunId": paper_run_id, "error": str(exc)},
            expected_states={"RUNNING", "RETRYING"},
        )
    _emit_operational_alert(
        "paper_walkforward_failed",
        severity="critical",
        title="Paper walk-forward failed",
        message=str(exc),
        source="paper_scheduler",
        related_id=str(failed.get("session_id") or paper_run_id),
        details={
            "paperRunId": paper_run_id,
            "sessionId": failed.get("session_id"),
            "tradeDate": failed.get("trade_date"),
            "error": str(exc),
        },
        dedupe_key=f"paper_walkforward_failed:{paper_run_id}",
    )
    return failed


@celery_app.task(
    name="lean_web.finalize_paper_execution_cycle",
    acks_late=True,
    reject_on_worker_lost=True,
)
def finalize_paper_execution_cycle_task(cycle_id: str):
    return paper_accounts.finalize_cycle(cycle_id)


@celery_app.task(name="lean_web.fail_paper_execution_cycle")
def fail_paper_execution_cycle_task(request, exc, traceback, cycle_id: str):  # pragma: no cover - Celery errback
    return paper_accounts.fail_cycle(cycle_id, "worker_failed", str(exc))


@celery_app.task(
    name="lean_web.run_paper_execution_cycle",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_paper_execution_cycle_task(cycle_id: str):
    from celery import chain

    context = paper_accounts.begin_cycle(cycle_id)
    if context.get("status") in {"waiting_data", "failed", "succeeded", "skipped"}:
        return context
    paper_run = context["paperRun"]
    workflow = chain(
        mark_paper_walkforward_running_task.si(paper_run["id"]),
        run_backtest_task.si(paper_run["task_id"], paper_run["backtest_run_id"]),
        finalize_paper_walkforward_task.si(paper_run["id"]),
        finalize_paper_execution_cycle_task.si(cycle_id),
    )
    result = workflow.apply_async(
        link_error=fail_paper_execution_cycle_task.s(cycle_id)
    )
    return {
        "cycleId": cycle_id,
        "paperRunId": paper_run["id"],
        "workflowTaskId": result.id,
        "status": "running",
    }


@celery_app.task(name="lean_web.schedule_due_paper_deployments")
def schedule_due_paper_deployments_task():
    return paper_accounts.schedule_due_deployments()


@celery_app.task(name="lean_web.recover_orphaned_paper_cycles")
def recover_orphaned_paper_cycles_task():
    return paper_accounts.recover_orphaned_cycles()


@celery_app.task(name="lean_web.refresh_paper_account_projections")
def refresh_paper_account_projections_task(account_id: str | None = None):
    if account_id:
        return {"accounts": [paper_accounts.rebuild_current_projection(account_id)]}
    page = paper_accounts.list_accounts(limit=200)
    return {
        "accounts": [
            paper_accounts.rebuild_current_projection(str(item["id"]))
            for item in page["items"]
            if item.get("status") != "archived"
        ]
    }


@celery_app.task(name="lean_web.deliver_paper_cycle_notifications")
def deliver_paper_cycle_notifications_task():
    return paper_accounts.deliver_notifications()


@celery_app.task(name="lean_web.schedule_paper_walkforward", bind=True, max_retries=2)
def schedule_paper_walkforward_task(self):
    from celery import chain

    scheduled = []
    recovered = paper_scheduler.recover_orphaned_jobs()
    retry_errors = []
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    for session in paper_service.list_sessions():
        if (
            not paper_service._is_lean_mode(session.get("mode"))
            or session.get("status") != "running"
            or not session.get("auto_advance")
        ):
            continue
        next_date = session.get("start_date")
        if session.get("last_processed_date"):
            next_date = next_trade_date(
                str(session.get("venue") or "china"),
                str(session["last_processed_date"]),
            )
        if not next_date or str(next_date) > today:
            continue
        current_runs = paper_service.list_walkforward_runs(session["id"])
        if any(
            item.get("trade_date") == str(next_date) and item.get("status") in {"queued", "running", "success"}
            for item in current_runs
        ):
            continue
        job = paper_scheduler.ensure_job(str(session["id"]), str(next_date))
        if job.get("state") == "COMPLETED":
            continue
        if job.get("state") in {"RUNNING", "READY"}:
            continue
        if job.get("state") in {"FAILED", "BLOCKED_DATA", "BLOCKED_QA", "RETRYING"}:
            if int(job.get("attempt") or 0) >= int(job.get("max_attempts") or 3):
                if job.get("state") != "ESCALATED":
                    job = paper_scheduler.transition_job(
                        str(job["id"]),
                        "ESCALATED",
                        event_type="retry_budget_exhausted",
                        payload={"error": job.get("last_error")},
                        expected_states={"FAILED", "BLOCKED_DATA", "BLOCKED_QA", "RETRYING"},
                    )
                continue
            if job.get("state") != "RETRYING":
                job = paper_scheduler.transition_job(
                    str(job["id"]),
                    "RETRYING",
                    event_type="automatic_retry",
                    expected_states={"FAILED", "BLOCKED_DATA", "BLOCKED_QA"},
                )
            job = paper_scheduler.transition_job(
                str(job["id"]),
                "READY",
                event_type="retry_ready",
                expected_states={"RETRYING"},
            )
        elif job.get("state") == "SCHEDULED":
            job = paper_scheduler.transition_job(
                str(job["id"]),
                "READY",
                event_type="readiness_passed",
                expected_states={"SCHEDULED"},
            )
        try:
            paper_run = paper_service.create_walkforward_run(session["id"], str(next_date))
            job = paper_scheduler.transition_job(
                str(job["id"]),
                "RUNNING",
                event_type="workflow_queued",
                payload={"paperRunId": paper_run["id"]},
                expected_states={"READY", "RETRYING"},
                paper_run_id=str(paper_run["id"]),
                task_id=str(paper_run.get("task_id") or "") or None,
            )
            workflow = chain(
                mark_paper_walkforward_running_task.si(paper_run["id"]),
                run_backtest_task.si(paper_run["task_id"], paper_run["backtest_run_id"]),
                finalize_paper_walkforward_task.si(paper_run["id"]),
            )
            workflow.apply_async(link_error=fail_paper_walkforward_task.s(paper_run["id"]))
            scheduled.append(paper_run["id"])
        except Exception as exc:
            message = str(exc).lower()
            blocked_state = "BLOCKED_QA" if "qa" in message else "BLOCKED_DATA" if any(
                token in message for token in ("data", "benchmark", "certif", "source", "reference")
            ) else "FAILED"
            try:
                paper_scheduler.transition_job(
                    str(job["id"]),
                    blocked_state,
                    event_type="schedule_failed",
                    payload={"error": str(exc)},
                    expected_states={"READY", "RUNNING"},
                )
            except Exception:
                logger.exception("Failed to transition Paper daily job after schedule error")
            paper_service.record_session_warning(session["id"], "paper_schedule_waiting", str(exc))
            _emit_operational_alert(
                "paper_schedule_failed",
                severity="warning",
                title="Paper automatic scheduling is waiting",
                message=str(exc),
                source="paper_scheduler",
                related_id=str(session["id"]),
                details={"sessionId": session["id"], "tradeDate": next_date, "error": str(exc)},
                dedupe_key=f"paper_schedule_failed:{session['id']}",
            )
            retry_errors.append(str(exc))
            continue
    if retry_errors:
        raise self.retry(exc=RuntimeError("; ".join(retry_errors[:3])), countdown=30 * 60)
    return {"scheduled": scheduled, "recovered": recovered}


def _update_table(table: str, row_id: str, **fields):
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = [json_dump(value) if key.endswith("_json") else value for key, value in fields.items()]
    values.append(row_id)
    with db() as connection:
        connection.execute(f"update {table} set {assignments} where id = ?", values)


def _task_project(task, run: dict[str, Any] | None = None):
    parameters = task.get("parameters") or (run or {}).get("parameters") or {}
    snapshot_dir = parameters.get("strategySnapshotDir")
    if snapshot_dir and Path(snapshot_dir).is_dir():
        return {
            "id": task.get("project_id"),
            "project_path": snapshot_dir,
            "main_file": parameters.get("strategySnapshotMainFile") or "main.py",
            "algorithm_class": parameters.get("strategySnapshotAlgorithmClass") or "Algorithm",
            "language": parameters.get("strategySnapshotLanguage") or "Python",
            "snapshot": True,
        }
    project_id = task.get("project_id")
    if not project_id:
        raise LeanPlatformError("project_required: Backtest tasks must reference a project snapshot.")
    return get_project(project_id)


@celery_app.task(name="lean_web.dispatch_experiment_batch")
def dispatch_experiment_batch_task(batch_id: str):
    from ..services.experiment_batches import dispatch_window

    return dispatch_window(batch_id)


@celery_app.task(
    name="lean_web.reconcile_experiment_batches",
    autoretry_for=(DatabaseUnavailableError,),
    retry_backoff=5,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
)
def reconcile_experiment_batches_task():
    from ..services.experiment_batches import dispatch_window, list_batches

    reconciled = []
    for batch in list_batches():
        if batch.get("status") in {"queued", "running"} and not batch.get("cancel_requested"):
            dispatch_window(str(batch["id"]))
            reconciled.append(str(batch["id"]))
    return {"reconciled": reconciled}


@celery_app.task(name="lean_web.run_research_batch_item")
def run_research_batch_item_task(batch_id: str, item_id: str):
    from ..research import factors
    from ..services.experiment_batches import finish_research_item

    with db() as connection:
        row = connection.execute("select * from experiment_batch_items where id=? and batch_id=?", (item_id, batch_id)).fetchone()
    item = row_to_dict(row)
    if not item:
        return {"status": "missing", "itemId": item_id}
    with db() as connection:
        connection.execute("update experiment_batch_items set status='running',started_at=? where id=?", (utc_now(), item_id))
    parameters = item.get("parameters") or {}
    try:
        mode = str(parameters.get("mode") or "analysis")
        if mode == "factor_batch" or parameters.get("factorName"):
            result = factors.evaluate_factor(
                factor_name=str(parameters.get("factorName") or "momentum"),
                universe_code=str(parameters.get("universeCode") or "ALL_A"),
                start_date=str(parameters.get("start") or parameters.get("startDate") or "2020-01-01"),
                end_date=str(parameters.get("end") or parameters.get("endDate") or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()),
                forward_days=int(parameters.get("forwardDays") or 1),
                quantiles=int(parameters.get("quantiles") or 5),
                engine=parameters.get("engine"),
                persist=True,
            )
        else:
            symbol = str(parameters.get("symbol") or "").upper()
            predicates = ("symbol=?",) if symbol else ()
            coverage_rows = market_lake.query_matching(
                kind="bars", columns="count(*) rows,min(trade_date) first_date,max(trade_date) last_date",
                predicates=predicates, parameters=(symbol,) if symbol else (),
            )
            coverage = coverage_rows[0] if coverage_rows else {"rows": 0, "first_date": None, "last_date": None}
            coverage["sources"] = len(market_lake.matching_scopes(kind="bars"))
            result = {"exampleKey": parameters.get("exampleKey"), "symbol": symbol or None, "coverage": coverage}
        finish_research_item(batch_id, item_id, result=result)
        dispatch_experiment_batch_task.apply_async(args=[batch_id], queue="default")
        return {"status": "success", "itemId": item_id, "result": result}
    except Exception as exc:
        finish_research_item(batch_id, item_id, error=str(exc))
        dispatch_experiment_batch_task.apply_async(args=[batch_id], queue="default")
        raise


@celery_app.task(name="lean_web.fetch_data_batch")
def fetch_data_batch_task(task_id: str):
    task = get_task(task_id)
    parameters = task["parameters"]
    symbols = parameters.get("symbols") or []
    provider = parameters.get("provider") or "auto"
    asset_class = parameters.get("assetClass") or "equity"
    market = parameters.get("market") or "usa"
    venue = parameters.get("venue") or None
    resolution = parameters.get("resolution") or "daily"
    data_type = parameters.get("dataType") or "trade"
    overwrite = bool(parameters.get("overwrite", False))
    outputsize = parameters.get("outputsize") or "compact"
    start_date = parameters.get("startDate") or None
    end_date = parameters.get("endDate") or None
    adjust = parameters.get("adjust") or ""
    api_key = parameters.get("apiKey") or None
    update_task(task_id, status="running", started_at=utc_now(), finished_at=None, error=None)
    results = []
    failures = []
    try:
        for symbol in symbols:
            symbol = str(symbol).upper().strip()
            if not symbol:
                continue
            append_log(task_id, f"Fetching {symbol} from {provider} ({asset_class}/{venue or market}/{resolution}).")
            try:
                asset = fetch_and_import_symbol(
                    symbol,
                    provider,
                    market=market,
                    asset_class=asset_class,
                    venue=venue,
                    resolution=resolution,
                    data_type=data_type,
                    overwrite=overwrite,
                    api_key=api_key,
                    outputsize=outputsize,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust,
                )
                append_log(task_id, f"Imported {symbol}: {asset['rows']} rows ({asset['first_date']} -> {asset['last_date']}).")
                results.append(asset)
            except Exception as exc:
                append_log(task_id, f"Failed {symbol}: {exc}")
                failures.append({"symbol": symbol, "error": str(exc)})
        status = "success" if results and not failures else "failed" if not results else "success"
        error = None if not failures else f"{len(failures)} symbol(s) failed."
        update_task(
            task_id,
            status=status,
            artifacts_json=[item["lean_file"] for item in results],
            error=error,
            finished_at=utc_now(),
        )
        _record_task_metric("data_fetch", status)
        return {"status": status, "results": results, "failures": failures}
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        _record_task_metric("data_fetch", "failed")
        raise


@celery_app.task(
    name="lean_web.download_on_demand_dataset",
    acks_late=True,
    reject_on_worker_lost=True,
)
def download_on_demand_dataset_task(task_id: str):
    task = get_task(task_id)
    parameters = task["parameters"]
    update_task(task_id, status="running", started_at=utc_now(), finished_at=None, error=None)
    append_log(
        task_id,
        f"Downloading TuShare dataset {parameters.get('dataset')} to explicit storage target {parameters.get('storageTarget')}.",
    )
    try:
        result = data_sync.download_on_demand_dataset(
            task_id=task_id,
            dataset_key=str(parameters.get("dataset") or ""),
            storage_target=str(parameters.get("storageTarget") or ""),
            relative_path=str(parameters.get("relativePath") or "") or None,
            file_format=str(parameters.get("format") or "parquet"),
            start_date=str(parameters.get("startDate") or "") or None,
            end_date=str(parameters.get("endDate") or "") or None,
            symbol=str(parameters.get("symbol") or "") or None,
            parameters=dict(parameters.get("apiParameters") or {}),
        )
        append_log(
            task_id,
            f"Exported {result['rows']} rows to {result['displayPath']} sha256={result['sha256']}.",
        )
        update_task(
            task_id,
            status="success",
            artifacts_json=[result["displayPath"]],
            finished_at=utc_now(),
        )
        _record_task_metric("on_demand_download", "success")
        return result
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        _record_task_metric("on_demand_download", "failed")
        raise


@celery_app.task(
    name="lean_web.sync_all_data",
    acks_late=True,
    reject_on_worker_lost=True,
)
def sync_all_data_task(task_id: str, run_id: str):
    task = get_task(task_id)
    if task.get("status") == CANCELLED:
        append_log(task_id, "Data synchronization was cancelled before the worker started it.")
        return {"status": "cancelled", "cancelled": True, "datasets": {}}
    update_task(task_id, status="running", started_at=utc_now(), finished_at=None, error=None)
    append_log(task_id, "Discovering TuShare Pro 5,000-point low-frequency entitlements.")
    try:
        result = data_sync.run_sync(run_id, task_id=task_id)
        run_status = str(result.get("status") or ("cancelled" if result.get("cancelled") else "success"))
        status = (
            "cancelled"
            if run_status == "cancelled"
            else "success"
            if run_status == "success"
            else "failed"
        )
        error = (
            "MySQL became unavailable; synchronization paused at its durable checkpoint."
            if run_status == "paused"
            else "One or more datasets require retry."
            if run_status == "partial"
            else None
        )
        update_task(task_id, status=status, artifacts_json=[], error=error, finished_at=utc_now())
        append_log(task_id, f"Data synchronization finished: {run_status}.")
        if run_status == "paused":
            _emit_operational_alert(
                "data_sync_paused",
                severity="critical",
                title="Governed data synchronization paused",
                message=error or "MySQL became unavailable.",
                source="data_sync",
                related_id=run_id,
                details={"runId": run_id, "taskId": task_id, "retryable": True},
                dedupe_key=f"data_sync_paused:{run_id}",
            )
        _record_task_metric("data_sync", run_status)
        return result
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        _emit_operational_alert(
            "data_sync_failed",
            severity="critical",
            title="Governed data synchronization failed",
            message=str(exc),
            source="data_sync",
            related_id=run_id,
            details={"runId": run_id, "taskId": task_id, "error": str(exc)},
            dedupe_key=f"data_sync_failed:{run_id}",
        )
        _record_task_metric("data_sync", "failed")
        raise


@celery_app.task(
    name="lean_web.persist_tushare_lineage",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=8,
)
def persist_tushare_lineage_task(job_id: str):
    return tushare_lineage.process_lineage_job(job_id)


@celery_app.task(name="lean_web.recover_tushare_lineage")
def recover_tushare_lineage_task():
    job_ids = tushare_lineage.recover_lineage_jobs()
    for job_id in job_ids:
        persist_tushare_lineage_task.apply_async(args=[job_id], queue="data-lineage")
    return {"queued": len(job_ids)}


@celery_app.task(
    name="lean_web.prepare_ml_data",
    acks_late=True,
    reject_on_worker_lost=True,
)
def prepare_ml_data_task(task_id: str, run_id: str):
    update_task(task_id, status="running", started_at=utc_now(), finished_at=None, error=None)
    try:
        result = ml_data_preparation.run_universe_backfill(
            run_id,
            log=lambda message: append_log(task_id, message),
            cancelled=lambda: bool(get_task(task_id).get("status") == CANCELLED),
        )
        status = "cancelled" if result.get("status") == "cancelled" else "success" if result.get("status") == "success" else "failed"
        update_task(task_id, status=status, error=None if status == "success" else str(result.get("status")), finished_at=utc_now())
        _record_task_metric("ml_data_preparation", str(result.get("status")))
        return result
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        data_sync.mark_run_failed(run_id, str(exc))
        _record_task_metric("ml_data_preparation", "failed")
        raise


@celery_app.task(
    name="lean_web.run_ml_research",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_ml_research_task(task_id: str, research_run_id: str):
    update_task(task_id, status="running", started_at=utc_now(), finished_at=None, error=None)
    with db() as connection:
        now = utc_now()
        connection.execute(
            "update research_runs set status='running',started_at=?,owner_heartbeat_at=? where id=?",
            (now, now, research_run_id),
        )
        connection.execute("update research_run_items set status='running',started_at=? where run_id=?", (utc_now(), research_run_id))
    try:
        def is_cancelled() -> bool:
            if get_task(task_id).get("status") == CANCELLED:
                return True
            with db() as connection:
                row = connection.execute("select cancel_requested from research_runs where id=?", (research_run_id,)).fetchone()
            return bool(row and row["cancel_requested"])

        result = ml_research.run_training(
            research_run_id,
            log=lambda message: append_log(task_id, message),
            cancelled=is_cancelled,
        )
        status = "cancelled" if result.get("status") == "cancelled" else "success"
        artifacts = result.get("artifacts") or {}
        artifact_paths = [
            value for key, value in artifacts.items()
            if key in {"rollingOosPredictions", "finalHoldoutPredictions", "featureImportance", "model"}
        ]
        update_task(task_id, status=status, artifacts_json=artifact_paths, finished_at=utc_now())
        _record_task_metric("ml_research", status)
        return result
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        _record_task_metric("ml_research", "failed")
        raise


@celery_app.task(
    name="lean_web.run_research_analysis",
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_research_analysis_task(task_id: str, research_run_id: str):
    update_task(task_id, status="running", started_at=utc_now(), finished_at=None, error=None)
    try:
        result = research_runs.execute_analysis_run(
            research_run_id,
            progress=lambda message: append_log(task_id, message),
        )
        status = str(result.get("status") or "failed")
        artifact_names = [
            str(item.get("name"))
            for item in ((result.get("result") or {}).get("artifacts") or [])
            if item.get("name")
        ]
        update_task(
            task_id,
            status="success" if status == "success" else "cancelled" if status == "cancelled" else "failed",
            artifacts_json=artifact_names,
            error=result.get("error"),
            finished_at=utc_now(),
        )
        _record_task_metric("research_analysis", status)
        return result
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        _record_task_metric("research_analysis", "failed")
        raise


@celery_app.task(
    name="lean_web.materialize_sync_data",
    acks_late=True,
    reject_on_worker_lost=True,
)
def materialize_sync_data_task(run_id: str):
    return data_sync.materialize_daily_run(run_id)


@celery_app.task(
    name="lean_web.maintain_derived_layers",
    acks_late=True,
    reject_on_worker_lost=True,
)
def maintain_derived_layers_task(run_id: str | None = None):
    run = derived_maintenance.maintenance_run(run_id) if run_id else None
    if run is None:
        run = derived_maintenance.create_maintenance_run(trigger_type="schedule" if run_id is None else "recovery")
    result = derived_maintenance.run_maintenance(str(run["id"]))
    summary = result.get("summary") or {}
    certified = ((summary.get("parquetConsistency") or {}).get("certifiedDatasetIds") or [])
    if result.get("status") == "success" and certified:
        for asset_class in ("equity", "index"):
            resolve_open_alert(
                f"source_certification_revoked:tushare:{asset_class}:china:china",
                actor="automatic_recertification",
            )
    return result


@celery_app.task(name="lean_web.recover_source_certifications")
def recover_source_certifications_task():
    certifications = [
        source_certification("tushare", asset_class=asset_class, market="china", venue="china")
        for asset_class in ("equity", "index")
    ]
    if all(item.get("isCertified") and item.get("isProduction") for item in certifications):
        return {"status": "ready", "scheduled": False}
    with db() as connection:
        active_sync = connection.execute(
            """
            select id,status from data_sync_runs
            where status in ('queued','running','cancelling')
            order by created_at desc limit 1
            """
        ).fetchone()
        active = connection.execute(
            """
            select id,status from derived_maintenance_runs
            where status in ('queued','running','retry_wait')
            order by created_at desc limit 1
            """
        ).fetchone()
        latest_maintenance = connection.execute(
            """
            select id,status,attempt_count,max_attempts,error from derived_maintenance_runs
            order by created_at desc limit 1
            """
        ).fetchone()
    exhausted = (
        latest_maintenance
        if latest_maintenance
        and latest_maintenance["status"] == "failed"
        and int(latest_maintenance["attempt_count"] or 0) >= int(latest_maintenance["max_attempts"] or 5)
        else None
    )
    if active_sync:
        return {
            "status": "waiting_for_data_sync",
            "scheduled": False,
            "dataSyncRunId": active_sync["id"],
        }
    if not active and exhausted:
        return {
            "status": "recovery_exhausted",
            "scheduled": False,
            "runId": exhausted["id"],
            "attemptCount": int(exhausted["attempt_count"] or 0),
            "maxAttempts": int(exhausted["max_attempts"] or 0),
            "error": exhausted["error"],
        }
    if active:
        active_status = str(active["status"])
        if active_status == "retry_wait":
            with db() as connection:
                retry_row = connection.execute(
                    "select next_retry_at,attempt_count,max_attempts from derived_maintenance_runs where id=?",
                    (active["id"],),
                ).fetchone()
            if retry_row and int(retry_row["attempt_count"] or 0) >= int(retry_row["max_attempts"] or 5):
                return {"status": "recovery_exhausted", "scheduled": False, "runId": active["id"]}
            next_retry = datetime.fromisoformat(str(retry_row["next_retry_at"])) if retry_row and retry_row["next_retry_at"] else None
            if next_retry and next_retry > datetime.now(timezone.utc):
                return {
                    "status": "recovery_backoff",
                    "scheduled": False,
                    "runId": active["id"],
                    "nextRetryAt": next_retry.isoformat(),
                }
            with db() as connection:
                connection.execute(
                    "update derived_maintenance_runs set status='queued' where id=? and status='retry_wait'",
                    (active["id"],),
                )
            dispatched = maintain_derived_layers_task.apply_async(args=[active["id"]])
            return {
                "status": "recovery_resumed",
                "scheduled": True,
                "runId": active["id"],
                "taskId": dispatched.id,
            }
        lease_active = derived_maintenance.maintenance_lease_active()
        if active_status == "queued" or database_backend() != "mysql" or lease_active:
            return {"status": "recovery_in_progress", "scheduled": False, "runId": active["id"]}
        orphaned_run_id = str(active["id"])
        _discard_orphaned_maintenance_message(orphaned_run_id)
        with db() as connection:
            connection.execute(
                """
                update derived_maintenance_runs
                set status='queued',error='orphaned_after_worker_restart',heartbeat_at=?
                where id=? and status='running'
                """,
                (utc_now(), orphaned_run_id),
            )
        dispatched = maintain_derived_layers_task.apply_async(args=[orphaned_run_id])
        return {
            "status": "orphan_checkpoint_resumed",
            "scheduled": True,
            "runId": orphaned_run_id,
            "taskId": dispatched.id,
        }
    run = derived_maintenance.create_maintenance_run(
        layers=["parquet"],
        trigger_type="source_recertification",
    )
    dispatched = maintain_derived_layers_task.apply_async(args=[run["id"]])
    return {
        "status": "recovery_scheduled",
        "scheduled": True,
        "runId": run["id"],
        "taskId": dispatched.id,
    }


def _broker_unacked_maintenance_tags(client: Any, run_id: str) -> list[str]:
    needle = run_id.encode("utf-8")
    task_name = b"lean_web.maintain_derived_layers"
    return [
        tag.decode("utf-8") if isinstance(tag, bytes) else str(tag)
        for tag, message in (client.hgetall("unacked") or {}).items()
        if needle in message and task_name in message
    ]


def _discard_orphaned_maintenance_message(run_id: str) -> int:
    try:
        import redis

        client = redis.Redis.from_url(
            celery_app.conf.broker_url,
            socket_connect_timeout=1,
            socket_timeout=2,
        )
        client.ping()
    except Exception:
        return 0
    tags = _broker_unacked_maintenance_tags(client, run_id)
    if tags:
        client.hdel("unacked", *tags)
        client.zrem("unacked_index", *tags)
    return len(tags)


def _broker_contains_sync_run(client: Any, run_id: str) -> bool:
    """Check ready and unacknowledged Redis messages without worker RPC.

    The bulk worker uses the solo pool, so it cannot answer Celery inspect
    requests while a long synchronization is active.  Redis messages retain
    ``argsrepr`` in their JSON envelope, which lets the recovery task avoid
    dispatching a duplicate while the original is queued or unacknowledged.
    """
    needle = run_id.encode("utf-8")
    messages: list[bytes] = []
    for queue in ("data-bulk", "data"):
        messages.extend(client.lrange(queue, 0, -1) or [])
    messages.extend(client.hvals("unacked") or [])
    return any(needle in message for message in messages)


def _broker_ready_contains_sync_run(client: Any, run_id: str) -> bool:
    needle = run_id.encode("utf-8")
    messages: list[bytes] = []
    for queue in ("data-bulk", "data"):
        messages.extend(client.lrange(queue, 0, -1) or [])
    return any(needle in message for message in messages)


def _broker_unacked_sync_tags(client: Any, run_id: str) -> list[str]:
    needle = run_id.encode("utf-8")
    task_name = b"lean_web.sync_all_data"
    return [
        tag.decode("utf-8") if isinstance(tag, bytes) else str(tag)
        for tag, message in (client.hgetall("unacked") or {}).items()
        if needle in message and task_name in message
    ]


def _broker_ready_contains_materialization(client: Any, run_id: str) -> bool:
    needle = run_id.encode("utf-8")
    task_name = b"lean_web.materialize_sync_data"
    return any(
        needle in message and task_name in message
        for message in (client.lrange("data-demand", 0, -1) or [])
    )


def _broker_unacked_materialization_tags(client: Any, run_id: str) -> list[str]:
    needle = run_id.encode("utf-8")
    task_name = b"lean_web.materialize_sync_data"
    return [
        tag.decode("utf-8") if isinstance(tag, bytes) else str(tag)
        for tag, message in (client.hgetall("unacked") or {}).items()
        if needle in message and task_name in message
    ]


def _materialization_lease_active(run_id: str) -> bool:
    """Use the MySQL advisory lock as the source of truth for live work."""
    if database_backend() != "mysql":
        return False
    lock_name = f"lean:materialize:{run_id}"[:64]
    with db() as connection:
        row = connection.execute(
            "select is_used_lock(?) as owner",
            (lock_name,),
        ).fetchone()
    return bool(row and row.get("owner") is not None)


@celery_app.task(
    name="lean_web.recover_data_sync",
    autoretry_for=(DatabaseUnavailableError,),
    retry_backoff=5,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
)
def recover_data_sync_task():
    """Requeue stale canonical or derived sync work after worker loss."""
    stale_seconds = max(60, int(os.environ.get("LEAN_DATA_SYNC_STALE_SECONDS", "300")))
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_seconds)).isoformat()
    with db() as connection:
        rows = connection.execute(
            """
            select id,task_id,status,heartbeat_at from data_sync_runs
            where status in ('queued','running') and cancel_requested=0
              and coalesce(heartbeat_at,started_at,created_at) < ?
            order by created_at
            """,
            (cutoff,),
        ).fetchall()
        derived_rows = connection.execute(
            """
            select id,derived_status_json,finished_at
            from data_sync_runs
            where canonical_status='ready' and derived_status_json is not null
            order by created_at
            """
        ).fetchall()
    stale_derived: list[tuple[str, dict[str, Any]]] = []
    cutoff_datetime = datetime.fromisoformat(cutoff)
    for row in derived_rows:
        try:
            payload = json.loads(row["derived_status_json"] or "{}")
        except (TypeError, ValueError):
            continue
        if payload.get("status") not in {"queued", "running"}:
            continue
        heartbeat_text = str(payload.get("heartbeatAt") or row["finished_at"] or "")
        try:
            heartbeat = datetime.fromisoformat(heartbeat_text.replace("Z", "+00:00"))
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        except ValueError:
            heartbeat = datetime.min.replace(tzinfo=timezone.utc)
        if heartbeat < cutoff_datetime:
            stale_derived.append((str(row["id"]), payload))
    if not rows and not stale_derived:
        return {"recovered": [], "preserved": [], "recoveredDerived": [], "preservedDerived": []}

    try:
        import redis

        client = redis.Redis.from_url(celery_app.conf.broker_url, socket_connect_timeout=1, socket_timeout=2)
        client.ping()
    except Exception as exc:  # pragma: no cover - requires broker outage.
        return {
            "recovered": [],
            "preserved": [],
            "recoveredDerived": [],
            "preservedDerived": [],
            "error": f"broker_unavailable:{exc}",
        }

    recovered: list[str] = []
    preserved: list[str] = []
    for row in rows:
        run_id = str(row["id"])
        task_id = str(row["task_id"] or "")
        if not task_id or _broker_ready_contains_sync_run(client, run_id):
            preserved.append(run_id)
            continue
        orphaned_tags = _broker_unacked_sync_tags(client, run_id)
        if orphaned_tags:
            # A fresh heartbeat keeps live long-running tasks out of this
            # recovery set. Matching unacked messages that reach here belong
            # to a worker that disappeared without acknowledging them.
            client.hdel("unacked", *orphaned_tags)
            client.zrem("unacked_index", *orphaned_tags)
            append_log(task_id, f"Removed {len(orphaned_tags)} orphaned broker message(s) after stale heartbeat.")
        # Mark queued before publishing. A concurrent recovery pass will then
        # see the published Redis envelope and preserve it.
        if not data_sync.queue_stale_run_for_recovery(run_id):
            continue
        result = sync_all_data_task.apply_async(args=[task_id, run_id], queue="data-bulk")
        update_task(task_id, celery_task_id=result.id, status="queued", error=None, finished_at=None)
        append_log(task_id, "Recovered orphaned data synchronization after worker restart.")
        recovered.append(run_id)
    recovered_derived: list[str] = []
    preserved_derived: list[str] = []
    for run_id, payload in stale_derived:
        if _materialization_lease_active(run_id) or _broker_ready_contains_materialization(client, run_id):
            preserved_derived.append(run_id)
            continue
        orphaned_tags = _broker_unacked_materialization_tags(client, run_id)
        if orphaned_tags:
            client.hdel("unacked", *orphaned_tags)
            client.zrem("unacked_index", *orphaned_tags)
        payload["status"] = "queued"
        payload["recoveryReason"] = "stale_derived_heartbeat"
        payload["recoveredAt"] = utc_now()
        if not data_sync.queue_stale_derived_for_recovery(run_id, payload):
            continue
        materialize_sync_data_task.apply_async(args=[run_id], queue="data-demand")
        recovered_derived.append(run_id)
    return {
        "recovered": recovered,
        "preserved": preserved,
        "recoveredDerived": recovered_derived,
        "preservedDerived": preserved_derived,
    }


@celery_app.task(name="lean_web.run_backtest", bind=True, max_retries=None)
def run_backtest_task(self, task_id: str, run_id: str):
    task = get_task(task_id)
    parameters = task["parameters"]
    existing_run = get_backtest(run_id)
    if existing_run and existing_run.get("status") == CANCELLED:
        append_log(task_id, "Backtest was cancelled before the worker started it.")
        update_task(task_id, status=CANCELLED, error="Cancellation requested by user.", finished_at=utc_now())
        _record_task_metric("backtest", CANCELLED)
        _record_backtest_metric(CANCELLED)
        return {"status": CANCELLED, "run_id": run_id}
    try:
        project = _task_project(task, existing_run)
    except Exception as exc:
        error = str(exc)
        finished_at = utc_now()
        append_log(task_id, f"Backtest rejected before execution: {error}")
        update_task(task_id, status=FAILED, error=error, finished_at=finished_at)
        update_backtest(
            run_id,
            status=FAILED,
            error=error,
            error_message=error,
            failure_json=failure_metadata("project", error, retryable=False),
            finished_at=finished_at,
        )
        _record_task_metric("backtest", FAILED)
        _record_backtest_metric(FAILED)
        return {"status": FAILED, "run_id": run_id, "error": error}

    settings = get_settings()
    max_concurrent = int(settings.get("maxConcurrentJobs") or 1)
    timeout_seconds = int(settings.get("jobTimeoutSeconds") or 7200)
    lease = acquire_scheduler_lease(
        resource="backtest",
        holder_id=run_id,
        limit=max_concurrent,
        ttl_seconds=timeout_seconds + 600,
        metadata={"task_id": task_id, "run_id": run_id},
    )
    if lease is None:
        append_log(task_id, f"Backtest concurrency limit reached ({max_concurrent}); waiting for a scheduler slot.")
        update_task(task_id, status="queued", error=None)
        update_backtest(run_id, status="queued", error=None, error_message=None)
        raise self.retry(countdown=5)

    append_log(task_id, f"Task {task_id} started.")
    update_task(task_id, status="running", started_at=utc_now(), error=None)
    started_at = utc_now()
    update_backtest(run_id, status="running", started_at=started_at, error=None, error_message=None)
    try:
        from ..services.experiment_batches import reconcile_backtest

        reconcile_backtest(run_id)
    except Exception:
        logger.exception("Unable to mark experiment batch item running for %s", run_id)

    run_dir = RUNS_DIR / run_id
    lean_cache: dict[str, Any] = {}
    strategy_path = Path(project["project_path"]) / project["main_file"]

    def update_fingerprint(execution_validation: dict[str, Any] | None = None) -> dict[str, Any]:
        fingerprint = build_run_fingerprint(
            run_id=run_id,
            parameters=parameters,
            docker_image=parameters.get("dockerImage", DEFAULT_DOCKER_IMAGE),
            lean_cache=lean_cache,
            strategy_path=strategy_path,
            config_path=run_dir / "config.json",
        )
        validation = build_backtest_validation(parameters, fingerprint)
        if execution_validation is not None:
            validation = merge_execution_validation(validation, execution_validation)
            fingerprint["rawResultSha256"] = execution_validation.get("rawResultSha256")
            fingerprint["canonicalResultSha256"] = execution_validation.get("canonicalResultSha256")
            fingerprint["resultTolerancePolicy"] = execution_validation.get("tolerancePolicy")
        experiment = build_experiment_record(
            run_id=run_id,
            parameters=parameters,
            fingerprint=fingerprint,
            project_id=task.get("project_id"),
            strategy_path=str(strategy_path),
            validation=validation,
        )
        update_backtest(
            run_id,
            fingerprint_json=fingerprint,
            validation_json=validation,
            experiment_json=experiment,
        )
        record_experiment_versions(
            run_id=run_id,
            project_id=task.get("project_id"),
            fingerprint=fingerprint,
            validation=validation,
            experiment=experiment,
        )
        return validation

    try:
        runner = LeanRunner(timeout_seconds=timeout_seconds)
        container_name = runner.container_name_for(run_id)
        update_backtest(run_id, container_name=container_name, work_dir=str(run_dir), results_dir=str(run_dir / "results"))
        if parameters.get("assetClass") == "equity" and (parameters.get("market") or parameters.get("venue")) == "china":
            universe_symbols = [str(value).upper() for value in parameters.get("universeSymbols") or []]
            gate_symbols = list(dict.fromkeys([str(parameters["ticker"]).upper(), *universe_symbols]))
            benchmark_for_gate = str(parameters.get("benchmarkSymbol") or "").upper()
            source = str(parameters.get("source") or parameters.get("provider") or DEFAULT_PRODUCTION_SOURCE)
            adjust = str(parameters.get("adjust") or "raw")
            for data_symbol in gate_symbols:
                assert_ashare_ready(
                    data_symbol,
                    parameters["start"],
                    parameters["end"],
                    adjust=adjust,
                    source=source,
                    allow_truncated=bool(parameters.get("allowTruncatedData")),
                )
            assert_benchmark_ready(
                benchmark_for_gate,
                parameters["start"],
                parameters["end"],
                asset_class=str(parameters.get("assetClass") or "equity"),
                market=str(parameters.get("market") or "china"),
                venue=str(parameters.get("venue") or parameters.get("market") or "china"),
                resolution=str(parameters.get("resolution") or "daily"),
                data_type=str(parameters.get("dataType") or "trade"),
                adjust=adjust,
                source=source,
                allow_truncated=bool(parameters.get("allowTruncatedData")),
            )
            for symbol in gate_symbols:
                gate = quality_gate_range(symbol, parameters["start"], parameters["end"])
                if not gate["passed"]:
                    report_id = gate["blockingReports"][0].get("id") if gate["blockingReports"] else None
                    detail = f"qa_failed:{report_id}" if report_id else "qa_failed"
                    raise LeanPlatformError(f"A-share data QA critical gate blocked backtest for {symbol}: {detail}")
            if universe_symbols:
                lean_cache["universe"] = {
                    symbol: ensure_ashare_lean_cache(symbol, source=source, adjust=adjust)
                    for symbol in universe_symbols
                }
            else:
                lean_cache["symbol"] = ensure_ashare_lean_cache(parameters["ticker"], source=source, adjust=adjust)
            benchmark_symbol = str(parameters.get("benchmarkSymbol") or "").upper()
            if benchmark_symbol:
                lean_cache["benchmark"] = ensure_ashare_lean_cache(benchmark_symbol, source=source, adjust=adjust)
        lean_cache["resultsAnalyzerReference"] = ensure_lean_results_analyzer_reference_data(
            parameters["start"],
            parameters["end"],
        )
        pre_execution_validation = update_fingerprint()
        if not pre_execution_validation.get("passed"):
            failed_gates = ",".join(
                str(gate.get("name"))
                for gate in pre_execution_validation.get("gates") or []
                if not gate.get("passed")
            )
            raise LeanPlatformError(f"pre_execution_gate_failed:{failed_gates or 'unknown'}")
        project_path = Path(project["project_path"])
        output = runner.run_backtest(
            run_id,
            parameters,
            run_dir=run_dir,
            output_callback=lambda line: append_log(task_id, line),
            docker_image=parameters.get("dockerImage", DEFAULT_DOCKER_IMAGE),
            algorithm_path=project_path / project["main_file"],
            algorithm_class=project["algorithm_class"],
            language=project["language"],
            project_dir=project_path,
        )

        latest_run = get_backtest(run_id)
        if latest_run and latest_run.get("status") == CANCELLED:
            append_log(task_id, "Backtest execution ended after cancellation.")
            update_task(task_id, status=CANCELLED, error="Cancellation requested by user.", finished_at=utc_now())
            _record_task_metric("backtest", CANCELLED)
            _record_backtest_metric(CANCELLED)
            return {"status": CANCELLED, "run_id": run_id}

        raw_success = bool(output["exit_code"] == 0 and output["result_json_path"] and not output.get("timed_out"))
        execution_validation = (
            audit_backtest_execution(
                Path(output["result_json_path"]),
                parameters,
                (get_backtest(run_id) or {}).get("validation") or {},
            )
            if raw_success
            else None
        )
        status = "success" if raw_success and execution_validation and execution_validation.get("passed") else "failed"
        error = (
            None
            if status == "success"
            else execution_failure_message(execution_validation or {})
            or output.get("error")
            or "Docker run failed or did not produce result JSON."
        )
        finished_at = utc_now()
        # Keep the run non-terminal until the normalized result ledger is
        # persisted. Paper, Insights and the Web UI use success as the
        # readiness contract.
        update_backtest(
            run_id,
            status="running",
            result_json_path=output["result_json_path"],
            summary_json_path=output["summary_json_path"],
            report_html_path=output["report_html_path"],
            statistics_json=output["statistics"],
            exit_code=output["exit_code"],
            error=error,
            error_message=error,
            failure_json=(
                None
                if status == "success"
                else failure_metadata(
                    "validation" if raw_success else "execution",
                    error,
                    retryable=not raw_success,
                    details={"executionValidation": execution_validation or {}},
                )
            ),
            container_name=output.get("container_name"),
            work_dir=output.get("work_dir"),
            results_dir=output.get("results_dir"),
        )
        update_fingerprint(execution_validation)
        if raw_success and output["result_json_path"]:
            run = get_backtest(run_id) or {}
            persist_result(
                run_id,
                Path(output["result_json_path"]),
                Path(output["summary_json_path"]) if output.get("summary_json_path") else None,
                run,
            )
            refreshed = get_backtest(run_id) or {}
            refreshed_fingerprint = refreshed.get("fingerprint") or {}
            if (
                status == "success"
                and (refreshed.get("dataset_release_id") or refreshed_fingerprint.get("datasetReleaseId"))
            ):
                issue_certificate(run_id, allow_nonterminal=True)
        finalized = get_backtest(run_id) or {}
        certificate_id = finalized.get("reproducibility_certificate_id")
        trust_status = "trusted" if status == "success" and certificate_id else "invalid" if status != "success" else "unverified"
        trust_reason = None if trust_status == "trusted" else (
            execution_failure_message(execution_validation or {})
            if status != "success"
            else "reproducibility_certificate_missing"
        )
        update_backtest(
            run_id,
            status=status,
            finished_at=finished_at,
            trust_status=trust_status,
            trust_reason=trust_reason,
            trust_evaluated_at=finished_at,
        )
        update_task(
            task_id,
            status=status,
            artifacts_json=[
                path
                for path in (
                    output["result_json_path"],
                    output["summary_json_path"],
                    output["report_html_path"],
                    output.get("artifact_manifest_path"),
                    output.get("stdout_log_path"),
                )
                if path
            ],
            error=error,
            finished_at=finished_at,
        )
        _record_task_metric("backtest", status)
        _record_backtest_metric(status)
        return {"status": status, "run_id": run_id}
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        finished_at = utc_now()
        latest_run = get_backtest(run_id)
        if latest_run and latest_run.get("status") == CANCELLED:
            update_task(task_id, status=CANCELLED, error="Cancellation requested by user.", finished_at=finished_at)
            _record_task_metric("backtest", CANCELLED)
            _record_backtest_metric(CANCELLED)
            return {"status": CANCELLED, "run_id": run_id}
        analysis_failed = bool(
            latest_run
            and latest_run.get("exit_code") == 0
            and latest_run.get("result_json_path")
        )
        update_backtest(
            run_id,
            status="failed",
            error=str(exc),
            error_message=str(exc),
            failure_json=failure_metadata(
                "analysis" if analysis_failed else "execution",
                str(exc),
                retryable=not analysis_failed,
            ),
            exit_code=latest_run.get("exit_code") if analysis_failed else -1,
            finished_at=finished_at,
            trust_status="invalid",
            trust_reason=str(exc),
            trust_evaluated_at=finished_at,
        )
        update_fingerprint()
        update_task(task_id, status="failed", error=str(exc), finished_at=finished_at)
        _record_task_metric("backtest", "failed")
        _record_backtest_metric("failed")
        raise
    finally:
        release_scheduler_lease(lease.get("id"))
        try:
            from ..services.experiment_batches import reconcile_backtest

            reconcile_backtest(run_id)
        except Exception:
            logger.exception("Unable to reconcile experiment batch for backtest %s", run_id)


@celery_app.task(name="lean_web.start_research")
def start_research_task(task_id: str, session_id: str):
    task = get_task(task_id)
    project = _task_project(task)
    if not project:
        raise LeanPlatformError("Research requires a project.")
    port = int(task["parameters"].get("port", 8888))
    with db() as connection:
        session_row = connection.execute("select workspace_path from research_workspaces where id=?", (session_id,)).fetchone()
    workspace_path = session_row["workspace_path"] if session_row and session_row["workspace_path"] else project["project_path"]
    update_task(task_id, status="running", started_at=utc_now())
    _update_table(
        "research_workspaces", session_id, status="starting", readiness_status="starting",
        container_status="creating", started_at=utc_now(), last_checked_at=utc_now(),
    )
    try:
        output = run_detached_research(
            session_id,
            Path(workspace_path),
            port,
            lambda line: append_log(task_id, line),
            image=str(get_settings().get("researchImage") or "quantconnect/research:latest"),
        )
        _update_table(
            "research_workspaces",
            session_id,
            status="running",
            container_id=output["container_id"],
            url=output["url"],
            readiness_status=output.get("readiness_status") or "ready",
            container_status=output.get("container_status") or "running",
            last_checked_at=utc_now(),
            finished_at=None,
        )
        update_task(task_id, status="success", artifacts_json=[output["url"]], finished_at=utc_now())
        _record_task_metric("research", "success")
        return output
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        _update_table(
            "research_workspaces", session_id, status="failed", readiness_status="failed",
            container_status="failed", error=str(exc), last_checked_at=utc_now(), finished_at=utc_now(),
        )
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        _record_task_metric("research", "failed")
        raise


@celery_app.task(name="lean_web.generate_report")
def generate_report_task(task_id: str, report_id: str):
    task = get_task(task_id)
    run_id = task["parameters"]["runId"]
    with db() as connection:
        row = connection.execute("select * from backtest_runs where id = ?", (run_id,)).fetchone()
    run = row_to_dict(row)
    if not run or not run.get("result_json_path"):
        raise LeanPlatformError("Backtest result JSON not found.")
    update_task(task_id, status="running", started_at=utc_now())
    try:
        report_path = REPORTS_DIR / f"{report_id}.html"
        render_report(Path(run["result_json_path"]), report_path)
        _update_table("reports", report_id, status="success", report_path=str(report_path), finished_at=utc_now())
        update_task(task_id, status="success", artifacts_json=[str(report_path)], finished_at=utc_now())
        _record_task_metric("report", "success")
        return {"reportPath": str(report_path), "statistics": extract_statistics(Path(run["result_json_path"]))}
    except Exception as exc:
        _update_table("reports", report_id, status="failed", error=str(exc), finished_at=utc_now())
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        _record_task_metric("report", "failed")
        raise
