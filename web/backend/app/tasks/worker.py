import json
from pathlib import Path
from typing import Any

from .celery_app import celery_app
from ..core.config import ALGORITHM_PATH, DEFAULT_DOCKER_IMAGE, REPORTS_DIR, RUNS_DIR
from ..db import db, json_dump, row_to_dict, utc_now
from ..lean import (
    LeanPlatformError,
    extract_statistics,
    new_run_id,
    render_report,
    run_detached_research,
    run_docker_backtest,
)
from ..observability.metrics import BACKTEST_STATUS, TASK_STATUS
from ..domain.backtest_job import CANCELLED
from ..repositories.backtest_repository import get_backtest, update_backtest
from ..runners.lean_runner import LeanRunner
from ..services.data import fetch_and_import_symbol
from ..services.ashare_multisource import quality_gate_range
from ..services.ashare_repository import assert_benchmark_ready
from ..services.backtest_validation import build_backtest_validation, build_experiment_record
from ..services.experiments import record_experiment_versions
from ..services.projects import get_project
from ..services.result_service import persist_result
from ..services.lean_cache import ensure_ashare_lean_cache
from ..services.run_fingerprint import build_run_fingerprint
from ..services.scheduler import acquire_scheduler_lease, release_scheduler_lease
from ..services.settings import get_settings
from ..services.tasks import append_log, get_task, update_task


def _record_task_metric(kind: str, status: str) -> None:
    if TASK_STATUS is not None:
        TASK_STATUS.labels(kind, status).inc()


def _record_backtest_metric(status: str) -> None:
    if BACKTEST_STATUS is not None:
        BACKTEST_STATUS.labels(status).inc()


def _update_table(table: str, row_id: str, **fields):
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = [json_dump(value) if key.endswith("_json") else value for key, value in fields.items()]
    values.append(row_id)
    with db() as connection:
        connection.execute(f"update {table} set {assignments} where id = ?", values)


def _task_project(task):
    project_id = task.get("project_id")
    return get_project(project_id) if project_id else None


@celery_app.task(name="lean_web.fetch_data_batch")
def fetch_data_batch_task(task_id: str):
    task = get_task(task_id)
    parameters = task["parameters"]
    symbols = parameters.get("symbols") or []
    provider = parameters.get("provider") or "stooq"
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
    update_task(task_id, status="running", started_at=utc_now(), error=None)
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


