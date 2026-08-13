from __future__ import annotations

import uuid
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts
from ..domain.backtest_job import duration_seconds, normalize_status


BACKTEST_UPDATE_COLUMNS = {
    "task_id",
    "project_id",
    "name",
    "symbol",
    "asset_class",
    "venue",
    "resolution",
    "data_type",
    "parameters_json",
    "status",
    "docker_image",
    "container_name",
    "work_dir",
    "results_dir",
    "result_json_path",
    "summary_json_path",
    "report_html_path",
    "log_path",
    "statistics_json",
    "exit_code",
    "error",
    "error_message",
    "created_at",
    "queued_at",
    "started_at",
    "finished_at",
    "duration_seconds",
    "fingerprint_json",
    "validation_json",
    "experiment_json",
    "failure_json",
    "dataset_release_id",
    "reproducibility_certificate_id",
    "trust_status",
    "trust_reason",
    "trust_evaluated_at",
}


def list_backtests(filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    clauses: list[str] = []
    values: list[Any] = []
    if filters.get("name"):
        clauses.append("name like ?")
        values.append(f"%{str(filters['name']).strip()}%")
    if filters.get("status"):
        clauses.append("status = ?")
        values.append(normalize_status(str(filters["status"])))
    if filters.get("project_id"):
        clauses.append("project_id = ?")
        values.append(filters["project_id"])
    if filters.get("symbol"):
        clauses.append("symbol = ?")
        values.append(str(filters["symbol"]).upper())
    if filters.get("market"):
        clauses.append("venue = ?")
        values.append(str(filters["market"]).lower())
    if filters.get("from_date"):
        clauses.append("created_at >= ?")
        values.append(filters["from_date"])
    if filters.get("to_date"):
        clauses.append("created_at <= ?")
        values.append(filters["to_date"])
    sql = """
        select id,task_id,project_id,name,symbol,asset_class,venue,resolution,data_type,
               parameters_json,status,docker_image,exit_code,error,error_message,failure_json,
               created_at,queued_at,started_at,finished_at,duration_seconds,validation_json,
               dataset_release_id,reproducibility_certificate_id,trust_status,trust_reason,
               trust_evaluated_at
        from backtest_runs
    """
    if clauses:
        sql += " where " + " and ".join(clauses)
    sql += " order by created_at desc"
    limit = filters.get("limit")
    offset = filters.get("offset")
    if limit is not None:
        sql += " limit ? offset ?"
        values.extend([max(1, int(limit)), max(0, int(offset or 0))])
    with db() as connection:
        rows = connection.execute(sql, values).fetchall()
    items = rows_to_dicts(rows)
    allowed_parameters = {
        "ticker", "symbol", "assetClass", "market", "venue", "resolution", "dataType",
        "start", "end", "cash", "initialCash", "benchmarkSymbol", "strategyTemplateKey",
    }
    for item in items:
        parameters = item.get("parameters") or {}
        item["parameters"] = {
            key: value for key, value in parameters.items()
            if key in allowed_parameters and not isinstance(value, (dict, list))
        }
        validation = item.get("validation") or {}
        item["validation"] = {
            key: validation.get(key) for key in ("schemaVersion", "passed", "severity")
            if key in validation
        }
    return items


def count_backtests(filters: dict[str, Any] | None = None) -> int:
    filters = filters or {}
    clauses: list[str] = []
    values: list[Any] = []
    for key, column, value in (
        ("name", "name like ?", f"%{str(filters['name']).strip()}%" if filters.get("name") else None),
        ("status", "status = ?", normalize_status(str(filters["status"])) if filters.get("status") else None),
        ("project_id", "project_id = ?", filters.get("project_id")),
        ("symbol", "symbol = ?", str(filters["symbol"]).upper() if filters.get("symbol") else None),
        ("market", "venue = ?", str(filters["market"]).lower() if filters.get("market") else None),
        ("from_date", "created_at >= ?", filters.get("from_date")),
        ("to_date", "created_at <= ?", filters.get("to_date")),
    ):
        if value is not None:
            clauses.append(column)
            values.append(value)
    sql = "select count(*) as count from backtest_runs"
    if clauses:
        sql += " where " + " and ".join(clauses)
    with db() as connection:
        row = connection.execute(sql, values).fetchone()
    return int(row["count"] if row else 0)


def get_backtest(job_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from backtest_runs where id = ?", (job_id,)).fetchone()
    return row_to_dict(row)


def update_backtest(job_id: str, **fields: Any) -> None:
    clean = {key: value for key, value in fields.items() if key in BACKTEST_UPDATE_COLUMNS}
    if not clean:
        return
    if "status" in clean:
        clean["status"] = normalize_status(str(clean["status"]))
    if "finished_at" in clean and "duration_seconds" not in clean:
        current = get_backtest(job_id)
        if current:
            clean["duration_seconds"] = duration_seconds(current.get("started_at"), clean.get("finished_at"))
    assignments = ", ".join(f"{key} = ?" for key in clean)
    values = [json_dump(value) if key.endswith("_json") else value for key, value in clean.items()]
    values.append(job_id)
    with db() as connection:
        connection.execute(f"update backtest_runs set {assignments} where id = ?", values)


def get_result(job_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from backtest_results where job_id = ?", (job_id,)).fetchone()
    return row_to_dict(row)


def save_result(job_id: str, payload: dict[str, Any], created_at: str) -> dict[str, Any]:
    result_id = payload.get("id") or str(uuid.uuid4())
    values = {
        "id": result_id,
        "job_id": job_id,
        "summary_metrics_json": payload.get("summary_metrics") or {},
        "equity_curve_json": payload.get("equity_curve") or [],
        "drawdown_curve_json": payload.get("drawdown_curve") or [],
        "orders_json": payload.get("orders") or [],
        "trades_json": payload.get("trades") or [],
        "holdings_json": payload.get("holdings") or [],
        "statistics_json": payload.get("statistics") or {},
        "performance_json": payload.get("performance") or {},
        "raw_result_path": payload.get("raw_result_path"),
        "raw_result_object_id": payload.get("raw_result_object_id"),
        "summary_object_id": payload.get("summary_object_id"),
        "created_at": created_at,
    }
    with db() as connection:
        connection.execute(
            """
            insert into backtest_results
                (id, job_id, summary_metrics_json, equity_curve_json, drawdown_curve_json,
                 orders_json, trades_json, holdings_json, statistics_json, performance_json, raw_result_path,
                 raw_result_object_id, summary_object_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(job_id) do update set
                summary_metrics_json = excluded.summary_metrics_json,
                equity_curve_json = excluded.equity_curve_json,
                drawdown_curve_json = excluded.drawdown_curve_json,
                orders_json = excluded.orders_json,
                trades_json = excluded.trades_json,
                holdings_json = excluded.holdings_json,
                statistics_json = excluded.statistics_json,
                performance_json = excluded.performance_json,
                raw_result_path = excluded.raw_result_path,
                raw_result_object_id = excluded.raw_result_object_id,
                summary_object_id = excluded.summary_object_id,
                created_at = excluded.created_at
            """,
            (
                values["id"],
                values["job_id"],
                json_dump(values["summary_metrics_json"]),
                json_dump(values["equity_curve_json"]),
                json_dump(values["drawdown_curve_json"]),
                json_dump(values["orders_json"]),
                json_dump(values["trades_json"]),
                json_dump(values["holdings_json"]),
                json_dump(values["statistics_json"]),
                json_dump(values["performance_json"]),
                values["raw_result_path"],
                values["raw_result_object_id"],
                values["summary_object_id"],
                values["created_at"],
            ),
        )
    return get_result(job_id) or {}
