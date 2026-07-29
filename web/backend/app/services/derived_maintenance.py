from __future__ import annotations

from datetime import date
import hashlib
import uuid
from typing import Any

from ..db import database_backend, db, json_dump, row_to_dict, rows_to_dicts, utc_now


LAYERS = ("parquet", "clickhouse")
MAINTENANCE_LOCK_NAME = "lean:derived:scheduled-maintenance"


def _scope_key(scope: dict[str, str]) -> str:
    return "|".join(
        scope[key]
        for key in ("asset_class", "market", "venue", "resolution", "data_type", "adjust")
    )


def _scope_from_key(scope_key: str, source: str) -> dict[str, str]:
    values = scope_key.split("|")
    if len(values) != 6:
        return {"scopeKey": scope_key, "source": source}
    return {
        "assetClass": values[0],
        "market": values[1],
        "venue": values[2],
        "resolution": values[3],
        "dataType": values[4],
        "adjust": values[5],
        "scopeKey": scope_key,
        "source": source,
    }


def create_maintenance_run(
    *,
    layers: list[str] | None = None,
    trigger_type: str = "manual",
) -> dict[str, Any]:
    selected = list(dict.fromkeys(str(item).strip().lower() for item in (layers or LAYERS)))
    unsupported = [item for item in selected if item not in LAYERS]
    if unsupported:
        raise ValueError(f"Unsupported derived layers: {', '.join(unsupported)}.")
    run_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into derived_maintenance_runs
                (id,trigger_type,status,requested_layers_json,summary_json,created_at)
            values (?,?,?,?,?,?)
            """,
            (run_id, trigger_type, "queued", json_dump(selected), json_dump({}), now),
        )
    return maintenance_run(run_id) or {}


def maintenance_run(run_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from derived_maintenance_runs where id=?", (run_id,)).fetchone()
    return row_to_dict(row)


def _watermark(layer: str, scope_key: str, source: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            """
            select * from derived_layer_watermarks
            where layer_key=? and scope_key=? and source=?
            """,
            (layer, scope_key, source),
        ).fetchone()
    return row_to_dict(row)


def _upsert_watermark(
    layer: str,
    scope: dict[str, str],
    *,
    status: str,
    canonical_start: str | None,
    canonical_end: str | None,
    materialized_start: str | None = None,
    materialized_end: str | None = None,
    row_count: int = 0,
    dataset_id: str | None = None,
    content_sha256: str | None = None,
    run_id: str,
    error: str | None = None,
    details: dict[str, Any] | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> None:
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into derived_layer_watermarks
                (layer_key,scope_key,source,canonical_start,canonical_end,
                 materialized_start,materialized_end,status,row_count,dataset_id,
                 content_sha256,last_maintenance_run_id,error,details_json,
                 started_at,completed_at,updated_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            on conflict(layer_key,scope_key,source) do update set
                canonical_start=excluded.canonical_start,
                canonical_end=excluded.canonical_end,
                materialized_start=coalesce(excluded.materialized_start,derived_layer_watermarks.materialized_start),
                materialized_end=coalesce(excluded.materialized_end,derived_layer_watermarks.materialized_end),
                status=excluded.status,
                row_count=excluded.row_count,
                dataset_id=coalesce(excluded.dataset_id,derived_layer_watermarks.dataset_id),
                content_sha256=coalesce(excluded.content_sha256,derived_layer_watermarks.content_sha256),
                last_maintenance_run_id=excluded.last_maintenance_run_id,
                error=excluded.error,
                details_json=excluded.details_json,
                started_at=coalesce(excluded.started_at,derived_layer_watermarks.started_at),
                completed_at=excluded.completed_at,
                updated_at=excluded.updated_at
            """,
            (
                layer,
                _scope_key(scope),
                scope["source"],
                canonical_start,
                canonical_end,
                materialized_start,
                materialized_end,
                status,
                row_count,
                dataset_id,
                content_sha256,
                run_id,
                error,
                json_dump(details or {}),
                started_at,
                completed_at,
                now,
            ),
        )


