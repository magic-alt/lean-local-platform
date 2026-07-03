import json
from pathlib import Path

from .celery_app import celery_app
from ..core.config import DEFAULT_DOCKER_IMAGE, REPORTS_DIR, RUNS_DIR
from ..db import db, json_dump, row_to_dict, utc_now
from ..lean import (
    LeanPlatformError,
    extract_statistics,
    new_run_id,
    render_report,
    run_detached_research,
    run_docker_backtest,
)
from ..services.data import fetch_and_import_symbol
from ..services.projects import get_project
from ..services.tasks import append_log, get_task, update_task


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
        status = "succeeded" if results and not failures else "failed" if not results else "succeeded"
        error = None if not failures else f"{len(failures)} symbol(s) failed."
        update_task(
            task_id,
            status=status,
            artifacts_json=[item["lean_file"] for item in results],
            error=error,
            finished_at=utc_now(),
        )
        return {"status": status, "results": results, "failures": failures}
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        raise


@celery_app.task(name="lean_web.run_backtest")
def run_backtest_task(task_id: str, run_id: str):
    task = get_task(task_id)
    parameters = task["parameters"]
    project = _task_project(task)
    append_log(task_id, f"Task {task_id} started.")
    update_task(task_id, status="running", started_at=utc_now(), error=None)
    _update_table("backtest_runs", run_id, status="running", started_at=utc_now(), error=None)

    try:
        run_dir = RUNS_DIR / run_id
        if project:
            project_path = Path(project["project_path"])
            output = run_docker_backtest(
                run_id,
                parameters,
                parameters.get("dockerImage", DEFAULT_DOCKER_IMAGE),
                run_dir,
                lambda line: append_log(task_id, line),
                algorithm_path=project_path / project["main_file"],
                algorithm_class=project["algorithm_class"],
                language=project["language"],
                project_dir=project_path,
            )
        else:
            output = run_docker_backtest(
                run_id,
                parameters,
                parameters.get("dockerImage", DEFAULT_DOCKER_IMAGE),
                run_dir,
                lambda line: append_log(task_id, line),
            )

        status = "succeeded" if output["exit_code"] == 0 and output["result_json_path"] else "failed"
        error = None if status == "succeeded" else "Docker run failed or did not produce result JSON."
        _update_table(
            "backtest_runs",
            run_id,
            status=status,
            result_json_path=output["result_json_path"],
            summary_json_path=output["summary_json_path"],
            report_html_path=output["report_html_path"],
            statistics_json=output["statistics"],
            exit_code=output["exit_code"],
            error=error,
            finished_at=utc_now(),
        )
        update_task(
            task_id,
            status=status,
            artifacts_json=[
                path
                for path in (output["result_json_path"], output["summary_json_path"], output["report_html_path"])
                if path
            ],
            error=error,
            finished_at=utc_now(),
        )
        return {"status": status, "run_id": run_id}
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        _update_table("backtest_runs", run_id, status="failed", error=str(exc), exit_code=-1, finished_at=utc_now())
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        raise


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
            status="succeeded",
            result_json={"candidates": results},
            finished_at=utc_now(),
        )
        update_task(task_id, status="succeeded", artifacts_json=[], finished_at=utc_now())
        return {"status": "succeeded", "optimization_id": optimization_id}
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        _update_table("optimization_runs", optimization_id, status="failed", error=str(exc), finished_at=utc_now())
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
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
            status="succeeded",
            container_id=output["container_id"],
            url=output["url"],
            finished_at=utc_now(),
        )
        update_task(task_id, status="succeeded", artifacts_json=[output["url"]], finished_at=utc_now())
        return output
    except Exception as exc:
        append_log(task_id, f"error: {exc}")
        _update_table("research_sessions", session_id, status="failed", error=str(exc), finished_at=utc_now())
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
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
        _update_table("reports", report_id, status="succeeded", report_path=str(report_path), finished_at=utc_now())
        update_task(task_id, status="succeeded", artifacts_json=[str(report_path)], finished_at=utc_now())
        return {"reportPath": str(report_path), "statistics": extract_statistics(Path(run["result_json_path"]))}
    except Exception as exc:
        _update_table("reports", report_id, status="failed", error=str(exc), finished_at=utc_now())
        update_task(task_id, status="failed", error=str(exc), finished_at=utc_now())
        raise
