from __future__ import annotations

from typing import Any

from ..db import database_backend, db, json_dump, utc_now
from .tushare_contracts import contract_snapshot, sync_contract_catalog


SCHEMA_VERSION = "market-data-v2"
LEGACY_MARKET_TABLES = (
    "securities",
    "instruments",
    "instrument_identifiers",
    "market_daily_bars",
    "market_intraday_bars",
    "market_ticks",
    "market_trade_status",
    "trade_calendar",
    "adjustment_factors",
    "corporate_actions",
    "daily_basic_values",
    "financial_statements",
    "financial_facts",
    "factor_values",
    "universe_membership",
    "index_weights",
    "futures_contracts",
    "futures_daily_bars",
    "futures_main_mapping",
)
CORE_V2_TABLES = (
    "market_schema_versions_v2",
    "data_providers_v2",
    "provider_datasets_v2",
    "dataset_contract_versions_v2",
    "source_observations_v2",
    "market_venues_v2",
    "market_instruments_v2",
    "financial_reports_v2",
    "financial_facts_v2",
    "index_definitions_v2",
    "index_memberships_v2",
    "index_weights_v2",
    "futures_contract_terms_v2",
    "option_contract_terms_v2",
    "columnar_datasets_v2",
    "columnar_partitions_v2",
)
VENUES = (
    ("SSE", "Shanghai Stock Exchange", "CN", "Asia/Shanghai", "CNY"),
    ("SZSE", "Shenzhen Stock Exchange", "CN", "Asia/Shanghai", "CNY"),
    ("BSE", "Beijing Stock Exchange", "CN", "Asia/Shanghai", "CNY"),
    ("CFFEX", "China Financial Futures Exchange", "CN", "Asia/Shanghai", "CNY"),
    ("DCE", "Dalian Commodity Exchange", "CN", "Asia/Shanghai", "CNY"),
    ("CZCE", "Zhengzhou Commodity Exchange", "CN", "Asia/Shanghai", "CNY"),
    ("SHFE", "Shanghai Futures Exchange", "CN", "Asia/Shanghai", "CNY"),
    ("INE", "Shanghai International Energy Exchange", "CN", "Asia/Shanghai", "CNY"),
    ("GFEX", "Guangzhou Futures Exchange", "CN", "Asia/Shanghai", "CNY"),
)


def _require_mysql() -> None:
    if database_backend() != "mysql":
        raise RuntimeError("commercial_market_schema_requires_mysql")


def _base_tables() -> set[str]:
    with db() as connection:
        if database_backend() == "mysql":
            rows = connection.execute(
                """
                select table_name from information_schema.tables
                where table_schema=database() and table_type='BASE TABLE'
                """
            ).fetchall()
            return {str(row["table_name"]) for row in rows}
        rows = connection.execute("select name as table_name from sqlite_master where type='table'").fetchall()
        return {str(row["table_name"]) for row in rows}


def commercial_schema_status() -> dict[str, Any]:
    tables = _base_tables()
    present_core = sorted(set(CORE_V2_TABLES) & tables)
    source_tables = sorted(table for table in tables if table.startswith("src_tushare_"))
    schema_record: dict[str, Any] | None = None
    if "market_schema_versions_v2" in tables:
        with db() as connection:
            row = connection.execute(
                "select * from market_schema_versions_v2 where version=?",
                (SCHEMA_VERSION,),
            ).fetchone()
            schema_record = dict(row) if row else None
    return {
        "version": SCHEMA_VERSION,
        "contractVersion": contract_snapshot()["contractVersion"],
        "coreTables": {"expected": len(CORE_V2_TABLES), "present": len(present_core), "missing": sorted(set(CORE_V2_TABLES) - tables)},
        "sourceTables": {"expected": len(contract_snapshot()["contracts"]), "present": len(source_tables)},
        "schemaRecord": schema_record,
    }


def commercial_rebuild_plan() -> dict[str, Any]:
    _require_mysql()
    tables = _base_tables()
    counts: dict[str, int] = {}
    with db() as connection:
        for table in LEGACY_MARKET_TABLES:
            if table not in tables:
                continue
            row = connection.execute(f"select count(*) as count from `{table}`").fetchone()
            counts[table] = int(row["count"] or 0)
    non_empty = {table: count for table, count in counts.items() if count}
    status = commercial_schema_status()
    return {
        **status,
        "legacyTables": counts,
        "nonEmptyLegacyTables": non_empty,
        "ready": not non_empty and not status["coreTables"]["missing"] and status["sourceTables"]["present"] == status["sourceTables"]["expected"],
        "activation": "not_automatic",
        "protectedDomains": ["projects", "strategies", "backtests", "paper", "research", "settings", "audit"],
    }


def prepare_commercial_schema() -> dict[str, Any]:
    """Seed v2 governance only after proving the legacy market domain is empty.

    This is intentionally not an activation switch. Application readers remain
    on the legacy schema until their compatibility migration is deployed.
    """
    plan = commercial_rebuild_plan()
    if not plan["ready"]:
        raise RuntimeError("commercial_market_schema_not_ready:" + json_dump(plan["nonEmptyLegacyTables"] or plan["coreTables"]["missing"]))
    sync_contract_catalog()
    now = utc_now()
    with db() as connection:
        for venue_code, name, country_code, timezone, currency in VENUES:
            connection.execute(
                """
                insert into market_venues_v2
                    (id,venue_code,name,country_code,timezone,currency,status,created_at,updated_at)
                values (?,?,?,?,?,?,'active',?,?)
                on conflict(venue_code) do update set
                    name=excluded.name,country_code=excluded.country_code,
                    timezone=excluded.timezone,currency=excluded.currency,
                    status=excluded.status,updated_at=excluded.updated_at
                """,
                (f"venue:{venue_code}", venue_code, name, country_code, timezone, currency, now, now),
            )
        connection.execute(
            """
            insert into market_schema_versions_v2
                (version,contract_version,state,prepared_at,activated_at,preparation_report_json)
            values (?,?,'prepared',?,null,?)
            on conflict(version) do update set
                contract_version=excluded.contract_version,state='prepared',
                prepared_at=excluded.prepared_at,preparation_report_json=excluded.preparation_report_json
            """,
            (SCHEMA_VERSION, contract_snapshot()["contractVersion"], now, json_dump(plan)),
        )
    return {**commercial_schema_status(), "prepared": True, "venues": len(VENUES)}
