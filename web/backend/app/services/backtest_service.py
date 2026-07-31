from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from typing import Any

from ..core.config import DEFAULT_DOCKER_IMAGE, RUNS_DIR
from ..db import db, json_dump, utc_now
from ..domain.backtest_job import CANCELLED, CREATED, FAILED, is_terminal
from ..lean_engine.errors import LeanPlatformError
from ..lean_engine.docker import validate_lean_docker_image
from ..lean_engine.ids import new_run_id
from ..repositories.backtest_repository import get_backtest, list_backtests, update_backtest
from ..runners.docker_runner import DockerRunner
from .projects import get_project
from .backtest_preflight import prepare_backtest_request
from .backtest_validation import build_backtest_validation, build_experiment_record
from .experiments import record_experiment_versions
from .run_fingerprint import build_run_fingerprint
from .strategies import get_template
from .tasks import append_log, create_task, get_task, update_task


def failure_metadata(stage: str, error: str, *, retryable: bool = False, details: dict[str, Any] | None = None) -> dict[str, Any]:
    text = str(error or "Backtest failed.")
    code = text.split(":", 1)[0].strip().lower().replace(" ", "_")
    if not code or len(code) > 80:
        code = f"{stage}_failed"
    return {
        "stage": stage,
        "code": code,
        "message": text,
        "retryable": retryable,
        "details": details or {},
    }


PIT_INDEX_TEMPLATE_KEYS = {"ashare_index_screening", "ashare_trend_pullback_portfolio"}


