import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .common import dispatch_task
from ..core.config import DEFAULT_DOCKER_IMAGE, RUNS_DIR
from ..core.errors import NotFoundError
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..lean_engine.config import validate_backtest_parameters
from ..lean_engine.errors import LeanPlatformError
from ..services.optimization import normalize_parameter_grid
from ..services.history_resources import delete_optimization
from ..services.projects import get_project
from ..services.strategies import list_templates
from ..services.tasks import create_task
from ..tasks.worker import optimize_task

router = APIRouter(prefix="/api/optimize", tags=["optimization"])


class OptimizationRequest(BaseModel):
    projectId: str
    symbol: str
    assetClass: str = "equity"
    market: str = "usa"
    venue: str | None = None
    resolution: str = "daily"
    dataType: str = "trade"
    start: str
    end: str
    cash: float = Field(default=100000, gt=0)
    parameters: dict[str, Any] = Field(default_factory=dict)
    parameterGrid: dict[str, Any] = Field(default_factory=dict)
    maxCandidates: int = Field(default=50, ge=1, le=200)
    fastValues: list[int] | None = None
    slowValues: list[int] | None = None
    dockerImage: str = DEFAULT_DOCKER_IMAGE


@router.get("")
def list_optimizations():
    with db() as connection:
        rows = connection.execute("select * from optimization_runs order by created_at desc").fetchall()
    return rows_to_dicts(rows)


@router.post("")
def create_optimization(request: OptimizationRequest):
    try:
        project = get_project(request.projectId)
        if project["language"] != "Python":
            raise LeanPlatformError("CSharp optimization is not enabled in this local web version yet.")
        parameter_grid = normalize_parameter_grid(
            request.parameterGrid,
            fast_values=request.fastValues,
            slow_values=request.slowValues,
            max_candidates=request.maxCandidates,
        )
        first_grid_values = {key: values[0] for key, values in parameter_grid.items()}
        project_parameters = dict((project.get("config") or {}).get("parameters") or {})
        base_parameters = {**project_parameters, **request.parameters, **first_grid_values}
        base = validate_backtest_parameters({
            "ticker": request.symbol,
            "assetClass": request.assetClass,
            "market": request.market,
            "venue": request.venue,
            "resolution": request.resolution,
            "dataType": request.dataType,
            "start": request.start,
            "end": request.end,
            "cash": request.cash,
            **base_parameters,
        })
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    optimization_id = str(uuid.uuid4())
    template_key = str((project.get("config") or {}).get("templateKey") or "")
    template = next((item for item in list_templates() if item["key"] == template_key), None)
    parameters = {
        **base,
        "baseParameters": {**project_parameters, **request.parameters},
        "parameterGrid": parameter_grid,
        "parameterSchema": template.get("parameters") if template else [],
        "maxCandidates": request.maxCandidates,
        "dockerImage": request.dockerImage,
    }
    task = create_task("optimization", f"Optimize {base['ticker']}", parameters, request.projectId, optimization_id)
    with db() as connection:
        connection.execute(
            """
            insert into optimization_runs
                (id, task_id, project_id, status, parameters_json, results_dir, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                optimization_id,
                task["id"],
                request.projectId,
                "queued",
                json_dump(parameters),
                str(RUNS_DIR / f"optimization-{optimization_id}"),
                utc_now(),
            ),
        )
    dispatch_task(optimize_task.s(task["id"], optimization_id), task["id"])
    return detail(optimization_id)


@router.get("/{optimization_id}")
def detail(optimization_id: str):
    with db() as connection:
        row = connection.execute("select * from optimization_runs where id = ?", (optimization_id,)).fetchone()
    item = row_to_dict(row)
    if item is None:
        raise HTTPException(status_code=404, detail="Optimization run not found.")
    return item


@router.delete("/{optimization_id}")
def delete(optimization_id: str):
    try:
        return delete_optimization(optimization_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