def _canonical_stats(scope: dict[str, str]) -> dict[str, Any]:
    predicates = " and ".join(f"{key}=?" for key in ("asset_class", "market", "venue", "resolution", "data_type", "adjust", "source"))
    values = [scope[key] for key in ("asset_class", "market", "venue", "resolution", "data_type", "adjust", "source")]
    with db() as connection:
        row = connection.execute(
            f"""
            select count(*) as row_count,min(trade_date) as first_date,max(trade_date) as last_date
            from market_daily_bars where {predicates}
            """,
            values,
        ).fetchone()
    return dict(row) if row else {"row_count": 0, "first_date": None, "last_date": None}


def _parquet_incremental_start(
    scope: dict[str, str],
    prior: dict[str, Any],
    *,
    current_row_count: int,
) -> str | None:
    """Choose the earliest year that may have changed since a proven export."""
    prior_end = str(prior.get("materialized_end") or "")
    dataset_id = str(prior.get("dataset_id") or "")
    if not prior_end or not dataset_id:
        return None

    with db() as connection:
        file_total = connection.execute(
            "select sum(row_count) as row_count from parquet_files where dataset_id=?",
            (dataset_id,),
        ).fetchone()
        registered_row_count = int(file_total["row_count"] or 0) if file_total else 0
        successful = connection.execute(
            """
            select max(finished_at) as finished_at
            from derived_maintenance_runs
            where status='success' and requested_layers_json like ?
            """,
            ('%"parquet"%',),
        ).fetchone()
        last_success = str(successful["finished_at"] or "") if successful else ""
        change_since = (
            str(prior.get("completed_at") or "")
            if registered_row_count == current_row_count
            else last_success
        ) or last_success
        if not change_since:
            return None

        predicates = " and ".join(
            f"{key}=?" for key in (
                "asset_class",
                "market",
                "venue",
                "resolution",
                "data_type",
                "adjust",
                "source",
            )
        )
        scope_values = [
            scope[key] for key in (
                "asset_class",
                "market",
                "venue",
                "resolution",
                "data_type",
                "adjust",
                "source",
            )
        ]
        changed = connection.execute(
            f"""
            select min(trade_date) as first_date
            from market_daily_bars
            where {predicates} and created_at > ?
            """,
            [*scope_values, change_since],
        ).fetchone()

        candidate_years = {int(prior_end[:4])}
        changed_date = str(changed["first_date"] or "") if changed else ""
        if changed_date:
            candidate_years.add(int(changed_date[:4]))

        if registered_row_count != current_row_count:
            canonical_years = connection.execute(
                f"""
                select substr(trade_date,1,4) as year,count(*) as row_count
                from market_daily_bars
                where {predicates}
                group by substr(trade_date,1,4)
                """,
                scope_values,
            ).fetchall()
            parquet_years = connection.execute(
                """
                select substr(first_timestamp,1,4) as year,sum(row_count) as row_count
                from parquet_files
                where dataset_id=?
                group by substr(first_timestamp,1,4)
                """,
                (dataset_id,),
            ).fetchall()
            canonical_counts = {
                str(row["year"]): int(row["row_count"] or 0)
                for row in canonical_years
            }
            parquet_counts = {
                str(row["year"]): int(row["row_count"] or 0)
                for row in parquet_years
            }
            mismatched_years = {
                int(year)
                for year in set(canonical_counts) | set(parquet_counts)
                if canonical_counts.get(year, 0) != parquet_counts.get(year, 0)
            }
            if mismatched_years:
                candidate_years.add(min(mismatched_years))
            else:
                return None

    return f"{min(candidate_years):04d}-01-01"


