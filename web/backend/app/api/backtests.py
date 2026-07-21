from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .common import dispatch_task
from ..core.config import DEFAULT_DOCKER_IMAGE
from ..core.errors import NotFoundError
from ..lean_engine.results import extract_chart_data, infer_holdings_from_orders
from ..repositories.backtest_repository import get_backtest
from ..services.backtest_service import (
    backtest_status,
    cancel_backtest,
    create_failed_backtest_job,
    create_backtest_job,
    fail_backtest_queue,
    mark_backtest_queued,
    query_backtests,
)
from ..services.backtest_preflight import prepare_backtest_request
from ..services.experiments import get_experiment_versions
from ..services.history_resources import delete_backtest
from ..services.result_service import result_for_job
from ..services.run_paths import run_directory, run_file
from ..services.projects import get_project
from ..services.strategy_admission import admission_for_run
from ..services.tasks import task_logs
from ..tasks.worker import run_backtest_task

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
    name: str | None = None
    assetClass: str = "equity"
    market: str = "usa"
    venue: str | None = None
    resolution: str = "daily"
    dataType: str = "trade"
    start: str
    end: str
    fast: int | None = Field(default=None, ge=1)
    slow: int | None = Field(default=None, ge=1)
    cash: float = Field(default=100000, gt=0)
    dockerImage: str = DEFAULT_DOCKER_IMAGE
    projectId: str
    parameters: dict[str, Any] = Field(default_factory=dict)


def _with_artifacts(run: dict[str, Any]) -> dict[str, Any]:
    run["job_id"] = run["id"]
    path = run_directory(run["id"], run.get("results_dir"), relative="results")
    run["artifacts"] = sorted(child.name for child in path.iterdir() if child.is_file()) if path.exists() else []
    return run


@router.get("")
def backtests(
    status: str | None = None,
    projectId: str | None = None,
    symbol: str | None = None,
    fromDate: str | None = None,
    toDate: str | None = None,
):
    return query_backtests(
        {
            "status": status,
            "project_id": projectId,
            "symbol": symbol,
            "from_date": fromDate,
            "to_date": toDate,
        }
    )


@router.post("")
def create_backtest(request: BacktestRequest):
    get_project(request.projectId)
    payload = request.model_dump()
    payload["extra"] = request.model_extra or {}
    try:
        run = create_backtest_job(payload)
    except Exception as exc:
        run = create_failed_backtest_job(payload, str(exc))
        return detail(run["id"])

    try:
        dispatch_task(run_backtest_task.s(run["task_id"], run["id"]), run["task_id"])
        mark_backtest_queued(run["id"])
    except HTTPException as exc:
        fail_backtest_queue(run["id"], str(exc.detail))
        raise
    return detail(run["id"])


@router.post("/preflight")
def preflight_backtest(request: BacktestRequest):
    get_project(request.projectId)
    payload = request.model_dump()
    payload["extra"] = request.model_extra or {}
    try:
        return prepare_backtest_request(payload, repair=True)["preflight"]
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "stage": "preflight",
                "code": str(exc).split(":", 1)[0].lower().replace(" ", "_"),
                "message": str(exc),
                "retryable": True,
            },
        ) from exc


