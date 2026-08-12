"""Explicit, auditable maintenance helpers for MySQL storage reduction.

Nothing in this module is scheduled automatically.  The command-line wrapper
requires an operator's ``--confirm`` flag before it calls a mutating helper.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
from typing import Any

from ..core.config import FILE_OBJECT_STORE_DIR, PARQUET_DIR, RUNTIME_DIR
from ..db import database_backend, db, row_to_dict
from . import db_object_store


REDUNDANT_INDEXES: tuple[tuple[str, str], ...] = (
    ("factor_values", "idx_factor_values_symbol_date"),
    ("market_daily_bars", "idx_market_daily_instrument_date"),
    ("ashare_daily_bars", "idx_ashare_daily_symbol_date"),
    ("ashare_trade_status", "idx_ashare_status_symbol_date"),
)

DAILY_BASIC_COLUMNS = (
    "turnover_rate",
    "turnover_rate_float",
    "volume_ratio",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dividend_yield",
    "dividend_yield_ttm",
    "total_share_shares",
    "float_share_shares",
    "free_share_shares",
    "total_mv_cny",
    "circ_mv_cny",
)

# These tables contain provider data, canonical market facts, or derived
# catalogues which can be regenerated.  They deliberately exclude projects,
# settings, user accounts, paper trading, backtests, reports, and strategy
# versions.  The order is child-before-parent where the schema has references.
MARKET_RESET_TABLES: tuple[str, ...] = (
    "provider_raw_archive_issues",
    "provider_raw_archives",
    "provider_raw_records",
    "provider_ingestion_manifests",
    "provider_dataset_watermarks",
    "provider_dataset_catalog",
    "data_sync_work_items",
    "data_sync_items",
    "data_sync_runs",
    "data_record_issues",
    "data_import_batches",
    "data_assets",
    "parquet_files",
    "derived_layer_watermarks",
    "derived_maintenance_runs",
    "asset_capabilities",
    "data_quality_reports",
    "data_gaps",
    "universe_coverage_watermarks",
    "index_source_artifacts",
    "index_membership_events",
    "index_weights",
    "universe_membership",
    "financial_facts",
    "financial_statements",
    "corporate_actions",
    "factor_values",
    "daily_basic_values",
    "adjustment_factors",
    "market_ticks",
    "market_intraday_bars",
    "market_trade_status",
    "market_daily_bars",
    "trade_calendar",
    "instrument_identifiers",
    "instruments",
    "securities",
)

ASHARE_COMPATIBILITY_RELATIONS = (
    "ashare_daily_bars",
    "ashare_trade_status",
    "legacy_ashare_daily_bars",
    "legacy_ashare_trade_status",
)

PRESERVED_TABLE_GROUPS = {
    "businessAndConfiguration": (
        "projects",
        "settings",
        "strategies",
        "portfolios",
        "paper_accounts",
        "paper_orders",
        "paper_positions",
    ),
    "backtestAndResearchMetadata": (
        "backtest_runs",
        "backtest_results",
        "dataset_versions",
        "reproducibility_certificates",
        "tasks",
        "pipeline_runs",
        "pipeline_steps",
    ),
}

# Backtest execution facts and their generated/reproducibility intermediates.
# Paper accounts, projects, strategies, settings, provider data, and PIT
# universe evidence are deliberately outside this list.
BACKTEST_PURGE_TABLES: tuple[str, ...] = (
    "reproducibility_certificates",
    "backtest_results",
    "backtest_runs",
    "experiment_batch_attempts",
    "experiment_batch_items",
    "experiment_batches",
    "experiments",
    "walk_forward_windows",
    "walk_forward_runs",
    "parameter_selection_events",
    "parameter_candidates",
    "oos_evaluations",
    "feature_pipeline_fits",
    "leakage_check_results",
    "factor_evaluations",
    "portfolio_optimization_runs",
    "dataset_versions",
    "reports",
    "qlib_research_imports",
    "qlib_signal_snapshots",
    "ml_feature_files",
    "ml_feature_sets",
    "ml_prediction_files",
    "ml_training_trials",
    "ml_training_runs",
)

BACKTEST_OBJECT_NAMESPACES = (
    "backtest-results",
    "lean-data-files",
    "pipeline-artifacts",
    "reproducibility-certificates",
    "object-store",  # Current contents are Qlib backtest/research output.
)

# MySQL refuses TRUNCATE on a referenced parent even after its child table is
# empty. These execution metadata tables are small, so DELETE is sufficient.
BACKTEST_DELETE_ONLY_TABLES = {"backtest_runs"}


def _require_mysql() -> None:
    if database_backend() != "mysql":
        raise RuntimeError("storage_maintenance_requires_mysql")


def _relation_types() -> dict[str, str]:
    _require_mysql()
    with db() as connection:
        rows = connection.execute(
            """
            select table_name as table_name,table_type as table_type from information_schema.tables
            where table_schema=database()
            """
        ).fetchall()
    return {str(row["table_name"]): str(row["table_type"]) for row in rows}


def _relation_columns(relation: str) -> set[str]:
    _require_mysql()
    with db() as connection:
        rows = connection.execute(
            """
            select column_name as column_name from information_schema.columns
            where table_schema=database() and table_name=?
            """,
            (relation,),
        ).fetchall()
    return {str(row["column_name"]) for row in rows}


def _relation_row_estimates(relations: tuple[str, ...], types: dict[str, str]) -> dict[str, int]:
    """Use InnoDB statistics instead of scanning large live tables for a plan."""
    estimates: dict[str, int] = {}
    with db() as connection:
        for relation in relations:
            if types.get(relation) != "BASE TABLE":
                continue
            row = connection.execute(
                """
                select table_rows as row_estimate from information_schema.tables
                where table_schema=database() and table_name=?
                """,
                (relation,),
            ).fetchone()
            estimates[relation] = int(row["row_estimate"] or 0) if row else 0
    return estimates


def _maintenance_work_state(types: dict[str, str]) -> tuple[dict[str, int], dict[str, int]]:
    """Separate live writers from abandoned status rows.

    A derived run is live only while its MySQL advisory lock is held. Pipeline
    rows have no lease or worker identity, so an old ``running`` row is
    historical metadata rather than proof of an active database writer.
    """
    active: dict[str, int] = {}
    stale: dict[str, int] = {}
    checks = ("tasks", "data_sync_runs")
    statuses = ("queued", "pending", "running", "started", "retrying")
    placeholders = ",".join("?" for _ in statuses)
    with db() as connection:
        for table in checks:
            if types.get(table) != "BASE TABLE":
                continue
            row = connection.execute(
                f"select count(*) as count from `{table}` where lower(status) in ({placeholders})",
                statuses,
            ).fetchone()
            count = int(row["count"] or 0)
            if count:
                active[table] = count
        if types.get("pipeline_runs") == "BASE TABLE":
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            live = connection.execute(
                f"""
                select count(*) as count from pipeline_runs
                where lower(status) in ({placeholders}) and started_at >= ?
                """,
                (*statuses, cutoff),
            ).fetchone()
            stale_rows = connection.execute(
                f"""
                select count(*) as count from pipeline_runs
                where lower(status) in ({placeholders}) and started_at < ?
                """,
                (*statuses, cutoff),
            ).fetchone()
            if int(live["count"] or 0):
                active["pipeline_runs"] = int(live["count"] or 0)
            if int(stale_rows["count"] or 0):
                stale["pipeline_runs"] = int(stale_rows["count"] or 0)
        if types.get("derived_maintenance_runs") == "BASE TABLE":
            row = connection.execute(
                f"select count(*) as count from derived_maintenance_runs where lower(status) in ({placeholders})",
                statuses,
            ).fetchone()
            count = int(row["count"] or 0)
            if count:
                from .derived_maintenance import maintenance_lease_active

                if maintenance_lease_active():
                    active["derived_maintenance_runs"] = count
                else:
                    stale["derived_maintenance_runs"] = count
    return active, stale


def market_reset_plan() -> dict[str, Any]:
    """Return the exact destructive scope without changing database state."""
    types = _relation_types()
    reset_tables = tuple(table for table in MARKET_RESET_TABLES if types.get(table) == "BASE TABLE")
    ashare_relations = tuple(name for name in ASHARE_COMPATIBILITY_RELATIONS if name in types)
    active_work, stale_work = _maintenance_work_state(types)
    return {
        "resetTables": list(reset_tables),
        "resetRowEstimates": _relation_row_estimates(reset_tables, types),
        "ashareRelations": {name: types[name] for name in ashare_relations},
        "activeWork": active_work,
        "staleStatusRecords": stale_work,
        "preservedTableGroups": {key: list(value) for key, value in PRESERVED_TABLE_GROUPS.items()},
        "derivedHandling": {
            "parquetDatasets": "invalidate_metadata_and_remove_files",
            "datasetReleases": "revoke_without_deleting_backtest_references",
            "clickhouse": "truncate_market_bars_when_enabled",
            "providerRawObjects": "delete_only_provider_raw_namespace",
        },
        "postResetBulkDatasets": [
            "stock_basic",
            "trade_cal",
            "daily",
            "adj_factor",
            "daily_basic",
            "suspend_d",
            "stk_limit",
            "index_basic",
            "index_daily",
            "fut_basic",
            "opt_basic",
        ],
    }


def _safe_maintenance_directory(directory: Path, *, required_leaf: str) -> Path:
    """Resolve and validate a narrow maintenance directory before mutation."""
    target = directory.expanduser().resolve()
    if target.name != required_leaf or target == target.parent:
        raise RuntimeError(f"unsafe_maintenance_directory:{target}")
    return target


def _remove_directory_contents(directory: Path, *, required_leaf: str) -> int:
    """Remove only children of a previously constrained maintenance directory."""
    target = _safe_maintenance_directory(directory, required_leaf=required_leaf)
    if not target.exists():
        return 0
    removed = 0
    for child in target.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed += 1
    return removed


def _write_reset_audit(payload: dict[str, Any]) -> str:
    directory = RUNTIME_DIR / "maintenance-audits"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = directory / f"market-reset-{stamp}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    return str(target)


def _table_exists(types: dict[str, str], table: str) -> bool:
    return types.get(table) == "BASE TABLE"


def backtest_purge_plan() -> dict[str, Any]:
    """Report the exact backtest purge scope without mutating MySQL."""
    types = _relation_types()
    tables = tuple(table for table in BACKTEST_PURGE_TABLES if _table_exists(types, table))
    object_counts: dict[str, int] = {}
    if _table_exists(types, "stored_objects"):
        placeholders = ",".join("?" for _ in BACKTEST_OBJECT_NAMESPACES)
        with db() as connection:
            rows = connection.execute(
                f"select namespace,count(*) as count from stored_objects where namespace in ({placeholders}) group by namespace",
                BACKTEST_OBJECT_NAMESPACES,
            ).fetchall()
        object_counts = {str(row["namespace"]): int(row["count"] or 0) for row in rows}
    return {
        "purgeTables": list(tables),
        "rowEstimates": _relation_row_estimates(tables, types),
        "objectNamespaces": list(BACKTEST_OBJECT_NAMESPACES),
        "objectCounts": object_counts,
        "preserved": ["projects", "settings", "strategy_versions", "paper_*", "provider_*", "universe-pit objects"],
    }


def purge_backtests() -> dict[str, Any]:
    """Delete all backtest execution rows and MySQL-resident generated output."""
    _require_mysql()
    types = _relation_types()
    active = _maintenance_work_state(types)[0]
    if active:
        raise RuntimeError(f"active_work_must_stop_before_backtest_purge:{active}")
    plan = backtest_purge_plan()
    tables = list(plan["purgeTables"])
    placeholders = ",".join("?" for _ in BACKTEST_OBJECT_NAMESPACES)
    with db() as connection:
        # These task rows are the execution handles for deleted backtests; do
        # not clear other task kinds such as data synchronization or insights.
        task_cursor = connection.execute("delete from tasks where kind='backtest'") if _table_exists(types, "tasks") else None
        # ``reproducibility_certificates`` has the only FK to stored_objects.
        # Clear all execution facts before removing their payload objects.
        for table in tables:
            if table in BACKTEST_DELETE_ONLY_TABLES:
                connection.execute(f"delete from `{table}`")
            else:
                connection.execute(f"truncate table `{table}`")
        if _table_exists(types, "object_store_items") and _table_exists(types, "stored_objects"):
            connection.execute(
                f"""
                delete i from object_store_items i join stored_objects o on o.id=i.stored_object_id
                where o.namespace in ({placeholders})
                """,
                BACKTEST_OBJECT_NAMESPACES,
            )
        if _table_exists(types, "stored_object_chunks") and _table_exists(types, "stored_objects"):
            connection.execute(
                f"""
                delete c from stored_object_chunks c join stored_objects o on o.id=c.object_id
                where o.namespace in ({placeholders})
                """,
                BACKTEST_OBJECT_NAMESPACES,
            )
        object_cursor = (
            connection.execute(
                f"delete from stored_objects where namespace in ({placeholders})",
                BACKTEST_OBJECT_NAMESPACES,
            )
            if _table_exists(types, "stored_objects")
            else None
        )
    compacted: list[str] = []
    with db() as connection:
        for table in ("stored_object_chunks", "stored_objects"):
            if _table_exists(types, table):
                connection.execute(f"optimize table `{table}`")
                compacted.append(table)
    result = {
        "status": "complete",
        "truncatedTables": tables,
        "backtestTasksDeleted": int(task_cursor.rowcount or 0) if task_cursor else 0,
        "objectsDeleted": int(object_cursor.rowcount or 0) if object_cursor else 0,
        "compactedTables": compacted,
        "completedAt": datetime.now(timezone.utc).isoformat(),
    }
    result["auditPath"] = _write_reset_audit({"backtestPurgePlan": plan, "result": result})
    return result


def write_mysql_schema_report(output: Path) -> dict[str, Any]:
    """Export current local MySQL structure and exact table counts as Markdown."""
    _require_mysql()
    destination = output.expanduser().resolve()
    if destination.suffix.lower() != ".md":
        raise ValueError("schema_report_requires_markdown_output")
    types = _relation_types()
    base_tables = tuple(sorted(name for name, kind in types.items() if kind == "BASE TABLE"))
    counts: dict[str, int] = {}
    with db() as connection:
        for table in base_tables:
            row = connection.execute(f"select count(*) as count from `{table}`").fetchone()
            counts[table] = int(row["count"] or 0)
        columns = connection.execute(
            """
            select table_name as table_name,column_name as column_name,column_type as column_type,
                   is_nullable as is_nullable,column_key as column_key,column_default as column_default,
                   extra as extra,column_comment as column_comment,ordinal_position as ordinal_position
            from information_schema.columns where table_schema=database()
            order by table_name,ordinal_position
            """
        ).fetchall()
        indexes = connection.execute(
            """
            select table_name as table_name,index_name as index_name,non_unique as non_unique,
                   seq_in_index as seq_in_index,column_name as column_name
            from information_schema.statistics where table_schema=database()
            order by table_name,index_name,seq_in_index
            """
        ).fetchall()
    by_table: dict[str, list[dict[str, Any]]] = {}
    for row in columns:
        by_table.setdefault(str(row["table_name"]), []).append(row_to_dict(row) or {})
    index_by_table: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in indexes:
        item = row_to_dict(row) or {}
        index_by_table.setdefault(str(item["table_name"]), {}).setdefault(str(item["index_name"]), []).append(item)
    lines = [
        "# Current MySQL Schema",
        "",
        f"Generated at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "This is a read-only structure snapshot of the local `lean_market` database. Row counts are exact at generation time; no row contents or credentials are included.",
        "",
        "## Tables and views",
        "",
        "| Relation | Type | Exact rows |",
        "| --- | --- | ---: |",
    ]
    for table in sorted(types):
        rows = str(counts.get(table, "—")) if types[table] == "BASE TABLE" else "—"
        lines.append(f"| `{table}` | {types[table].lower()} | {rows} |")
    for table in sorted(types):
        lines.extend(["", f"## `{table}`", "", "| Column | Type | Null | Key | Default | Extra |", "| --- | --- | --- | --- | --- | --- |"])
        for column in by_table.get(table, []):
            default = str(column.get("column_default") or "").replace("|", "\\|")
            lines.append(
                f"| `{column['column_name']}` | `{column['column_type']}` | {column['is_nullable']} | "
                f"{column.get('column_key') or ''} | {default} | {column.get('extra') or ''} |"
            )
        table_indexes = index_by_table.get(table, {})
        if table_indexes:
            lines.extend(["", "Indexes:"])
            for name, members in table_indexes.items():
                columns_text = ", ".join(f"`{item['column_name']}`" for item in members)
                unique = "unique" if int(members[0].get("non_unique") or 0) == 0 else "non-unique"
                lines.append(f"- `{name}` ({unique}): {columns_text}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"output": str(destination), "relations": len(types), "baseTables": len(base_tables)}


def _drop_relation(connection: Any, relation: str, relation_type: str | None) -> None:
    if relation_type == "VIEW":
        connection.execute(f"drop view `{relation}`")
    elif relation_type == "BASE TABLE":
        connection.execute(f"drop table `{relation}`")


def _create_ashare_compatibility_views(connection: Any) -> None:
    connection.execute(
        """
        create view ashare_daily_bars as
        select symbol,trade_date,open,high,low,close,volume,amount,turnover_rate,
               prev_close,pct_change,adj_factor,adjust,source,batch_id,created_at
        from market_daily_bars
        where asset_class='equity' and market='china' and venue='china'
          and resolution='daily' and data_type='trade'
        """
    )
    connection.execute(
        f"""
        create view ashare_trade_status as
        select symbol,trade_date,is_suspended,limit_up,limit_down,is_limit_up,is_limit_down,
               is_one_word_limit_up,is_one_word_limit_down,can_buy,can_sell,is_st,source,batch_id
        from (
            select m.*, row_number() over (
                partition by m.symbol,m.trade_date
                order by {_status_priority_sql()} desc,m.updated_at desc,m.source desc
            ) as source_rank
            from market_trade_status m
            where m.asset_class='equity' and m.market='china' and m.venue='china'
        ) selected where source_rank=1
        """
    )


def _invalidate_derived_catalogues(connection: Any, types: dict[str, str], timestamp: str) -> dict[str, int]:
    invalidated: dict[str, int] = {}
    if types.get("parquet_datasets") == "BASE TABLE":
        columns = _relation_columns("parquet_datasets")
        assignments = ["row_count=0", "file_count=0"]
        parameters: list[Any] = []
        if "status" in columns:
            assignments.append("status='invalidated'")
        if "is_production" in columns:
            assignments.append("is_production=0")
        if "is_certified" in columns:
            assignments.append("is_certified=0")
        if "qa_status" in columns:
            assignments.append("qa_status='invalidated'")
        if "superseded_at" in columns:
            assignments.append("superseded_at=?")
            parameters.append(timestamp)
        if "superseded_reason" in columns:
            assignments.append("superseded_reason='direct_market_reset'")
        if "updated_at" in columns:
            assignments.append("updated_at=?")
            parameters.append(timestamp)
        cursor = connection.execute(
            "update parquet_datasets set " + ",".join(assignments),
            parameters,
        )
        invalidated["parquet_datasets"] = int(cursor.rowcount or 0)
    if types.get("dataset_releases") == "BASE TABLE":
        cursor = connection.execute(
            """
            update dataset_releases
            set status='revoked',revoked_at=?,revoke_reason='direct_market_reset'
            where status <> 'revoked'
            """,
            (timestamp,),
        )
        invalidated["dataset_releases"] = int(cursor.rowcount or 0)
    if types.get("reproducibility_certificates") == "BASE TABLE":
        cursor = connection.execute(
            "update reproducibility_certificates set status='invalidated' where status <> 'invalidated'"
        )
        invalidated["reproducibility_certificates"] = int(cursor.rowcount or 0)
    if types.get("paper_account_trust_certifications") == "BASE TABLE":
        cursor = connection.execute(
            """
            update paper_account_trust_certifications
            set status='revoked',revoked_at=?,revoke_reason='direct_market_reset'
            where status <> 'revoked'
            """,
            (timestamp,),
        )
        invalidated["paper_account_trust_certifications"] = int(cursor.rowcount or 0)
    return invalidated


def direct_market_reset() -> dict[str, Any]:
    """Clear regenerable market data without touching business/backtest rows.

    This function is intentionally only reachable through the CLI's three
    explicit acknowledgements.  It releases InnoDB space using TRUNCATE for
    base tables, replaces duplicate A-share tables with compatibility views,
    invalidates derived catalogues rather than violating their backtest FKs,
    and clears only the provider-raw external object namespace.
    """
    _require_mysql()
    # Validate every filesystem target before any database or ClickHouse
    # mutation.  A custom broad path must fail before destructive work starts.
    _safe_maintenance_directory(PARQUET_DIR, required_leaf="parquet")
    _safe_maintenance_directory(FILE_OBJECT_STORE_DIR / "provider-raw", required_leaf="provider-raw")
    plan = market_reset_plan()
    if plan["activeWork"]:
        raise RuntimeError(f"active_work_must_stop_before_market_reset:{plan['activeWork']}")

    from . import market_data

    clickhouse = market_data.clear_market_bars()
    types = _relation_types()
    timestamp = datetime.now(timezone.utc).isoformat()
    raw_object_ids: list[str] = []
    if types.get("provider_raw_archives") == "BASE TABLE":
        with db() as connection:
            raw_object_ids = [
                str(row["object_id"])
                for row in connection.execute("select distinct object_id from provider_raw_archives").fetchall()
            ]

    reset_tables = [table for table in MARKET_RESET_TABLES if types.get(table) == "BASE TABLE"]
    with db() as connection:
        invalidated = _invalidate_derived_catalogues(connection, types, timestamp)
        for relation in ASHARE_COMPATIBILITY_RELATIONS:
            _drop_relation(connection, relation, types.get(relation))
        for table in reset_tables:
            connection.execute(f"truncate table `{table}`")
        _create_ashare_compatibility_views(connection)

    deleted_objects = 0
    for object_id in raw_object_ids:
        db_object_store.delete_object(object_id)
        deleted_objects += 1
    compacted_object_tables: list[str] = []
    if deleted_objects and _relation_types().get("stored_object_chunks") == "BASE TABLE":
        # Provider-raw chunks were selectively deleted to preserve backtest
        # evidence.  Rebuilding this much smaller residual table is what
        # actually returns its now-free .ibd pages to the filesystem.
        with db() as connection:
            connection.execute("optimize table stored_object_chunks")
        compacted_object_tables.append("stored_object_chunks")
    filesystem = {
        "parquetEntriesRemoved": _remove_directory_contents(PARQUET_DIR, required_leaf="parquet"),
        "providerRawEntriesRemoved": _remove_directory_contents(FILE_OBJECT_STORE_DIR / "provider-raw", required_leaf="provider-raw"),
    }
    result = {
        "status": "complete",
        "completedAt": datetime.now(timezone.utc).isoformat(),
        "truncatedTables": reset_tables,
        "droppedAshareRelations": plan["ashareRelations"],
        "createdViews": ["ashare_daily_bars", "ashare_trade_status"],
        "invalidated": invalidated,
        "providerRawObjectsDeleted": deleted_objects,
        "compactedObjectTables": compacted_object_tables,
        "filesystem": filesystem,
        "clickhouse": clickhouse,
        "preservedTableGroups": plan["preservedTableGroups"],
    }
    result["auditPath"] = _write_reset_audit({"plan": plan, "result": result})
    return result


def storage_report() -> dict[str, Any]:
    """Return logical data/index bytes without probing the host filesystem."""
    with db() as connection:
        rows = connection.execute(
            """
            select table_name as table_name, table_rows as table_rows,
                   data_length as data_length, index_length as index_length, data_free as data_free
            from information_schema.tables
            where table_schema=database()
            order by data_length+index_length desc
            """
        ).fetchall()
    tables = [row_to_dict(row) or {} for row in rows]
    return {
        "tables": tables,
        "dataBytes": sum(int(item.get("data_length") or 0) for item in tables),
        "indexBytes": sum(int(item.get("index_length") or 0) for item in tables),
        "freeBytes": sum(int(item.get("data_free") or 0) for item in tables),
    }


def redundant_index_status() -> list[dict[str, Any]]:
    _require_mysql()
    result = []
    with db() as connection:
        for table, index in REDUNDANT_INDEXES:
            row = connection.execute(
                """
                select is_visible as visible from information_schema.statistics
                where table_schema=database() and table_name=? and index_name=?
                limit 1
                """,
                (table, index),
            ).fetchone()
            result.append({"table": table, "index": index, "exists": bool(row), "visible": bool(row and row["visible"] == "YES")})
    return result


def set_redundant_indexes_visible(*, visible: bool) -> list[dict[str, Any]]:
    _require_mysql()
    target = "VISIBLE" if visible else "INVISIBLE"
    applied = []
    with db() as connection:
        for item in redundant_index_status():
            if not item["exists"] or item["visible"] == visible:
                applied.append({**item, "changed": False})
                continue
            connection.execute(f"alter table `{item['table']}` alter index `{item['index']}` {target}")
            applied.append({**item, "visible": visible, "changed": True})
    return applied


def drop_redundant_indexes() -> list[dict[str, Any]]:
    _require_mysql()
    applied = []
    with db() as connection:
        for item in redundant_index_status():
            if not item["exists"]:
                applied.append({**item, "dropped": False})
                continue
            connection.execute(f"alter table `{item['table']}` drop index `{item['index']}`")
            applied.append({**item, "dropped": True})
    return applied


def optimize_tables(tables: list[str]) -> list[str]:
    _require_mysql()
    allowed = {table for table, _ in REDUNDANT_INDEXES} | {"factor_values"}
    invalid = sorted(set(tables) - allowed)
    if invalid:
        raise ValueError(f"unsupported_optimize_tables:{','.join(invalid)}")
    with db() as connection:
        for table in tables:
            connection.execute(f"optimize table `{table}`")
    return tables


def _wide_value_sql(alias: str = "d") -> str:
    branches = " ".join(f"when '{column}' then {alias}.{column}" for column in DAILY_BASIC_COLUMNS)
    return f"case f.factor_name {branches} else null end"


def daily_basic_eav_audit() -> dict[str, int]:
    """Classify legacy EAV values without relying on compatibility views."""
    value = _wide_value_sql()
    with db() as connection:
        row = connection.execute(
            f"""
            select
              count(*) as legacy_rows,
              sum(case when d.symbol is null then 1 else 0 end) as uncovered_rows,
              sum(case when d.symbol is not null and ({value}) is null then 1 else 0 end) as null_wide_rows,
              sum(case when d.symbol is not null and ({value}) is not null
                        and abs(f.value - ({value})) <= 0.000000001 then 1 else 0 end) as equivalent_rows,
              sum(case when d.symbol is not null and ({value}) is not null
                        and abs(f.value - ({value})) > 0.000000001 then 1 else 0 end) as mismatched_rows
            from factor_values f
            left join daily_basic_values d
              on d.symbol=f.symbol and d.trade_date=f.trade_date and d.source=f.source
            where f.source='tushare:daily_basic'
            """
        ).fetchone()
    result = row_to_dict(row) or {}
    return {key: int(result.get(key) or 0) for key in ("legacy_rows", "uncovered_rows", "null_wide_rows", "equivalent_rows", "mismatched_rows")}


def delete_equivalent_daily_basic_eav(*, batch_size: int = 10_000, max_batches: int | None = None) -> dict[str, int]:
    """Delete only legacy rows whose wide-column value is present and equal."""
    value = _wide_value_sql()
    deleted = 0
    batches = 0
    last_key = ("", "", "", "")
    while max_batches is None or batches < max_batches:
        with db() as connection:
            rows = connection.execute(
                f"""
                select f.symbol,f.trade_date,f.factor_name,f.source
                from factor_values f join daily_basic_values d
                  on d.symbol=f.symbol and d.trade_date=f.trade_date and d.source=f.source
                where f.source='tushare:daily_basic' and ({value}) is not null
                  and abs(f.value - ({value})) <= 0.000000001
                  and (f.symbol,f.trade_date,f.factor_name,f.source) > (?,?,?,?)
                order by f.symbol,f.trade_date,f.factor_name,f.source
                limit ?
                """,
                (*last_key, max(1, min(int(batch_size), 100_000))),
            ).fetchall()
            if not rows:
                break
            connection.executemany(
                """
                delete from factor_values
                where symbol=? and trade_date=? and factor_name=? and source=?
                """,
                [(row["symbol"], row["trade_date"], row["factor_name"], row["source"]) for row in rows],
            )
            last = rows[-1]
            last_key = (str(last["symbol"]), str(last["trade_date"]), str(last["factor_name"]), str(last["source"]))
        deleted += len(rows)
        batches += 1
    return {"deleted": deleted, "batches": batches, **daily_basic_eav_audit()}


def migrate_objects(*, limit: int, namespace: str | None = None) -> dict[str, int]:
    return db_object_store.migrate_database_objects_to_filesystem(limit=limit, namespace=namespace)


def prune_expired_objects(*, retention_days: int = 180, limit: int = 1_000) -> dict[str, int]:
    """Remove only explicitly disposable object namespaces, preserving evidence."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, int(retention_days)))).isoformat()
    namespaces = ("backtest-results", "lean-data-files", "pipeline-artifacts")
    placeholders = ",".join("?" for _ in namespaces)
    with db() as connection:
        rows = connection.execute(
            f"""
            select id from stored_objects
            where namespace in ({placeholders}) and created_at < ?
              and not exists (select 1 from provider_raw_archives a where a.object_id=stored_objects.id)
            order by created_at,id limit ?
            """,
            [*namespaces, cutoff, max(1, min(int(limit), 10_000))],
        ).fetchall()
    deleted = 0
    for row in rows:
        db_object_store.delete_object(str(row["id"]))
        deleted += 1
    return {"deleted": deleted, "cutoff": cutoff}