def _existing_layer_seed(layer: str, scope: dict[str, str], stats: dict[str, Any]) -> dict[str, Any]:
    """Adopt only an existing derived layer that exactly matches canonical coverage."""
    if layer == "parquet":
        with db() as connection:
            row = connection.execute(
                """
                select id,start_date,end_date,row_count,is_certified,qa_status
                from parquet_datasets
                where asset_class=? and market=? and venue=? and resolution=?
                  and data_type=? and adjust=? and source=?
                order by updated_at desc limit 1
                """,
                (
                    scope["asset_class"],
                    scope["market"],
                    scope["venue"],
                    scope["resolution"],
                    scope["data_type"],
                    scope["adjust"],
                    scope["source"],
                ),
            ).fetchone()
        item = dict(row) if row else {}
        matches = bool(
            item
            and int(item.get("is_certified") or 0) == 1
            and item.get("qa_status") == "ok"
            and int(item.get("row_count") or 0) == int(stats.get("row_count") or 0)
            and str(item.get("start_date") or "") == str(stats.get("first_date") or "")
            and str(item.get("end_date") or "") == str(stats.get("last_date") or "")
        )
        if not matches:
            return {}
        return {
            "materialized_start": item["start_date"],
            "materialized_end": item["end_date"],
            "row_count": int(item["row_count"]),
            "dataset_id": item["id"],
            "seededFromExisting": True,
        }

    from . import market_data

    try:
        item = market_data.scope_stats(scope)
    except Exception:
        return {}
    matches = bool(
        item.get("enabled")
        and int(item.get("rowCount") or 0) == int(stats.get("row_count") or 0)
        and str(item.get("firstDate") or "") == str(stats.get("first_date") or "")
        and str(item.get("lastDate") or "") == str(stats.get("last_date") or "")
    )
    if not matches:
        return {}
    return {
        "materialized_start": item["firstDate"],
        "materialized_end": item["lastDate"],
        "row_count": int(item["rowCount"]),
        "seededFromExisting": True,
    }


def _canonical_date_counts(scope: dict[str, str]) -> dict[str, int]:
    predicates = " and ".join(
        f"{key}=?" for key in ("asset_class", "market", "venue", "resolution", "data_type", "adjust", "source")
    )
    values = [
        scope[key]
        for key in ("asset_class", "market", "venue", "resolution", "data_type", "adjust", "source")
    ]
    with db() as connection:
        rows = connection.execute(
            f"""
            select trade_date,count(*) as row_count
            from market_daily_bars
            where {predicates}
            group by trade_date
            order by trade_date
            """,
            values,
        ).fetchall()
    return {str(row["trade_date"]): int(row["row_count"]) for row in rows}


def _clickhouse_reconcile_dates(scope: dict[str, str]) -> dict[str, Any]:
    """Repair missing ClickHouse dates without hiding surplus derived rows."""
    from . import market_data

    canonical_counts = _canonical_date_counts(scope)
    derived_counts = market_data.scope_date_counts(scope)
    surplus_dates = sorted(
        item_date
        for item_date, row_count in derived_counts.items()
        if row_count > canonical_counts.get(item_date, 0)
    )
    if surplus_dates:
        return {
            "status": "failed",
            "enabled": True,
            "inserted": 0,
            "mode": "date_count_reconciliation",
            "errors": [
                {
                    "error": "clickhouse_surplus_rows_require_explicit_rebuild",
                    "dates": surplus_dates[:20],
                }
            ],
        }

    repair_dates = sorted(
        item_date
        for item_date, row_count in canonical_counts.items()
        if derived_counts.get(item_date, 0) < row_count
    )
    inserted = 0
    skipped = 0
    batches = 0
    errors: list[dict[str, Any]] = []
    scope_columns = ("asset_class", "market", "venue", "resolution", "data_type", "adjust", "source")
    scope_predicates = " and ".join(f"{key}=?" for key in scope_columns)
    scope_values = [scope[key] for key in scope_columns]

    for offset in range(0, len(repair_dates), 100):
        date_chunk = repair_dates[offset : offset + 100]
        placeholders = ",".join("?" for _ in date_chunk)
        with db() as connection:
            rows = connection.execute(
                f"""
                select symbol,trade_date,open,high,low,close,volume
                from market_daily_bars
                where {scope_predicates} and trade_date in ({placeholders})
                order by symbol,trade_date
                """,
                [*scope_values, *date_chunk],
            ).fetchall()
        by_symbol: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row)
            symbol = str(item.pop("symbol"))
            item["date"] = str(item.pop("trade_date"))
            by_symbol.setdefault(symbol, []).append(item)
        entries = [
            (
                {
                    "asset_class": scope["asset_class"],
                    "symbol": symbol,
                    "market": scope["market"],
                    "venue": scope["venue"],
                    "resolution": scope["resolution"],
                    "data_type": scope["data_type"],
                    "source": scope["source"],
                },
                items,
            )
            for symbol, items in by_symbol.items()
        ]
        results = market_data.mirror_rows_batch(entries)
        inserted += sum(int(result.get("inserted") or 0) for result in results)
        skipped += sum(int(result.get("skipped") or 0) for result in results)
        batches += max((int(result.get("batches") or 0) for result in results), default=0)
        errors.extend(
            {"error": str(result["error"])[:500]}
            for result in results
            if result.get("error")
        )
        if errors:
            break

    stats = market_data.scope_stats(scope)
    expected_rows = sum(canonical_counts.values())
    exact = bool(
        not errors
        and int(stats.get("rowCount") or 0) == expected_rows
        and str(stats.get("firstDate") or "") == (min(canonical_counts) if canonical_counts else "")
        and str(stats.get("lastDate") or "") == (max(canonical_counts) if canonical_counts else "")
    )
    if not exact and not errors:
        errors.append(
            {
                "error": "clickhouse_reconciliation_mismatch",
                "expectedRows": expected_rows,
                "actualRows": int(stats.get("rowCount") or 0),
            }
        )
    return {
        "status": "ready" if exact else "failed",
        "enabled": True,
        "mode": "date_count_reconciliation",
        "repairDates": len(repair_dates),
        "inserted": inserted,
        "skipped": skipped,
        "batches": batches,
        "errors": errors[:20],
    }


