from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Callable

from ..core.config import MARKET_DATA_DIR as PARQUET_DIR, PARQUET_COMPRESSION
from ..db import db, json_dump, rows_to_dicts, utc_now
from ..lean_engine.symbols import normalize_symbol
from . import market_lake
from .source_gate import PRIMARY_DATA_SOURCE, resolve_source_context

try:  # pragma: no cover
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None

try:  # pragma: no cover
    import polars as pl
except Exception:  # pragma: no cover
    pl = None


DATASET_NAMESPACE = uuid.UUID("0c36692c-1d8d-4e19-9dc0-7c4435b2b8a6")
MARKET_DAILY_BAR_NUMERIC_COLUMNS = (
    "open", "high", "low", "close", "settle", "volume", "amount",
    "turnover_rate", "open_interest", "prev_close", "pct_change", "adj_factor",
)


def _clean(value: str | None, default: str = "") -> str:
    return (value or default).strip().lower() or default


def _normalize_scope(
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = PRIMARY_DATA_SOURCE,
) -> dict[str, str]:
    market = _clean(market, "china")
    return {
        "asset_class": _clean(asset_class, "equity"),
        "market": market,
        "venue": _clean(venue, market),
        "resolution": _clean(resolution, "daily"),
        "data_type": _clean(data_type, "trade"),
        "adjust": _clean(adjust, "raw"),
        "source": _clean(source, PRIMARY_DATA_SOURCE),
    }


def _dataset_key(**scope: str) -> str:
    return market_lake.dataset_key(kind="bars", **scope)


def _dataset_id(dataset_key: str) -> str:
    return str(uuid.uuid5(DATASET_NAMESPACE, dataset_key))


def _market_daily_bar_frame(rows: list[dict[str, Any]]) -> Any:
    if pl is None:
        raise RuntimeError("polars is required for Parquet market data")
    frame = pl.DataFrame(rows, infer_schema_length=None)
    expressions = [
        pl.col(column).cast(pl.Float64, strict=False).alias(column)
        for column in MARKET_DAILY_BAR_NUMERIC_COLUMNS
        if column in frame.columns
    ]
    return frame.with_columns(expressions) if expressions else frame


def _manifest_files(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "path": item.get("path"),
            "relativePath": item.get("path"),
            "visiblePath": str(PARQUET_DIR / str(item.get("path"))),
            "partition": {"year": item.get("year")},
            "rowCount": int(item.get("rowCount") or 0),
            "firstTimestamp": item.get("firstTimestamp"),
            "lastTimestamp": item.get("lastTimestamp"),
            "sha256": item.get("sha256"),
            "size": int(item.get("size") or 0),
        }
        for item in manifest.get("files") or []
    ]


