import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .common import dispatch_task
from ..core.config import DEFAULT_DOCKER_IMAGE, RUNS_DIR
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..lean_engine.config import validate_backtest_parameters
from ..lean_engine.errors import LeanPlatformError
from ..services.projects import get_project
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
    fastValues: list[int] = Field(default_factory=lambda: [5, 10, 15])
    slowValues: list[int] = Field(default_factory=lambda: [20, 30, 50])
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
        base = validate_backtest_parameters({
            "ticker": request.symbol,
            "assetClass": request.assetClass,
            "market": request.market,
            "venue": request.venue,
            "resolution": request.resolution,
            "dataType": request.dataType,
            "start": request.start,
            "end": request.end,
            "fast": min(request.fastValues or [10]),
            "slow": max(request.slowValues or [30]),
            "cash": request.cash,
        })
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    optimization_id = str(uuid.uuid4())
    parameters = {
        **base,
        "fastValues": request.fastValues,
        "slowValues": request.slowValues,
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