@celery_app.task(name="lean_web.run_backtest", bind=True, max_retries=None)
def run_backtest_task(self, task_id: str, run_id: str):
    task = get_task(task_id)
    parameters = task["parameters"]
    project = _task_project(task)
    existing_run = get_backtest(run_id)
    if existing_run and existing_run.get("status") == CANCELLED:
        append_log(task_id, "Backtest was cancelled before the worker started it.")
        update_task(task_id, status=CANCELLED, error="Cancellation requested by user.", finished_at=utc_now())
        _record_task_metric("backtest", CANCELLED)
        _record_backtest_metric(CANCELLED)
        return {"status": CANCELLED, "run_id": run_id}

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

    run_dir = RUNS_DIR / run_id
    lean_cache: dict[str, Any] = {}
    strategy_path = Path(project["project_path"]) / project["main_file"] if project else ALGORITHM_PATH

    def update_fingerprint() -> None:
        fingerprint = build_run_fingerprint(
            run_id=run_id,
            parameters=parameters,
            docker_image=parameters.get("dockerImage", DEFAULT_DOCKER_IMAGE),
            lean_cache=lean_cache,
            strategy_path=strategy_path,
            config_path=run_dir / "config.json",
        )
        validation = build_backtest_validation(parameters, fingerprint)
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

    try:
        runner = LeanRunner(timeout_seconds=timeout_seconds)
        container_name = runner.container_name_for(run_id)
        update_backtest(run_id, container_name=container_name, work_dir=str(run_dir), results_dir=str(run_dir / "results"))
        if parameters.get("assetClass") == "equity" and (parameters.get("market") or parameters.get("venue")) == "china":
            gate_symbols = [str(parameters["ticker"]).upper()]
            benchmark_for_gate = str(parameters.get("benchmarkSymbol") or "").upper()
            assert_benchmark_ready(
                benchmark_for_gate,
                parameters["start"],
                parameters["end"],
                asset_class=str(parameters.get("assetClass") or "equity"),
                market=str(parameters.get("market") or "china"),
                venue=str(parameters.get("venue") or parameters.get("market") or "china"),
                resolution=str(parameters.get("resolution") or "daily"),
                data_type=str(parameters.get("dataType") or "trade"),
                adjust=str(parameters.get("adjust") or "raw"),
            )
            if benchmark_for_gate:
                gate_symbols.append(benchmark_for_gate)
            for symbol in gate_symbols:
                gate = quality_gate_range(symbol, parameters["start"], parameters["end"])
                if not gate["passed"]:
                    report_id = gate["blockingReports"][0].get("id") if gate["blockingReports"] else None
                    detail = f"qa_failed:{report_id}" if report_id else "qa_failed"
                    raise LeanPlatformError(f"A-share data QA critical gate blocked backtest for {symbol}: {detail}")
            source = str(parameters.get("source") or parameters.get("provider") or "akshare")
            adjust = str(parameters.get("adjust") or "raw")
            lean_cache["symbol"] = ensure_ashare_lean_cache(parameters["ticker"], source=source, adjust=adjust)
            benchmark_symbol = str(parameters.get("benchmarkSymbol") or "").upper()
            if benchmark_symbol:
                lean_cache["benchmark"] = ensure_ashare_lean_cache(benchmark_symbol, source=source, adjust=adjust)
        update_fingerprint()
        if project:
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
        else:
            output = runner.run_backtest(
                run_id,
                parameters,
                run_dir=run_dir,
                output_callback=lambda line: append_log(task_id, line),
                docker_image=parameters.get("dockerImage", DEFAULT_DOCKER_IMAGE),
            )

        latest_run = get_backtest(run_id)
        if latest_run and latest_run.get("status") == CANCELLED:
            append_log(task_id, "Backtest execution ended after cancellation.")
            update_task(task_id, status=CANCELLED, error="Cancellation requested by user.", finished_at=utc_now())
            _record_task_metric("backtest", CANCELLED)
            _record_backtest_metric(CANCELLED)
            return {"status": CANCELLED, "run_id": run_id}

        status = "success" if output["exit_code"] == 0 and output["result_json_path"] and not output.get("timed_out") else "failed"
        error = None if status == "success" else output.get("error") or "Docker run failed or did not produce result JSON."
        finished_at = utc_now()
        update_backtest(
            run_id,
            status=status,
            result_json_path=output["result_json_path"],
            summary_json_path=output["summary_json_path"],
            report_html_path=output["report_html_path"],
            statistics_json=output["statistics"],
            exit_code=output["exit_code"],
            error=error,
            error_message=error,
            container_name=output.get("container_name"),
            work_dir=output.get("work_dir"),
            results_dir=output.get("results_dir"),
            finished_at=finished_at,
        )
        update_fingerprint()
        if status == "success" and output["result_json_path"]:
            run = get_backtest(run_id) or {}
            persist_result(
                run_id,
                Path(output["result_json_path"]),
                Path(output["summary_json_path"]) if output.get("summary_json_path") else None,
                run,
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
        update_backtest(run_id, status="failed", error=str(exc), error_message=str(exc), exit_code=-1, finished_at=finished_at)
        update_fingerprint()
        update_task(task_id, status="failed", error=str(exc), finished_at=finished_at)
        _record_task_metric("backtest", "failed")
        _record_backtest_metric("failed")
        raise
    finally:
        release_scheduler_lease(lease.get("id"))


@celery_app.task(name="lean_web.optimize")
def optimize_task(task_id: str, optimization_id: str):
    task = get_task(task_id)
    parameters = task["parameters"]
    project = _task_project(task)
    if not project:
        raise LeanPlatformError("Optimization requires a project.")

    update_task(task_id, status="running", started_at=utc_now(), error=None)
    _update_table("optimization_runs", optimization_id, status="running", started_at=utc_now(), error=None)
    results = []
    try:
        fast_values = parameters.get("fastValues") or [10]
        slow_values = parameters.get("slowValues") or [30]
        for fast in fast_values:
            for slow in slow_values:
                if int(fast) >= int(slow):
                    continue
                child_params = {**parameters, "fast": int(fast), "slow": int(slow)}
                run_id = new_run_id(child_params["ticker"], child_params["start"], child_params["end"]) + f"-f{fast}-s{slow}"
                append_log(task_id, f"Running candidate fast={fast} slow={slow}")
                output = run_docker_backtest(
                    run_id,
                    child_params,
                    child_params.get("dockerImage", DEFAULT_DOCKER_IMAGE),
                    RUNS_DIR / run_id,
                    lambda line: append_log(task_id, line),
                    algorithm_path=Path(project["project_path"]) / project["main_file"],
                    algorithm_class=project["algorithm_class"],
                    language=project["language"],
                    project_dir=Path(project["project_path"]),
                )
                if output["exit_code"] != 0 or not output["result_json_path"]:
                    raise LeanPlatformError(f"Candidate fast={fast} slow={slow} did not produce a result JSON.")
                results.append({
                    "runId": run_id,
                    "fast": fast,
                    "slow": slow,
                    "statistics": output["statistics"],
                    "resultJson": output["result_json_path"],
                })
        _update_table(
            "optimization_runs",
            optimization_id,
            status="success",
            result_json={"candidates": results},
            finished_at=utc_now(),
        )
        update_task(task_id, status="success", artifacts_json=[], finished_at=utc_now())
        _record_task_metric("optimization", "success")
        return {"status": "success", "optimization_id": optimization_id}
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        _update_table("optimization_runs", optimization_id, status="failed", error=str(exc), finished_at=utc_now())
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        _record_task_metric("optimization", "failed")
        raise


@celery_app.task(name="lean_web.start_research")
def start_research_task(task_id: str, session_id: str):
    task = get_task(task_id)
    project = _task_project(task)
    if not project:
        raise LeanPlatformError("Research requires a project.")
    port = int(task["parameters"].get("port", 8888))
    update_task(task_id, status="running", started_at=utc_now())
    _update_table("research_sessions", session_id, status="running", started_at=utc_now())
    try:
        output = run_detached_research(
            session_id,
            Path(project["project_path"]),
            port,
            lambda line: append_log(task_id, line),
        )
        _update_table(
            "research_sessions",
            session_id,
            status="success",
            container_id=output["container_id"],
            url=output["url"],
            finished_at=utc_now(),
        )
        update_task(task_id, status="success", artifacts_json=[output["url"]], finished_at=utc_now())
        _record_task_metric("research", "success")
        return output
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        _update_table("research_sessions", session_id, status="failed", error=str(exc), finished_at=utc_now())
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