def _register(scope: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
    files = _manifest_files(manifest)
    dataset_key = str(manifest.get("datasetKey") or _dataset_key(**scope))
    dataset_id = _dataset_id(dataset_key)
    row_count = sum(int(item["rowCount"]) for item in files)
    starts = [str(item["firstTimestamp"]) for item in files if item.get("firstTimestamp")]
    ends = [str(item["lastTimestamp"]) for item in files if item.get("lastTimestamp")]
    now = utc_now()
    metadata = {
        "authority": "parquet",
        "manifest": market_lake.MANIFEST_NAME,
        "manifestSha256": manifest.get("manifestSha256"),
        "writeMode": "direct_atomic_partition",
    }
    with db() as connection:
        connection.execute(
            """
            insert into parquet_datasets
                (id,dataset_key,asset_class,market,venue,resolution,data_type,adjust,source,
                 root_path,schema_version,start_date,end_date,row_count,file_count,metadata_json,
                 created_at,updated_at,dataset_version,environment,is_production,is_certified,qa_status)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'research',0,0,'pending')
            on conflict(dataset_key) do update set
                root_path=excluded.root_path,schema_version=excluded.schema_version,
                start_date=excluded.start_date,end_date=excluded.end_date,
                row_count=excluded.row_count,file_count=excluded.file_count,
                metadata_json=excluded.metadata_json,updated_at=excluded.updated_at,
                dataset_version=excluded.dataset_version
            """,
            (
                dataset_id, dataset_key, scope["asset_class"], scope["market"], scope["venue"],
                scope["resolution"], scope["data_type"], scope["adjust"], scope["source"],
                f"parquet/{dataset_key}", market_lake.MANIFEST_SCHEMA_VERSION,
                min(starts) if starts else None, max(ends) if ends else None,
                row_count, len(files), json_dump(metadata), now, now, manifest.get("datasetVersion"),
            ),
        )
        connection.execute("delete from parquet_files where dataset_id=?", (dataset_id,))
        for item in files:
            connection.execute(
                """
                insert into parquet_files
                    (id,dataset_id,file_path,partition_json,row_count,first_timestamp,
                     last_timestamp,sha256,size,created_at)
                values (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid5(DATASET_NAMESPACE, f"{dataset_id}:{item['path']}")),
                    dataset_id, f"parquet/{item['path']}", json_dump(item["partition"]),
                    item["rowCount"], item["firstTimestamp"], item["lastTimestamp"],
                    item.get("sha256") or "", item["size"], now,
                ),
            )
    return {
        "id": dataset_id,
        "datasetKey": dataset_key,
        "datasetVersion": manifest.get("datasetVersion"),
        "manifestSha256": manifest.get("manifestSha256"),
        "rootPath": f"parquet/{dataset_key}",
        "rowCount": row_count,
        "fileCount": len(files),
        "startDate": min(starts) if starts else None,
        "endDate": max(ends) if ends else None,
        "files": files,
    }


def export_market_daily_bars(
    *,
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = PRIMARY_DATA_SOURCE,
    start_date: str | None = None,
    end_date: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    incremental: bool = False,
) -> dict[str, Any]:
    """Adopt/register an existing direct-written lake; no SQL export occurs."""
    del start_date, end_date, incremental
    scope = _normalize_scope(asset_class, market, venue, resolution, data_type, adjust, source)
    manifest = market_lake.adopt_legacy_files(kind="bars", **scope)
    if not manifest.get("files"):
        raise ValueError(f"parquet_dataset_missing:{_dataset_key(**scope)}")
    result = _register(scope, manifest)
    if progress_callback:
        progress_callback(
            {
                "stage": "parquet_adopt",
                "scope": scope,
                "rowsProcessed": result["rowCount"],
                "expectedRows": result["rowCount"],
                "fileCount": result["fileCount"],
            }
        )
    return result


def _available_scopes(*, include_research_sources: bool = True) -> list[dict[str, str]]:
    """Return directly readable bar scopes from the canonical lake.

    Kept as the maintenance-layer seam because tests and operators may narrow
    the scope set, but discovery itself no longer queries a SQL quote table.
    """
    scopes = market_lake.all_scopes(kind="bars")
    if include_research_sources:
        return scopes
    return [scope for scope in scopes if scope["source"] == PRIMARY_DATA_SOURCE]


def list_datasets() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for scope in market_lake.all_scopes(kind="bars"):
        # Native date partitions carry per-file manifests rather than one
        # synthetic dataset manifest. Build the registry view from the files
        # themselves so counts and checksums stay truthful.
        manifest = market_lake.adopt_legacy_files(**scope)
        files = _manifest_files(manifest)
        starts = [item["firstTimestamp"] for item in files if item.get("firstTimestamp")]
        ends = [item["lastTimestamp"] for item in files if item.get("lastTimestamp")]
        result.append(
            {
                "id": _dataset_id(str(manifest.get("datasetKey"))),
                "dataset_key": manifest.get("datasetKey"),
                "dataset_version": manifest.get("datasetVersion"),
                "asset_class": scope["asset_class"], "market": scope["market"],
                "venue": scope["venue"], "resolution": scope["resolution"],
                "data_type": scope["data_type"], "adjust": scope["adjust"],
                "source": scope["source"],
                "root_path": f"parquet/{manifest.get('datasetKey')}",
                "row_count": sum(int(item["rowCount"]) for item in files),
                "file_count": len(files),
                "start_date": min(starts) if starts else None,
                "end_date": max(ends) if ends else None,
                "metadata": {"authority": "parquet", "manifestSha256": manifest.get("manifestSha256")},
            }
        )
    return result


def _persist_consistency_report(report: dict[str, Any]) -> str:
    report_id = str(uuid.uuid4())
    with db() as connection:
        connection.execute(
            """
            insert into data_quality_reports
                (id,report_type,asset_class,market,symbol,start_date,end_date,
                 sources_json,severity,result_json,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                report_id, "parquet_consistency", report.get("assetClass") or "multi",
                report.get("market") or "multi", None, report.get("startDate"), report.get("endDate"),
                json_dump(report.get("sources") or []), report["severity"], json_dump(report), utc_now(),
            ),
        )
    return report_id


def parquet_consistency_report(
    *,
    asset_class: str | None = None,
    market: str | None = None,
    venue: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
    adjust: str | None = None,
    sources: list[str] | None = None,
    include_research_sources: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    del include_research_sources
    items: list[dict[str, Any]] = []
    source_filter = {_clean(item) for item in sources or []}
    scopes = market_lake.matching_scopes(
        kind="bars", asset_class=asset_class, market=market, venue=venue,
        resolution=resolution, data_type=data_type, adjust=adjust,
    )
    if source_filter:
        scopes = [scope for scope in scopes if scope["source"] in source_filter]
    for scope in scopes:
        if not market_lake.load_manifest(**scope).get("manifestSha256"):
            market_lake.adopt_legacy_files(**scope)
        integrity = market_lake.integrity_report(**scope)
        manifest = market_lake.load_manifest(**scope)
        files = _manifest_files(manifest)
        row_count = sum(int(item["rowCount"]) for item in files)
        items.append(
            {
                "datasetId": _dataset_id(str(manifest.get("datasetKey"))),
                "datasetKey": manifest.get("datasetKey"),
                "datasetVersion": manifest.get("datasetVersion"),
                "datasetRows": row_count,
                "datasetFiles": len(files),
                "severity": "ok" if integrity["passed"] else "critical",
                "passed": integrity["passed"],
                "issues": integrity["issues"],
                "parquet": {"rowCount": row_count, "fileCount": len(files)},
            }
        )
        _register(scope, manifest)
    missing = bool(source_filter and not items)
    severity = "critical" if missing or any(not item["passed"] for item in items) else "ok"
    report = {
        "reportType": "parquet_consistency", "assetClass": asset_class, "market": market,
        "venue": venue, "resolution": resolution, "dataType": data_type, "adjust": adjust,
        "sources": sorted(source_filter), "severity": severity, "passed": severity == "ok",
        "datasetCount": len(items), "criticalCount": sum(not item["passed"] for item in items),
        "warningCount": 0, "issues": ["parquet_dataset_missing"] if missing else [], "items": items,
    }
    if persist:
        report["reportId"] = _persist_consistency_report(report)
    return report


def certify_consistent_production_datasets(report: dict[str, Any]) -> list[str]:
    if not report.get("reportId"):
        return []
    certified: list[str] = []
    with db() as connection:
        for item in report.get("items") or []:
            if not item.get("passed") or int(item.get("datasetRows") or 0) <= 0:
                continue
            dataset_id = str(item["datasetId"])
            connection.execute(
                """
                update parquet_datasets set environment='production',is_production=1,is_certified=1,
                    certified_at=?,certified_by='parquet-manifest-v2',qa_status='ok',qa_report_id=?
                where id=? and source=?
                """,
                (utc_now(), report["reportId"], dataset_id, PRIMARY_DATA_SOURCE),
            )
            if getattr(connection, "total_changes", 0):
                certified.append(dataset_id)
    return certified


def rebuild_all_market_parquet(
    *,
    asset_class: str | None = None,
    market: str | None = None,
    venue: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
    adjust: str | None = None,
    sources: list[str] | None = None,
    include_research_sources: bool = False,
    start_date: str | None = None,
    end_date: str | None = None,
    continue_on_error: bool = True,
    persist_report: bool = True,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    del start_date, end_date, continue_on_error
    scopes = market_lake.matching_scopes(
        kind="bars", asset_class=asset_class, market=market, venue=venue,
        resolution=resolution, data_type=data_type, adjust=adjust,
    )
    source_filter = {_clean(item) for item in sources or []}
    if source_filter:
        scopes = [scope for scope in scopes if scope["source"] in source_filter]
    adopted = []
    for scope in scopes:
        manifest = market_lake.adopt_legacy_files(**scope)
        adopted.append(_register(scope, manifest))
        if progress_callback:
            progress_callback({"stage": "parquet_adopt", "scope": scope})
    report = parquet_consistency_report(
        asset_class=asset_class, market=market, venue=venue, resolution=resolution,
        data_type=data_type, adjust=adjust, sources=sources,
        include_research_sources=include_research_sources, persist=persist_report,
    )
    return {
        "scopeCount": len(scopes), "rebuiltCount": 0, "adoptedCount": len(adopted),
        "errorCount": 0, "rebuilt": [], "adopted": adopted, "errors": [],
        "consistencyReport": report,
        "certifiedDatasetIds": certify_consistent_production_datasets(report),
    }


def query_duckdb_bars(
    *,
    asset_class: str = "equity",
    symbol: str,
    market: str | None = None,
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    provider_source: str = PRIMARY_DATA_SOURCE,
    adjust: str = "raw",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
    allow_research_source: bool = False,
) -> dict[str, Any]:
    if duckdb is None:
        return {"enabled": False, "source": "parquet", "effectiveEngine": "duckdb", "items": [], "count": 0, "error": "duckdb is not installed"}
    context = resolve_source_context(
        {}, source=provider_source, allow_research_source=allow_research_source,
        asset_class=asset_class, market=market or venue or "china", venue=venue or market,
    )
    source = str(context["source"])
    scope = _normalize_scope(asset_class, market or venue or "china", venue, resolution, data_type, adjust, source)
    value = symbol.strip().upper()
    if scope["asset_class"] == "equity" and scope["market"] in {"china", "hongkong"}:
        value = normalize_symbol(value, scope["market"])
    predicates = ["symbol = ?"]
    parameters: list[Any] = [value]
    if start_date:
        predicates.append("trade_date >= ?")
        parameters.append(start_date)
    if end_date:
        predicates.append("trade_date <= ?")
        parameters.append(end_date)
    rows = market_lake.query_rows(
        kind="bars", **scope, columns="trade_date,open,high,low,close,volume,source",
        predicates=predicates, parameters=parameters, order_by="trade_date asc,source asc",
        limit=max(1, min(int(limit), 5000)),
    )
    manifest = market_lake.load_manifest(kind="bars", **scope)
    return {
        "enabled": True, "source": "parquet", "effectiveEngine": "duckdb",
        "dataset": {"datasetKey": manifest.get("datasetKey"), "datasetVersion": manifest.get("datasetVersion")},
        "items": [
            {
                "timestamp": str(row["trade_date"]), "open": row.get("open"), "high": row.get("high"),
                "low": row.get("low"), "close": row.get("close"), "volume": row.get("volume"),
                "source": row.get("source"),
            }
            for row in rows
        ],
        "count": len(rows),
    }


def _market_source_lineage(scope: dict[str, str], *_: Any, expected_row_count: int = 0, **__: Any) -> dict[str, Any]:
    manifest = market_lake.load_manifest(kind="bars", **scope)
    return {
        "passed": bool(manifest.get("files")) and expected_row_count >= 0,
        "authority": "parquet_manifest",
        "manifestSha256": manifest.get("manifestSha256"),
    }