def enrich_strategy_backtest_request(request_data: dict[str, Any]) -> dict[str, Any]:
    """Inject server-owned PIT inputs required by A-share index strategies."""
    project_id = str(request_data.get("projectId") or "").strip()
    if not project_id:
        raise LeanPlatformError("project_required: Select a project before starting a backtest.")
    project = get_project(project_id)
    project_config = project.get("config") or {}
    template_key = str(project_config.get("templateKey") or "").strip()
    if template_key not in PIT_INDEX_TEMPLATE_KEYS:
        return request_data

    parameters = dict(request_data.get("parameters") or {})
    if parameters.get("universeSchedule") and parameters.get("fundamentalSchedule"):
        return request_data

    from .experiment_batches import (
        INDEX_BENCHMARKS,
        _fundamental_schedule,
        _membership_schedule,
    )

    example_defaults = project_config.get("exampleDefaults") or {}
    universe_code = str(
        parameters.get("universeCode")
        or project_config.get("universeCode")
        or example_defaults.get("universeCode")
        or "CSI300"
    ).upper()
    if universe_code not in INDEX_BENCHMARKS:
        raise LeanPlatformError(
            "A-share index screening supports CSI300, CSI500, CSI1000 and STAR50."
        )
    start = str(request_data.get("start") or "")
    end = str(request_data.get("end") or "")
    schedule = _membership_schedule(universe_code, start, end)
    if not schedule:
        raise LeanPlatformError(
            f"No historical PIT schedule is available for {universe_code} in the selected range."
        )
    universe_symbols = sorted({str(row["symbol"]).upper() for row in schedule})
    fundamental_schedule = _fundamental_schedule(universe_symbols, start, end)
    model_variant = str(parameters.get("modelVariant") or "B").upper()
    if (template_key == "ashare_index_screening" or model_variant == "C") and not fundamental_schedule:
        raise LeanPlatformError(
            f"No point-in-time fundamentals are available for {universe_code} in the selected range. "
            "Sync daily_basic, income, balancesheet and fina_indicator before running this case."
        )
    benchmark = INDEX_BENCHMARKS[universe_code]
    enriched = dict(request_data)
    enriched["benchmarkSymbol"] = benchmark
    enriched["parameters"] = {
        **parameters,
        "benchmarkSymbol": benchmark,
        "universeCode": universe_code,
        "dynamicUniverse": True,
        "universeSchedule": json.dumps(
            schedule,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "universeSymbols": universe_symbols,
        "fundamentalSchedule": json.dumps(
            fundamental_schedule,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "fundamentalRecordCount": len(fundamental_schedule),
    }
    return enriched


def create_backtest_job(request_data: dict[str, Any]) -> dict[str, Any]:
    request_data = enrich_strategy_backtest_request(request_data)
    project_id = str(request_data.get("projectId") or "").strip()
    if not project_id:
        raise LeanPlatformError("project_required: Select a project before starting a backtest.")
    project = get_project(project_id)
    if project["language"] != "Python":
        raise LeanPlatformError("CSharp project execution is not enabled in this local web version yet.")

    project_config = project.get("config") or {}
    template_key = str(project_config.get("templateKey") or "").strip()
    try:
        template = get_template(template_key) if template_key else {}
    except ValueError:
        # Custom projects can outlive a file-backed template registration.
        template = {}
    required_market = str(template.get("requiredMarket") or "").lower()
    requested_market = str(
        request_data.get("market") or project_config.get("market") or ""
    ).lower()
    if required_market and requested_market != required_market:
        raise LeanPlatformError(
            f"strategy_template_market_mismatch:{template_key}:"
            f"required={required_market}:requested={requested_market or 'missing'}"
        )
    required_resolution = str(template.get("requiredResolution") or "").lower()
    requested_resolution = str(
        request_data.get("resolution") or project_config.get("resolution") or "daily"
    ).lower()
    if required_resolution and requested_resolution != required_resolution:
        raise LeanPlatformError(
            f"strategy_template_resolution_mismatch:{template_key}:"
            f"required={required_resolution}:requested={requested_resolution}"
        )

    prepared = prepare_backtest_request(request_data, repair=True)
    parameters = prepared["parameters"]
    preflight = prepared["preflight"]
    if template.get("requiresUniverseSchedule") and not parameters.get("universeSchedule"):
        raise LeanPlatformError(
            f"strategy_template_universe_schedule_required:{template_key}"
        )
    if template_key:
        parameters["strategyTemplateKey"] = template_key
        parameters["strategyMode"] = str(template.get("strategyMode") or "STANDARD")
        parameters["researchOnly"] = bool(template.get("researchOnly", False))
        parameters["tradable"] = bool(template.get("tradable", True))
        parameters["admissionEligible"] = bool(template.get("admissionEligible", True))
    if template_key == "ashare_trend_pullback_portfolio":
        parameters.setdefault("slippageModel", "participation_sqrt")
        parameters["ashareNextOpenFillModel"] = True
    parameters["initialCash"] = parameters["cash"]
    parameters["initial_cash"] = parameters["cash"]
    docker_image = validate_lean_docker_image(request_data.get("dockerImage") or DEFAULT_DOCKER_IMAGE)
    parameters["dockerImage"] = docker_image
    run_id = new_run_id(parameters["ticker"], parameters["start"], parameters["end"])
    run_dir = RUNS_DIR / run_id
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    if template_key == "ashare_trend_pullback_portfolio":
        from .ashare_trend_pullback import write_trend_pullback_snapshot

        snapshot = write_trend_pullback_snapshot(run_dir, parameters)
        parameters.update(
            {
                "trendPullbackInputFile": snapshot["containerPath"],
                "trendPullbackInputSha256": snapshot["sha256"],
                "trendPullbackInputSchemaVersion": snapshot["schemaVersion"],
                "trendPullbackInputCoverage": snapshot["coverage"],
            }
        )
    fingerprint_parameters = dict(parameters)
    fingerprint_parameters["preflight"] = preflight
    shared_snapshot = request_data.get("sharedStrategySnapshotDir")
    snapshot_dir = Path(shared_snapshot).resolve() if shared_snapshot else run_dir / "strategy"
    snapshot_source = request_data.get("strategySnapshotSourceDir")
    source_path = Path(snapshot_source).resolve() if snapshot_source else Path(project["project_path"]).resolve()
    if shared_snapshot:
        allowed_root = RUNS_DIR.resolve()
        if allowed_root not in snapshot_dir.parents or not snapshot_dir.is_dir():
            raise LeanPlatformError("Shared strategy snapshot must be a managed directory under runs.")
    else:
        if snapshot_source:
            allowed_root = RUNS_DIR.resolve()
            if source_path != allowed_root and allowed_root not in source_path.parents:
                raise LeanPlatformError("Paper strategy snapshot must be stored under the managed runs directory.")
            if not source_path.is_dir():
                raise LeanPlatformError("Paper strategy snapshot directory is missing.")
        shutil.copytree(source_path, snapshot_dir)
    parameters["strategySnapshotDir"] = str(snapshot_dir)
    parameters["strategySnapshotMainFile"] = (
        request_data.get("strategySnapshotMainFile") if snapshot_source else None
    ) or project["main_file"]
    parameters["strategySnapshotAlgorithmClass"] = (
        request_data.get("strategySnapshotAlgorithmClass") if snapshot_source else None
    ) or project["algorithm_class"]
    parameters["strategySnapshotLanguage"] = (
        request_data.get("strategySnapshotLanguage") if snapshot_source else None
    ) or project["language"]
    task = create_task("backtest", f"Backtest {parameters['ticker']}", parameters, project_id, run_id, status=CREATED)
    now = utc_now()
    name = request_data.get("name") or f"{parameters['ticker']} {parameters['start']} -> {parameters['end']}"
    strategy_path = Path(parameters["strategySnapshotDir"]) / str(parameters["strategySnapshotMainFile"])
    fingerprint = build_run_fingerprint(
        run_id=run_id,
        parameters=fingerprint_parameters,
        docker_image=docker_image,
        strategy_path=strategy_path,
        config_path=run_dir / "config.json",
    )
    validation = build_backtest_validation(fingerprint_parameters, fingerprint)
    experiment = build_experiment_record(
        run_id=run_id,
        parameters=fingerprint_parameters,
        fingerprint=fingerprint,
        project_id=project_id,
        strategy_path=str(strategy_path),
        validation=validation,
    )
    with db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id, task_id, project_id, name, symbol, asset_class, venue, resolution, data_type,
                 parameters_json, status, docker_image, container_name, work_dir, results_dir, log_path, created_at,
                 fingerprint_json, validation_json, experiment_json)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                task["id"],
                project_id,
                name,
                parameters["ticker"],
                parameters.get("assetClass", "equity"),
                parameters.get("venue") or parameters.get("market"),
                parameters.get("resolution", "daily"),
                parameters.get("dataType", "trade"),
                json_dump(parameters),
                CREATED,
                docker_image,
                f"lean-{run_id}"[:60],
                str(run_dir),
                str(results_dir),
                task["log_path"],
                now,
                json_dump(fingerprint),
                json_dump(validation),
                json_dump(experiment),
            ),
        )
    record_experiment_versions(
        run_id=run_id,
        project_id=project_id,
        fingerprint=fingerprint,
        validation=validation,
        experiment=experiment,
    )
    return get_backtest(run_id) or {}


