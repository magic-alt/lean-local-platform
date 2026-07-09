from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from ..core.config import ALGORITHM_PATH, DEFAULT_DOCKER_IMAGE, RUNS_DIR
from ..db import db, json_dump, utc_now
from ..domain.backtest_job import CANCELLED, CREATED, FAILED, is_terminal
from ..lean_engine.config import validate_backtest_parameters
from ..lean_engine.errors import LeanPlatformError
from ..lean_engine.ids import new_run_id
from ..repositories.backtest_repository import get_backtest, list_backtests, update_backtest
from ..runners.docker_runner import DockerRunner
from .projects import get_project
from .ashare_multisource import quality_gate_range
from .ashare_repository import assert_ashare_ready, assert_benchmark_ready, data_coverage
from .data_provider_manager import DATA_PROVIDER_MANAGER
from .backtest_validation import build_backtest_validation, build_experiment_record
from .experiments import record_experiment_versions
from .run_fingerprint import build_run_fingerprint
from .source_gate import apply_source_context, resolve_source_context
from .tasks import append_log, create_task, get_task, update_task
from .trading_config import merge_ashare_trading_config


def create_backtest_job(request_data: dict[str, Any]) -> dict[str, Any]:
    template_parameters = dict(request_data.get("parameters") or {})
    if request_data.get("fast") is not None:
        template_parameters["fast"] = request_data["fast"]
    if request_data.get("slow") is not None:
        template_parameters["slow"] = request_data["slow"]
    for key, value in request_data.get("extra", {}).items():
        if key not in template_parameters:
            template_parameters[key] = value

    parameters = validate_backtest_parameters(
        {
            "ticker": request_data["symbol"],
            "assetClass": request_data.get("assetClass", "equity"),
            "market": request_data.get("market", "usa"),
            "venue": request_data.get("venue"),
            "resolution": request_data.get("resolution", "daily"),
            "dataType": request_data.get("dataType", "trade"),
            "start": request_data["start"],
            "end": request_data["end"],
            "cash": request_data.get("cash", 100000),
            **template_parameters,
        }
    )

    def _source_has_data(symbol: str, source: str) -> bool:
        adjust = str(parameters.get("adjust") or "raw")
        coverage = data_coverage(symbol, parameters["start"], parameters["end"], adjust=adjust, source=source)
        return max(int(coverage["bar_count"] or 0), int(coverage["market_bar_count"] or 0)) > 0

    def _resolve_request_source(requested: str, symbols_to_check: list[str]) -> str | None:
        chain = DATA_PROVIDER_MANAGER.chain(
            requested,
            market=parameters["market"],
            asset_class=parameters["assetClass"],
            start_date=parameters["start"],
            end_date=parameters["end"],
            strict=False,
        )
        if not chain:
            raise LeanPlatformError(f"No usable source chain for {requested}.")
        for source in chain:
            if all(_source_has_data(symbol, source) for symbol in symbols_to_check):
                return source
        return None

    is_china_equity = parameters.get("assetClass") == "equity" and (parameters.get("market") or parameters.get("venue")) == "china"
    preflight_source = parameters.get("source")
    if is_china_equity:
        explicit_source = (
            request_data.get("source")
            or request_data.get("providerSource")
            or request_data.get("provider")
            or request_data.get("parameters", {}).get("source")
        )
        requested_source = str(explicit_source).strip() if explicit_source is not None else None
        requested_context = None
        if requested_source:
            requested_context = resolve_source_context(
                parameters,
                source=requested_source,
                allow_research_source=bool(request_data.get("allowResearchSource") or parameters.get("allowResearchSource")),
                asset_class=str(parameters.get("assetClass") or "equity"),
                market=str(parameters.get("market") or "china"),
                venue=str(parameters.get("venue") or parameters.get("market") or "china"),
            )
            requested_source = requested_context["source"]
        else:
            parameters.pop("source", None)
            parameters.pop("providerSource", None)
        adjust = str(parameters.get("adjust") or "raw")
        parameters = merge_ashare_trading_config(parameters, request_data)
        benchmark_symbol = str(parameters.get("benchmarkSymbol") or "").upper()
        symbols_to_gate = [parameters["ticker"]]
        symbols_to_check = [parameters["ticker"]]
        preflight_source: str | None
        if requested_source:
            effective_source = _resolve_request_source(requested_source, symbols_to_check)
            if effective_source is None:
                raise LeanPlatformError(
                    f"A-share daily bars are missing for {parameters['ticker']} in {parameters['start']} -> {parameters['end']} "
                    f"and all fallback sources for requested source {requested_source}."
                )
            preflight_source = effective_source
            if effective_source == requested_source and requested_context is not None:
                parameters = apply_source_context(parameters, requested_context)
            elif effective_source != requested_source:
                effective_context = resolve_source_context(
                    parameters,
                    source=effective_source,
                    allow_research_source=bool(request_data.get("allowResearchSource") or parameters.get("allowResearchSource")),
                    asset_class=str(parameters.get("assetClass") or "equity"),
                    market=str(parameters.get("market") or "china"),
                    venue=str(parameters.get("venue") or parameters.get("market") or "china"),
                )
                parameters = apply_source_context(parameters, effective_context)
                parameters["sourceFallback"] = requested_source
        else:
            preflight_source = _resolve_request_source("auto", symbols_to_check)
            if preflight_source is None:
                raise LeanPlatformError(
                    f"A-share daily bars are missing for {parameters['ticker']} in {parameters['start']} -> {parameters['end']} "
                    f"for all available sources."
                )
        assert_ashare_ready(parameters["ticker"], parameters["start"], parameters["end"], adjust=adjust, source=preflight_source)
        assert_benchmark_ready(
            benchmark_symbol,
            parameters["start"],
            parameters["end"],
            asset_class=str(parameters.get("assetClass") or "equity"),
            market=str(parameters.get("market") or "china"),
            venue=str(parameters.get("venue") or parameters.get("market") or "china"),
            resolution=str(parameters.get("resolution") or "daily"),
            data_type=str(parameters.get("dataType") or "trade"),
            adjust=adjust,
            source=preflight_source,
        )
        if benchmark_symbol:
            symbols_to_gate.append(benchmark_symbol)
        for symbol in symbols_to_gate:
            gate = quality_gate_range(symbol, parameters["start"], parameters["end"])
            if not gate["passed"]:
                report_id = gate["blockingReports"][0].get("id") if gate["blockingReports"] else None
                detail = f"qa_failed:{report_id}" if report_id else "qa_failed"
                raise LeanPlatformError(f"A-share data QA critical gate blocked backtest for {symbol}: {detail}")
    parameters["initialCash"] = parameters["cash"]
    parameters["initial_cash"] = parameters["cash"]
    fingerprint_parameters = dict(parameters)
    if preflight_source:
        fingerprint_parameters["source"] = preflight_source
    project_id = request_data.get("projectId")
    if project_id:
        project = get_project(project_id)
        if project["language"] != "Python":
            raise LeanPlatformError("CSharp project execution is not enabled in this local web version yet.")

    docker_image = request_data.get("dockerImage") or DEFAULT_DOCKER_IMAGE
    parameters["dockerImage"] = docker_image
    run_id = new_run_id(parameters["ticker"], parameters["start"], parameters["end"])
    task = create_task("backtest", f"Backtest {parameters['ticker']}", parameters, project_id, run_id, status=CREATED)
    run_dir = RUNS_DIR / run_id
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    name = request_data.get("name") or f"{parameters['ticker']} {parameters['start']} -> {parameters['end']}"
    strategy_path = Path(project["project_path"]) / project["main_file"] if project_id else ALGORITHM_PATH
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


def create_failed_backtest_job(request_data: dict[str, Any], error: str) -> dict[str, Any]:
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
                 error_message, created_at, started_at, finished_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    update_backtest(job_id, status=FAILED, error=error, error_message=error, finished_at=now)


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