def _clickhouse_incremental(scope: dict[str, str], start_date: str | None) -> dict[str, Any]:
    from . import market_data

    if not market_data.enabled():
        return {"status": "disabled", "enabled": False, "inserted": 0}
    if not start_date:
        return _clickhouse_reconcile_dates(scope)
    predicates = [
        "asset_class=?",
        "market=?",
        "venue=?",
        "resolution=?",
        "data_type=?",
        "adjust=?",
        "source=?",
    ]
    values: list[Any] = [
        scope["asset_class"],
        scope["market"],
        scope["venue"],
        scope["resolution"],
        scope["data_type"],
        scope["adjust"],
        scope["source"],
    ]
    if start_date:
        predicates.append("trade_date>=?")
        values.append(start_date)
    with db() as connection:
        symbols = [
            str(row["symbol"])
            for row in connection.execute(
                f"select distinct symbol from market_daily_bars where {' and '.join(predicates)} order by symbol",
                values,
            ).fetchall()
        ]
    inserted = 0
    skipped = 0
    batches = 0
    errors: list[dict[str, str]] = []
    pending: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    pending_rows = 0

    def flush() -> None:
        nonlocal inserted, skipped, batches, pending, pending_rows
        if not pending:
            return
        results = market_data.mirror_rows_batch(pending)
        for (metadata, _rows), result in zip(pending, results, strict=True):
            inserted += int(result.get("inserted") or 0)
            skipped += int(result.get("skipped") or 0)
            batches += int(result.get("batches") or 0)
            if result.get("error"):
                errors.append({"symbol": str(metadata["symbol"]), "error": str(result["error"])[:500]})
        pending = []
        pending_rows = 0

    for symbol in symbols:
        bars = market_data.query_database_bars(
            asset_class=scope["asset_class"],
            symbol=symbol,
            market=scope["market"],
            venue=scope["venue"],
            resolution=scope["resolution"],
            data_type=scope["data_type"],
            provider_source=scope["source"],
            start_date=start_date,
            limit=0,
        )["items"]
        pending.append(
            (
                {
                    "symbol": symbol,
                    "asset_class": scope["asset_class"],
                    "market": scope["market"],
                    "venue": scope["venue"],
                    "resolution": scope["resolution"],
                    "data_type": scope["data_type"],
                    "source": scope["source"],
                },
                bars,
            )
        )
        pending_rows += len(bars)
        if len(pending) >= 100 or pending_rows >= 500_000:
            flush()
    flush()
    return {
        "status": "failed" if errors else "ready",
        "enabled": True,
        "symbols": len(symbols),
        "inserted": inserted,
        "skipped": skipped,
        "batches": batches,
        "errors": errors[:20],
    }