def create_failed_backtest_job(
    request_data: dict[str, Any],
    error: str,
    *,
    stage: str = "preflight",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbol = str(request_data.get("symbol") or request_data.get("ticker") or "UNKNOWN").strip().upper()
    start = str(request_data.get("start") or "unknown-start")
    end = str(request_data.get("end") or "unknown-end")
    project_id = request_data.get("projectId")
    docker_image = request_data.get("dockerImage") or DEFAULT_DOCKER_IMAGE
    parameters = {
        "ticker": symbol,
        "assetClass": request_data.get("assetClass", "equity"),
        "market": request_data.get("market", "usa"),
        "venue": request_data.get("venue"),
        "resolution": request_data.get("resolution", "daily"),
        "dataType": request_data.get("dataType", "trade"),
        "start": start,
        "end": end,
        "cash": request_data.get("cash", 100000),
        **(request_data.get("parameters") or {}),
        **(request_data.get("extra") or {}),
    }
    run_symbol = re.sub(r"[^A-Za-z0-9]+", "", symbol) or "INVALID"
    run_id = new_run_id(run_symbol, start, end)
    task = create_task("backtest", f"Backtest {symbol}", parameters, project_id, run_id, status=FAILED)
    append_log(task["id"], f"Backtest preflight failed: {error}")
    run_dir = RUNS_DIR / run_id
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    name = request_data.get("name") or f"{symbol} {start} -> {end}"
    with db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id, task_id, project_id, name, symbol, asset_class, venue, resolution, data_type,
                 parameters_json, status, docker_image, container_name, work_dir, results_dir, log_path, error,
                 error_message, failure_json, created_at, started_at, finished_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                task["id"],
                project_id,
                name,
                symbol,
                parameters.get("assetClass", "equity"),
                parameters.get("venue") or parameters.get("market"),
                parameters.get("resolution", "daily"),
                parameters.get("dataType", "trade"),
                json_dump(parameters),
                FAILED,
                docker_image,
                f"lean-{run_id}"[:60],
                str(run_dir),
                str(results_dir),
                task["log_path"],
                error,
                error,
                json_dump(failure_metadata(stage, error, details=details)),
                now,
                now,
                now,
            ),
        )
    return get_backtest(run_id) or {}


def mark_backtest_queued(job_id: str) -> None:
    now = utc_now()
    update_backtest(job_id, status="queued", queued_at=now)


def fail_backtest_queue(job_id: str, error: str) -> None:
    now = utc_now()
    update_backtest(
        job_id,
        status=FAILED,
        error=error,
        error_message=error,
        failure_json=failure_metadata("queue", error, retryable=True),
        finished_at=now,
    )


def cancel_backtest(job_id: str) -> dict[str, Any]:
    run = get_backtest(job_id)
    if not run:
        raise KeyError("Backtest run not found.")
    if is_terminal(run.get("status")):
        return run
    if run.get("task_id"):
        try:
            task = get_task(run["task_id"])
            celery_task_id = task.get("celery_task_id")
            append_log(run["task_id"], "Cancellation requested by user.")
            if celery_task_id:
                from ..tasks.celery_app import celery_app

                celery_app.control.revoke(celery_task_id, terminate=True)
            update_task(run["task_id"], status=CANCELLED, error="Cancellation requested by user.", finished_at=utc_now())
        except Exception:
            pass
    if run.get("container_name"):
        try:
            DockerRunner.stop_container(str(run["container_name"]))
        except Exception:
            pass
    now = utc_now()
    update_backtest(
        job_id,
        status=CANCELLED,
        error="Cancellation requested by user.",
        error_message="Cancellation requested by user.",
        finished_at=now,
    )
    try:
        from .experiment_batches import reconcile_backtest

        reconcile_backtest(job_id)
    except Exception:
        pass
    return get_backtest(job_id) or run


def backtest_status(job_id: str) -> dict[str, Any]:
    run = get_backtest(job_id)
    if not run:
        raise KeyError("Backtest run not found.")
    return {
        "job_id": run["id"],
        "status": run["status"],
        "created_at": run.get("created_at"),
        "queued_at": run.get("queued_at"),
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "duration_seconds": run.get("duration_seconds"),
        "error": run.get("error_message") or run.get("error"),
    }


def query_backtests(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return list_backtests(filters)
