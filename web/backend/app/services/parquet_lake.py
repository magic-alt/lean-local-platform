from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from ..core.config import PARQUET_COMPRESSION, PARQUET_DIR
from ..db import db, json_dump, rows_to_dicts, utc_now
from ..lean_engine.symbols import normalize_symbol
from .source_gate import PRIMARY_DATA_SOURCE, PRODUCTION_SOURCES, require_source_allowed, resolve_source_context

try:  # pragma: no cover - exercised when dependency is installed.
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None

try:  # pragma: no cover - exercised when dependency is installed.
    import polars as pl
except Exception:  # pragma: no cover
    pl = None


SCHEMA_VERSION = 1
DATASET_NAMESPACE = uuid.UUID("0c36692c-1d8d-4e19-9dc0-7c4435b2b8a6")
FILE_NAMESPACE = uuid.UUID("5bb3fc9a-6849-4d73-bd43-5d66d0b75f06")


def _clean(value: str | None, default: str = "") -> str:
    text = (value or default).strip().lower()
    return text or default


def _dataset_key(
    *,
    asset_class: str,
    market: str,
    venue: str,
    resolution: str,
    data_type: str,
    adjust: str,
    source: str,
) -> str:
    return "/".join(
        [
            f"asset_class={asset_class}",
            f"market={market}",
            f"venue={venue}",
            f"resolution={resolution}",
            f"data_type={data_type}",
            f"adjust={adjust}",
            f"source={source}",
        ]
    )


def _dataset_id(dataset_key: str) -> str:
    return str(uuid.uuid5(DATASET_NAMESPACE, dataset_key))


def _file_id(path: str | Path) -> str:
    return str(uuid.uuid5(FILE_NAMESPACE, str(path)))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(PARQUET_DIR))
    except ValueError:
        return str(path)


def _logical_parquet_path(path: Path) -> str:
    relative = _relative_path(path).replace("\\", "/")
    if relative.startswith("parquet/") or Path(relative).is_absolute():
        return relative
    return f"parquet/{relative}"


def _visible_parquet_path(path: str | Path) -> Path:
    raw = Path(path)
    if raw.exists():
        return raw
    text = str(path).replace("\\", "/")
    candidates: list[Path] = []
    if "/parquet/" in text:
        candidates.append(PARQUET_DIR / text.split("/parquet/", 1)[1])
    if text.startswith("parquet/"):
        candidates.append(PARQUET_DIR / text.removeprefix("parquet/"))
    if not raw.is_absolute():
        candidates.append(PARQUET_DIR / raw)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else raw


def _normalize_scope(
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = "akshare",
) -> dict[str, str]:
    market_key = _clean(market, "china")
    return {
        "asset_class": _clean(asset_class, "equity"),
        "market": market_key,
        "venue": _clean(venue, market_key),
        "resolution": _clean(resolution, "daily"),
        "data_type": _clean(data_type, "trade"),
        "adjust": _clean(adjust, "raw"),
        "source": _clean(source, "akshare"),
    }


def _query_symbol(symbol: str, scope: dict[str, str]) -> str:
    value = symbol.strip()
    if not value:
        return value
    if scope["asset_class"] == "equity":
        if scope["market"] == "china":
            return normalize_symbol(value, "china")
        if scope["market"] == "hongkong":
            return normalize_symbol(value, "hongkong")
        if value.startswith(("SH", "SZ", "SS", "BJ")):
            return normalize_symbol(value, "china")
    return value.strip().upper()


def _dataset_root(scope: dict[str, str]) -> Path:
    path = PARQUET_DIR
    for part in (
        f"asset_class={scope['asset_class']}",
        f"market={scope['market']}",
        f"venue={scope['venue']}",
        f"resolution={scope['resolution']}",
        f"data_type={scope['data_type']}",
        f"adjust={scope['adjust']}",
        f"source={scope['source']}",
    ):
        path = path / part
    return path