def _run_locked(run_id: str) -> dict[str, Any]:
    from .parquet_lake import (
        _available_scopes,
        certify_consistent_production_datasets,
        export_market_daily_bars,
        parquet_consistency_report,
    )

    run = maintenance_run(run_id)
    if not run:
        raise ValueError(f"Derived maintenance run {run_id} not found.")
    if run["status"] == "success":
        return run
    layers = list(run.get("requested_layers") or LAYERS)
    started = utc_now()
    with db() as connection:
        connection.execute(
            "update derived_maintenance_runs set status='running',started_at=?,error=null where id=?",
            (started, run_id),
        )
    scopes = _available_scopes(include_research_sources=False)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    canonical_end = max((str(_canonical_stats(scope).get("last_date") or "") for scope in scopes), default="") or None
    try:
        for scope in scopes:
            stats = _canonical_stats(scope)
            scope_key = _scope_key(scope)
            if int(stats.get("row_count") or 0) <= 0:
                continue
            for layer in layers:
                prior = _watermark(layer, scope_key, scope["source"]) or _existing_layer_seed(layer, scope, stats)
                _upsert_watermark(
                    layer,
                    scope,
                    status="running",
                    canonical_start=stats.get("first_date"),
                    canonical_end=stats.get("last_date"),
                    materialized_start=prior.get("materialized_start"),
                    materialized_end=prior.get("materialized_end"),
                    row_count=int(prior.get("row_count") or 0),
                    run_id=run_id,
                    details={
                        "previousWatermark": prior.get("materialized_end"),
                        "seededFromExisting": bool(prior.get("seededFromExisting")),
                    },
                    started_at=started,
                )
                try:
                    if layer == "parquet":
                        incremental_start = _parquet_incremental_start(
                            scope,
                            prior,
                            current_row_count=int(stats["row_count"]),
                        )
                        output = export_market_daily_bars(
                            **scope,
                            start_date=incremental_start,
                            incremental=bool(incremental_start),
                        )
                        digest = hashlib.sha256(
                            json_dump(
                                [
                                    {"path": item["relativePath"], "sha256": item["sha256"], "rows": item["rowCount"]}
                                    for item in output.get("files") or []
                                ]
                            ).encode("utf-8")
                        ).hexdigest()
                        status = "ready"
                        row_count = int(output.get("rowCount") or 0)
                        details = {
                            "mode": "incremental_year_rewrite" if incremental_start else "initial_full",
                            "fileCount": output.get("fileCount"),
                            "incrementalStart": incremental_start,
                        }
                        dataset_id = output.get("id")
                    else:
                        output = _clickhouse_incremental(scope, prior.get("materialized_end"))
                        status = str(output["status"])
                        row_count = int(stats["row_count"]) if status == "ready" else int(prior.get("row_count") or 0)
                        digest = (
                            hashlib.sha256(f"{scope_key}|{scope['source']}|{stats['last_date']}|{stats['row_count']}".encode()).hexdigest()
                            if status == "ready"
                            else None
                        )
                        details = output
                        dataset_id = None
                        if status == "failed":
                            error = "; ".join(
                                str(item.get("error") or "ClickHouse mirror failed")
                                for item in output.get("errors") or []
                            )[:2000]
                            errors.append(
                                {
                                    "layer": layer,
                                    "scopeKey": scope_key,
                                    "source": scope["source"],
                                    "error": error or "clickhouse_incremental_failed",
                                }
                            )
                    completed = utc_now()
                    _upsert_watermark(
                        layer,
                        scope,
                        status=status,
                        canonical_start=stats.get("first_date"),
                        canonical_end=stats.get("last_date"),
                        materialized_start=stats.get("first_date") if status == "ready" else prior.get("materialized_start"),
                        materialized_end=stats.get("last_date") if status == "ready" else prior.get("materialized_end"),
                        row_count=row_count,
                        dataset_id=dataset_id,
                        content_sha256=digest,
                        run_id=run_id,
                        details=details,
                        started_at=started,
                        completed_at=completed,
                    )
                    results.append({"layer": layer, "scopeKey": scope_key, "source": scope["source"], "status": status, **details})
                except Exception as exc:  # noqa: BLE001 - continue other independent scopes
                    error = str(exc)
                    errors.append({"layer": layer, "scopeKey": scope_key, "source": scope["source"], "error": error})
                    _upsert_watermark(
                        layer,
                        scope,
                        status="failed",
                        canonical_start=stats.get("first_date"),
                        canonical_end=stats.get("last_date"),
                        materialized_start=prior.get("materialized_start"),
                        materialized_end=prior.get("materialized_end"),
                        row_count=int(prior.get("row_count") or 0),
                        run_id=run_id,
                        error=error,
                        details={"error": error},
                        started_at=started,
                        completed_at=utc_now(),
                    )
        consistency = None
        if "parquet" in layers and any(item["layer"] == "parquet" and item["status"] == "ready" for item in results):
            consistency = parquet_consistency_report(
                sources=sorted({scope["source"] for scope in scopes}),
                include_research_sources=False,
                persist=True,
            )
            certified_ids = certify_consistent_production_datasets(consistency)
            consistency["certifiedDatasetIds"] = certified_ids
            if not consistency.get("passed"):
                errors.append({"layer": "parquet", "scopeKey": "*", "error": "parquet_consistency_failed"})
            else:
                production_dataset_ids = {
                    str(item.get("datasetId"))
                    for item in consistency.get("items") or []
                    if (item.get("sourceLineage") or {}).get("passed")
                }
                if production_dataset_ids and not production_dataset_ids.issubset(set(certified_ids)):
                    errors.append(
                        {
                            "layer": "parquet",
                            "scopeKey": "*",
                            "error": "production_source_recertification_incomplete",
                        }
                    )
        effective_errors = list(errors)
        status = "success" if not effective_errors else "partial" if results else "failed"
        summary = {
            "layers": layers,
            "scopeCount": len(scopes),
            "results": results,
            "errors": errors,
            "parquetConsistency": consistency,
        }
        with db() as connection:
            connection.execute(
                """
                update derived_maintenance_runs
                set status=?,canonical_watermark=?,summary_json=?,error=?,finished_at=?
                where id=?
                """,
                (
                    status,
                    canonical_end,
                    json_dump(summary),
                    "; ".join(item["error"] for item in errors[:5]) or None,
                    utc_now(),
                    run_id,
                ),
            )
        return maintenance_run(run_id) or {}
    except Exception as exc:
        with db() as connection:
            connection.execute(
                "update derived_maintenance_runs set status='failed',error=?,finished_at=? where id=?",
                (str(exc), utc_now(), run_id),
            )
        raise


