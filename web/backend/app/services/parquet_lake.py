from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Callable

from ..core.config import PARQUET_COMPRESSION, PARQUET_DIR, PARQUET_PARTITION_ROWS
from ..db import database_backend, db, json_dump, rows_to_dicts, utc_now
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
MARKET_DAILY_BAR_TEXT_COLUMNS = (
    "instrument_id",
    "symbol",
    "asset_class",
    "market",
    "venue",
    "trade_date",
    "resolution",
    "data_type",
    "adjust",
    "source",
    "batch_id",
    "created_at",
)
MARKET_DAILY_BAR_NUMERIC_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "settle",
    "volume",
    "amount",
    "turnover_rate",
    "open_interest",
    "prev_close",
    "pct_change",
    "adj_factor",
)


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


def _iter_market_row_batches(
    scope: dict[str, str],
    start_date: str | None,
    end_date: str | None,
    *,
    batch_size: int = 100_000,
):
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
    table = "market_daily_bars force index (primary)" if database_backend() == "mysql" else "market_daily_bars"
    sql = f"""
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
            from {table}
            where {" and ".join(predicates)}
            order by instrument_id asc, trade_date asc
            """
    with db() as connection:
        if hasattr(connection, "iter_batches"):
            yield from connection.iter_batches(sql, params, batch_size=batch_size)
            return
        cursor = connection.execute(sql, params)
        while True:
            rows = cursor.fetchmany(max(1, int(batch_size)))
            if not rows:
                break
            yield rows_to_dicts(rows)


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
    expected_row_count: int | None = None,
) -> dict[str, Any]:
    if scope["source"] != PRIMARY_DATA_SOURCE or scope["asset_class"] != "equity":
        return {"required": False, "passed": True, "batchCount": 0, "invalidBatches": []}

    # A governed full rebuild is the preferred lineage proof. It avoids
    # grouping the complete canonical table by every historical import batch,
    # which is both redundant and prohibitively expensive after years of
    # incremental updates. Certification remains fail-closed: canonical,
    # manifest and archived raw row counts must match exactly, every manifest
    # must have succeeded without rejected rows, and every archive must still
    # resolve to stored chunks.
    if expected_row_count is not None:
        with db() as connection:
            governed_run = connection.execute(
                """
                select id,mode,summary_json from data_sync_runs
                where provider=? and status='success' and canonical_status='ready'
                  and mode in ('initial_full','full_rebuild','resume_checkpoint')
                order by finished_at desc limit 1
                """,
                (PRIMARY_DATA_SOURCE,),
            ).fetchone()
            if governed_run:
                manifest = connection.execute(
                    """
                    select count(*) as manifest_count,
                           sum(response_rows) as response_rows,
                           sum(rejected_rows) as rejected_rows,
                           sum(case when status='success' then 0 else 1 end) as failed_manifests
                    from provider_ingestion_manifests
                    where run_id=? and provider=? and dataset_key='daily'
                    """,
                    (governed_run["id"], PRIMARY_DATA_SOURCE),
                ).fetchone()
                archive = connection.execute(
                    """
                    select count(*) as archive_count,sum(a.row_count) as archived_rows
                    from provider_raw_archives a
                    join stored_objects o on o.id=a.object_id
                    where a.run_id=? and a.provider=? and a.dataset_key='daily'
                      and exists (select 1 from stored_object_chunks c where c.object_id=o.id)
                    """,
                    (governed_run["id"], PRIMARY_DATA_SOURCE),
                ).fetchone()
            else:
                manifest = None
                archive = None
        governed_run = dict(governed_run) if governed_run else None
        manifest = dict(manifest) if manifest else None
        archive = dict(archive) if archive else None
        if governed_run:
            try:
                run_summary = json.loads(governed_run["summary_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                run_summary = {}
            daily_evidence = next(
                (
                    item
                    for item in (run_summary.get("completionEvidence") or {}).get("items", [])
                    if item.get("datasetKey") == "daily"
                ),
                {},
            )
            effective_mode = str(governed_run.get("mode") or "")
            if effective_mode == "resume_checkpoint":
                effective_mode = str(run_summary.get("resumeBaseMode") or run_summary.get("mode") or "")
            response_rows = int((manifest or {}).get("response_rows") or 0)
            archived_rows = int((archive or {}).get("archived_rows") or 0)
            passed = bool(
                effective_mode in {"initial_full", "full_rebuild"}
                and daily_evidence.get("passed")
                and int(daily_evidence.get("responseRows") or 0) == expected_row_count
                and int((manifest or {}).get("manifest_count") or 0) > 0
                and int((manifest or {}).get("failed_manifests") or 0) == 0
                and int((manifest or {}).get("rejected_rows") or 0) == 0
                and response_rows == expected_row_count
                and int((archive or {}).get("archive_count") or 0) > 0
                and archived_rows == expected_row_count
            )
            if passed:
                return {
                    "required": True,
                    "passed": True,
                    "validationMode": "governed_full_rebuild",
                    "runId": str(governed_run["id"]),
                    "batchCount": int((manifest or {}).get("manifest_count") or 0),
                    "responseRows": response_rows,
                    "archivedRows": archived_rows,
                    "invalidBatches": [],
                }
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
        grouped_rows = connection.execute(
            f"""
            select m.batch_id, m.symbol, count(*) as row_count
            from market_daily_bars m
            where {" and ".join(predicates)}
            group by m.batch_id, m.symbol
            """,
            params,
        ).fetchall()
        batch_ids = sorted(
            {
                str(row["batch_id"])
                for row in grouped_rows
                if row["batch_id"]
            }
        )
        batch_metadata: dict[str, dict[str, Any]] = {}
        for offset in range(0, len(batch_ids), 400):
            chunk = batch_ids[offset : offset + 400]
            placeholders = ",".join("?" for _ in chunk)
            batch_rows = connection.execute(
                f"""
                select id, provider, status, config_json, qa_report_json
                from data_import_batches
                where id in ({placeholders})
                """,
                chunk,
            ).fetchall()
            batch_metadata.update(
                {str(row["id"]): dict(row) for row in batch_rows}
            )
    parsed_rows: list[tuple[Any, dict[str, Any], dict[str, Any]]] = []
    sync_run_ids: set[str] = set()
    parsed_batch_metadata: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for grouped_row in grouped_rows:
        batch_id = str(grouped_row["batch_id"] or "")
        metadata = batch_metadata.get(batch_id) or {}
        if batch_id not in parsed_batch_metadata:
            try:
                qa_report = json.loads(metadata.get("qa_report_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                qa_report = {}
            try:
                batch_config = json.loads(metadata.get("config_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                batch_config = {}
            parsed_batch_metadata[batch_id] = (qa_report, batch_config)
        qa_report, batch_config = parsed_batch_metadata[batch_id]
        row = {
            **dict(grouped_row),
            "provider": metadata.get("provider"),
            "status": metadata.get("status"),
        }
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

    # A governed full rebuild may prove that existing canonical rows are
    # byte-for-byte unchanged. In that case rewriting millions of identical
    # rows only to replace batch_id is unnecessary write amplification. Accept
    # the latest completed run-level lineage after its per-symbol manifest,
    # raw archive and completion evidence have all passed; the consistency
    # report below still compares canonical MySQL and Parquet contents.
    governed_run_id: str | None = None
    governed_manifests: dict[str, dict[str, Any]] = {}
    with db() as connection:
        governed_run = connection.execute(
            """
            select id,mode,summary_json from data_sync_runs
            where provider=? and status='success' and canonical_status='ready'
              and mode in ('initial_full','full_rebuild','resume_checkpoint')
            order by finished_at desc limit 1
            """,
            (PRIMARY_DATA_SOURCE,),
        ).fetchone()
        if governed_run:
            try:
                run_summary = json.loads(governed_run["summary_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                run_summary = {}
            daily_evidence = next(
                (
                    item for item in (run_summary.get("completionEvidence") or {}).get("items", [])
                    if item.get("datasetKey") == "daily"
                ),
                {},
            )
            effective_mode = str(governed_run["mode"] or "")
            if effective_mode == "resume_checkpoint":
                effective_mode = str(run_summary.get("resumeBaseMode") or run_summary.get("mode") or "")
            candidate_run_id = str(governed_run["id"])
            if effective_mode in {"initial_full", "full_rebuild"} and daily_evidence.get("passed"):
                archive = connection.execute(
                    """
                    select count(*) as count from provider_raw_archives a
                    join stored_objects o on o.id=a.object_id
                    where a.run_id=? and a.dataset_key='daily'
                      and exists (select 1 from stored_object_chunks c where c.object_id=o.id)
                    """,
                    (candidate_run_id,),
                ).fetchone()
                if archive and int(archive["count"] or 0) > 0:
                    governed_run_id = candidate_run_id
                    governed_manifests = {
                        str(item["scope_key"]): dict(item)
                        for item in connection.execute(
                            """
                            select scope_key,status,response_rows,rejected_rows
                            from provider_ingestion_manifests
                            where run_id=? and provider=? and dataset_key='daily'
                            """,
                            (candidate_run_id, PRIMARY_DATA_SOURCE),
                        ).fetchall()
                    }

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
            and (
                str(provenance.get("scopeKey") or "") == symbol
                or symbol in {str(item) for item in (provenance.get("scopeKeys") or [])}
            )
            and str(manifest.get("status") or "").lower() == "success"
            and int(manifest.get("response_rows") or 0) > 0
            and int(manifest.get("rejected_rows") or 0) == 0
            and sync_run_id in archive_evidence
        )
        governed_manifest = governed_manifests.get(symbol) or {}
        run_level_evidence_valid = bool(
            governed_run_id
            and str(governed_manifest.get("status") or "").lower() == "success"
            and int(governed_manifest.get("response_rows") or 0) > 0
            and int(governed_manifest.get("rejected_rows") or 0) == 0
        )
        evidence_valid = evidence_valid or run_level_evidence_valid
        batch_controls_valid = bool(
            (
                str(row["status"] or "").lower() == "success"
                and qa_report.get("passed") is True
                and declared_environment == "production"
            )
            or run_level_evidence_valid
        )
        valid = bool(
            row["batch_id"]
            and str(row["provider"] or "").lower() == PRIMARY_DATA_SOURCE
            and batch_controls_valid
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
        "passed": bool(grouped_rows) and not invalid,
        "batchCount": len(grouped_rows),
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


def _write_partition(frame: Any, root: Path, year: int, *, part_name: str = "part-00000") -> dict[str, Any]:
    partition_dir = root / f"year={year}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    path = partition_dir / f"{part_name}.parquet"
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


def _market_daily_bar_frame(rows: list[dict[str, Any]]) -> Any:
    """Build a stable frame without sample-based numeric type inference."""
    schema_overrides = {
        **{column: pl.Utf8 for column in MARKET_DAILY_BAR_TEXT_COLUMNS},
        **{column: pl.Float64 for column in MARKET_DAILY_BAR_NUMERIC_COLUMNS},
    }
    return pl.DataFrame(rows, schema_overrides=schema_overrides, strict=False)


def _upsert_dataset(
    scope: dict[str, str],
    root: Path,
    row_stats: dict[str, Any],
    files: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    key = _dataset_key(**scope)
    dataset_id = _dataset_id(key)
    row_count = int(row_stats.get("rowCount") or 0)
    first_date = str(row_stats.get("firstDate")) if row_stats.get("firstDate") else None
    last_date = str(row_stats.get("lastDate")) if row_stats.get("lastDate") else None
    root_path = _logical_parquet_path(root)
    file_manifest = sorted([
        {
            "path": _logical_parquet_path(item["path"]),
            "rowCount": item["row_count"],
            "sha256": item["sha256"],
        }
        for item in files
    ], key=lambda item: item["path"])
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
                row_count,
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
        "rowCount": row_count,
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
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    incremental: bool = False,
) -> dict[str, Any]:
    if pl is None:
        raise RuntimeError("polars is required to export Parquet datasets.")
    scope = _normalize_scope(asset_class, market, venue, resolution, data_type, adjust, source)
    requested_stats = _market_row_count(scope, start_date, end_date)
    row_stats = _market_row_count(scope) if incremental else requested_stats
    root = _dataset_root(scope)
    root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    retained_files: list[dict[str, Any]] = []
    affected_start_year = int(start_date[:4]) if incremental and start_date else None
    affected_end_year = int(end_date[:4]) if incremental and end_date else date.today().year
    if incremental and affected_start_year is not None:
        dataset_id = _dataset_id(_dataset_key(**scope))
        for item in _parquet_files_for_dataset(dataset_id):
            partition = item.get("partition") or {}
            year = int(partition.get("year") or str(item.get("first_timestamp") or "")[:4] or 0)
            if affected_start_year <= year <= affected_end_year:
                continue
            filename = Path(str(item.get("file_path") or "")).name
            physical_path = root / f"year={year}" / filename
            if not physical_path.exists():
                continue
            retained_files.append(
                {
                    "path": physical_path,
                    "partition": {"year": year},
                    "row_count": int(item.get("row_count") or 0),
                    "first_timestamp": item.get("first_timestamp"),
                    "last_timestamp": item.get("last_timestamp"),
                    "sha256": item.get("sha256"),
                    "size": int(item.get("size") or 0),
                }
            )
    part_counts: dict[int, int] = {}
    partition_buffers: dict[int, list[Any]] = {}
    partition_buffer_rows: dict[int, int] = {}
    partition_target_rows = PARQUET_PARTITION_ROWS
    exported_rows = 0
    expected_rows = int(requested_stats.get("rowCount") or 0)

    def flush_year(year: int) -> None:
        frames = partition_buffers.pop(year, [])
        partition_buffer_rows.pop(year, None)
        if not frames:
            return
        partition = pl.concat(frames, rechunk=True) if len(frames) > 1 else frames[0]
        part_index = part_counts.get(year, 0)
        files.append(
            _write_partition(
                partition,
                root,
                year,
                part_name=f"part-{part_index:05d}",
            )
        )
        part_counts[year] = part_index + 1

    for rows in _iter_market_row_batches(scope, start_date, end_date):
        if not rows:
            continue
        frame = _market_daily_bar_frame(rows).with_columns(
            pl.col("trade_date").str.slice(0, 4).cast(pl.Int32).alias("year")
        )
        # partition_by performs one linear split. Filtering the full 100k-row
        # frame once per distinct year multiplied CPU by the complete history
        # depth and could starve the Docker control plane during a rebuild.
        year_partitions = frame.partition_by("year", maintain_order=True)
        for year_frame in year_partitions:
            year_value = int(year_frame.get_column("year")[0])
            partition = year_frame.drop("year")
            partition_buffers.setdefault(year_value, []).append(partition)
            partition_buffer_rows[year_value] = partition_buffer_rows.get(year_value, 0) + partition.height
            if partition_buffer_rows[year_value] >= partition_target_rows:
                flush_year(year_value)
        exported_rows += len(rows)
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "parquet_export",
                    "scope": scope,
                    "rowsProcessed": exported_rows,
                    "expectedRows": expected_rows,
                    "fileCount": len(files),
                }
            )
    for year in sorted(partition_buffers):
        flush_year(year)
    if exported_rows != expected_rows:
        raise RuntimeError(
            f"parquet_export_row_count_mismatch: expected={expected_rows} exported={exported_rows}"
        )
    expected_paths = {item["path"].resolve() for item in files}
    existing_candidates = (
        (
            existing
            for year in range(affected_start_year, affected_end_year + 1)
            for existing in (root / f"year={year}").glob("*.parquet")
        )
        if incremental and affected_start_year is not None
        else root.glob("year=*/*.parquet")
    )
    for existing in existing_candidates:
        if existing.resolve() not in expected_paths:
            existing.unlink()
    all_files = [*retained_files, *files]
    metadata = {
        "exported_from": "market_daily_bars",
        "compression": PARQUET_COMPRESSION,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "read_batch": "streaming_cursor_100000_rows",
        "partition_write_target_rows": partition_target_rows,
        "source_order": "instrument_id_trade_date",
        "maintenance_mode": "incremental_year_rewrite" if incremental else "full_rebuild",
    }
    return _upsert_dataset(scope, root, row_stats, all_files, metadata)


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
        source_lineage = _market_source_lineage(
            scope,
            dataset.get("start_date"),
            dataset.get("end_date"),
            expected_row_count=int(mysql_counts.get("rowCount") or 0),
        )
        duckdb_counts = {"enabled": duckdb is not None, "rowCount": None, "firstDate": None, "lastDate": None, "error": None}
        if duckdb is not None and files and not missing_files:
            paths = ", ".join(_sql_string(str(item["visible_path"])) for item in resolved_files)
            duckdb_connection = None
            try:
                duckdb_connection = duckdb.connect(database=":memory:")
                duckdb_connection.execute("set memory_limit='128MB'")
                duckdb_connection.execute("set threads=1")
                duckdb_connection.execute("set preserve_insertion_order=false")
                row = duckdb_connection.execute(
                    f"""
                    select count(*) as row_count, min(trade_date) as first_date, max(trade_date) as last_date
                    from read_parquet([{paths}])
                    """
                ).fetchone()
                duckdb_counts.update({"rowCount": row[0], "firstDate": str(row[1]) if row[1] is not None else None, "lastDate": str(row[2]) if row[2] is not None else None})
            except Exception as exc:
                duckdb_counts["error"] = str(exc)
            finally:
                if duckdb_connection is not None:
                    duckdb_connection.close()
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
    report_issues: list[str] = []
    if normalized_sources and not items:
        report_issues.append("parquet_dataset_missing")
    severity = (
        "critical"
        if report_issues or any(item["severity"] == "critical" for item in items)
        else ("warning" if any(item["severity"] == "warning" for item in items) else "ok")
    )
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
        "issues": report_issues,
        "items": items,
    }
    if persist:
        report["reportId"] = _persist_consistency_report(report)
    return report


def _certify_consistent_production_datasets(report: dict[str, Any]) -> list[str]:
    """Promote only immutable, non-empty TuShare datasets proven by a persisted QA report."""
    report_id = report.get("reportId")
    if not report_id:
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
            file_rows = connection.execute(
                "select file_path,row_count,sha256 from parquet_files where dataset_id=? order by file_path",
                (dataset_id,),
            ).fetchall()
            file_manifest = [
                {
                    "path": str(file_row["file_path"]),
                    "rowCount": int(file_row["row_count"] or 0),
                    "sha256": str(file_row["sha256"] or ""),
                }
                for file_row in file_rows
            ]
            if not file_manifest:
                continue
            manifest_sha256 = hashlib.sha256(json_dump(file_manifest).encode("utf-8")).hexdigest()
            dataset_version = f"{PRIMARY_DATA_SOURCE}-{dataset_id[:12]}-{manifest_sha256[:12]}"
            connection.execute(
                """
                update parquet_datasets
                set environment = 'production',
                    is_production = 1,
                    is_certified = 1,
                    dataset_version = ?,
                    certified_at = ?,
                    certified_by = 'parquet-consistency-v1',
                    qa_status = 'ok',
                    qa_report_id = ?,
                    updated_at = ?
                where id = ? and source = ?
                """,
                (dataset_version, certified_at, report_id, certified_at, dataset_id, PRIMARY_DATA_SOURCE),
            )
            certified_ids.append(dataset_id)
    return certified_ids


def certify_consistent_production_datasets(report: dict[str, Any]) -> list[str]:
    """Public recovery entrypoint; certification remains gated by persisted consistency evidence."""
    return _certify_consistent_production_datasets(report)


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
            rebuilt.append(
                export_market_daily_bars(
                    **scope,
                    start_date=start_date,
                    end_date=end_date,
                    progress_callback=progress_callback,
                )
            )
        except Exception as exc:
            errors.append({"scope": scope, "error": str(exc)})
            if not continue_on_error:
                raise
    scope_sources = sorted({scope["source"] for scope in scopes})
    if progress_callback is not None:
        progress_callback(
            {
                "stage": "parquet_consistency",
                "scopeCount": len(scopes),
                "rebuiltCount": len(rebuilt),
            }
        )
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