def _fetch_market_rows(scope: dict[str, str], start_date: str | None, end_date: str | None) -> list[dict[str, Any]]:
    predicates = [
        "asset_class = ?",
        "market = ?",
        "venue = ?",
        "resolution = ?",
        "data_type = ?",
        "adjust = ?",
        "source = ?",
    ]
    params: list[Any] = [
        scope["asset_class"],
        scope["market"],
        scope["venue"],
        scope["resolution"],
        scope["data_type"],
        scope["adjust"],
        scope["source"],
    ]
    if start_date:
        predicates.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        predicates.append("trade_date <= ?")
        params.append(end_date)
    with db() as connection:
        rows = connection.execute(
            f"""
            select
                instrument_id,
                symbol,
                asset_class,
                market,
                venue,
                trade_date,
                resolution,
                data_type,
                open,
                high,
                low,
                close,
                settle,
                volume,
                amount,
                turnover_rate,
                open_interest,
                prev_close,
                pct_change,
                adjust,
                adj_factor,
                source,
                batch_id,
                created_at
            from market_daily_bars
            where {" and ".join(predicates)}
            order by trade_date asc, symbol asc
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def _market_row_count(scope: dict[str, str], start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    predicates = [
        "asset_class = ?",
        "market = ?",
        "venue = ?",
        "resolution = ?",
        "data_type = ?",
        "adjust = ?",
        "source = ?",
    ]
    params: list[Any] = [
        scope["asset_class"],
        scope["market"],
        scope["venue"],
        scope["resolution"],
        scope["data_type"],
        scope["adjust"],
        scope["source"],
    ]
    if start_date:
        predicates.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        predicates.append("trade_date <= ?")
        params.append(end_date)
    with db() as connection:
        row = connection.execute(
            f"""
            select count(*) as row_count, min(trade_date) as first_date, max(trade_date) as last_date
            from market_daily_bars
            where {" and ".join(predicates)}
            """,
            params,
        ).fetchone()
    return {"rowCount": row["row_count"] if row else 0, "firstDate": row["first_date"] if row else None, "lastDate": row["last_date"] if row else None}


def _market_source_lineage(
    scope: dict[str, str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    if scope["source"] != PRIMARY_DATA_SOURCE or scope["asset_class"] != "equity":
        return {"required": False, "passed": True, "batchCount": 0, "invalidBatches": []}
    predicates = [
        "m.asset_class = ?", "m.market = ?", "m.venue = ?", "m.resolution = ?",
        "m.data_type = ?", "m.adjust = ?", "m.source = ?",
    ]
    params: list[Any] = [
        scope["asset_class"], scope["market"], scope["venue"], scope["resolution"],
        scope["data_type"], scope["adjust"], scope["source"],
    ]
    if start_date:
        predicates.append("m.trade_date >= ?")
        params.append(start_date)
    if end_date:
        predicates.append("m.trade_date <= ?")
        params.append(end_date)
    with db() as connection:
        rows = connection.execute(
            f"""
            select m.batch_id, m.symbol, b.provider, b.status, b.config_json, b.qa_report_json,
                   count(*) as row_count
            from market_daily_bars m
            left join data_import_batches b on b.id = m.batch_id
            where {" and ".join(predicates)}
            group by m.batch_id, m.symbol, b.provider, b.status, b.config_json, b.qa_report_json
            order by m.batch_id, m.symbol
            """,
            params,
        ).fetchall()
    parsed_rows: list[tuple[Any, dict[str, Any], dict[str, Any]]] = []
    sync_run_ids: set[str] = set()
    for row in rows:
        try:
            qa_report = json.loads(row["qa_report_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            qa_report = {}
        try:
            batch_config = json.loads(row["config_json"] or "{}")
        except (TypeError, json.JSONDecodeError):
            batch_config = {}
        parsed_rows.append((row, qa_report, batch_config))
        provenance = batch_config.get("provenance") or {}
        sync_run_id = str(provenance.get("syncRunId") or "")
        if sync_run_id:
            sync_run_ids.add(sync_run_id)

    manifest_evidence: dict[tuple[str, str], dict[str, Any]] = {}
    archive_evidence: set[str] = set()
    if sync_run_ids:
        placeholders = ",".join("?" for _ in sync_run_ids)
        with db() as connection:
            manifest_rows = connection.execute(
                f"""
                select run_id, scope_key, status, response_rows, rejected_rows
                from provider_ingestion_manifests
                where provider=? and dataset_key='daily' and run_id in ({placeholders})
                """,
                [PRIMARY_DATA_SOURCE, *sorted(sync_run_ids)],
            ).fetchall()
            archive_rows = connection.execute(
                f"""
                select distinct a.run_id
                from provider_raw_archives a
                join stored_objects o on o.id=a.object_id
                where a.provider=? and a.dataset_key='daily' and a.run_id in ({placeholders})
                  and exists (select 1 from stored_object_chunks c where c.object_id=o.id)
                """,
                [PRIMARY_DATA_SOURCE, *sorted(sync_run_ids)],
            ).fetchall()
        manifest_evidence = {
            (str(item["run_id"]), str(item["scope_key"])): dict(item)
            for item in manifest_rows
        }
        archive_evidence = {str(item["run_id"]) for item in archive_rows}

    invalid: list[dict[str, Any]] = []
    for row, qa_report, batch_config in parsed_rows:
        provenance = batch_config.get("provenance") or {}
        sync_run_id = str(provenance.get("syncRunId") or "")
        symbol = str(row["symbol"] or "")
        manifest = manifest_evidence.get((sync_run_id, symbol)) or {}
        declared_environment = str(
            provenance.get("environment")
            or batch_config.get("environment")
            or qa_report.get("environment")
            or "research"
        ).strip().lower()
        synthetic = bool(
            provenance.get("synthetic")
            or batch_config.get("synthetic")
            or qa_report.get("synthetic")
        )
        evidence_valid = bool(
            sync_run_id
            and provenance.get("providerEvidence") == "ingestion_manifest_and_raw_archive"
            and provenance.get("datasetKey") == "daily"
            and str(provenance.get("scopeKey") or "") == symbol
            and str(manifest.get("status") or "").lower() == "success"
            and int(manifest.get("response_rows") or 0) > 0
            and int(manifest.get("rejected_rows") or 0) == 0
            and sync_run_id in archive_evidence
        )
        valid = bool(
            row["batch_id"]
            and str(row["provider"] or "").lower() == PRIMARY_DATA_SOURCE
            and str(row["status"] or "").lower() == "success"
            and qa_report.get("passed") is True
            and declared_environment == "production"
            and not synthetic
            and evidence_valid
        )
        if not valid:
            invalid.append(
                {
                    "batchId": row["batch_id"],
                    "provider": row["provider"],
                    "status": row["status"],
                    "qaPassed": qa_report.get("passed"),
                    "environment": declared_environment,
                    "synthetic": synthetic,
                    "syncRunId": sync_run_id or None,
                    "providerEvidenceValid": evidence_valid,
                    "rowCount": row["row_count"],
                }
            )
    return {
        "required": True,
        "passed": bool(rows) and not invalid,
        "batchCount": len(rows),
        "invalidBatches": invalid[:100],
    }


def _available_scopes(
    *,
    asset_class: str | None = None,
    market: str | None = None,
    venue: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
    adjust: str | None = None,
    sources: list[str] | None = None,
    include_research_sources: bool = False,
) -> list[dict[str, str]]:
    predicates: list[str] = []
    params: list[Any] = []
    filters = {
        "asset_class": asset_class,
        "market": market,
        "venue": venue,
        "resolution": resolution,
        "data_type": data_type,
        "adjust": adjust,
    }
    for column, value in filters.items():
        if value:
            predicates.append(f"{column} = ?")
            params.append(_clean(value))
    if sources:
        normalized = [require_source_allowed(source, allow_research_source=include_research_sources) for source in sources if source.strip()]
        if normalized:
            predicates.append(f"source in ({', '.join('?' for _ in normalized)})")
            params.extend(normalized)
    elif not include_research_sources:
        normalized = sorted(PRODUCTION_SOURCES)
        predicates.append(f"source in ({', '.join('?' for _ in normalized)})")
        params.extend(normalized)
    where = f"where {' and '.join(predicates)}" if predicates else ""
    with db() as connection:
        rows = connection.execute(
            f"""
            select distinct asset_class, market, venue, resolution, data_type, adjust, source
            from market_daily_bars
            {where}
            order by asset_class, market, venue, resolution, data_type, adjust, source
            """,
            params,
        ).fetchall()
    return [
        _normalize_scope(
            row["asset_class"],
            row["market"],
            row["venue"],
            row["resolution"],
            row["data_type"],
            row["adjust"],
            row["source"],
        )
        for row in rows
    ]


def _write_partition(frame: Any, root: Path, year: int) -> dict[str, Any]:
    partition_dir = root / f"year={year}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    path = partition_dir / "part-00000.parquet"
    temp_path = path.with_suffix(".parquet.tmp")
    frame.write_parquet(temp_path, compression=PARQUET_COMPRESSION)
    temp_path.replace(path)
    return {
        "path": path,
        "partition": {"year": year},
        "row_count": frame.height,
        "first_timestamp": frame.select(pl.col("trade_date").min()).item(),
        "last_timestamp": frame.select(pl.col("trade_date").max()).item(),
        "sha256": _sha256(path),
        "size": path.stat().st_size,
    }


def _upsert_dataset(scope: dict[str, str], root: Path, rows: list[dict[str, Any]], files: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    key = _dataset_key(**scope)
    dataset_id = _dataset_id(key)
    first_date = min((str(row["trade_date"]) for row in rows), default=None)
    last_date = max((str(row["trade_date"]) for row in rows), default=None)
    root_path = _logical_parquet_path(root)
    file_manifest = [
        {
            "path": _logical_parquet_path(item["path"]),
            "rowCount": item["row_count"],
            "sha256": item["sha256"],
        }
        for item in files
    ]
    manifest_sha256 = hashlib.sha256(
        json_dump(file_manifest).encode("utf-8")
    ).hexdigest()
    dataset_version = f"{scope['source']}-{dataset_id[:12]}-{manifest_sha256[:12]}"
    with db() as connection:
        connection.execute(
            """
            insert into parquet_datasets
                (id, dataset_key, asset_class, market, venue, resolution, data_type, adjust, source,
                 root_path, schema_version, start_date, end_date, row_count, file_count,
                 dataset_version, environment, is_production, is_certified, certified_at, certified_by,
                 coverage_start, coverage_end, qa_status, qa_report_id,
                 metadata_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(dataset_key) do update set
                asset_class = excluded.asset_class,
                market = excluded.market,
                venue = excluded.venue,
                resolution = excluded.resolution,
                data_type = excluded.data_type,
                adjust = excluded.adjust,
                source = excluded.source,
                root_path = excluded.root_path,
                schema_version = excluded.schema_version,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                row_count = excluded.row_count,
                file_count = excluded.file_count,
                dataset_version = excluded.dataset_version,
                environment = excluded.environment,
                is_production = excluded.is_production,
                is_certified = excluded.is_certified,
                certified_at = excluded.certified_at,
                certified_by = excluded.certified_by,
                coverage_start = excluded.coverage_start,
                coverage_end = excluded.coverage_end,
                qa_status = excluded.qa_status,
                qa_report_id = excluded.qa_report_id,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                dataset_id,
                key,
                scope["asset_class"],
                scope["market"],
                scope["venue"],
                scope["resolution"],
                scope["data_type"],
                scope["adjust"],
                scope["source"],
                root_path,
                SCHEMA_VERSION,
                first_date,
                last_date,
                len(rows),
                len(files),
                dataset_version,
                "research",
                0,
                0,
                None,
                None,
                first_date,
                last_date,
                "pending",
                None,
                json_dump(metadata),
                now,
                now,
            ),
        )
        connection.execute("delete from parquet_files where dataset_id = ?", (dataset_id,))
        for item in files:
            path = item["path"]
            file_path = _logical_parquet_path(path)
            connection.execute(
                """
                insert into parquet_files
                    (id, dataset_id, file_path, partition_json, row_count, first_timestamp,
                     last_timestamp, sha256, size, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _file_id(file_path),
                    dataset_id,
                    file_path,
                    json_dump(item["partition"]),
                    item["row_count"],
                    item["first_timestamp"],
                    item["last_timestamp"],
                    item["sha256"],
                    item["size"],
                    now,
                ),
            )
    return {
        "id": dataset_id,
        "datasetKey": key,
        "rootPath": root_path,
        "schemaVersion": SCHEMA_VERSION,
        "rowCount": len(rows),
        "fileCount": len(files),
        "startDate": first_date,
        "endDate": last_date,
        "files": [
            {
                "path": _logical_parquet_path(item["path"]),
                "relativePath": _relative_path(item["path"]),
                "visiblePath": str(item["path"]),
                "partition": item["partition"],
                "rowCount": item["row_count"],
                "firstTimestamp": item["first_timestamp"],
                "lastTimestamp": item["last_timestamp"],
                "sha256": item["sha256"],
                "size": item["size"],
            }
            for item in files
        ],
    }


def export_market_daily_bars(
    *,
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = "akshare",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    if pl is None:
        raise RuntimeError("polars is required to export Parquet datasets.")
    scope = _normalize_scope(asset_class, market, venue, resolution, data_type, adjust, source)
    rows = _fetch_market_rows(scope, start_date, end_date)
    root = _dataset_root(scope)
    root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    if rows:
        frame = pl.DataFrame(rows).with_columns(pl.col("trade_date").str.slice(0, 4).cast(pl.Int32).alias("year"))
        for year in sorted(frame.get_column("year").unique().to_list()):
            partition = frame.filter(pl.col("year") == year).drop("year")
            files.append(_write_partition(partition, root, int(year)))
    metadata = {
        "exported_from": "market_daily_bars",
        "compression": PARQUET_COMPRESSION,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
    }
    return _upsert_dataset(scope, root, rows, files, metadata)


def _parquet_files_for_dataset(dataset_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select *
            from parquet_files
            where dataset_id = ?
            order by first_timestamp asc, file_path asc
            """,
            (dataset_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def _persist_consistency_report(report: dict[str, Any]) -> str:
    created_at = utc_now()
    report_id = str(uuid.uuid4())
    with db() as connection:
        connection.execute(
            """
            insert into data_quality_reports
                (id, report_type, asset_class, market, symbol, start_date, end_date,
                 sources_json, severity, result_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                "parquet_consistency",
                report.get("assetClass") or "multi",
                report.get("market") or "multi",
                None,
                report.get("startDate"),
                report.get("endDate"),
                json_dump(report.get("sources") or []),
                report["severity"],
                json_dump(report),
                created_at,
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
    normalized_sources = [require_source_allowed(source, allow_research_source=include_research_sources) for source in sources or [] if source.strip()]
    with db() as connection:
        predicates: list[str] = []
        params: list[Any] = []
        filters = {
            "asset_class": asset_class,
            "market": market,
            "venue": venue,
            "resolution": resolution,
            "data_type": data_type,
            "adjust": adjust,
        }
        for column, value in filters.items():
            if value:
                predicates.append(f"{column} = ?")
                params.append(_clean(value))
        if normalized_sources:
            predicates.append(f"source in ({', '.join('?' for _ in normalized_sources)})")
            params.extend(normalized_sources)
        elif not include_research_sources:
            predicates.append("is_production = 1 and is_certified = 1")
        where = f"where {' and '.join(predicates)}" if predicates else ""
        rows = connection.execute(
            f"""
            select *
            from parquet_datasets
            {where}
            order by dataset_key asc
            """,
            params,
        ).fetchall()
    datasets = rows_to_dicts(rows)
    items: list[dict[str, Any]] = []
    for dataset in datasets:
        scope = _normalize_scope(
            dataset["asset_class"],
            dataset["market"],
            dataset["venue"],
            dataset["resolution"],
            dataset["data_type"],
            dataset["adjust"],
            dataset["source"],
        )
        files = _parquet_files_for_dataset(dataset["id"])
        resolved_files = [{**item, "visible_path": _visible_parquet_path(item["file_path"])} for item in files]
        missing_files = [item["file_path"] for item in resolved_files if not item["visible_path"].exists()]
        hash_mismatches = [
            {
                "filePath": item["file_path"],
                "visiblePath": str(item["visible_path"]),
                "expected": item["sha256"],
                "actual": _sha256(item["visible_path"]),
            }
            for item in resolved_files
            if item["visible_path"].exists() and _sha256(item["visible_path"]) != item["sha256"]
        ]
        mysql_counts = _market_row_count(scope, dataset.get("start_date"), dataset.get("end_date"))
        source_lineage = _market_source_lineage(scope, dataset.get("start_date"), dataset.get("end_date"))
        duckdb_counts = {"enabled": duckdb is not None, "rowCount": None, "firstDate": None, "lastDate": None, "error": None}
        if duckdb is not None and files and not missing_files:
            paths = ", ".join(_sql_string(str(item["visible_path"])) for item in resolved_files)
            try:
                row = duckdb.connect(database=":memory:").execute(
                    f"""
                    select count(*) as row_count, min(trade_date) as first_date, max(trade_date) as last_date
                    from read_parquet([{paths}])
                    """
                ).fetchone()
                duckdb_counts.update({"rowCount": row[0], "firstDate": str(row[1]) if row[1] is not None else None, "lastDate": str(row[2]) if row[2] is not None else None})
            except Exception as exc:
                duckdb_counts["error"] = str(exc)
        issues = []
        if missing_files:
            issues.append("missing_parquet_files")
        if hash_mismatches:
            issues.append("parquet_sha256_mismatch")
        if mysql_counts["rowCount"] != dataset["row_count"]:
            issues.append("mysql_dataset_row_count_mismatch")
        if duckdb_counts["rowCount"] is not None and duckdb_counts["rowCount"] != dataset["row_count"]:
            issues.append("duckdb_dataset_row_count_mismatch")
        if duckdb_counts["error"]:
            issues.append("duckdb_query_failed")
        if not source_lineage["passed"]:
            issues.append("provider_lineage_missing_or_unverified")
        severity = "critical" if any(issue in issues for issue in {"missing_parquet_files", "parquet_sha256_mismatch", "mysql_dataset_row_count_mismatch", "duckdb_dataset_row_count_mismatch"}) else ("warning" if issues or duckdb is None else "ok")
        items.append(
            {
                "datasetId": dataset["id"],
                "datasetKey": dataset["dataset_key"],
                "severity": severity,
                "passed": severity == "ok",
                "issues": issues,
                "datasetRows": dataset["row_count"],
                "datasetFiles": dataset["file_count"],
                "mysql": mysql_counts,
                "sourceLineage": source_lineage,
                "duckdb": duckdb_counts,
                "missingFiles": missing_files,
                "hashMismatches": hash_mismatches,
                "resolvedFiles": [
                    {"filePath": item["file_path"], "visiblePath": str(item["visible_path"])}
                    for item in resolved_files
                ],
            }
        )
    severity = "critical" if any(item["severity"] == "critical" for item in items) else ("warning" if any(item["severity"] == "warning" for item in items) else "ok")
    report = {
        "reportType": "parquet_consistency",
        "assetClass": asset_class,
        "market": market,
        "venue": venue,
        "resolution": resolution,
        "dataType": data_type,
        "adjust": adjust,
        "sources": normalized_sources,
        "startDate": min((item["mysql"]["firstDate"] for item in items if item["mysql"]["firstDate"]), default=None),
        "endDate": max((item["mysql"]["lastDate"] for item in items if item["mysql"]["lastDate"]), default=None),
        "severity": severity,
        "passed": severity == "ok",
        "datasetCount": len(items),
        "criticalCount": sum(1 for item in items if item["severity"] == "critical"),
        "warningCount": sum(1 for item in items if item["severity"] == "warning"),
        "items": items,
    }
    if persist:
        report["reportId"] = _persist_consistency_report(report)
    return report


def _certify_consistent_production_datasets(report: dict[str, Any]) -> list[str]:
    """Promote only immutable, non-empty TuShare datasets proven by a persisted QA report."""
    report_id = report.get("reportId")
    if not report_id or not report.get("passed"):
        return []

    certified_at = utc_now()
    certified_ids: list[str] = []
    with db() as connection:
        for item in report.get("items") or []:
            if (
                not item.get("passed")
                or int(item.get("datasetRows") or 0) <= 0
                or not (item.get("sourceLineage") or {}).get("passed")
            ):
                continue
            dataset_id = str(item.get("datasetId") or "")
            dataset = connection.execute(
                "select source from parquet_datasets where id = ?",
                (dataset_id,),
            ).fetchone()
            if not dataset or str(dataset["source"]).lower() != PRIMARY_DATA_SOURCE:
                continue
            connection.execute(
                """
                update parquet_datasets
                set environment = 'production',
                    is_production = 1,
                    is_certified = 1,
                    certified_at = ?,
                    certified_by = 'parquet-consistency-v1',
                    qa_status = 'ok',
                    qa_report_id = ?,
                    updated_at = ?
                where id = ? and source = ?
                """,
                (certified_at, report_id, certified_at, dataset_id, PRIMARY_DATA_SOURCE),
            )
            certified_ids.append(dataset_id)
    return certified_ids


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
) -> dict[str, Any]:
    scopes = _available_scopes(
        asset_class=asset_class,
        market=market,
        venue=venue,
        resolution=resolution,
        data_type=data_type,
        adjust=adjust,
        sources=sources,
        include_research_sources=include_research_sources,
    )
    rebuilt: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for scope in scopes:
        try:
            rebuilt.append(export_market_daily_bars(**scope, start_date=start_date, end_date=end_date))
        except Exception as exc:
            errors.append({"scope": scope, "error": str(exc)})
            if not continue_on_error:
                raise
    scope_sources = sorted({scope["source"] for scope in scopes})
    consistency = parquet_consistency_report(
        asset_class=asset_class,
        market=market,
        venue=venue,
        resolution=resolution,
        data_type=data_type,
        adjust=adjust,
        sources=sources or scope_sources,
        include_research_sources=include_research_sources,
        persist=persist_report,
    )
    certified_ids = _certify_consistent_production_datasets(consistency)
    return {
        "scopeCount": len(scopes),
        "rebuiltCount": len(rebuilt),
        "errorCount": len(errors),
        "rebuilt": rebuilt,
        "errors": errors,
        "consistencyReport": consistency,
        "certifiedDatasetIds": certified_ids,
    }


def list_datasets() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select *
            from parquet_datasets
            order by updated_at desc, dataset_key asc
            """
        ).fetchall()
    return rows_to_dicts(rows)


def _sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _dataset_files(scope: dict[str, str]) -> tuple[dict[str, Any] | None, list[str]]:
    key = _dataset_key(**scope)
    with db() as connection:
        dataset = connection.execute("select * from parquet_datasets where dataset_key = ?", (key,)).fetchone()
        if dataset is None:
            return None, []
        files = connection.execute(
            """
            select file_path
            from parquet_files
            where dataset_id = ?
            order by first_timestamp asc, file_path asc
            """,
            (dataset["id"],),
        ).fetchall()
    return dict(dataset), [str(_visible_parquet_path(row["file_path"])) for row in files]


def query_duckdb_bars(
    *,
    asset_class: str = "equity",
    symbol: str,
    market: str | None = None,
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    provider_source: str = "akshare",
    adjust: str = "raw",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
    allow_research_source: bool = False,
) -> dict[str, Any]:
    if duckdb is None:
        return {"enabled": False, "source": "duckdb", "items": [], "count": 0, "error": "duckdb is not installed"}
    source_context = resolve_source_context(
        {},
        source=provider_source,
        allow_research_source=allow_research_source,
        asset_class=asset_class,
        market=market or venue or "china",
        venue=venue or market,
    )
    provider_source = str(source_context["source"])
    scope = _normalize_scope(asset_class, market or venue or "china", venue, resolution, data_type, adjust, provider_source)
    dataset, files = _dataset_files(scope)
    if not dataset or not files:
        return {"enabled": True, "source": "duckdb", "items": [], "count": 0, "message": "No matching Parquet dataset metadata found."}
    paths = ", ".join(_sql_string(path) for path in files)
    predicates = ["symbol = ?"]
    params: list[Any] = [_query_symbol(symbol, scope)]
    if start_date:
        predicates.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        predicates.append("trade_date <= ?")
        params.append(end_date)
    bounded_limit = max(1, min(int(limit), 5000))
    params.append(bounded_limit)
    sql = f"""
        select trade_date, open, high, low, close, volume, source
        from read_parquet([{paths}])
        where {" and ".join(predicates)}
        order by trade_date asc, source asc
        limit ?
    """
    rows = duckdb.connect(database=":memory:").execute(sql, params).fetchall()
    items = [
        {
            "timestamp": str(row[0]),
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
            "volume": row[5],
            "source": row[6],
        }
        for row in rows
    ]
    return {
        "enabled": True,
        "source": "duckdb",
        "dataset": {"id": dataset["id"], "datasetKey": dataset["dataset_key"]},
        "items": items,
        "count": len(items),
    }