def run_maintenance(run_id: str) -> dict[str, Any]:
    if database_backend() != "mysql":
        return _run_locked(run_id)
    with db() as connection:
        acquired = connection.execute("select get_lock(?,0) as acquired", (MAINTENANCE_LOCK_NAME,)).fetchone()
        if int((acquired or {}).get("acquired") or 0) != 1:
            return {"id": run_id, "status": "already_running"}
        try:
            return _run_locked(run_id)
        finally:
            connection.execute("select release_lock(?)", (MAINTENANCE_LOCK_NAME,))


def maintenance_lease_active() -> bool:
    """Return whether a MySQL session still owns the maintenance lease."""
    if database_backend() != "mysql":
        return False
    with db() as connection:
        row = connection.execute(
            "select is_used_lock(?) as owner",
            (MAINTENANCE_LOCK_NAME,),
        ).fetchone()
    return bool(row and row.get("owner") is not None)


def watermarks() -> dict[str, Any]:
    with db() as connection:
        rows = connection.execute(
            "select * from derived_layer_watermarks order by layer_key,scope_key,source"
        ).fetchall()
        run_rows = connection.execute(
            "select * from derived_maintenance_runs order by created_at desc limit 20"
        ).fetchall()
    items = []
    for item in rows_to_dicts(rows):
        items.append({**_scope_from_key(item["scope_key"], item["source"]), **item})
    return {
        "items": items,
        "count": len(items),
        "layers": {
            layer: {
                "count": sum(1 for item in items if item["layer_key"] == layer),
                "ready": sum(1 for item in items if item["layer_key"] == layer and item["status"] == "ready"),
                "failed": sum(1 for item in items if item["layer_key"] == layer and item["status"] == "failed"),
                "watermark": max(
                    (str(item.get("materialized_end") or "") for item in items if item["layer_key"] == layer),
                    default="",
                )
                or None,
            }
            for layer in LAYERS
        },
        "runs": rows_to_dicts(run_rows),
        "schedule": {"timezone": "Asia/Shanghai", "days": "Monday-Friday", "defaultTime": "19:30"},
        "asOfDate": date.today().isoformat(),
    }
