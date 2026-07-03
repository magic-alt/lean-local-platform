from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from .common import dispatch_task
from ..core.config import DEFAULT_DOCKER_IMAGE, RUNS_DIR
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..lean import LeanPlatformError, extract_chart_data, new_run_id, validate_backtest_parameters
from ..services.projects import get_project
from ..services.tasks import create_task, get_task, task_logs
from ..tasks.worker import run_backtest_task

router = APIRouter(prefix="/api/backtests", tags=["backtests"])


class BacktestRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    symbol: str
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
    projectId: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


def _with_artifacts(run: dict[str, Any]) -> dict[str, Any]:
    path = Path(run["results_dir"])
    run["artifacts"] = sorted(child.name for child in path.iterdir() if child.is_file()) if path.exists() else []
    return run


@router.get("")
def backtests():
    with db() as connection:
        rows = connection.execute("select * from backtest_runs order by created_at desc").fetchall()
    return rows_to_dicts(rows)


@router.post("")
def create_backtest(request: BacktestRequest):
    try:
        template_parameters = dict(request.parameters or {})
        if request.fast is not None:
            template_parameters["fast"] = request.fast
        if request.slow is not None:
            template_parameters["slow"] = request.slow
        for key, value in (request.model_extra or {}).items():
            if key not in template_parameters:
                template_parameters[key] = value
        parameters = validate_backtest_parameters(
            {
                "ticker": request.symbol,
                "assetClass": request.assetClass,
                "market": request.market,
                "venue": request.venue,
                "resolution": request.resolution,
                "dataType": request.dataType,
                "start": request.start,
                "end": request.end,
                "cash": request.cash,
                **template_parameters,
            }
        )
        if request.projectId:
            project = get_project(request.projectId)
            if project["language"] != "Python":
                raise LeanPlatformError("CSharp project execution is not enabled in this local web version yet.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parameters["dockerImage"] = request.dockerImage
    run_id = new_run_id(parameters["ticker"], parameters["start"], parameters["end"])
    task = create_task("backtest", f"Backtest {parameters['ticker']}", parameters, request.projectId, run_id)
    run_dir = RUNS_DIR / run_id
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    with db() as connection:
        connection.execute(
            """
            insert into backtest_runs
                (id, task_id, project_id, symbol, asset_class, venue, resolution, data_type, parameters_json, status, docker_image, results_dir, log_path, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                task["id"],
                request.projectId,
                parameters["ticker"],
                parameters.get("assetClass", "equity"),
                parameters.get("venue") or parameters.get("market"),
                parameters.get("resolution", "daily"),
                parameters.get("dataType", "trade"),
                json_dump(parameters),
                "queued",
                request.dockerImage,
                str(results_dir),
                task["log_path"],
                utc_now(),
            ),
        )
    dispatch_task(run_backtest_task.s(task["id"], run_id), task["id"])
    return detail(run_id)


@router.get("/{run_id}")
def detail(run_id: str):
    with db() as connection:
        row = connection.execute("select * from backtest_runs where id = ?", (run_id,)).fetchone()
    run = row_to_dict(row)
    if run is None:
        raise HTTPException(status_code=404, detail="Backtest run not found.")
    return _with_artifacts(run)


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
    result_path = run.get("result_json_path")
    if not result_path or not Path(result_path).exists():
        raise HTTPException(status_code=404, detail="Result JSON not found.")
    parameters = run.get("parameters") or {}
    return extract_chart_data(
        Path(result_path),
        symbol=run.get("symbol"),
        market=parameters.get("market"),
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
    path = Path(run["results_dir"]) / name
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")
    return FileResponse(path)