@router.get("/{run_id}")
def detail(run_id: str):
    run = get_backtest(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    return _with_artifacts(run)


@router.delete("/{run_id}")
def delete(run_id: str):
    try:
        return delete_backtest(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{run_id}/status")
def status(run_id: str):
    try:
        return backtest_status(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Backtest run not found.") from exc


@router.get("/{run_id}/result")
def result(run_id: str):
    run = detail(run_id)
    result_record = result_for_job(run_id)
    if not result_record:
        raise HTTPException(status_code=404, detail="Backtest result not found.")
    orders = result_record.get("orders")
    if not result_record.get("holdings"):
        fallback_orders = orders if isinstance(orders, list) else []
        price_series: list[dict[str, Any]] = []
        if not isinstance(fallback_orders, list) or not fallback_orders:
            result_path = run.get("result_json_path")
            if result_path:
                try:
                    resolved_result_path = run_file(
                        run_id,
                        result_path,
                        f"results/{run_id}.json",
                    )
                    chart_data = extract_chart_data(
                        resolved_result_path,
                        symbol=run.get("symbol"),
                        benchmark_symbol=(run.get("parameters") or {}).get("benchmarkSymbol"),
                        market=(run.get("parameters") or {}).get("market"),
                        benchmark_market=(run.get("parameters") or {}).get("benchmarkMarket"),
                        start=(run.get("parameters") or {}).get("start"),
                        end=(run.get("parameters") or {}).get("end"),
                        asset_class=(run.get("parameters") or {}).get("assetClass"),
                        venue=(run.get("parameters") or {}).get("venue"),
                        resolution=(run.get("parameters") or {}).get("resolution"),
                        data_type=(run.get("parameters") or {}).get("dataType"),
                    )
                    fallback_orders = chart_data.get("orders") or []
                    series = chart_data.get("series") or {}
                    price_series = series.get("price") or []
                except Exception:
                    fallback_orders = []
        try:
            if fallback_orders:
                result_record["holdings"] = infer_holdings_from_orders(fallback_orders, price_series)
            elif not result_record.get("holdings"):
                result_record["holdings"] = []
        except Exception:
            result_record["holdings"] = []
    if not result_record.get("holdings"):
        result_record["holdings"] = []
    return {"job": run, "result": result_record}


@router.get("/{run_id}/results")
def results(run_id: str):
    return result(run_id)


@router.get("/{run_id}/validation")
def validation(run_id: str):
    run = detail(run_id)
    return {
        "job_id": run["id"],
        "validation": run.get("validation"),
        "experiment": run.get("experiment"),
        "fingerprint": run.get("fingerprint"),
    }


@router.get("/{run_id}/admission")
def admission(run_id: str, profile: str = "institutional"):
    try:
        return admission_for_run(run_id, profile)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{run_id}/versions")
def versions(run_id: str):
    run = detail(run_id)
    version_record = get_experiment_versions(run_id)
    if version_record is None:
        raise HTTPException(status_code=404, detail="Experiment versions not found.")
    return {"job_id": run["id"], **version_record}


@router.post("/{run_id}/cancel")
def cancel(run_id: str):
    try:
        return _with_artifacts(cancel_backtest(run_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Backtest run not found.") from exc


@router.get("/{run_id}/logs")
def logs(run_id: str):
    run = detail(run_id)
    if run.get("task_id"):
        return {"logs": task_logs(run["task_id"])}
    path = Path(run.get("log_path") or "")
    return {"logs": path.read_text(encoding="utf-8", errors="replace")[-120000:] if path.exists() else ""}


@router.get("/{run_id}/chart-data")
def chart_data(run_id: str):
    run = detail(run_id)
    result_path = run_file(
        run_id,
        run.get("result_json_path"),
        f"results/{run_id}.json",
    )
    if not result_path.is_file():
        raise HTTPException(status_code=404, detail="Result JSON not found.")
    parameters = run.get("parameters") or {}
    return extract_chart_data(
        result_path,
        symbol=run.get("symbol"),
        benchmark_symbol=parameters.get("benchmarkSymbol"),
        market=parameters.get("market"),
        benchmark_market=parameters.get("benchmarkMarket"),
        start=parameters.get("start"),
        end=parameters.get("end"),
        asset_class=parameters.get("assetClass"),
        venue=parameters.get("venue"),
        resolution=parameters.get("resolution"),
        data_type=parameters.get("dataType"),
    )


@router.get("/{run_id}/artifacts/{name}")
def artifact(run_id: str, name: str):
    run = detail(run_id)
    if "/" in name or "\\" in name or name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid artifact name.")
    results_dir = run_directory(run_id, run.get("results_dir"), relative="results")
    path = results_dir / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return FileResponse(path)
