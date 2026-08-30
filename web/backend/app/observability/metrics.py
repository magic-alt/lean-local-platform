from __future__ import annotations

import time
import os
import shutil
from typing import Callable

from fastapi import Request, Response

try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
except Exception:  # pragma: no cover - allows the app to boot before optional deps are installed.
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"
    Counter = Gauge = Histogram = None  # type: ignore[assignment]
    generate_latest = None  # type: ignore[assignment]


def _metric(factory, *args, **kwargs):
    if factory is None:
        return None
    return factory(*args, **kwargs)


API_REQUESTS = _metric(
    Counter,
    "lean_api_requests_total",
    "HTTP requests handled by the LEAN web API.",
    ["method", "path", "status"],
)
API_LATENCY = _metric(
    Histogram,
    "lean_api_request_duration_seconds",
    "HTTP request latency for the LEAN web API.",
    ["method", "path"],
)
DEPENDENCY_UP = _metric(
    Gauge,
    "lean_dependency_up",
    "Dependency health, where 1 is reachable and 0 is unavailable.",
    ["service"],
)
TASK_STATUS = _metric(
    Gauge,
    "lean_tasks_status_total",
    "Task count grouped by task kind and status from the runtime database.",
    ["kind", "status"],
)
BACKTEST_STATUS = _metric(
    Gauge,
    "lean_backtests_status_total",
    "Backtest run count grouped by status from the runtime database.",
    ["status"],
)
DATA_ASSETS_TOTAL = _metric(Gauge, "lean_data_assets_total", "Number of imported data assets indexed in the runtime database.")
CELERY_QUEUE_DEPTH = _metric(
    Gauge,
    "lean_celery_queue_depth",
    "Pending Celery messages by queue.",
    ["queue"],
)
DATABASE_CONNECTIONS = _metric(
    Gauge,
    "lean_database_connections",
    "Current database connections observed by the platform.",
)
FILESYSTEM_FREE_BYTES = _metric(
    Gauge,
    "lean_filesystem_free_bytes",
    "Free capacity on critical local storage roots.",
    ["path"],
)


async def metrics_middleware(request: Request, call_next: Callable) -> Response:
    start = time.perf_counter()
    status = 500
    response: Response | None = None
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", request.url.path)
        elapsed = time.perf_counter() - start
        if API_REQUESTS is not None:
            API_REQUESTS.labels(request.method, path, str(status)).inc()
        if API_LATENCY is not None:
            API_LATENCY.labels(request.method, path).observe(elapsed)


def set_dependency_status(service: str, ok: bool) -> None:
    if DEPENDENCY_UP is not None:
        DEPENDENCY_UP.labels(service).set(1 if ok else 0)


def refresh_runtime_metrics() -> None:
    if TASK_STATUS is None or BACKTEST_STATUS is None or DATA_ASSETS_TOTAL is None:
        return
    try:
        from ..db import connect

        connection = connect()
        try:
            for row in connection.execute("select kind, status, count(*) as count from tasks group by kind, status"):
                TASK_STATUS.labels(row["kind"], row["status"]).set(row["count"])
            for row in connection.execute("select status, count(*) as count from backtest_runs group by status"):
                BACKTEST_STATUS.labels(row["status"]).set(row["count"])
            row = connection.execute("select count(*) as count from data_assets").fetchone()
            DATA_ASSETS_TOTAL.set(row["count"] if row else 0)
            try:
                from ..db import database_backend

                if database_backend() == "postgresql":
                    database_row = connection.execute(
                        "select count(*) as count from pg_stat_activity where datname=current_database()"
                    ).fetchone()
                    if database_row and DATABASE_CONNECTIONS is not None:
                        DATABASE_CONNECTIONS.set(float(database_row["count"]))
            except Exception:
                pass
        finally:
            connection.close()
    except Exception:
        pass
    if FILESYSTEM_FREE_BYTES is not None:
        from ..core.config import DATA_DIR, RUNTIME_DIR

        for path in dict.fromkeys(
            str(item) for item in (os.environ.get("LEAN_DATA_DIR") or DATA_DIR, os.environ.get("LEAN_RUNTIME_DIR") or RUNTIME_DIR)
        ):
            try:
                FILESYSTEM_FREE_BYTES.labels(path).set(shutil.disk_usage(path).free)
            except OSError:
                continue
    if CELERY_QUEUE_DEPTH is None:
        return
    try:
        from ..services.broker import queue_depths

        for queue, depth in queue_depths().items():
            CELERY_QUEUE_DEPTH.labels(queue).set(depth)
    except Exception:
        pass


def metrics_response() -> Response:
    refresh_runtime_metrics()
    if generate_latest is None:
        return Response("# prometheus_client is not installed\n", media_type=CONTENT_TYPE_LATEST)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
