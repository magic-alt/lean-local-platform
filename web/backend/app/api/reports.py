import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from .common import dispatch_task
from ..db import db, row_to_dict, rows_to_dicts, utc_now
from ..core.errors import NotFoundError
from ..services.db_object_store import get_object, read_bytes
from ..services.report_export import csv_report, json_report, markdown_report, pdf_report, report_payload
from ..services.history_resources import delete_generated_report
from ..services.tasks import create_task
from ..tasks.worker import generate_report_task

router = APIRouter(prefix="/api/reports", tags=["reports"])

REPORT_FILE_CACHE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


class ReportRequest(BaseModel):
    runId: str


def _stored_object(object_id: str | None) -> dict[str, Any] | None:
    if not object_id:
        return None
    with db() as connection:
        row = connection.execute(
            """
            select id, namespace, object_key, content_type, encoding, size, sha256,
                   storage_mode, source_path, metadata_json, created_at, updated_at
            from stored_objects
            where id = ?
            """,
            (object_id,),
        ).fetchone()
    return row_to_dict(row)


def _stored_objects_for_run(run_id: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select id, namespace, object_key, content_type, encoding, size, sha256,
                   storage_mode, source_path, metadata_json, created_at, updated_at
            from stored_objects
            where namespace = ? and object_key like ?
            order by object_key asc, updated_at desc
            """,
            ("backtest-results", f"{run_id}/%"),
        ).fetchall()
    items = rows_to_dicts(rows)
    if items:
        return items
    return [
        item
        for item in (
            _stored_object(result.get("raw_result_object_id")),
            _stored_object(result.get("summary_object_id")),
        )
        if item is not None
    ]


def _backtest_report_id(run_id: str) -> str:
    return f"backtest:{run_id}"


def _run_id_from_report_id(report_id: str) -> str:
    for prefix in ("backtest:", "backtest-"):
        if report_id.startswith(prefix):
            return report_id[len(prefix) :]
    return report_id


def _backtest_report_from_rows(run: dict[str, Any], result: dict[str, Any] | None) -> dict[str, Any]:
    result = result or {}
    stored_objects = _stored_objects_for_run(run["id"], result)
    return {
        "id": _backtest_report_id(run["id"]),
        "source": "backtest_run",
        "task_id": run.get("task_id"),
        "run_id": run["id"],
        "status": run.get("status"),
        "symbol": run.get("symbol"),
        "parameters": run.get("parameters") or {},
        "asset_class": run.get("asset_class"),
        "venue": run.get("venue"),
        "resolution": run.get("resolution"),
        "data_type": run.get("data_type"),
        "report_path": run.get("report_html_path"),
        "result_json_path": run.get("result_json_path") or result.get("raw_result_path"),
        "summary_json_path": run.get("summary_json_path"),
        "raw_result_object_id": result.get("raw_result_object_id"),
        "summary_object_id": result.get("summary_object_id"),
        "storedObjects": stored_objects,
        "result": result,
        "fingerprint": run.get("fingerprint"),
        "validation": run.get("validation"),
        "experiment": run.get("experiment"),
        "error": run.get("error") or run.get("error_message"),
        "created_at": run.get("created_at"),
        "finished_at": run.get("finished_at"),
    }


def _light_report(item: dict[str, Any]) -> dict[str, Any]:
    result = item.get("result") or {}
    parameters = item.get("parameters") or result.get("parameters") or {}
    summary = result.get("summary_metrics") or item.get("summary_metrics") or {}
    fingerprint = item.get("fingerprint") or {}
    is_backtest = item.get("source") == "backtest_run"
    data_source = parameters.get("source") or fingerprint.get("source") or (fingerprint.get("data") or {}).get("scope", {}).get("source")
    run_id = item.get("run_id") or item.get("id")
    return {
        "id": item.get("id"),
        "runId": run_id,
        "run_id": run_id,
        "type": "backtest" if is_backtest else "report",
        "source": "backtest_run" if is_backtest else "generated_report",
        "dataSource": data_source,
        "status": item.get("status"),
        "symbol": item.get("symbol") or parameters.get("ticker") or parameters.get("symbol"),
        "benchmark": parameters.get("benchmarkSymbol") or fingerprint.get("benchmark_symbol"),
        "startDate": parameters.get("start"),
        "endDate": parameters.get("end"),
        "createdAt": item.get("created_at"),
        "created_at": item.get("created_at"),
        "summaryMetrics": summary,
        "hasStoredObjects": bool(item.get("storedObjects") or item.get("raw_result_object_id") or item.get("summary_object_id")),
        "hasFingerprint": bool(fingerprint),
        "error": item.get("error"),
    }


def _backtest_report(report_id: str) -> dict[str, Any] | None:
    run_id = _run_id_from_report_id(report_id)
    with db() as connection:
        run_row = connection.execute("select * from backtest_runs where id = ?", (run_id,)).fetchone()
        if run_row is None:
            return None
        result_row = connection.execute("select * from backtest_results where job_id = ?", (run_id,)).fetchone()
    run = row_to_dict(run_row) or {}
    result = row_to_dict(result_row) if result_row is not None else None
    return _backtest_report_from_rows(run, result)


@router.get("")
def list_reports(
    limit: int = 500,
    offset: int = 0,
    paged: bool = False,
    source: str | None = None,
    status: str | None = None,
    runId: str | None = None,
    detail: bool = False,
):
    bounded_limit = max(1, min(int(limit), 1000))
    bounded_offset = max(0, int(offset))
    scan_limit = bounded_limit + bounded_offset
    source_filter = source.strip().lower() if source else None
    report_clauses = []
    report_values: list[Any] = []
    backtest_clauses = [
        "(r.report_html_path is not null or r.result_json_path is not null or r.summary_json_path is not null or br.job_id is not null)"
    ]
    backtest_values: list[Any] = []
    if status:
        report_clauses.append("status = ?")
        report_values.append(status)
        backtest_clauses.append("r.status = ?")
        backtest_values.append(status)
    if runId:
        report_clauses.append("run_id = ?")
        report_values.append(runId)
        backtest_clauses.append("r.id = ?")
        backtest_values.append(runId)
    report_where = f"where {' and '.join(report_clauses)}" if report_clauses else ""
    backtest_where = f"where {' and '.join(backtest_clauses)}"
    with db() as connection:
        report_count = 0
        report_rows = []
        if source_filter in (None, "reports"):
            report_count = connection.execute(f"select count(*) as count from reports {report_where}", report_values).fetchone()["count"]
            report_rows = connection.execute(
                f"select * from reports {report_where} order by created_at desc, id desc limit ?",
                [*report_values, scan_limit],
            ).fetchall()
        backtest_count = 0
        backtest_rows = []
        if source_filter in (None, "backtest_run", "backtest"):
            backtest_count = connection.execute(
                f"""
                select count(*) as count
                from backtest_runs r
                left join backtest_results br on br.job_id = r.id
                {backtest_where}
                """,
                backtest_values,
            ).fetchone()["count"]
            backtest_rows = connection.execute(
                f"""
            select r.*, br.id as result_id, br.summary_metrics_json, br.equity_curve_json,
                   br.drawdown_curve_json, br.orders_json, br.trades_json, br.holdings_json,
                   br.statistics_json as result_statistics_json, br.performance_json,
                   br.raw_result_path, br.raw_result_object_id, br.summary_object_id,
                   br.created_at as result_created_at
            from backtest_runs r
            left join backtest_results br on br.job_id = r.id
            {backtest_where}
            order by r.created_at desc, r.id desc
            limit 500
            """.replace("limit 500", "limit ?"),
                [*backtest_values, scan_limit],
            ).fetchall()
    reports = [{**item, "source": "reports"} for item in rows_to_dicts(report_rows)]
    backtests = []
    for row in backtest_rows:
        item = row_to_dict(row) or {}
        result = None
        if item.get("result_id"):
            result = {
                "id": item.pop("result_id"),
                "job_id": item["id"],
                "summary_metrics": item.pop("summary_metrics", None),
                "equity_curve": item.pop("equity_curve", None),
                "drawdown_curve": item.pop("drawdown_curve", None),
                "orders": item.pop("orders", None),
                "trades": item.pop("trades", None),
                "holdings": item.pop("holdings", None),
                "statistics": item.pop("result_statistics", None),
                "performance": item.pop("performance", None),
                "raw_result_path": item.pop("raw_result_path", None),
                "raw_result_object_id": item.pop("raw_result_object_id", None),
                "summary_object_id": item.pop("summary_object_id", None),
                "created_at": item.pop("result_created_at", None),
            }
        backtests.append(_backtest_report_from_rows(item, result))
    items = sorted([*reports, *backtests], key=lambda item: item.get("created_at") or "", reverse=True)
    output_items = items if detail else [_light_report(item) for item in items]
    sliced = output_items[bounded_offset : bounded_offset + bounded_limit]
    if paged:
        return {"items": sliced, "count": report_count + backtest_count, "limit": bounded_limit, "offset": bounded_offset}
    return sliced


@router.post("")
def create_report(request: ReportRequest):
    report_id = str(uuid.uuid4())
    task = create_task("report", f"Report {request.runId}", {"runId": request.runId}, None, report_id)
    with db() as connection:
        connection.execute(
            "insert into reports (id, task_id, run_id, status, created_at) values (?, ?, ?, ?, ?)",
            (report_id, task["id"], request.runId, "queued", utc_now()),
        )
    dispatch_task(generate_report_task.s(task["id"], report_id), task["id"])
    return detail(report_id)


@router.get("/{report_id}")
def detail(report_id: str):
    with db() as connection:
        row = connection.execute("select * from reports where id = ?", (report_id,)).fetchone()
    item = row_to_dict(row)
    if item is None:
        item = _backtest_report(report_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return item


@router.delete("/{report_id}")
def delete(report_id: str):
    try:
        return delete_generated_report(report_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{report_id}/objects")
def report_objects(report_id: str, limit: int = 100, offset: int = 0):
    item = detail(report_id)
    run_id = item.get("run_id") or _run_id_from_report_id(report_id)
    objects = _stored_objects_for_run(run_id, item.get("result") or {})
    bounded_limit = max(1, min(int(limit), 1000))
    bounded_offset = max(0, int(offset))
    sliced = objects[bounded_offset : bounded_offset + bounded_limit]
    return {"items": sliced, "count": len(objects), "limit": bounded_limit, "offset": bounded_offset}


@router.get("/{report_id}/objects/{object_id}")
def report_object(report_id: str, object_id: str):
    objects = report_objects(report_id, limit=1000, offset=0)["items"]
    allowed = {item["id"] for item in objects}
    if object_id not in allowed:
        raise HTTPException(status_code=404, detail="Report object not found.")
    item = get_object(object_id)
    if not item:
        raise HTTPException(status_code=404, detail="Report object not found.")
    content = read_bytes(object_id)
    return Response(
        content=content,
        media_type=item.get("content_type") or "application/octet-stream",
        headers={"X-Object-SHA256": item.get("sha256") or "", "X-Object-Key": item.get("object_key") or ""},
    )


@router.get("/{report_id}/file")
def report_file(report_id: str):
    item = detail(report_id)
    path = Path(item.get("report_path") or item.get("report_html_path") or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report file not found.")
    return FileResponse(path, headers=REPORT_FILE_CACHE_HEADERS)


def _export_report_item(report_id: str) -> dict[str, Any]:
    item = detail(report_id)
    run_id = item.get("run_id")
    if run_id:
        backtest_item = _backtest_report(_backtest_report_id(run_id))
        if backtest_item:
            item = {**backtest_item, **{key: value for key, value in item.items() if value not in (None, "", [])}}
    return item


@router.get("/{report_id}/export")
def export_report(report_id: str, format: str = "html"):
    export_format = format.strip().lower()
    item = _export_report_item(report_id)
    filename_base = f"backtest-report-{_run_id_from_report_id(report_id).replace(':', '-')}"
    if export_format == "html":
        path = Path(item.get("report_path") or item.get("report_html_path") or "")
        if not path.exists():
            raise HTTPException(status_code=404, detail="HTML report file not found.")
        return FileResponse(
            path,
            media_type="text/html",
            headers={
                "Content-Disposition": f'inline; filename="{filename_base}.html"',
                "X-Content-Type-Options": "nosniff",
                **REPORT_FILE_CACHE_HEADERS,
            },
        )

    payload = report_payload(item)
    if export_format in {"md", "markdown"}:
        return Response(
            markdown_report(payload),
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'inline; filename="{filename_base}.md"',
                "X-Content-Type-Options": "nosniff",
                **REPORT_FILE_CACHE_HEADERS,
            },
        )
    if export_format == "json":
        return Response(
            json_report(payload),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'inline; filename="{filename_base}.json"',
                "X-Content-Type-Options": "nosniff",
                **REPORT_FILE_CACHE_HEADERS,
            },
        )
    if export_format == "csv":
        return Response(
            csv_report(payload),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'inline; filename="{filename_base}.csv"',
                "X-Content-Type-Options": "nosniff",
                **REPORT_FILE_CACHE_HEADERS,
            },
        )
    if export_format == "pdf":
        try:
            content = pdf_report(payload)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return Response(
            content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename_base}.pdf"',
                "X-Content-Type-Options": "nosniff",
                **REPORT_FILE_CACHE_HEADERS,
            },
        )
    raise HTTPException(status_code=400, detail="Unsupported report export format.")