def prune_expired_provider_raw_records(*, retention_days: int = 180, limit: int = 10_000) -> dict[str, int | str]:
    """Prune online dedupe metadata only after a readable archive is present.

    ``provider_raw_archives`` is run-scoped, so this intentionally retains a
    row unless at least one archive for its source batch can be checksum-read.
    A future historical sync may re-create these lightweight keys; provider
    payload evidence remains retained indefinitely in the external store.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, int(retention_days)))).isoformat()
    with db() as connection:
        rows = connection.execute(
            """
            select r.provider,r.dataset_key,r.record_key,a.object_id
            from provider_raw_records r
            join provider_raw_archives a
              on a.provider=r.provider and a.dataset_key=r.dataset_key and a.run_id=r.batch_id
            join stored_objects o on o.id=a.object_id
            where r.ingested_at < ? and (o.storage_mode='filesystem' or exists (
                select 1 from stored_object_chunks c where c.object_id=o.id
            ))
            order by r.ingested_at,r.provider,r.dataset_key,r.record_key
            limit ?
            """,
            (cutoff, max(1, min(int(limit), 100_000))),
        ).fetchall()
    valid_objects: dict[str, bool] = {}
    records: set[tuple[str, str, str]] = set()
    for row in rows:
        object_id = str(row["object_id"])
        if object_id not in valid_objects:
            try:
                db_object_store.read_bytes(object_id)
                valid_objects[object_id] = True
            except (OSError, ValueError):
                valid_objects[object_id] = False
        if valid_objects[object_id]:
            records.add((str(row["provider"]), str(row["dataset_key"]), str(row["record_key"])))
    if records:
        with db() as connection:
            connection.executemany(
                "delete from provider_raw_records where provider=? and dataset_key=? and record_key=?",
                sorted(records),
            )
    return {"deleted": len(records), "scanned": len(rows), "cutoff": cutoff}


ASHARE_STATUS_COLUMNS = (
    "is_limit_up",
    "is_limit_down",
    "is_one_word_limit_up",
    "is_one_word_limit_down",
    "is_st",
)


def prepare_ashare_canonical_storage() -> dict[str, int]:
    """Add and backfill A-share-only status facts in the canonical table."""
    _require_mysql()
    with db() as connection:
        existing = {
            str(row["column_name"])
            for row in connection.execute(
                """
                select column_name as column_name from information_schema.columns
                where table_schema=database() and table_name='market_trade_status'
                """
            ).fetchall()
        }
        for column in ASHARE_STATUS_COLUMNS:
            if column not in existing:
                connection.execute(f"alter table market_trade_status add column `{column}` int not null default 0")
        cursor = connection.execute(
            """
            update market_trade_status m join ashare_trade_status a
              on a.symbol=m.symbol and a.trade_date=m.trade_date and a.source=m.source
            set m.is_limit_up=a.is_limit_up,
                m.is_limit_down=a.is_limit_down,
                m.is_one_word_limit_up=a.is_one_word_limit_up,
                m.is_one_word_limit_down=a.is_one_word_limit_down,
                m.is_st=a.is_st
            where m.asset_class='equity' and m.market='china'
            """
        )
    return {"backfilled": int(cursor.rowcount or 0), "addedColumns": len(set(ASHARE_STATUS_COLUMNS) - existing)}


def ashare_canonical_coverage() -> dict[str, int]:
    """Count A-share rows that lack their same-source canonical counterpart."""
    _require_mysql()
    with db() as connection:
        daily = connection.execute(
            """
            select count(*) as total,
                   sum(case when m.instrument_id is null then 1 else 0 end) as missing
            from ashare_daily_bars a left join market_daily_bars m
              on m.symbol=a.symbol and m.trade_date=a.trade_date and m.adjust=a.adjust and m.source=a.source
             and m.asset_class='equity' and m.market='china' and m.resolution='daily' and m.data_type='trade'
            """
        ).fetchone()
        status = connection.execute(
            """
            select count(*) as total,
                   sum(case when m.instrument_id is null then 1 else 0 end) as missing
            from ashare_trade_status a left join market_trade_status m
              on m.symbol=a.symbol and m.trade_date=a.trade_date and m.source=a.source
             and m.asset_class='equity' and m.market='china'
            """
        ).fetchone()
    return {
        "dailyRows": int(daily["total"] or 0),
        "dailyMissing": int(daily["missing"] or 0),
        "statusRows": int(status["total"] or 0),
        "statusMissing": int(status["missing"] or 0),
    }


def _status_priority_sql() -> str:
    return """case
        when lower(source) like '%suspend%' or lower(source) like '%daily_absence%' then 120
        when lower(source) like '%official%' then 110
        when lower(source) like '%inferred%' or lower(source) like '%ohlcv%' then 10
        when lower(source) regexp 'tushare|jqdata|rqdata|ifind|choice|wind|stk_limit' then 100
        when lower(source) like '%manual%' then 90
        when (lower(source) regexp 'adata|baostock|akshare|sina|eastmoney') then 70
        else 50 end"""


def cutover_ashare_compatibility_views() -> None:
    """Rename duplicate A-share tables and replace them with read-compatible views."""
    _require_mysql()
    coverage = ashare_canonical_coverage()
    if coverage["dailyMissing"] or coverage["statusMissing"]:
        raise RuntimeError(f"ashare_canonical_coverage_incomplete:{coverage}")
    with db() as connection:
        legacy = connection.execute(
            """
            select table_name from information_schema.tables
            where table_schema=database() and table_name in ('legacy_ashare_daily_bars','legacy_ashare_trade_status')
            """
        ).fetchall()
        if legacy:
            raise RuntimeError("ashare_legacy_tables_already_exist")
        connection.execute("rename table ashare_daily_bars to legacy_ashare_daily_bars, ashare_trade_status to legacy_ashare_trade_status")
        _create_ashare_compatibility_views(connection)


def drop_ashare_legacy_tables() -> None:
    _require_mysql()
    with db() as connection:
        connection.execute("drop table if exists legacy_ashare_daily_bars")
        connection.execute("drop table if exists legacy_ashare_trade_status")
