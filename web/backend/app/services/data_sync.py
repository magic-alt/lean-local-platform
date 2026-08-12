from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import shutil
import threading
import time
import uuid
from typing import Any, Callable, TypeVar

from ..core.config import (
    DATA_DIR,
    HOST_DATA_DIR,
    HOST_PARQUET_DIR,
    HOST_PLATFORM_DIR,
    PARQUET_DIR,
    RUNTIME_DIR,
)
from ..db import DatabaseUnavailableError, bulk_db, database_backend, db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..research.factors import upsert_daily_basic_factor_values
from .ashare_repository import (
    import_security_master,
    upsert_adjustment_factors,
    upsert_corporate_actions,
    upsert_index_weights,
    upsert_trade_status,
)
from .data import import_ashare_research_batch
from .db_object_store import put_bytes
from .market_repository import upsert_market_daily_bars_batch
from .pit_data import import_financial_statements
from .tushare_adapter import TushareAdapter
from .tushare_contracts import contract_for, contract_public_item, coverage_report, sync_contract_catalog
from .tushare_rate_limit import DEFAULT_CALLS_PER_MINUTE, global_tushare_quota_status
from .tushare_typed_source import persist_typed_source_rows
from .tushare_lineage import async_lineage_enabled, enqueue_lineage_job, lineage_metrics


T = TypeVar("T")
logger = logging.getLogger(__name__)


# Provider responses are Python dictionaries and are duplicated temporarily by
# validation, raw lineage archiving, comparison, and canonical writers.  A
# 500k-row logical batch can therefore consume several GiB even when its wire
# payload is comparatively small.  Keep the bound in code so an old .env value
# cannot reintroduce an OOM after a deployment upgrade.
MAX_SYNC_BATCH_ROWS = 100_000


def _sync_batch_rows(env_key: str, default: int = 100_000) -> int:
    return max(1_000, min(MAX_SYNC_BATCH_ROWS, int(os.environ.get(env_key, str(default)))))


def _sync_batch_units(env_key: str, default: int = 16, *, maximum: int = 16) -> int:
    return max(1, min(maximum, int(os.environ.get(env_key, str(default)))))


def _finite_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first_finite_number(*values: Any) -> float | None:
    for value in values:
        number = _finite_number(value)
        if number is not None:
            return number
    return None


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    api_name: str
    category: str
    scope: str = "global"
    cadence: str = "daily"
    probe: dict[str, Any] = field(default_factory=dict)
    key_fields: tuple[str, ...] = ()
    date_field: str | None = None
    instrument_field: str | None = "ts_code"
    normalizer: str | None = None
    sync_policy: str = "bulk"
    initial_fetch: str = "auto"
    incremental_fetch: str = "auto"
    rate_limit_per_hour: int | None = None
    retain_raw: bool = True
    catalog_date_field: str | None = None


# Versioned low-frequency registry for the local 5,000-point TuShare entitlement.
# A successful probe is authoritative because some endpoints require separate grants.
DATASET_REGISTRY: tuple[DatasetSpec, ...] = (
    DatasetSpec("stock_basic", "stock_basic", "A股/基础", probe={"list_status": "L"}, key_fields=("ts_code",), normalizer="stock_basic"),
    DatasetSpec("namechange", "namechange", "A股/基础", "instrument", probe={"ts_code": "600519.SH"}, key_fields=("ts_code", "start_date", "name"), date_field="start_date", normalizer="namechange", initial_fetch="per_symbol_full", incremental_fetch="per_symbol_full"),
    DatasetSpec("trade_cal", "trade_cal", "A股/基础", probe={"exchange": "SSE", "start_date": "20260101", "end_date": "20260110"}, key_fields=("exchange", "cal_date"), date_field="cal_date", normalizer="trade_cal"),
    DatasetSpec("daily", "daily", "A股/行情", "instrument", probe={"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date", normalizer="daily", initial_fetch="per_symbol_full", incremental_fetch="by_trade_date"),
    DatasetSpec("adj_factor", "adj_factor", "A股/行情", "instrument", probe={"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date", normalizer="adj_factor", initial_fetch="per_symbol_full", incremental_fetch="by_trade_date"),
    DatasetSpec("daily_basic", "daily_basic", "A股/行情", "instrument", probe={"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date", normalizer="daily_basic", initial_fetch="per_symbol_full", incremental_fetch="by_trade_date"),
    DatasetSpec("suspend_d", "suspend_d", "A股/交易状态", "instrument", probe={"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "suspend_date", "suspend_timing"), date_field="suspend_date", normalizer="suspend_d", initial_fetch="per_symbol_full", incremental_fetch="by_trade_date"),
    DatasetSpec("stk_limit", "stk_limit", "A股/交易状态", "instrument", probe={"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date", normalizer="stk_limit", initial_fetch="per_symbol_full", incremental_fetch="by_trade_date"),
    DatasetSpec("dividend", "dividend", "A股/财务", "instrument", "quarterly", {"ts_code": "600519.SH"}, ("ts_code", "end_date", "ann_date", "div_proc"), "ann_date", normalizer="dividend"),
    DatasetSpec("income", "income", "A股/财务", "instrument", "quarterly", {"ts_code": "600519.SH", "start_date": "20250101", "end_date": "20261231"}, ("ts_code", "end_date", "ann_date", "report_type"), "ann_date", normalizer="financial"),
    DatasetSpec("balancesheet", "balancesheet", "A股/财务", "instrument", "quarterly", {"ts_code": "600519.SH", "start_date": "20250101", "end_date": "20261231"}, ("ts_code", "end_date", "ann_date", "report_type"), "ann_date", normalizer="financial"),
    DatasetSpec("cashflow", "cashflow", "A股/财务", "instrument", "quarterly", {"ts_code": "600519.SH", "start_date": "20250101", "end_date": "20261231"}, ("ts_code", "end_date", "ann_date", "report_type"), "ann_date", normalizer="financial"),
    DatasetSpec("forecast", "forecast", "A股/财务", "instrument", "quarterly", {"ts_code": "600519.SH"}, ("ts_code", "end_date", "ann_date", "type"), "ann_date"),
    DatasetSpec("express", "express", "A股/财务", "instrument", "quarterly", {"ts_code": "600519.SH"}, ("ts_code", "end_date", "ann_date"), "ann_date"),
    DatasetSpec("fina_indicator", "fina_indicator", "A股/财务", "instrument", "quarterly", {"ts_code": "600519.SH", "start_date": "20250101", "end_date": "20261231"}, ("ts_code", "end_date", "ann_date"), "ann_date", normalizer="financial"),
    DatasetSpec("index_basic", "index_basic", "指数", probe={"market": "SSE"}, key_fields=("ts_code",), catalog_date_field="list_date"),
    DatasetSpec("index_daily", "index_daily", "指数", "window", probe={"ts_code": "000300.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date", normalizer="index_daily"),
    DatasetSpec("index_weight", "index_weight", "指数", "window", "monthly", {"index_code": "000300.SH", "start_date": "20260101", "end_date": "20260331"}, ("index_code", "con_code", "trade_date"), "trade_date", normalizer="index_weight"),
    DatasetSpec("index_classify", "index_classify", "指数/行业", probe={"src": "SW2021", "level": "L1"}, key_fields=("index_code",), normalizer="sw_industry"),
    DatasetSpec("index_member_all", "index_member_all", "指数/行业", "instrument", probe={"ts_code": "600519.SH", "is_new": "Y"}, key_fields=("ts_code", "l1_code", "in_date"), date_field="in_date", normalizer="sw_industry"),
    DatasetSpec("sw_industry", "index_member_all", "指数/行业", "instrument", probe={"ts_code": "600519.SH", "is_new": "Y"}, key_fields=("ts_code", "l1_code", "in_date"), date_field="in_date", normalizer="sw_industry"),
    DatasetSpec("fund_basic", "fund_basic", "基金", probe={"market": "E"}, key_fields=("ts_code",)),
    DatasetSpec("fund_daily", "fund_daily", "基金", "window", probe={"trade_date": "20260109"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("fund_nav", "fund_nav", "基金", "window", probe={"nav_date": "20260109"}, key_fields=("ts_code", "nav_date", "end_date", "ann_date"), date_field="nav_date"),
    DatasetSpec("fund_portfolio", "fund_portfolio", "基金", "window", "quarterly", {"ann_date": "20260331"}, ("ts_code", "symbol", "end_date", "ann_date"), "ann_date"),
    DatasetSpec("cb_basic", "cb_basic", "可转债", probe={}, key_fields=("ts_code",)),
    DatasetSpec("cb_daily", "cb_daily", "可转债", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("cb_call", "cb_call", "可转债", "window", probe={"ann_date": "20260110"}, key_fields=("ts_code", "ann_date", "call_type"), date_field="ann_date"),
    DatasetSpec("fut_basic", "fut_basic", "期货", probe={"exchange": "CFFEX"}, key_fields=("ts_code",), catalog_date_field="list_date"),
    DatasetSpec("fut_daily", "fut_daily", "期货", "window", probe={"trade_date": "20260109"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("fut_mapping", "fut_mapping", "期货", "window", probe={"trade_date": "20260109"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("opt_basic", "opt_basic", "期权", probe={"exchange": "SSE"}, key_fields=("ts_code",), catalog_date_field="list_date"),
    DatasetSpec("opt_daily", "opt_daily", "期权", "window", probe={"trade_date": "20260109"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("hk_basic", "hk_basic", "港股", probe={"list_status": "L"}, key_fields=("ts_code",), sync_policy="on_demand", rate_limit_per_hour=1),
    DatasetSpec("hk_daily", "hk_daily", "港股", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date", sync_policy="on_demand", rate_limit_per_hour=1),
    DatasetSpec("us_basic", "us_basic", "美股", probe={}, key_fields=("ts_code",), sync_policy="on_demand"),
    DatasetSpec("us_daily", "us_daily", "美股", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date", sync_policy="on_demand"),
    DatasetSpec("fx_obasic", "fx_obasic", "外汇", probe={}, key_fields=("ts_code",)),
    DatasetSpec("fx_daily", "fx_daily", "外汇", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("shibor", "shibor", "宏观", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("date",), date_field="date"),
    DatasetSpec("lpr", "shibor_lpr", "宏观", "window", "monthly", {"start_date": "20250101", "end_date": "20261231"}, ("date",), "date"),
    DatasetSpec("cn_gdp", "cn_gdp", "宏观", cadence="quarterly", key_fields=("quarter",)),
    DatasetSpec("cn_cpi", "cn_cpi", "宏观", cadence="monthly", key_fields=("month",)),
    DatasetSpec("cn_ppi", "cn_ppi", "宏观", cadence="monthly", key_fields=("month",)),
    DatasetSpec("cn_m", "cn_m", "宏观", cadence="monthly", key_fields=("month",)),
    DatasetSpec("margin", "margin", "特色/交易", "window", probe={"trade_date": "20260109"}, key_fields=("trade_date", "exchange_id"), date_field="trade_date"),
    DatasetSpec("top_list", "top_list", "特色/交易", "window", probe={"trade_date": "20260109"}, key_fields=("trade_date", "ts_code", "name"), date_field="trade_date"),
    DatasetSpec("block_trade", "block_trade", "特色/交易", "window", probe={"trade_date": "20260109"}, key_fields=("ts_code", "trade_date", "price", "vol"), date_field="trade_date"),
    DatasetSpec("repurchase", "repurchase", "特色/公司行为", "window", probe={"ann_date": "20260109"}, key_fields=("ts_code", "ann_date", "proc"), date_field="ann_date"),
    DatasetSpec("share_float", "share_float", "特色/公司行为", "window", probe={"ann_date": "20260109"}, key_fields=("ts_code", "ann_date", "float_date", "holder_name"), date_field="ann_date"),
    DatasetSpec("pledge_stat", "pledge_stat", "特色/公司行为", "instrument", "weekly", {"ts_code": "600519.SH"}, ("ts_code", "end_date"), "end_date"),
)

# The workstation cache is intentionally scoped to A-share execution plus the
# futures/options data needed by stock-linked strategies. Everything else is
# fetched by the workflow that actually requests it and is not part of the
# one-click database fill.
BULK_DATASET_KEYS = {
    "stock_basic",
    "trade_cal",
    "daily",
    "adj_factor",
    "daily_basic",
    "suspend_d",
    "stk_limit",
    "dividend",
    "index_basic",
    "index_daily",
    "fut_basic",
    "opt_basic",
}
LOSSLESS_CANONICAL_NORMALIZERS = {
    "stock_basic",
    "namechange",
    "adj_factor",
    "daily_basic",
    "financial",
    "stk_limit",
}
DATASET_REGISTRY = tuple(
    replace(
        spec,
        sync_policy="on_demand" if spec.key not in BULK_DATASET_KEYS else "bulk",
        # These datasets are losslessly represented by their canonical tables;
        # manifests retain request, key and payload hashes for audit. Daily is
        # intentionally excluded, as is index_weight: production certification
        # and PIT governance require a deterministic compressed provider
        # archive. This does not restore per-row JSON;
        # provider_raw_records.payload_json remains empty and the
        # content-addressed gzip object is deduplicated.
        retain_raw=False
        if spec.normalizer in LOSSLESS_CANONICAL_NORMALIZERS
        else spec.retain_raw,
    )
    for spec in DATASET_REGISTRY
)


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    if isinstance(frame, list):
        return [dict(item) for item in frame]
    if hasattr(frame, "to_dict"):
        return [dict(item) for item in frame.to_dict("records")]
    return []


def _compact(value: date) -> str:
    return value.strftime("%Y%m%d")


def _iso(value: Any) -> str | None:
    text = str(value or "").strip().replace("-", "")
    if len(text) < 8 or not text[:8].isdigit():
        return None
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}"


def _permission_error(exc: Exception) -> tuple[str, str]:
    reason = str(exc).strip()[:1000]
    lowered = reason.lower()
    if any(token in lowered for token in ("权限", "积分", "permission", "privilege", "access denied")):
        return "denied", reason
    if any(
        token in lowered
        for token in (
            "频率",
            "每分钟",
            "每小时",
            "超过访问",
            "rate",
            "too many",
            "timeout",
            "temporar",
            "connection",
        )
    ):
        return "retryable", reason
    return "unknown", reason


def _catalog_metadata(spec: DatasetSpec) -> dict[str, Any]:
    result = {
        "apiName": spec.api_name,
        "keyFields": list(spec.key_fields),
        "dateField": spec.date_field,
        "instrumentField": spec.instrument_field,
        "normalizer": spec.normalizer,
        "entitlementPoints": 5000,
        "boundary": "low_frequency",
        "syncPolicy": spec.sync_policy,
        "initialFetch": spec.initial_fetch,
        "incrementalFetch": spec.incremental_fetch,
        "rateLimitPerHour": spec.rate_limit_per_hour,
        "retainRaw": spec.retain_raw,
        "catalogDateField": spec.catalog_date_field,
    }
    contract = contract_for(spec.key) or contract_for(spec.api_name)
    if contract:
        public_contract = contract_public_item(contract)
        result.update(
            {
                "contractVersion": public_contract["contractVersion"],
                "storageTier": public_contract["storageTier"],
                "canonicalStatus": "wired" if spec.normalizer else public_contract["storageTier"],
                "fieldCoverage": public_contract["fieldCoverage"],
                "sourceTable": public_contract["sourceTable"],
                "documentationUrl": public_contract["documentationUrl"],
            }
        )
    return result


def ensure_catalog() -> None:
    sync_contract_catalog()
    with db() as connection:
        for spec in DATASET_REGISTRY:
            connection.execute(
                """
                insert into provider_dataset_catalog
                    (provider, dataset_key, api_name, category, scope_type, cadence,
                     permission_status, row_count, metadata_json, sync_policy, rate_limit_per_hour, skip_reason)
                values ('tushare', ?, ?, ?, ?, ?, 'unknown', 0, ?, ?, ?, ?)
                on conflict(provider, dataset_key) do update set
                    api_name = excluded.api_name,
                    category = excluded.category,
                    scope_type = excluded.scope_type,
                    cadence = excluded.cadence,
                    metadata_json = excluded.metadata_json,
                    sync_policy = excluded.sync_policy,
                    rate_limit_per_hour = excluded.rate_limit_per_hour,
                    skip_reason = excluded.skip_reason
                """,
                (
                    spec.key,
                    spec.api_name,
                    spec.category,
                    spec.scope,
                    spec.cadence,
                    json_dump(_catalog_metadata(spec)),
                    spec.sync_policy,
                    spec.rate_limit_per_hour,
                    "Low-frequency or separately entitled data is fetched only when used."
                    if spec.sync_policy == "on_demand"
                    else None,
                ),
            )


def catalog_payload() -> dict[str, Any]:
    ensure_catalog()
    with db() as connection:
        rows = connection.execute(
            "select * from provider_dataset_catalog where provider = 'tushare' order by category, dataset_key"
        ).fetchall()
        active = connection.execute(
            "select * from data_sync_runs where status in ('queued','running','cancelling') order by created_at desc limit 1"
        ).fetchone()
        latest = connection.execute(
            "select * from data_sync_runs order by created_at desc limit 1"
        ).fetchone()
        completed_initial_sync = connection.execute(
            """
            select id from data_sync_runs
            where status = 'success' and coalesce(canonical_status, 'ready') = 'ready'
            order by finished_at desc limit 1
            """
        ).fetchone()
    items = rows_to_dicts(rows)
    from .asset_capabilities import refresh_capabilities

    capabilities = refresh_capabilities()

    def capability_asset(dataset_key: str) -> str | None:
        if dataset_key.startswith("fut_"):
            return "future"
        if dataset_key.startswith("opt_"):
            return "option"
        if dataset_key.startswith("cb_"):
            return "convertible_bond"
        if dataset_key.startswith("fund_"):
            return "etf"
        if dataset_key.startswith("index_"):
            return "index"
        if dataset_key in {"stock_basic", "namechange", "daily", "adj_factor", "daily_basic", "suspend_d", "stk_limit"}:
            return "equity"
        return None

    for item in items:
        asset_class = capability_asset(str(item["dataset_key"]))
        capability = next(
            (
                value for value in capabilities
                if value["asset_class"] == asset_class and value["resolution"] == "daily"
            ),
            None,
        )
        if capability:
            item["capabilityState"] = capability["state"]
            item["canonicalRowCount"] = int(capability.get("canonical_row_count") or 0)
            item["capabilityReason"] = capability.get("executable_reason")
    active_run = sync_run(str(active["id"])) if active else None
    latest_run = sync_run(str(latest["id"])) if latest else None
    return {
        "provider": "tushare",
        "entitlementPoints": 5000,
        "boundary": "low_frequency",
        "items": items,
        "count": len(items),
        "available": sum(item.get("permission_status") in {"available", "empty"} for item in items),
        "storage": _disk_metrics(),
        # Include item-level state so a page refresh still shows the dataset
        # currently being checked or synchronized.
        "activeRun": active_run,
        "latestRun": latest_run,
        # A successful canonical run is durable database state. Do not infer this
        # from the most recent run because a later cancelled run must not make the
        # UI forget that the initial library was already built.
        "hasCompletedInitialSync": bool(completed_initial_sync),
        "recommendedMode": "incremental" if completed_initial_sync else "initial_full",
        "contractCoverage": coverage_report(DATASET_REGISTRY),
    }


def on_demand_storage_targets() -> list[dict[str, Any]]:
    """Return explicitly selectable, server-writable export roots."""
    data_root = DATA_DIR.expanduser().resolve()
    host_data_root = HOST_DATA_DIR.expanduser().resolve()
    parquet_root = PARQUET_DIR.expanduser().resolve()
    runtime_root = (RUNTIME_DIR / "exports").resolve()
    targets: list[dict[str, Any]] = [
        {
            "id": "data",
            "label": "LEAN 数据目录",
            "path": str(data_root),
            "displayPath": str(host_data_root),
            "kind": "mounted_data",
        },
        {
            "id": "parquet",
            "label": "Parquet 数据湖",
            "path": str(parquet_root),
            "displayPath": str(HOST_PARQUET_DIR),
            "kind": "parquet_lake",
        },
        {
            "id": "workspace",
            "label": "项目导出目录",
            "path": str(runtime_root),
            "displayPath": str(HOST_PLATFORM_DIR / "web" / "runtime" / "exports"),
            "kind": "workspace",
        },
    ]
    configured = [item.strip() for item in os.environ.get("LEAN_ON_DEMAND_EXPORT_ROOTS", "").split(os.pathsep) if item.strip()]
    for index, raw_path in enumerate(configured, start=1):
        path = Path(raw_path).expanduser().resolve()
        targets.append(
            {
                "id": f"external_{index}",
                "label": f"外部存储 {index}",
                "path": str(path),
                "displayPath": str(path),
                "kind": "external",
            }
        )
    return targets


def _on_demand_destination(storage_target: str, relative_path: str | None) -> tuple[Path, Path]:
    target = next((item for item in on_demand_storage_targets() if item["id"] == storage_target), None)
    if not target:
        raise ValueError("A valid storage target must be selected explicitly.")
    relative = Path(str(relative_path or "tushare-on-demand").strip())
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Export subdirectory must be a relative path without '..'.")
    root = Path(str(target["path"])).resolve()
    output_dir = (root / relative).resolve()
    if not output_dir.is_relative_to(root):
        raise ValueError("Export path escapes the selected storage target.")
    display_root = Path(str(target["displayPath"])).expanduser()
    return output_dir, display_root / relative


def _query(pro: Any, spec: DatasetSpec, params: dict[str, Any]) -> list[dict[str, Any]]:
    if hasattr(pro, "query"):
        return _records(pro.query(spec.api_name, **params))
    return _records(getattr(pro, spec.api_name)(**params))


_BULK_MARKET_VARIANTS: dict[str, tuple[str, ...]] = {
    "index_basic": ("MSCI", "CSI", "SSE", "SZSE", "CICC", "SW", "OTH"),
    "fut_basic": ("CFFEX", "DCE", "CZCE", "SHFE", "INE", "GFEX"),
    "opt_basic": ("SSE", "SZSE", "CFFEX", "DCE", "CZCE", "SHFE"),
}

# Keep the workstation's benchmark library deliberately small, but include the
# broad A-share indices exposed by the built-in research and strategy flows.
# The previous single-code query only synchronized CSI 300, while Index Preview
# made every index-basic code look chartable.
DEFAULT_INDEX_DAILY_CODES: tuple[str, ...] = (
    "000001.SH",  # SSE Composite
    "000016.SH",  # SSE 50
    "000300.SH",  # CSI 300
    "000688.SH",  # STAR 50
    "000852.SH",  # CSI 1000
    "000905.SH",  # CSI 500
    "399001.SZ",  # Shenzhen Component
    "399006.SZ",  # ChiNext
)


def _missing_default_index_daily_codes() -> set[str]:
    expected = {code.split(".", 1)[0] for code in DEFAULT_INDEX_DAILY_CODES}
    with db() as connection:
        rows = connection.execute(
            """
            select distinct symbol from market_daily_bars
            where asset_class='index' and market='china' and source='tushare'
            """
        ).fetchall()
    available = {str(row["symbol"] or "") for row in rows}
    return expected - available


def _complete_global_query(pro: Any, spec: DatasetSpec, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch independent market partitions concurrently, preserving request order."""
    concurrency = max(1, min(32, int(os.environ.get("LEAN_TUSHARE_FETCH_CONCURRENCY", "16"))))

    def fetch_many(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(requests) == 1:
            return _call_with_retry(lambda: _query(pro, spec, requests[0]))
        # The shared proxy enforces the account-wide rolling quota. Keep result
        # order deterministic while independent partitions are in flight.
        with ThreadPoolExecutor(
            max_workers=min(concurrency, len(requests)),
            thread_name_prefix=f"tushare-{spec.key}",
        ) as executor:
            futures = [
                executor.submit(_call_with_retry, lambda request=request: _query(pro, spec, request))
                for request in requests
            ]
            records: list[dict[str, Any]] = []
            for future in futures:
                records.extend(future.result())
        return records

    variants = _BULK_MARKET_VARIANTS.get(spec.key)
    if variants:
        key = "exchange" if spec.key in {"fut_basic", "opt_basic"} else "market"
        records = fetch_many([{**params, key: value} for value in variants])
        deduplicated = {_record_key(spec, row): row for row in records}
        return list(deduplicated.values())

    if spec.key == "index_daily" and params.get("start_date") and params.get("end_date"):
        start = date.fromisoformat(str(params["start_date"])[:4] + "-" + str(params["start_date"])[4:6] + "-" + str(params["start_date"])[6:8])
        end = date.fromisoformat(str(params["end_date"])[:4] + "-" + str(params["end_date"])[4:6] + "-" + str(params["end_date"])[6:8])
        requested_code = str(params.get("ts_code") or "").strip().upper()
        index_codes = DEFAULT_INDEX_DAILY_CODES if requested_code in {"", "000300.SH"} else (requested_code,)
        requests: list[dict[str, Any]] = []
        for index_code in index_codes:
            cursor = start
            while cursor <= end:
                window_end = min(end, cursor + timedelta(days=2_499))
                requests.append(
                    {
                        **params,
                        "ts_code": index_code,
                        "start_date": _compact(cursor),
                        "end_date": _compact(window_end),
                    }
                )
                cursor = window_end + timedelta(days=1)
        records = fetch_many(requests)
        deduplicated = {_record_key(spec, row): row for row in records}
        return list(deduplicated.values())
    return _query(pro, spec, params)


def _call_with_retry(call: Callable[[], T], *, attempts: int = 3) -> T:
    """Retry only transient provider failures; permission and data errors fail fast."""
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except Exception as exc:  # noqa: BLE001
            category, _ = _permission_error(exc)
            if category != "retryable" or attempt >= attempts:
                raise
            time.sleep(float(attempt))
    raise RuntimeError("unreachable")


def _mysql_infrastructure_failure(exc: BaseException) -> bool:
    """Identify connection loss that should pause, not skip, a bulk run."""
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, DatabaseUnavailableError):
            return True
        try:
            if int(current.args[0]) in {1040, 2003, 2006, 2013}:
                return True
        except (IndexError, TypeError, ValueError):
            pass
        message = str(current).lower()
        if "lost connection to mysql server" in message or "mysql server has gone away" in message:
            return True
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        if current.__context__ is not None:
            pending.append(current.__context__)
    return False


def probe_permissions(
    adapter: TushareAdapter,
    *,
    only: set[str] | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
) -> dict[str, int]:
    ensure_catalog()
    counts = {"available": 0, "empty": 0, "denied": 0, "retryable": 0, "unknown": 0}
    for spec in DATASET_REGISTRY:
        if only and spec.key not in only:
            continue
        if spec.sync_policy == "on_demand":
            continue
        if run_id and _cancelled(run_id, task_id):
            break
        if run_id:
            _item(run_id, spec.key, status="checking", error="")
        checked = utc_now()
        try:
            rows = _query(adapter.pro, spec, dict(spec.probe))
            status = "available" if rows else "empty"
            reason = None
        except Exception as exc:  # noqa: BLE001
            status, reason = _permission_error(exc)
            if "每小时" in str(reason or ""):
                with db() as connection:
                    connection.execute(
                        """
                        update provider_dataset_catalog
                        set sync_policy='on_demand', skip_reason=?, rate_limit_per_hour=1
                        where provider='tushare' and dataset_key=?
                        """,
                        (reason, spec.key),
                    )
        counts[status] += 1
        with db() as connection:
            connection.execute(
                """
                update provider_dataset_catalog
                set permission_status = ?, permission_reason = ?, last_checked_at = ?
                where provider = 'tushare' and dataset_key = ?
                """,
                (status, reason, checked, spec.key),
            )
        if run_id and not _cancelled(run_id, task_id):
            _item(run_id, spec.key, status="queued")
    return counts


def _permission_probe_keys(selected_keys: set[str], *, max_age: timedelta = timedelta(hours=6)) -> set[str]:
    cutoff = datetime.now(timezone.utc) - max_age
    with db() as connection:
        rows = connection.execute(
            "select dataset_key, permission_status, last_checked_at from provider_dataset_catalog where provider='tushare'"
        ).fetchall()
    result: set[str] = set()
    for row in rows:
        key = str(row["dataset_key"])
        if key not in selected_keys:
            continue
        spec = next((item for item in DATASET_REGISTRY if item.key == key), None)
        if spec and spec.sync_policy == "on_demand":
            continue
        try:
            checked = datetime.fromisoformat(str(row["last_checked_at"])) if row["last_checked_at"] else None
            if checked and checked.tzinfo is None:
                checked = checked.replace(tzinfo=timezone.utc)
        except ValueError:
            checked = None
        if row["permission_status"] == "unknown" or not checked or checked < cutoff:
            result.add(key)
    return result


def _permission_summary(selected_keys: set[str]) -> dict[str, int]:
    counts = {"available": 0, "empty": 0, "denied": 0, "retryable": 0, "unknown": 0}
    with db() as connection:
        rows = connection.execute(
            "select dataset_key, permission_status from provider_dataset_catalog where provider='tushare'"
        ).fetchall()
    for row in rows:
        if row["dataset_key"] not in selected_keys:
            continue
        status = str(row["permission_status"] or "unknown")
        counts[status if status in counts else "unknown"] += 1
    return counts


def _permission_skip_message(status: str, reason: str | None) -> str:
    if status == "denied":
        label = "Skipped: TuShare permission unavailable."
    elif status == "retryable":
        label = "Deferred: TuShare rate limit or temporary provider failure."
    elif status == "unknown":
        label = "Skipped: TuShare permission could not be verified."
    else:
        label = "Skipped: TuShare dataset unavailable."
    detail = str(reason or "").strip()
    return f"{label} {detail}".strip()[:2000]


def _record_key(spec: DatasetSpec, row: dict[str, Any]) -> str:
    values = [str(row.get(field) or "") for field in spec.key_fields]
    if not values or not any(values):
        return _content_sha256(row)
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


def _update_content_hash(digest: Any, value: Any) -> None:
    """Hash JSON-like provider values without constructing per-row JSON."""
    if hasattr(value, "item"):
        value = value.item()
    if value is None:
        digest.update(b"n")
        return
    if isinstance(value, bool):
        digest.update(b"b1" if value else b"b0")
        return
    if isinstance(value, int):
        encoded = str(value).encode("ascii")
        digest.update(b"i" + len(encoded).to_bytes(8, "big") + encoded)
        return
    if isinstance(value, float):
        encoded = value.hex().encode("ascii")
        digest.update(b"f" + len(encoded).to_bytes(8, "big") + encoded)
        return
    if isinstance(value, (datetime, date)):
        value = value.isoformat()
    if isinstance(value, bytes):
        digest.update(b"y" + len(value).to_bytes(8, "big") + value)
        return
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        digest.update(b"s" + len(encoded).to_bytes(8, "big") + encoded)
        return
    if isinstance(value, dict):
        digest.update(b"d" + len(value).to_bytes(8, "big"))
        for key in sorted(value, key=lambda item: str(item)):
            _update_content_hash(digest, str(key))
            _update_content_hash(digest, value[key])
        return
    if isinstance(value, (list, tuple)):
        digest.update(b"l" + len(value).to_bytes(8, "big"))
        for item in value:
            _update_content_hash(digest, item)
        return
    _update_content_hash(digest, str(value))


def _content_sha256(value: Any) -> str:
    digest = hashlib.sha256()
    _update_content_hash(digest, value)
    return digest.hexdigest()


def _api_snapshot(adapter: TushareAdapter) -> dict[str, int]:
    counter = getattr(getattr(adapter, "pro", None), "call_counts", None)
    return counter() if callable(counter) else {}


def _api_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {
        key: max(0, int(after.get(key, 0)) - int(before.get(key, 0)))
        for key in set(before) | set(after)
        if int(after.get(key, 0)) > int(before.get(key, 0))
    }


def _validate_dataset_rows(spec: DatasetSpec, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the critical/warning gate shared by every registry dataset."""
    from .cross_asset_quality import validate_cross_asset_rows

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        missing_required: list[str] = []
        if spec.key_fields:
            first_key = spec.key_fields[0]
            if row.get(first_key) in (None, ""):
                missing_required.append(first_key)
            optional_missing = [field for field in spec.key_fields[1:] if row.get(field) in (None, "")]
            if optional_missing:
                warnings.append({"row": index, "code": "optional_key_blank", "fields": optional_missing})
        if spec.date_field:
            value = row.get(spec.date_field)
            if value in (None, ""):
                missing_required.append(spec.date_field)
            elif _iso(value) is None:
                errors.append({"row": index, "code": "invalid_date", "field": spec.date_field, "value": str(value)[:80]})
        if missing_required:
            errors.append({"row": index, "code": "missing_required", "fields": sorted(set(missing_required))})
        key = _record_key(spec, row)
        if key in seen:
            errors.append({"row": index, "code": "duplicate_primary_key", "key": key})
        seen.add(key)
        if len(errors) >= 50:
            break
    asset_quality = validate_cross_asset_rows(spec.key, rows)
    errors.extend(asset_quality.get("criticalErrors") or [])
    warnings.extend(asset_quality.get("warnings") or [])
    result = {
        "status": "failed" if errors else "warning" if warnings else "passed",
        "criticalErrors": errors[:50],
        "warnings": warnings[:50],
        "checkedRows": len(rows),
        "rejectedRows": len({item["row"] for item in errors}),
        "assetQuality": asset_quality,
        # Reuse the key digest in the ingestion manifest. Previously every
        # successful batch hashed every natural key a second time during the
        # metadata transaction.
        "keysSha256": hashlib.sha256("|".join(sorted(seen)).encode("utf-8")).hexdigest(),
    }
    if errors:
        raise ValueError(f"{spec.key} validation gate failed: {json_dump(result)}")
    return result


def _record_ingestion_manifest(
    *,
    run_id: str,
    spec: DatasetSpec,
    scope_key: str,
    request: dict[str, Any],
    rows: list[dict[str, Any]],
    validation: dict[str, Any],
    endpoint_counts: dict[str, int],
    coverage_start: str | None,
    coverage_end: str | None,
    status: str = "success",
) -> None:
    parameters = _ingestion_manifest_parameters(
        run_id=run_id,
        spec=spec,
        scope_key=scope_key,
        request=request,
        rows=rows,
        validation=validation,
        endpoint_counts=endpoint_counts,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        status=status,
    )
    with db() as connection:
        connection.execute(
            """
            insert into provider_ingestion_manifests
                (id,run_id,provider,dataset_key,scope_key,request_json,response_rows,
                 normalized_rows,rejected_rows,payload_sha256,keys_sha256,coverage_start,
                 coverage_end,status,validation_json,endpoint_counts_json,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            parameters,
        )


def _ingestion_manifest_parameters(
    *,
    run_id: str,
    spec: DatasetSpec,
    scope_key: str,
    request: dict[str, Any],
    rows: list[dict[str, Any]],
    validation: dict[str, Any],
    endpoint_counts: dict[str, int],
    coverage_start: str | None,
    coverage_end: str | None,
    status: str = "success",
) -> tuple[Any, ...]:
    # json.dumps performs the traversal in C and is materially faster than the
    # generic Python recursive hasher for multi-million-row rebuilds. Sorted
    # keys and compact separators keep the digest deterministic.
    canonical_payload = json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return (
        str(uuid.uuid4()), run_id, "tushare", spec.key, scope_key, json_dump(request),
        len(rows), len(rows) - int(validation.get("rejectedRows") or 0),
        int(validation.get("rejectedRows") or 0),
        hashlib.sha256(canonical_payload).hexdigest(),
        str(validation.get("keysSha256") or hashlib.sha256(b"").hexdigest()),
        coverage_start, coverage_end, status, json_dump(validation),
        json_dump(endpoint_counts), utc_now(),
    )


def _coverage_watermarks(spec: DatasetSpec) -> dict[str, str]:
    with db() as connection:
        rows = connection.execute(
            """
            select scope_key, coverage_end from provider_dataset_watermarks
            where provider='tushare' and dataset_key=?
            """,
            (spec.key,),
        ).fetchall()
    return {str(row["scope_key"]): str(row["coverage_end"]) for row in rows if row["coverage_end"]}


def _set_coverage_watermark(
    spec: DatasetSpec,
    *,
    scope_key: str,
    coverage_start: str,
    coverage_end: str,
    rows: list[dict[str, Any]],
    run_id: str,
    validation_status: str,
) -> None:
    parameters = _coverage_watermark_parameters(
        spec,
        scope_key=scope_key,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        rows=rows,
        run_id=run_id,
        validation_status=validation_status,
    )
    with db() as connection:
        connection.execute(
            """
            insert into provider_dataset_watermarks
                (provider,dataset_key,scope_key,coverage_start,coverage_end,last_data_date,
                 last_run_id,empty_result,validation_status,updated_at)
            values ('tushare',?,?,?,?,?,?,?,?,?)
            on conflict(provider,dataset_key,scope_key) do update set
                coverage_start=case
                    when provider_dataset_watermarks.coverage_start is null then excluded.coverage_start
                    when excluded.coverage_start < provider_dataset_watermarks.coverage_start then excluded.coverage_start
                    else provider_dataset_watermarks.coverage_start end,
                coverage_end=excluded.coverage_end,
                last_data_date=coalesce(excluded.last_data_date,provider_dataset_watermarks.last_data_date),
                last_run_id=excluded.last_run_id,
                empty_result=excluded.empty_result,
                validation_status=excluded.validation_status,
                updated_at=excluded.updated_at
            """,
            parameters,
        )


def _coverage_watermark_parameters(
    spec: DatasetSpec,
    *,
    scope_key: str,
    coverage_start: str,
    coverage_end: str,
    rows: list[dict[str, Any]],
    run_id: str,
    validation_status: str,
) -> tuple[Any, ...]:
    data_dates = sorted(
        value for value in (_iso(row.get(spec.date_field)) for row in rows) if value
    ) if spec.date_field else []
    return (
        spec.key, scope_key, coverage_start, coverage_end,
        data_dates[-1] if data_dates else None, run_id, 0 if rows else 1,
        validation_status, utc_now(),
    )


def _persist_instrument_batch_metadata(
    *,
    run_id: str,
    spec: DatasetSpec,
    entries: list[dict[str, Any]],
    endpoint_counts: dict[str, int],
    row_counts: dict[str, int],
    batch_id: str,
) -> None:
    """Commit manifests, watermarks, resolved failures and work state together."""
    if not entries:
        return
    manifest_parameters = [
        _ingestion_manifest_parameters(
            run_id=run_id,
            spec=spec,
            scope_key=str(entry["scope_key"]),
            request=dict(entry["request"]),
            rows=list(entry["raw_rows"]),
            validation=dict(entry["validation"]),
            endpoint_counts=endpoint_counts,
            coverage_start=str(entry["coverage_start"]),
            coverage_end=str(entry["coverage_end"]),
        )
        for entry in entries
    ]
    watermark_parameters = [
        _coverage_watermark_parameters(
            spec,
            scope_key=str(entry["scope_key"]),
            coverage_start=str(entry["coverage_start"]),
            coverage_end=str(entry["coverage_end"]),
            rows=list(entry["raw_rows"]),
            run_id=run_id,
            validation_status=str(entry["validation"]["status"]),
        )
        for entry in entries
        if entry.get("write_watermark", True)
    ]
    now = utc_now()
    with db() as connection:
        connection.executemany(
            """
            insert into provider_ingestion_manifests
                (id,run_id,provider,dataset_key,scope_key,request_json,response_rows,
                 normalized_rows,rejected_rows,payload_sha256,keys_sha256,coverage_start,
                 coverage_end,status,validation_json,endpoint_counts_json,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            manifest_parameters,
        )
        if watermark_parameters:
            connection.executemany(
                """
                insert into provider_dataset_watermarks
                    (provider,dataset_key,scope_key,coverage_start,coverage_end,last_data_date,
                     last_run_id,empty_result,validation_status,updated_at)
                values ('tushare',?,?,?,?,?,?,?,?,?)
                on conflict(provider,dataset_key,scope_key) do update set
                    coverage_start=case
                        when provider_dataset_watermarks.coverage_start is null then excluded.coverage_start
                        when excluded.coverage_start < provider_dataset_watermarks.coverage_start then excluded.coverage_start
                        else provider_dataset_watermarks.coverage_start end,
                    coverage_end=excluded.coverage_end,
                    last_data_date=coalesce(excluded.last_data_date,provider_dataset_watermarks.last_data_date),
                    last_run_id=excluded.last_run_id,
                    empty_result=excluded.empty_result,
                    validation_status=excluded.validation_status,
                    updated_at=excluded.updated_at
                """,
                watermark_parameters,
            )
        connection.executemany(
            """
            update data_record_issues
            set status='resolved', resolved_at=?, resolution_batch_id=?
            where dataset_key=? and coalesce(instrument_code, '')=coalesce(?, '')
              and source='tushare' and issue_code='sync_failed' and status='open'
            """,
            [(now, batch_id, spec.key, str(entry["scope_key"])) for entry in entries],
        )
        connection.executemany(
            """
            update data_sync_work_items
            set status='committed', attempts=attempts+1, row_count=?, error=null,
                committed_at=?
            where run_id=? and dataset_key=? and work_key=?
            """,
            [
                (int(row_counts.get(str(entry["work_key"]), 0)), now, run_id, spec.key, str(entry["work_key"]))
                for entry in entries
            ],
        )


def _persist_trade_date_batch_metadata(
    *,
    run_id: str,
    spec: DatasetSpec,
    entries: list[dict[str, Any]],
    endpoint_counts: dict[str, int],
    row_counts: dict[str, int],
    batch_id: str,
) -> None:
    """Commit contiguous trade-date manifests, watermarks and work state."""
    if not entries:
        return
    manifest_parameters = [
        _ingestion_manifest_parameters(
            run_id=run_id,
            spec=spec,
            scope_key=f"trade_date:{entry['work_key']}",
            request={"tradeDate": entry["work_key"]},
            rows=list(entry["raw_rows"]),
            validation=dict(entry["validation"]),
            endpoint_counts=endpoint_counts,
            coverage_start=str(entry["work_key"]),
            coverage_end=str(entry["work_key"]),
        )
        for entry in entries
    ]
    last_trade_date = str(entries[-1]["work_key"])
    latest_by_symbol: dict[str, str] = {}
    for entry in entries:
        for row in entry["rows"]:
            symbol = str(row.get("symbol") or "")
            trade_date = str(row.get("trade_date") or "")
            if symbol and trade_date and trade_date > latest_by_symbol.get(symbol, ""):
                latest_by_symbol[symbol] = trade_date
    now = utc_now()
    with db() as connection:
        connection.executemany(
            """
            insert into provider_ingestion_manifests
                (id,run_id,provider,dataset_key,scope_key,request_json,response_rows,
                 normalized_rows,rejected_rows,payload_sha256,keys_sha256,coverage_start,
                 coverage_end,status,validation_json,endpoint_counts_json,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            manifest_parameters,
        )
        connection.execute(
            """
            update provider_dataset_watermarks
            set coverage_end=?,last_run_id=?,validation_status='passed',updated_at=?
            where provider='tushare' and dataset_key=? and coverage_end<?
            """,
            (last_trade_date, run_id, now, spec.key, last_trade_date),
        )
        if latest_by_symbol:
            connection.executemany(
                """
                update provider_dataset_watermarks
                set last_data_date=?,empty_result=0
                where provider='tushare' and dataset_key=? and scope_key=?
                """,
                [(trade_date, spec.key, symbol) for symbol, trade_date in latest_by_symbol.items()],
            )
        connection.execute(
            """
            update data_record_issues
            set status='resolved',resolved_at=?,resolution_batch_id=?
            where dataset_key=? and source='tushare' and issue_code='sync_failed'
              and status='open' and instrument_code is null
            """,
            (now, batch_id, spec.key),
        )
        connection.executemany(
            """
            update data_sync_work_items
            set status='committed',attempts=attempts+1,row_count=?,error=null,committed_at=?
            where run_id=? and dataset_key=? and work_key=?
            """,
            [
                (int(row_counts.get(str(entry["work_key"]), 0)), now, run_id, spec.key, str(entry["work_key"]))
                for entry in entries
            ],
        )


def _bootstrap_sparse_watermarks_from_legacy_checkpoint(
    spec: DatasetSpec,
    securities: list[dict[str, Any]],
) -> dict[str, str]:
    """Convert a trustworthy sequential legacy checkpoint into coverage rows."""
    if spec.key != "suspend_d" or not securities:
        return {}
    with db() as connection:
        row = connection.execute(
            """
            select i.checkpoint_json,r.summary_json,r.id as run_id
            from data_sync_items i join data_sync_runs r on r.id=i.run_id
            where i.dataset_key=? and i.checkpoint_json is not null
              and i.status in ('success','partial','cancelled')
            order by r.created_at desc limit 1
            """,
            (spec.key,),
        ).fetchone()
    record = row_to_dict(row) or {}
    checkpoint = record.get("checkpoint") or {}
    summary = record.get("summary") or {}
    completed = min(len(securities), max(0, int(checkpoint.get("index") or 0)))
    coverage_end = str(summary.get("marketDataEndDate") or "")
    if completed <= 0 or not coverage_end:
        return {}
    now = utc_now()
    parameters = [
        (
            "tushare",
            spec.key,
            str(item["symbol"]),
            str(item.get("listed_date") or "1990-01-01"),
            coverage_end,
            None,
            str(record.get("run_id") or ""),
            0,
            "legacy_checkpoint",
            now,
        )
        for item in securities[:completed]
    ]
    with bulk_db() as connection:
        connection.executemany(
            """
            insert into provider_dataset_watermarks
                (provider,dataset_key,scope_key,coverage_start,coverage_end,last_data_date,
                 last_run_id,empty_result,validation_status,updated_at)
            values (?,?,?,?,?,?,?,?,?,?)
            on conflict(provider,dataset_key,scope_key) do update set
                coverage_end=case when excluded.coverage_end>provider_dataset_watermarks.coverage_end
                                  then excluded.coverage_end else provider_dataset_watermarks.coverage_end end,
                last_run_id=excluded.last_run_id,
                validation_status=excluded.validation_status,
                updated_at=excluded.updated_at
            """,
            parameters,
        )
    return {str(item["symbol"]): coverage_end for item in securities[:completed]}


def _archive_raw_batch(
    spec: DatasetSpec,
    rows: list[dict[str, Any]],
    run_id: str,
) -> dict[str, Any]:
    """Store one compressed provider response instead of duplicated row JSON."""
    if not rows or not spec.retain_raw:
        return {}
    payload = json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    # The serialized provider payload is already canonical (sorted keys and
    # compact separators). Hash those bytes directly instead of traversing
    # every row a second time with the generic content hasher.
    payload_sha256 = hashlib.sha256(payload).hexdigest()
    gzip_level = max(1, min(9, int(os.environ.get("LEAN_RAW_ARCHIVE_GZIP_LEVEL", "1"))))
    compressed = gzip.compress(payload, compresslevel=gzip_level, mtime=0)
    archive_sha256 = hashlib.sha256(compressed).hexdigest()
    _assert_disk_capacity(len(compressed) * 2)
    # Content-addressed keys deduplicate identical responses across retries and
    # later runs; the archive catalog separately records every run reference.
    object_key = f"tushare/{spec.key}/{payload_sha256}.json.gz"
    stored = put_bytes(
        "provider-raw",
        object_key,
        compressed,
        content_type="application/json",
        metadata={
            "provider": "tushare",
            "datasetKey": spec.key,
            "runId": run_id,
            "rowCount": len(rows),
            "compression": "gzip",
            "payloadSha256": payload_sha256,
            "archiveSha256": archive_sha256,
            "uncompressedSize": len(payload),
        },
        bulk=True,
    )
    object_id = str(stored.get("id") or "")
    if not object_id:
        raise RuntimeError("Database object storage must be enabled to retain provider raw data.")
    archive_id = str(
        uuid.uuid5(
            uuid.UUID("27c004a9-9cca-431a-8758-a23d3bebacb7"),
            f"tushare:{spec.key}:{run_id}:{payload_sha256}",
        )
    )
    with bulk_db() as connection:
        connection.execute(
            """
            insert into provider_raw_archives
                (id,provider,dataset_key,run_id,object_id,row_count,payload_sha256,
                 archive_sha256,uncompressed_size,compressed_size,compression,created_at)
            values (?, 'tushare', ?, ?, ?, ?, ?, ?, ?, ?, 'gzip', ?)
            on conflict(provider,dataset_key,run_id,payload_sha256) do update set
                object_id=excluded.object_id,
                row_count=excluded.row_count,
                archive_sha256=excluded.archive_sha256,
                uncompressed_size=excluded.uncompressed_size,
                compressed_size=excluded.compressed_size,
                created_at=excluded.created_at
            """,
            (
                archive_id,
                spec.key,
                run_id,
                object_id,
                len(rows),
                payload_sha256,
                archive_sha256,
                len(payload),
                len(compressed),
                utc_now(),
            ),
        )
    if async_lineage_enabled():
        typed_source = enqueue_lineage_job(
            run_id=run_id,
            dataset_key=spec.key,
            object_id=object_id,
            row_count=len(rows),
        )
    else:
        typed_source = persist_typed_source_rows(spec.key, rows, run_id)
    return {
        "id": archive_id,
        "objectId": object_id,
        "rowCount": len(rows),
        "payloadSha256": payload_sha256,
        "archiveSha256": archive_sha256,
        "uncompressedSize": len(payload),
        "compressedSize": len(compressed),
        "typedSource": typed_source,
    }


def _save_raw(
    spec: DatasetSpec,
    rows: list[dict[str, Any]],
    batch_id: str,
    *,
    assume_new: bool = False,
    archive: bool = True,
) -> tuple[int, int]:
    now = utc_now()
    prepared: dict[str, tuple[Any, ...]] = {}
    digests: dict[str, str] = {}
    canonical_rows: list[dict[str, Any]] = []
    storage_date_field = spec.date_field or spec.catalog_date_field
    for raw in rows:
        row = {key: (value.item() if hasattr(value, "item") else value) for key, value in raw.items()}
        canonical_rows.append(row)
        digest = _content_sha256(row)
        key = _record_key(spec, row)
        instrument = (str(row.get(spec.instrument_field) or "") or None) if spec.instrument_field else None
        prepared[key] = (
            "tushare",
            spec.key,
            key,
            _iso(row.get(storage_date_field)) if storage_date_field else None,
            instrument,
            "",
            digest,
            batch_id,
            row.get("update_time") or row.get("ann_date"),
            now,
        )
        digests[key] = digest
    if not prepared:
        return 0, 0

    if spec.retain_raw and archive:
        _archive_raw_batch(spec, canonical_rows, batch_id)
    # Drop our reference without mutating the list passed to the archive
    # implementation (test and alternate stores may retain it for auditing).
    canonical_rows = []

    # The row table now contains only keys, dates and hashes. Reserve enough
    # room for its indexes without multiplying by the removed JSON payload.
    _assert_disk_capacity(len(prepared) * 512)

    with bulk_db() as connection:
        existing: dict[str, tuple[str, str | None]] = {}
        keys = list(prepared)
        if not assume_new:
            lookup_size = 4000 if database_backend() == "mysql" else 500
            for offset in range(0, len(keys), lookup_size):
                chunk = keys[offset : offset + lookup_size]
                placeholders = ",".join("?" for _ in chunk)
                records = connection.execute(
                    f"""
                    select record_key, content_sha256, business_date from provider_raw_records
                    where provider='tushare' and dataset_key=? and record_key in ({placeholders})
                    """,
                    [spec.key, *chunk],
                ).fetchall()
                existing.update(
                    {
                        str(record["record_key"]): (
                            str(record["content_sha256"]),
                            str(record["business_date"]) if record["business_date"] else None,
                        )
                        for record in records
                    }
                )

        # ``record_key`` is the clustered primary-key suffix in MySQL. Sorting
        # each chunk turns otherwise random hash-key insertion into an ordered
        # B-tree walk; secondary indexes can absorb the corresponding
        # non-clustered order more cheaply.
        changed_keys = sorted(
            key
            for key in keys
            if existing.get(key) != (digests[key], prepared[key][3])
        )
        if changed_keys:
            connection.executemany(
                """
                insert into provider_raw_records
                    (provider, dataset_key, record_key, business_date, instrument_code,
                     payload_json, content_sha256, batch_id, source_updated_at, ingested_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(provider, dataset_key, record_key) do update set
                    business_date=excluded.business_date,
                    instrument_code=excluded.instrument_code,
                    payload_json=excluded.payload_json,
                    content_sha256=excluded.content_sha256,
                    batch_id=excluded.batch_id,
                    source_updated_at=excluded.source_updated_at,
                    ingested_at=excluded.ingested_at
                """,
                [prepared[key] for key in changed_keys],
            )
    inserted = sum(key not in existing for key in changed_keys)
    return inserted, len(changed_keys) - inserted


def _cancelled(run_id: str, task_id: str | None = None) -> bool:
    with db() as connection:
        row = connection.execute(
            "select cancel_requested, status, task_id from data_sync_runs where id = ?",
            (run_id,),
        ).fetchone()
    if not row:
        return True
    if task_id and row["task_id"] != task_id:
        return True
    return bool(row["cancel_requested"] or row["status"] == "cancelled")


def _current_task(run_id: str, task_id: str | None) -> bool:
    if not task_id:
        return True
    with db() as connection:
        row = connection.execute("select task_id from data_sync_runs where id=?", (run_id,)).fetchone()
    return bool(row and row["task_id"] == task_id)


def audit_existing_data() -> dict[str, int]:
    """Register legacy/untrusted partitions so repair is explicit and auditable."""
    detected = 0
    with db() as connection:
        rows = connection.execute(
            """
            select source, symbol, min(trade_date) as start_date, max(trade_date) as end_date, count(*) as row_count
            from market_daily_bars
            where asset_class='equity' and market='china' and venue='china'
              and resolution='daily' and data_type='trade'
              and source in ('test', 'manual', 'csv')
            group by source, symbol
            """
        ).fetchall()
        for row in rows:
            existing = connection.execute(
                """
                select id from data_record_issues
                where dataset_key='daily' and source=? and instrument_code=?
                  and issue_code='untrusted_source' and status='open'
                limit 1
                """,
                (row["source"], row["symbol"]),
            ).fetchone()
            if existing:
                continue
            connection.execute(
                """
                insert into data_record_issues
                    (id,dataset_key,source,instrument_code,start_date,end_date,issue_code,severity,status,details_json,detected_at)
                values (?,'daily',?,?,?,?,'untrusted_source','warning','open',?,?)
                """,
                (
                    str(uuid.uuid4()), row["source"], row["symbol"], row["start_date"], row["end_date"],
                    json_dump({"rowCount": row["row_count"], "action": "replace_with_tushare"}), utc_now(),
                ),
            )
            detected += 1
    return {"detected": detected}


def _rolling_throughput_metrics(
    metrics: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    result = dict(metrics)
    now = time.time()
    counters = [
        int(result.get("downloadedRows") or 0),
        int(result.get("committedRows") or 0),
        int(result.get("sessionProcessedUnits") or 0),
        int(result.get("apiCalls") or 0),
    ]
    samples = list((previous or {}).get("_rateSamples") or [])
    if samples and any(int(samples[-1][index + 1]) > value for index, value in enumerate(counters)):
        samples = []
    sample = [now, *counters]
    if samples and now - float(samples[-1][0]) < 0.5:
        samples[-1] = sample
    else:
        samples.append(sample)
    cutoff = now - 60.0
    recent = [entry for entry in samples if float(entry[0]) > cutoff]
    if len(recent) >= 2:
        samples = recent
    else:
        older = [entry for entry in samples if float(entry[0]) <= cutoff]
        samples = ([older[-1]] if older else []) + recent
        samples = samples or [sample]
    samples = samples[-121:]
    baseline = samples[0]
    span = max(0.001, now - float(baseline[0]))
    if len(samples) == 1:
        rolling_download = float(result.get("downloadRowsPerSecond") or 0.0)
        rolling_write = float(result.get("writeRowsPerSecond") or 0.0)
        rolling_units = float(result.get("unitsPerSecond") or 0.0)
        rolling_api = float(result.get("apiCallsPerMinute") or 0.0)
    else:
        rolling_download = max(0, counters[0] - int(baseline[1])) / span
        rolling_write = max(0, counters[1] - int(baseline[2])) / span
        rolling_units = max(0, counters[2] - int(baseline[3])) / span
        rolling_api = max(0, counters[3] - int(baseline[4])) * 60.0 / span
    remaining = max(0, int(result.get("totalUnits") or 0) - int(result.get("processedUnits") or 0))
    result.update(
        {
            "rollingDownloadRowsPerSecond": round(rolling_download, 2),
            "rollingWriteRowsPerSecond": round(rolling_write, 2),
            "rollingUnitsPerSecond": round(rolling_units, 3),
            "rollingApiCallsPerMinute": round(min(DEFAULT_CALLS_PER_MINUTE, rolling_api), 2),
            "rollingEtaSeconds": round(remaining / rolling_units, 1) if rolling_units > 0 else None,
            "rateWindowSeconds": round(min(60.0, span), 1),
            "_rateSamples": samples,
        }
    )
    return result


def _item(run_id: str, dataset: str, **fields: Any) -> None:
    checkpoint = fields.pop("checkpoint", None)
    metrics = fields.pop("metrics", None)
    existing: dict[str, Any] = {}
    if checkpoint is not None or metrics is not None:
        with db() as connection:
            existing_row = connection.execute(
                "select * from data_sync_items where run_id=? and dataset_key=?",
                (run_id, dataset),
            ).fetchone()
        existing = row_to_dict(existing_row) or {}
    if metrics is not None:
        fields["metrics_json"] = json_dump(
            _rolling_throughput_metrics(dict(metrics), dict(existing.get("metrics") or {}))
        )
    if checkpoint is not None:
        previous_checkpoint = existing.get("checkpoint") or {}
        previous_index = int(previous_checkpoint.get("index") or 0)
        next_index = int(checkpoint.get("index") or 0)
        if previous_index > next_index:
            return
        for counter in ("processed", "inserted", "updated", "failed"):
            if counter in fields:
                fields[counter] = max(int(existing.get(counter) or 0), int(fields[counter] or 0))
        fields["checkpoint_json"] = json_dump(checkpoint)
    else:
        fields["checkpoint_json"] = None
    clean = {key: value for key, value in fields.items() if value is not None}
    assignments = ", ".join(f"{key} = ?" for key in clean)
    with db() as connection:
        connection.execute(
            f"update data_sync_items set {assignments} where run_id = ? and dataset_key = ?",
            [*clean.values(), run_id, dataset],
        )
        connection.execute(
            "update data_sync_runs set heartbeat_at=? where id=? and status in ('queued','running','cancelling')",
            (utc_now(), run_id),
        )


def _disk_hard_reserve_bytes(total_bytes: int) -> int:
    return max(500 * 1024**3, int(total_bytes * 0.50))


def _disk_metrics() -> dict[str, Any]:
    path = os.environ.get("LEAN_DATA_SYNC_SPOOL_DIR") or str(os.environ.get("LEAN_RUNTIME_DIR") or "/tmp")
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        usage = shutil.disk_usage("/")
    reserve = _disk_hard_reserve_bytes(usage.total)
    metrics = {
        "diskFreeBytes": usage.free,
        "diskTotalBytes": usage.total,
        "diskFreePercent": round(usage.free * 100 / max(usage.total, 1), 2),
        "diskReserveBytes": reserve,
        "diskWritableBytes": max(0, usage.free - reserve),
    }
    metrics.update(_database_storage_metrics())
    return metrics


_DATABASE_SIZE_CACHE: tuple[float, dict[str, Any]] = (0.0, {})
_DATABASE_SIZE_REFRESH_LOCK = threading.Lock()
_DATABASE_SIZE_REFRESHING = False


def _directory_allocated_bytes(path: Path) -> int:
    """Return allocated bytes without following links outside ``path``."""
    total = 0
    pending = [path]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except OSError:
            continue
        for entry in entries:
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            blocks = getattr(stat, "st_blocks", 0)
            total += int(blocks * 512 if blocks else stat.st_size)
            if entry.is_dir(follow_symlinks=False):
                pending.append(Path(entry.path))
    return total


def _measure_database_storage(observer_dir: Path) -> dict[str, Any]:
    if str(observer_dir) != "." and observer_dir.is_dir():
        return {
            "databaseBytes": _directory_allocated_bytes(observer_dir),
            "databaseSizeSource": "physical_data_directory",
        }
    with db() as connection:
        row = connection.execute(
            """
            select coalesce(sum(data_length + index_length), 0) as table_bytes
            from information_schema.tables where table_schema=database()
            """
        ).fetchone()
        try:
            logs = connection.execute("show binary logs").fetchall()
            binlog_bytes = sum(int(item.get("File_size") or item.get("file_size") or 0) for item in logs)
        except Exception:
            binlog_bytes = 0
    return {
        "databaseBytes": int(row["table_bytes"] or 0) + binlog_bytes,
        "databaseSizeSource": "mysql_metadata_estimate",
    }


def _refresh_database_storage(observer_dir: Path) -> None:
    global _DATABASE_SIZE_CACHE, _DATABASE_SIZE_REFRESHING
    try:
        measured = _measure_database_storage(observer_dir)
        with _DATABASE_SIZE_REFRESH_LOCK:
            _DATABASE_SIZE_CACHE = (time.monotonic(), measured)
    finally:
        with _DATABASE_SIZE_REFRESH_LOCK:
            _DATABASE_SIZE_REFRESHING = False


def _database_storage_metrics() -> dict[str, Any]:
    global _DATABASE_SIZE_CACHE, _DATABASE_SIZE_REFRESHING
    on_demand_limit_gb = os.environ.get("LEAN_MYSQL_ON_DEMAND_MAX_DATABASE_GB")
    if on_demand_limit_gb is None:
        # Backward-compatible alias; it no longer applies to one-click sync.
        on_demand_limit_gb = os.environ.get("LEAN_MYSQL_MAX_DATABASE_GB", "50")
    on_demand_limit = int(float(on_demand_limit_gb) * 1024**3)
    if database_backend() != "mysql":
        return {
            "databaseBytes": 0,
            "databaseLimitBytes": 0,
            "databaseUsagePercent": 0.0,
            "databaseLimitEnforced": False,
            "onDemandDatabaseLimitBytes": on_demand_limit,
            "databaseSizeSource": "not_mysql",
        }
    checked_at, cached = _DATABASE_SIZE_CACHE
    cache_seconds = max(5.0, float(os.environ.get("LEAN_MYSQL_SIZE_CACHE_SECONDS", "60")))
    observer_dir = Path(os.environ.get("LEAN_MYSQL_DATA_OBSERVER_DIR", "")).expanduser()
    if not cached:
        cached = _measure_database_storage(observer_dir)
        _DATABASE_SIZE_CACHE = (time.monotonic(), cached)
    elif time.monotonic() - checked_at >= cache_seconds:
        with _DATABASE_SIZE_REFRESH_LOCK:
            if not _DATABASE_SIZE_REFRESHING:
                _DATABASE_SIZE_REFRESHING = True
                threading.Thread(
                    target=_refresh_database_storage,
                    args=(observer_dir,),
                    name="mysql-storage-metrics",
                    daemon=True,
                ).start()
    result = {
        "databaseBytes": int(cached.get("databaseBytes") or 0),
        # One-click bulk synchronization is intentionally not capped by the
        # on-demand cache policy. It remains protected by the disk reserve.
        "databaseLimitBytes": 0,
        "databaseUsagePercent": 0.0,
        "databaseLimitEnforced": False,
        "onDemandDatabaseLimitBytes": on_demand_limit,
        "databaseSizeSource": str(cached.get("databaseSizeSource") or "unknown"),
    }
    return result


def _assert_disk_capacity(estimated_write_bytes: int = 0, *, enforce_database_limit: bool = False) -> None:
    metrics = _disk_metrics()
    free = int(metrics["diskFreeBytes"])
    total = int(metrics["diskTotalBytes"])
    hard_reserve = int(metrics.get("diskReserveBytes") or _disk_hard_reserve_bytes(total))
    database_limit = int(metrics.get("onDemandDatabaseLimitBytes") or 0)
    estimated_write = max(0, estimated_write_bytes)
    # Canonical tables contain both governed bulk-sync rows and on-demand
    # repairs, so the physical size of the whole MySQL instance is not an
    # on-demand cache usage measurement. Comparing that aggregate size with
    # this limit permanently blocks small repairs as soon as a legitimate
    # full sync grows beyond the default 50 GiB ceiling. Bound the individual
    # on-demand write here; aggregate growth remains protected by the physical
    # disk reserve below.
    if enforce_database_limit and database_limit and estimated_write > database_limit:
        raise RuntimeError(
            "on_demand_database_guard: estimated MySQL on-demand write exceeds the per-request limit; "
            f"estimatedWrite={estimated_write}, limit={database_limit}. "
            "Choose an external download target, reduce the requested range, or move "
            "LEAN_MYSQL_DATA_DIR to external storage."
        )
    if free - estimated_write < hard_reserve:
        raise RuntimeError(
            "data_sync_disk_guard: insufficient free space; "
            f"free={free}, estimatedWrite={estimated_write}, reserve={hard_reserve}"
        )


def _throughput_metrics(
    started: float,
    *,
    phase: str,
    api_calls: int,
    downloaded: int,
    committed: int,
    queue_depth: int = 0,
    processed_units: int = 0,
    fetched_units: int | None = None,
    total_units: int = 0,
    empty_units: int = 0,
    validated: int = 0,
    quarantined: int = 0,
    endpoint_calls: dict[str, int] | None = None,
    timings: dict[str, float] | None = None,
    rate_units: int | None = None,
    include_storage: bool = True,
) -> dict[str, Any]:
    elapsed = max(0.001, time.monotonic() - started)
    session_units = processed_units if rate_units is None else max(0, rate_units)
    units_per_second = session_units / elapsed
    remaining_units = max(0, total_units - processed_units)
    return {
        "phase": phase,
        "apiCalls": api_calls,
        # This is an elapsed-time average, not a provider-observed request
        # rate. Cap it at the global rolling-window quota so a legal startup
        # burst is never presented as if TuShare's limit had been exceeded.
        "apiCallsPerMinute": round(min(DEFAULT_CALLS_PER_MINUTE, api_calls * 60 / elapsed), 2),
        "apiQuotaPerMinute": DEFAULT_CALLS_PER_MINUTE,
        "downloadedRows": downloaded,
        "committedRows": committed,
        "downloadRowsPerSecond": round(downloaded / elapsed, 2),
        "writeRowsPerSecond": round(committed / elapsed, 2),
        "queueDepth": queue_depth,
        "processedUnits": processed_units,
        "fetchedUnits": processed_units if fetched_units is None else max(0, fetched_units),
        "sessionProcessedUnits": session_units,
        "totalUnits": total_units,
        "emptyUnits": empty_units,
        "validatedRows": validated,
        "quarantinedRows": quarantined,
        "unitsPerSecond": round(units_per_second, 3),
        "etaSeconds": round(remaining_units / units_per_second, 1) if units_per_second > 0 else None,
        "endpointCalls": endpoint_calls or {},
        "timingsMs": {key: round(value, 2) for key, value in (timings or {}).items()},
        "elapsedSeconds": round(elapsed, 2),
        **(_disk_metrics() if include_storage else {}),
    }


def _ensure_work_items(run_id: str, dataset: str, work: list[tuple[str, int]]) -> None:
    if not work:
        return
    with db() as connection:
        connection.executemany(
            """
            insert into data_sync_work_items
                (run_id,dataset_key,work_key,sequence_no,status)
            values (?,?,?,?,'pending')
            on conflict(run_id,dataset_key,work_key) do update set
                sequence_no=excluded.sequence_no
            """,
            [(run_id, dataset, key, sequence) for key, sequence in work],
        )


def _work_status(run_id: str, dataset: str) -> dict[str, str]:
    with db() as connection:
        rows = connection.execute(
            "select work_key,status from data_sync_work_items where run_id=? and dataset_key=?",
            (run_id, dataset),
        ).fetchall()
    return {str(row["work_key"]): str(row["status"]) for row in rows}


def _mark_work_items(
    run_id: str,
    dataset: str,
    keys: list[str],
    *,
    status: str,
    row_counts: dict[str, int] | None = None,
    error: str | None = None,
) -> None:
    if not keys:
        return
    now = utc_now()
    with db() as connection:
        connection.executemany(
            """
            update data_sync_work_items
            set status=?, attempts=attempts+1, row_count=?, error=?,
                fetched_at=case when ?='fetched' then ? else fetched_at end,
                committed_at=case when ?='committed' then ? else committed_at end
            where run_id=? and dataset_key=? and work_key=?
            """,
            [
                (
                    status,
                    int((row_counts or {}).get(key, 0)),
                    error,
                    status,
                    now,
                    status,
                    now,
                    run_id,
                    dataset,
                    key,
                )
                for key in keys
            ],
        )


def _item_state(run_id: str, dataset: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute(
            "select * from data_sync_items where run_id=? and dataset_key=?",
            (run_id, dataset),
        ).fetchone()
    return row_to_dict(row) or {}


def _checkpoint_complete(item: dict[str, Any]) -> bool:
    checkpoint = item.get("checkpoint") or {}
    total = int(checkpoint.get("total") or 0)
    # The adj_factor fast path has persistent work items, so reaching the end
    # only means every item was attempted; failed work must remain resumable.
    # Legacy generic datasets intentionally preserve their completed partial
    # checkpoints because retrying them restarts the whole instrument loop.
    work_items_complete = (
        str(item.get("dataset_key") or "") not in {"daily", "adj_factor", "suspend_d", "stk_limit"}
        or int(item.get("failed") or checkpoint.get("failed") or 0) == 0
    )
    return (
        work_items_complete
        and total > 0
        and int(checkpoint.get("index") or 0) >= total
    )


def _listed_securities() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select symbol, listed_date, delisted_date, status
            from securities
            where status in ('listed','delisted','pending')
              and symbol not like '200%'
              and symbol not like '900%'
            order by symbol
            """
        ).fetchall()
    return rows_to_dicts(rows)


def _latest_open_trade_date(end_date: str, market: str = "china") -> str:
    """Return the last known open session, avoiding weekend/holiday API fan-out."""
    with db() as connection:
        row = connection.execute(
            """
            select max(trade_date) as trade_date
            from trade_calendar
            where market=? and is_open=1 and trade_date<=?
            """,
            (market, end_date),
        ).fetchone()
    return str(row["trade_date"]) if row and row["trade_date"] else end_date


def _latest_bar(symbol: str) -> str | None:
    with db() as connection:
        row = connection.execute(
            """
            select max(trade_date) as trade_date from market_daily_bars
            where symbol=? and adjust='raw' and source='tushare'
              and asset_class='equity' and market='china' and venue='china'
              and resolution='daily' and data_type='trade'
            """,
            (symbol,),
        ).fetchone()
    return str(row["trade_date"]) if row and row["trade_date"] else None


def _latest_bars_by_symbol() -> dict[str, str]:
    with db() as connection:
        rows = connection.execute(
            """
            select symbol,max(trade_date) as trade_date
            from market_daily_bars
            where adjust='raw' and source='tushare'
              and asset_class='equity' and market='china' and venue='china'
              and resolution='daily' and data_type='trade'
            group by symbol
            """
        ).fetchall()
    return {str(row["symbol"]): str(row["trade_date"]) for row in rows if row["trade_date"]}


def _latest_raw_date(spec: DatasetSpec, symbol: str | None = None) -> str | None:
    with db() as connection:
        if spec.key == "adj_factor":
            if symbol:
                row = connection.execute(
                    "select max(trade_date) as business_date from adjustment_factors where source='tushare' and symbol=?",
                    (symbol,),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    select last_data_date as business_date from provider_dataset_catalog
                    where provider='tushare' and dataset_key='adj_factor'
                    """
                ).fetchone()
                if not row or not row["business_date"]:
                    row = connection.execute(
                        "select max(trade_date) as business_date from adjustment_factors where source='tushare'",
                    ).fetchone()
            return str(row["business_date"]) if row and row["business_date"] else None
        if symbol:
            suffix = ".SH" if symbol.startswith(("5", "6", "9")) else ".BJ" if symbol.startswith(("4", "8")) else ".SZ"
            row = connection.execute(
                """
                select max(business_date) as business_date
                from provider_raw_records
                where provider='tushare' and dataset_key=?
                  and instrument_code in (?, ?)
                """,
                (spec.key, symbol, f"{symbol}{suffix}"),
            ).fetchone()
        else:
            row = connection.execute(
                """
                select max(business_date) as business_date
                from provider_raw_records
                where provider='tushare' and dataset_key=?
                """,
                (spec.key,),
            ).fetchone()
    return str(row["business_date"]) if row and row["business_date"] else None


def _latest_raw_dates_by_instrument(spec: DatasetSpec) -> dict[str, str]:
    """Load all instrument watermarks once instead of scanning per symbol."""
    with db() as connection:
        rows = connection.execute(
            """
            select instrument_code, max(business_date) as business_date
            from provider_raw_records
            where provider='tushare' and dataset_key=? and instrument_code is not null
            group by instrument_code
            """,
            (spec.key,),
        ).fetchall()
    result: dict[str, str] = {}
    for row in rows:
        instrument = str(row["instrument_code"] or "").strip()
        business_date = str(row["business_date"] or "").strip()
        if not instrument or not business_date:
            continue
        result[instrument] = business_date
        # Instrument-scoped datasets currently use A-share codes. Store the
        # normalized six-digit alias used by `_listed_securities()` as well.
        result.setdefault(instrument.split(".", 1)[0], business_date)
    return result


def _raw_row_for_symbol(spec: DatasetSpec, row: dict[str, Any], symbol: str | None) -> dict[str, Any]:
    if spec.normalizer == "index_weight":
        return {
            **row,
            "index_code": "000300.SH",
            "con_code": row.get("symbol"),
        }
    if not symbol or row.get(spec.instrument_field or ""):
        return row
    suffix = ".SH" if symbol.startswith(("5", "6", "9")) else ".BJ" if symbol.startswith(("4", "8")) else ".SZ"
    result = {**row, spec.instrument_field or "ts_code": f"{symbol}{suffix}"}
    if spec.normalizer == "daily":
        # ``TushareAdapter.daily_rows`` deliberately exposes the canonical
        # market-data shape (``date``/``symbol``), while the provider lineage
        # manifest and lightweight raw index use TuShare's
        # ``trade_date``/``ts_code`` contract.  Validate the provider-shaped
        # audit row, not the canonical import row, otherwise every real daily
        # response is rejected even though its date was normalized correctly.
        result.setdefault("trade_date", row.get("date"))
    elif spec.normalizer == "dividend":
        result.setdefault("ann_date", (row.get("metadata") or {}).get("announce_date") or row.get("ex_date"))
        result.setdefault("end_date", row.get("ex_date"))
        result.setdefault("div_proc", (row.get("metadata") or {}).get("process"))
    elif spec.normalizer == "financial":
        result.setdefault("end_date", row.get("report_date"))
        result.setdefault("ann_date", row.get("announce_date"))
        result.setdefault("report_type", row.get("statement_type"))
    return result


def _sync_stock_basic(adapter: TushareAdapter, batch_id: str) -> tuple[int, int, int]:
    api_before = _api_snapshot(adapter)
    records = adapter.stock_basic(["L", "D", "P"])
    spec = next(item for item in DATASET_REGISTRY if item.key == "stock_basic")
    raw_rows = []
    for item in records:
        raw_rows.append({**item, "ts_code": item.get("ts_code") or item.get("symbol")})
    validation = _validate_dataset_rows(spec, raw_rows)
    if spec.retain_raw:
        inserted, updated = _save_raw(spec, raw_rows, batch_id)
    else:
        inserted, updated = len(raw_rows), 0
    # The endpoint returns the full security master on every request. Its
    # canonical bulk upsert is idempotent and replaces the former duplicate
    # raw-row JSON write.
    if inserted or updated:
        import_security_master(records, source="tushare:stock_basic", universe_code="ALL_A", bulk=True)
    _record_ingestion_manifest(
        run_id=batch_id,
        spec=spec,
        scope_key="global",
        request={"listStatus": ["L", "D", "P"]},
        rows=raw_rows,
        validation=validation,
        endpoint_counts=_api_delta(api_before, _api_snapshot(adapter)),
        coverage_start=None,
        coverage_end=None,
    )
    return len(records), inserted, updated


def _sync_calendar(
    adapter: TushareAdapter,
    batch_id: str,
    end_date: str,
    *,
    full_refresh: bool = False,
) -> tuple[int, int, int]:
    spec = next(item for item in DATASET_REGISTRY if item.key == "trade_cal")
    latest = None if full_refresh else _latest_raw_date(spec)
    start_date = (date.fromisoformat(latest) + timedelta(days=1)).isoformat() if latest else "1990-01-01"
    if start_date > end_date:
        validation = _validate_dataset_rows(spec, [])
        _record_ingestion_manifest(
            run_id=batch_id,
            spec=spec,
            scope_key="SSE",
            request={"exchange": "SSE", "startDate": start_date, "endDate": end_date, "noOp": True},
            rows=[],
            validation=validation,
            endpoint_counts={},
            coverage_start=latest,
            coverage_end=end_date,
        )
        _set_coverage_watermark(
            spec,
            scope_key="SSE",
            coverage_start=latest or end_date,
            coverage_end=end_date,
            rows=[],
            run_id=batch_id,
            validation_status=str(validation["status"]),
        )
        return 0, 0, 0
    api_before = _api_snapshot(adapter)
    rows = adapter.trade_calendar(start_date, end_date, exchange="SSE")
    raw = [{**item, "cal_date": str(item.get("trade_date") or "").replace("-", ""), "exchange": "SSE"} for item in rows]
    validation = _validate_dataset_rows(spec, raw)
    inserted, updated = _save_raw(spec, raw, batch_id)
    from .ashare_repository import upsert_trade_calendar
    open_dates = [str(item["trade_date"]) for item in rows if item.get("is_open")]
    upsert_trade_calendar("china", open_dates, source="tushare:trade_cal:SSE", batch_id=batch_id)
    _record_ingestion_manifest(
        run_id=batch_id,
        spec=spec,
        scope_key="SSE",
        request={"exchange": "SSE", "startDate": start_date, "endDate": end_date},
        rows=raw,
        validation=validation,
        endpoint_counts=_api_delta(api_before, _api_snapshot(adapter)),
        coverage_start=start_date,
        coverage_end=end_date,
    )
    _set_coverage_watermark(
        spec,
        scope_key="SSE",
        coverage_start=start_date,
        coverage_end=end_date,
        rows=raw,
        run_id=batch_id,
        validation_status=str(validation["status"]),
    )
    return len(rows), inserted, updated


def _sync_daily_by_trade_date(
    adapter: TushareAdapter,
    spec: DatasetSpec,
    run_id: str,
    batch_id: str,
    end_date: str,
    task_id: str | None,
    *,
    securities: list[dict[str, Any]],
    start_after: str,
    reconcile_full_snapshot: bool = False,
) -> tuple[int, int, int, int]:
    """Increment daily bars with one full-market request per missing session."""
    state = _item_state(run_id, spec.key)
    processed = int(state.get("processed") or 0)
    inserted = int(state.get("inserted") or 0)
    updated = int(state.get("updated") or 0)
    failed = int(state.get("failed") or 0)
    started = time.monotonic()
    api_before = _api_snapshot(adapter)
    endpoint_calls: dict[str, int] = {}
    api_calls = downloaded = committed = empty_units = validated = 0
    fetched_units = processed
    timings = {
        "fetchWait": 0.0,
        "validate": 0.0,
        "rawArchive": 0.0,
        "canonicalCompareWrite": 0.0,
        "metadata": 0.0,
    }
    concurrency = max(1, min(32, int(os.environ.get("LEAN_TUSHARE_FETCH_CONCURRENCY", "16"))))
    batch_dates = _sync_batch_units("LEAN_DAILY_INCREMENT_BATCH_DATES", 16)
    chunk_rows = _sync_batch_rows("LEAN_DAILY_SYNC_CHUNK_ROWS")
    with db() as connection:
        dates = connection.execute(
            """
            select trade_date from trade_calendar
            where market='china' and is_open=1 and trade_date>? and trade_date<=?
            order by trade_date
            """,
            (start_after, end_date),
        ).fetchall()
    work = [
        {"work_key": str(row["trade_date"]), "sequence": sequence}
        for sequence, row in enumerate(dates, start=1)
    ]
    _ensure_work_items(
        run_id,
        spec.key,
        [(str(entry["work_key"]), int(entry["sequence"])) for entry in work],
    )
    statuses = _work_status(run_id, spec.key)
    pending_work = [entry for entry in work if statuses.get(str(entry["work_key"])) != "committed"]
    processed = sum(1 for entry in work if statuses.get(str(entry["work_key"])) == "committed")
    session_processed_base = processed
    total = len(work)
    if not pending_work:
        _item(
            run_id,
            spec.key,
            metrics=_throughput_metrics(
                started,
                phase="validate",
                api_calls=0,
                downloaded=0,
                committed=0,
                processed_units=processed,
                total_units=total,
                rate_units=0,
            ),
        )
        return processed, inserted, updated, failed

    securities_by_symbol = {str(item["symbol"]): item for item in securities}
    buffered: list[dict[str, Any]] = []
    buffered_rows = 0
    last_committed_date: str | None = None
    failure_samples: list[dict[str, Any]] = []

    def fetch(entry: dict[str, Any]) -> list[dict[str, Any]]:
        return _call_with_retry(lambda: adapter.daily_rows_for_date(str(entry["work_key"])))

    def flush() -> None:
        nonlocal buffered, buffered_rows, processed, inserted, updated, committed
        nonlocal empty_units, last_committed_date
        if not buffered:
            return
        _item(
            run_id,
            spec.key,
            metrics=_throughput_metrics(
                started,
                phase="load",
                api_calls=api_calls,
                downloaded=downloaded,
                committed=committed,
                queue_depth=0,
                processed_units=processed,
                fetched_units=fetched_units,
                total_units=total,
                empty_units=empty_units,
                validated=validated,
                endpoint_calls=endpoint_calls,
                timings=timings,
                rate_units=processed - session_processed_base,
            ),
        )
        all_raw_rows = [row for entry in buffered for row in entry["raw_rows"]]

        grouped: dict[str, list[dict[str, Any]]] = {}
        for entry in buffered:
            for row in entry["rows"]:
                grouped.setdefault(str(row["symbol"]), []).append(row)
        first_date = str(buffered[0]["work_key"])
        last_date = str(buffered[-1]["work_key"])
        import_entries = [
            {
                "symbol": symbol,
                "rows": rows,
                "listed_date": securities_by_symbol.get(symbol, {}).get("listed_date"),
                "delisted_date": securities_by_symbol.get(symbol, {}).get("delisted_date"),
                "snapshot_start": first_date,
                "snapshot_end": last_date,
            }
            for symbol, rows in sorted(grouped.items())
        ]
        stage_started = time.perf_counter()
        if all_raw_rows:
            _archive_raw_batch(spec, all_raw_rows, batch_id)
        timings["rawArchive"] += (time.perf_counter() - stage_started) * 1000
        stage_started = time.perf_counter()
        result = import_ashare_research_batch(
            import_entries,
            sync_run_id=run_id,
            reconcile_full_snapshot=False,
        )
        if reconcile_full_snapshot:
            _item(
                run_id,
                spec.key,
                metrics=_throughput_metrics(
                    started,
                    phase="reconcile",
                    api_calls=api_calls,
                    downloaded=downloaded,
                    committed=committed,
                    queue_depth=0,
                    processed_units=processed,
                    fetched_units=fetched_units,
                    total_units=total,
                    empty_units=empty_units,
                    validated=validated,
                    endpoint_calls=endpoint_calls,
                    timings=timings,
                    rate_units=processed - session_processed_base,
                ),
            )
            _reconcile_daily_trade_date_batch(
                first_date,
                last_date,
                [row for entry in buffered for row in entry["rows"]],
                run_id=run_id,
            )
        timings["canonicalCompareWrite"] += (time.perf_counter() - stage_started) * 1000
        row_counts = {str(entry["work_key"]): len(entry["rows"]) for entry in buffered}
        stage_started = time.perf_counter()
        _persist_trade_date_batch_metadata(
            run_id=run_id,
            spec=spec,
            entries=buffered,
            endpoint_counts=endpoint_calls,
            row_counts=row_counts,
            batch_id=str(result.get("batch_id") or batch_id),
        )
        timings["metadata"] += (time.perf_counter() - stage_started) * 1000
        batch_rows = sum(row_counts.values())
        inserted += batch_rows
        updated += int(result.get("updatedRows") or 0)
        committed += batch_rows
        empty_units += sum(1 for entry in buffered if not entry["rows"])
        processed += len(buffered)
        last_committed_date = last_date
        _item(
            run_id,
            spec.key,
            processed=processed,
            inserted=inserted,
            updated=updated,
            failed=failed,
            error=json_dump({"failed": failed, "samples": failure_samples}) if failed else "",
            checkpoint={"index": processed, "total": total, "symbol": last_date},
            metrics=_throughput_metrics(
                started,
                phase="load",
                api_calls=api_calls,
                downloaded=downloaded,
                committed=committed,
                processed_units=processed,
                total_units=total,
                empty_units=empty_units,
                validated=validated,
                endpoint_calls=endpoint_calls,
                timings=timings,
                rate_units=processed - session_processed_base,
            ),
        )
        buffered = []
        buffered_rows = 0

    _item(
        run_id,
        spec.key,
        metrics=_throughput_metrics(
            started,
            phase="fetch",
            api_calls=api_calls,
            downloaded=downloaded,
            committed=committed,
            processed_units=processed,
            fetched_units=fetched_units,
            total_units=total,
            endpoint_calls=endpoint_calls,
            rate_units=processed - session_processed_base,
        ),
    )
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="tushare-daily-date") as executor:
        pending: dict[int, Any] = {}
        submit_cursor = 0
        stop_submission = False
        while submit_cursor < min(len(pending_work), concurrency):
            entry = pending_work[submit_cursor]
            pending[int(entry["sequence"])] = executor.submit(fetch, entry)
            submit_cursor += 1
        for entry in pending_work:
            if not buffered and _cancelled(run_id, task_id):
                for future in pending.values():
                    future.cancel()
                break
            sequence = int(entry["sequence"])
            future = pending.pop(sequence)
            try:
                stage_started = time.perf_counter()
                rows = future.result()
                timings["fetchWait"] += (time.perf_counter() - stage_started) * 1000
                endpoint_calls = _api_delta(api_before, _api_snapshot(adapter))
                api_calls = sum(endpoint_calls.values())
                downloaded += len(rows)
                fetched_units += 1
                stage_started = time.perf_counter()
                raw_rows = [
                    _raw_row_for_symbol(spec, row, str(row.get("symbol") or ""))
                    for row in rows
                ]
                validation = _validate_dataset_rows(spec, raw_rows)
                validated += len(raw_rows)
                timings["validate"] += (time.perf_counter() - stage_started) * 1000
                trade_date = str(entry["work_key"])
                buffered.append(
                    {
                        **entry,
                        "rows": rows,
                        "raw_rows": raw_rows,
                        "validation": validation,
                        "request": {"tradeDate": trade_date},
                        "coverage_start": trade_date,
                        "coverage_end": trade_date,
                    }
                )
                buffered_rows += len(rows)
            except Exception as exc:  # noqa: BLE001
                flush()
                failed += 1
                trade_date = str(entry["work_key"])
                sample = _record_sync_failure(spec, None, trade_date, trade_date, exc)
                if len(failure_samples) < 10:
                    failure_samples.append(sample)
                _mark_work_items(run_id, spec.key, [trade_date], status="failed", error=str(exc))
                processed += 1
                stop_submission = True
                for pending_future in pending.values():
                    pending_future.cancel()
                break
            else:
                # A batch-write failure is not an instrument fetch failure.
                # Let it abort the dataset with all work items still pending;
                # otherwise the same growing buffer is archived and written
                # again for every following symbol.
                if len(buffered) >= batch_dates or buffered_rows >= chunk_rows:
                    flush()
            finally:
                if not stop_submission and submit_cursor < len(pending_work):
                    next_entry = pending_work[submit_cursor]
                    pending[int(next_entry["sequence"])] = executor.submit(fetch, next_entry)
                    submit_cursor += 1
        flush()

    if last_committed_date:
        _advance_sparse_market_watermarks(
            spec,
            securities,
            coverage_end=last_committed_date,
            run_id=run_id,
        )
    return processed, inserted, updated, failed


def _sync_daily(
    adapter: TushareAdapter,
    run_id: str,
    batch_id: str,
    end_date: str,
    task_id: str | None = None,
    full_refresh: bool = False,
    reconcile_full_snapshot: bool | None = None,
    minimum_start_date: str | None = None,
) -> tuple[int, int, int, int]:
    reconcile_snapshot = (
        full_refresh
        if reconcile_full_snapshot is None
        else bool(reconcile_full_snapshot)
    )
    state = _item_state(run_id, "daily")
    checkpoint = state.get("checkpoint") or {}
    resume_after = max(0, int(checkpoint.get("index") or 0))
    processed = int(state.get("processed") or 0)
    session_processed_base = processed
    inserted = int(state.get("inserted") or 0)
    updated = int(state.get("updated") or 0)
    failed = int(state.get("failed") or 0)
    securities = _listed_securities()
    spec = next(item for item in DATASET_REGISTRY if item.key == "daily")
    existing_work = _work_status(run_id, spec.key)
    active_securities = [
        item for item in securities if str(item.get("status") or "listed") == "listed"
    ]
    active_scope_keys = {str(item["symbol"]) for item in active_securities}
    coverage_by_scope = _coverage_watermarks(spec) if not full_refresh else {}
    active_coverage = {
        symbol: coverage_by_scope[symbol]
        for symbol in active_scope_keys
        if symbol in coverage_by_scope
    }
    market_start_after = min(active_coverage.values()) if active_coverage else None
    uncovered_active = [
        item for item in active_securities if str(item["symbol"]) not in active_coverage
    ]
    uncovered_started_after_frontier = bool(
        market_start_after
        and all(str(item.get("listed_date") or "") > market_start_after for item in uncovered_active)
    )
    resumed_symbol_work = any(
        len(key) != 10 or key[4:5] != "-" or key[7:8] != "-"
        for key in existing_work
    )
    date_mode_start_after: str | None = None
    if (
        full_refresh
        and not resumed_symbol_work
        and hasattr(adapter, "daily_rows_for_date")
        and active_scope_keys
    ):
        first_date = min(
            max(str(item.get("listed_date") or "1990-12-19"), minimum_start_date or "1990-12-19")
            for item in active_securities
        )
        date_mode_start_after = (date.fromisoformat(first_date) - timedelta(days=1)).isoformat()
    elif (
        not full_refresh
        and not resumed_symbol_work
        and hasattr(adapter, "daily_rows_for_date")
        and active_scope_keys
        and market_start_after
        and (not uncovered_active or uncovered_started_after_frontier)
    ):
        date_mode_start_after = market_start_after
    if date_mode_start_after:
        return _sync_daily_by_trade_date(
            adapter,
            spec,
            run_id,
            batch_id,
            end_date,
            task_id,
            securities=securities,
            start_after=date_mode_start_after,
            reconcile_full_snapshot=reconcile_snapshot,
        )
    latest_by_symbol = {} if full_refresh else _latest_bars_by_symbol()
    started = time.monotonic()
    api_before = _api_snapshot(adapter)
    endpoint_calls: dict[str, int] = {}
    api_calls = downloaded = committed = empty_units = validated = 0
    fetched_units = processed
    timings = {
        "fetchWait": 0.0,
        "validate": 0.0,
        "rawArchive": 0.0,
        "canonicalCompareWrite": 0.0,
        "metadata": 0.0,
    }
    concurrency = max(1, min(32, int(os.environ.get("LEAN_TUSHARE_FETCH_CONCURRENCY", "16"))))
    batch_units = _sync_batch_units("LEAN_DAILY_SYNC_BATCH_UNITS", 16)
    chunk_rows = _sync_batch_rows("LEAN_DAILY_SYNC_CHUNK_ROWS")

    work: list[tuple[int, dict[str, Any], str, str, str]] = []
    for index, security in enumerate(securities, start=1):
        if index <= resume_after:
            continue
        symbol = str(security["symbol"])
        latest = latest_by_symbol.get(symbol)
        initial_start = str(security.get("listed_date") or "1990-01-01")
        if minimum_start_date:
            initial_start = max(initial_start, minimum_start_date)
        start = (date.fromisoformat(latest) + timedelta(days=1)).isoformat() if latest else initial_start
        delisted_date = str(security.get("delisted_date") or "")
        symbol_end = min(end_date, delisted_date) if delisted_date else end_date
        work.append((index, security, symbol, start, symbol_end))
    _ensure_work_items(run_id, spec.key, [(symbol, index) for index, _, symbol, _, _ in work])
    # A process-level batch failure may reset the item-level checkpoint while
    # already committed work rows remain durable. Treat those rows as the
    # source of truth so a resume never downloads the market from symbol one.
    work_statuses = _work_status(run_id, spec.key)
    committed_units = sum(status == "committed" for status in work_statuses.values())
    if committed_units:
        processed = max(processed, committed_units)
        session_processed_base = processed
        work = [
            item
            for item in work
            if work_statuses.get(item[2]) != "committed"
        ]

    def fetch(item: tuple[int, dict[str, Any], str, str, str]) -> list[dict[str, Any]]:
        _, _, symbol, start, symbol_end = item
        if start > symbol_end:
            return []
        try:
            return _call_with_retry(
                lambda: adapter.daily_rows(
                    symbol, start, symbol_end, adjust="raw", include_limits=False,
                    include_adjustments=False, include_index_fallback=False,
                    max_window_days=8000,
                )
            )
        except TypeError:
            return _call_with_retry(lambda: adapter.daily_rows(symbol, start, symbol_end, adjust="raw"))

    buffered: list[dict[str, Any]] = []
    buffered_rows = 0
    last_checkpoint = {
        "symbol": checkpoint.get("symbol"),
        "index": max(resume_after, processed),
        "total": len(securities),
    }
    last_activity_published = 0.0

    def publish_activity(phase: str, queue_depth: int, *, force: bool = False) -> None:
        """Publish download activity before a large write batch is committed."""
        nonlocal last_activity_published
        now = time.monotonic()
        if not force and now - last_activity_published < 1.0:
            return
        last_activity_published = now
        _item(
            run_id,
            "daily",
            processed=processed,
            inserted=inserted,
            updated=updated,
            failed=failed,
            checkpoint=last_checkpoint,
            metrics=_throughput_metrics(
                started,
                phase=phase,
                api_calls=api_calls,
                downloaded=downloaded,
                committed=committed,
                queue_depth=queue_depth,
                processed_units=processed,
                fetched_units=fetched_units,
                total_units=len(securities),
                empty_units=empty_units,
                validated=validated,
                endpoint_calls=endpoint_calls,
                timings=timings,
                rate_units=processed - session_processed_base,
                # The first activity event must reach the UI immediately;
                # measuring a large MySQL data directory can be deferred until
                # actual rows have started moving.
                include_storage=downloaded > 0 or committed > 0,
            ),
        )

    def publish(last_entry: dict[str, Any], queue_depth: int) -> None:
        nonlocal last_checkpoint
        last_checkpoint = {
            "symbol": last_entry["symbol"],
            "index": last_entry["index"],
            "total": len(securities),
        }
        publish_activity("load", queue_depth, force=True)

    def flush(queue_depth: int) -> None:
        nonlocal buffered, buffered_rows, processed, inserted, updated, committed, empty_units
        if not buffered:
            return
        publish_activity("load", queue_depth, force=True)
        all_audit_rows = [row for entry in buffered for row in entry["raw_rows"]]
        import_entries = [
            {
                "symbol": entry["symbol"], "rows": entry["rows"],
                "listed_date": entry["security"].get("listed_date"),
                "delisted_date": entry["security"].get("delisted_date"),
                "snapshot_start": entry["start"],
                "snapshot_end": entry["end"],
            }
            for entry in buffered if entry["rows"] or reconcile_snapshot
        ]
        stage_started = time.perf_counter()
        if all_audit_rows:
            _archive_raw_batch(spec, all_audit_rows, batch_id)
        timings["rawArchive"] += (time.perf_counter() - stage_started) * 1000
        stage_started = time.perf_counter()
        result = import_ashare_research_batch(
            import_entries,
            sync_run_id=run_id,
            reconcile_full_snapshot=reconcile_snapshot,
        )
        timings["canonicalCompareWrite"] += (time.perf_counter() - stage_started) * 1000
        metadata_entries = [
            {
                "work_key": entry["symbol"], "scope_key": entry["symbol"],
                "request": {"symbol": entry["symbol"], "startDate": entry["start"], "endDate": entry["end"]},
                "raw_rows": entry["raw_rows"], "validation": entry["validation"],
                "coverage_start": entry["start"], "coverage_end": entry["end"],
                "write_watermark": entry["start"] <= entry["end"],
            }
            for entry in buffered
        ]
        row_counts = {entry["symbol"]: len(entry["rows"]) for entry in buffered}
        stage_started = time.perf_counter()
        _persist_instrument_batch_metadata(
            run_id=run_id, spec=spec, entries=metadata_entries,
            endpoint_counts=endpoint_calls, row_counts=row_counts,
            batch_id=str(result.get("batch_id") or batch_id),
        )
        timings["metadata"] += (time.perf_counter() - stage_started) * 1000
        batch_rows = sum(row_counts.values())
        inserted += batch_rows
        updated += int(result.get("updatedRows") or 0)
        committed += batch_rows
        empty_units += sum(1 for entry in buffered if not entry["rows"])
        processed += len(buffered)
        last_entry = buffered[-1]
        buffered = []
        buffered_rows = 0
        publish(last_entry, queue_depth)

    publish_activity("fetch", len(work), force=True)
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="tushare-daily") as executor:
        pending: dict[int, Any] = {}
        submit_cursor = 0
        # Futures retain completed response rows while the writer is busy.
        # Bound read-ahead by the same unit limit as the in-memory write batch.
        while submit_cursor < min(len(work), concurrency):
            item = work[submit_cursor]
            pending[item[0]] = executor.submit(fetch, item)
            submit_cursor += 1
        for index, security, symbol, start, symbol_end in work:
            if _cancelled(run_id, task_id):
                flush(len(pending))
                for future in pending.values():
                    future.cancel()
                break
            future = pending.pop(index)
            try:
                stage_started = time.perf_counter()
                rows = future.result()
                timings["fetchWait"] += (time.perf_counter() - stage_started) * 1000
                endpoint_calls = _api_delta(api_before, _api_snapshot(adapter))
                api_calls = sum(endpoint_calls.values())
                downloaded += len(rows)
                fetched_units += 1
                stage_started = time.perf_counter()
                audit_rows = [_raw_row_for_symbol(spec, row, symbol) for row in rows]
                validation = _validate_dataset_rows(spec, audit_rows)
                validated += len(rows)
                timings["validate"] += (time.perf_counter() - stage_started) * 1000
                buffered.append(
                    {"index": index, "security": security, "symbol": symbol, "start": start,
                     "end": symbol_end, "rows": rows, "raw_rows": audit_rows, "validation": validation}
                )
                buffered_rows += len(rows)
                publish_activity("fetch", len(pending))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                processed += 1
                _record_sync_failure(spec, symbol, start, symbol_end, exc)
                _mark_work_items(run_id, spec.key, [symbol], status="failed", error=str(exc))
                publish({"symbol": symbol, "index": index}, len(pending))
            else:
                # Keep write/metadata/reconciliation exceptions out of the
                # per-symbol retry path. They invalidate the whole buffered
                # transaction and must not cause repeated writes of that same
                # buffer under subsequent symbols.
                if buffered_rows >= chunk_rows or len(buffered) >= batch_units:
                    flush(len(pending))
            if submit_cursor < len(work):
                next_item = work[submit_cursor]
                pending[next_item[0]] = executor.submit(fetch, next_item)
                submit_cursor += 1
            if not _current_task(run_id, task_id):
                break
        flush(len(pending))
    if reconcile_snapshot and failed == 0 and not _cancelled(run_id, task_id):
        _reconcile_daily_manifest_scope(run_id)
    return processed, inserted, updated, failed


def _reconcile_daily_trade_date_batch(
    start_date: str,
    end_date: str,
    rows: list[dict[str, Any]],
    *,
    run_id: str | None = None,
    heartbeat_interval_seconds: float = 10.0,
) -> int:
    """Reconcile an authoritative full-rebuild date slice after it is loaded."""
    keys = sorted(
        {
            (str(row.get("symbol") or ""), str(row.get("date") or row.get("trade_date") or ""))
            for row in rows
            if row.get("symbol") and (row.get("date") or row.get("trade_date"))
        }
    )
    deleted = 0
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None

    def heartbeat() -> None:
        interval = max(0.1, float(heartbeat_interval_seconds))
        while not heartbeat_stop.wait(interval):
            try:
                with db() as connection:
                    connection.execute(
                        """
                        update data_sync_runs set heartbeat_at=?
                        where id=? and status in ('queued','running','cancelling')
                        """,
                        (utc_now(), run_id),
                    )
            except Exception:  # noqa: BLE001 - progress reporting must not abort canonical writes.
                logger.warning("Daily reconciliation heartbeat failed for run %s", run_id, exc_info=True)

    if run_id:
        heartbeat_thread = threading.Thread(
            target=heartbeat,
            name=f"daily-reconcile-heartbeat-{run_id[:8]}",
            daemon=True,
        )
        heartbeat_thread.start()

    try:
        with bulk_db() as connection:
            connection.execute(
                """
                create temporary table if not exists tmp_daily_date_keys (
                    symbol varchar(32) not null,
                    trade_date varchar(10) not null,
                    primary key(symbol,trade_date)
                )
                """
            )
            connection.execute("delete from tmp_daily_date_keys")
            if keys:
                connection.executemany(
                    "insert into tmp_daily_date_keys(symbol,trade_date) values (?,?)",
                    keys,
                )
            for table, source in (
                ("market_trade_status", "tushare:ohlcv_inferred"),
                ("market_daily_bars", "tushare"),
            ):
                cursor = connection.execute(
                    f"""
                    delete from {table}
                    where source=? and trade_date>=? and trade_date<=?
                      and not exists (
                          select 1 from tmp_daily_date_keys k
                          where k.symbol={table}.symbol and k.trade_date={table}.trade_date
                      )
                    """,
                    (source, start_date, end_date),
                )
                deleted += max(0, int(cursor.rowcount or 0))
    finally:
        heartbeat_stop.set()
        if heartbeat_thread:
            heartbeat_thread.join(timeout=1.0)
    return deleted


def _reconcile_daily_manifest_scope(run_id: str) -> int:
    """Remove TuShare daily symbols outside the completed full-run scope."""
    deleted = 0
    with bulk_db() as connection:
        manifest_predicate = """
            not exists (
                select 1 from provider_ingestion_manifests p
                where p.run_id=? and p.provider='tushare' and p.dataset_key='daily'
                  and p.status='success' and p.scope_key={table}.symbol
            )
        """
        for table, source in (
            ("market_trade_status", "tushare:ohlcv_inferred"),
            ("market_daily_bars", "tushare"),
        ):
            cursor = connection.execute(
                f"delete from {table} where source=? and " + manifest_predicate.format(table=table),
                (source, run_id),
            )
            deleted += max(0, int(cursor.rowcount or 0))
    return deleted


def _generic_params(
    spec: DatasetSpec,
    start_date: str,
    end_date: str,
    symbol: str | None = None,
) -> dict[str, Any]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    params = dict(spec.probe)
    for key in list(params):
        if key == "start_date":
            params[key] = _compact(start)
        elif key in {"end_date", "trade_date", "ann_date", "nav_date"}:
            params[key] = _compact(end)
    if symbol and spec.instrument_field:
        suffix = ".SH" if symbol.startswith(("5", "6", "9")) else ".BJ" if symbol.startswith(("4", "8")) else ".SZ"
        params[spec.instrument_field] = f"{symbol}{suffix}"
    return params


def _normalized_rows(adapter: TushareAdapter, spec: DatasetSpec, symbol: str, start: str, end: str) -> list[dict[str, Any]] | None:
    if spec.normalizer == "namechange":
        return adapter.namechange_rows(symbol)
    if spec.normalizer == "adj_factor":
        return [
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "adj_factor": factor,
                "source": "tushare",
            }
            for trade_date, factor in sorted(adapter.adjustment_factors(symbol, start, end).items())
        ]
    if spec.normalizer == "daily_basic":
        return adapter.daily_basic_rows(symbol, start, end)
    if spec.normalizer == "suspend_d":
        return adapter.suspend_rows(symbol, start, end)
    if spec.normalizer == "stk_limit":
        return [
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "limit_up": prices.get("limitUp"),
                "limit_down": prices.get("limitDown"),
                "source": "tushare:stk_limit",
            }
            for trade_date, prices in sorted(adapter.limit_prices(symbol, start, end, strict=True).items())
        ]
    if spec.normalizer == "dividend":
        return adapter.dividend_rows(symbol, start, end)
    if spec.normalizer == "financial":
        return getattr(adapter, f"{spec.api_name}_rows")(symbol, start, end)
    return None


def _normalize_optional(
    spec: DatasetSpec,
    rows: list[dict[str, Any]],
    batch_id: str,
    *,
    bulk: bool = False,
) -> None:
    if not rows:
        return
    if spec.normalizer == "adj_factor":
        upsert_adjustment_factors(rows, source="tushare", batch_id=batch_id)
    elif spec.normalizer == "namechange":
        now = utc_now()
        parameters = []
        for row in rows:
            payload = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
            parameters.append(
                (
                    str(uuid.uuid5(uuid.NAMESPACE_URL, f"name:{row['symbol']}:{row['start_date']}:{row['name']}")),
                    row["symbol"],
                    row["name"],
                    row["start_date"],
                    row.get("end_date"),
                    int(bool(row.get("is_st"))),
                    row.get("source") or "tushare:namechange",
                    hashlib.sha256(payload.encode("utf-8")).hexdigest(),
                    now,
                )
            )
        connection_factory = bulk_db if bulk else db
        with connection_factory() as connection:
            connection.executemany(
                """
                insert into security_name_history
                    (id,symbol,name,start_date,end_date,is_st,source,payload_hash,created_at)
                values (?,?,?,?,?,?,?,?,?)
                on conflict(symbol,start_date,name) do update set
                    end_date=excluded.end_date,is_st=excluded.is_st,
                    source=excluded.source,payload_hash=excluded.payload_hash
                """,
                parameters,
            )
    elif spec.normalizer == "index_daily":
        # Keep the canonical security type as index.  LEAN's generated cache
        # remains equity-shaped because strategy templates subscribe through
        # AddEquity, but storage and source lineage must not disguise an index
        # as a listed company with the same numeric code.
        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            symbol = str(row.get("symbol") or row.get("ts_code") or "").split(".", 1)[0].upper()
            close = _finite_number(row.get("close"))
            trade_date = row.get("trade_date") or row.get("date")
            if not symbol or not trade_date or close is None:
                continue
            normalized_rows.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    # TuShare's pre-launch CSI history can contain close-only
                    # rows.  A flat OHLC bar preserves that published close
                    # without inventing an intraday range.
                    "open": _finite_number(row.get("open")) or close,
                    "high": _finite_number(row.get("high")) or close,
                    "low": _finite_number(row.get("low")) or close,
                    "close": close,
                    "prev_close": _first_finite_number(row.get("pre_close"), row.get("prev_close")),
                    "pct_change": _first_finite_number(row.get("pct_chg"), row.get("pct_change")),
                    "volume": (_first_finite_number(row.get("vol"), row.get("volume")) or 0) * (100 if "vol" in row else 1),
                    "amount": (_finite_number(row.get("amount")) or 0) * 1000,
                    "adj_factor": 1.0,
                }
            )
        # One lookup and SQL pipeline covers every benchmark symbol. The former
        # per-index loop opened a transaction for each individual symbol.
        upsert_market_daily_bars_batch(
            normalized_rows,
            asset_class="index",
            market="china",
            venue="china",
            source="tushare",
            batch_id=batch_id,
            resolution="daily",
            data_type="trade",
            adjust="raw",
            bulk=bulk,
        )
    elif spec.normalizer == "daily_basic":
        upsert_daily_basic_factor_values(
            rows,
            source="tushare:daily_basic",
            batch_id=batch_id,
            bulk=bulk,
        )
    elif spec.normalizer == "dividend":
        upsert_corporate_actions(rows, source="tushare:dividend", batch_id=batch_id, bulk=bulk)
    elif spec.normalizer == "financial":
        import_financial_statements(rows, source=f"tushare:{spec.api_name}", bulk=bulk)
    elif spec.normalizer == "index_weight":
        upsert_index_weights(rows, source="tushare:index_weight", batch_id=batch_id, bulk=bulk)
    elif spec.normalizer == "suspend_d":
        statuses = [
            {
                "symbol": row["symbol"],
                "trade_date": row["suspend_date"],
                "is_suspended": True,
                "can_buy": False,
                "can_sell": False,
            }
            for row in rows
            if row.get("suspend_date") and row.get("is_full_day", True)
        ]
        if statuses:
            upsert_trade_status(statuses, source="tushare:suspend_d", batch_id=batch_id, bulk=bulk)
    elif spec.normalizer == "stk_limit":
        statuses = [
            {
                "symbol": row["symbol"],
                "trade_date": row["trade_date"],
                "limit_up": row.get("limit_up"),
                "limit_down": row.get("limit_down"),
                "can_buy": True,
                "can_sell": True,
            }
            for row in rows
            if row.get("trade_date")
        ]
        if statuses:
            upsert_trade_status(statuses, source="tushare:stk_limit", batch_id=batch_id, bulk=bulk)


def _record_sync_failure(
    spec: DatasetSpec,
    symbol: str | None,
    start_date: str,
    end_date: str,
    exc: Exception,
) -> dict[str, Any]:
    """Persist a compact, de-duplicated failure that operators can act on."""
    error = str(exc).strip()[:2000] or exc.__class__.__name__
    details = {"error": error, "exceptionType": exc.__class__.__name__}
    now = utc_now()
    with db() as connection:
        existing = connection.execute(
            """
            select id from data_record_issues
            where dataset_key=? and coalesce(instrument_code, '')=coalesce(?, '')
              and source='tushare' and issue_code='sync_failed' and status='open'
            order by detected_at desc limit 1
            """,
            (spec.key, symbol),
        ).fetchone()
        if existing:
            connection.execute(
                """
                update data_record_issues
                set start_date=?, end_date=?, details_json=?, detected_at=?
                where id=?
                """,
                (start_date, end_date, json_dump(details), now, existing["id"]),
            )
        else:
            connection.execute(
                """
                insert into data_record_issues
                    (id,dataset_key,source,instrument_code,start_date,end_date,issue_code,
                     severity,status,details_json,detected_at)
                values (?,?,?,?,?,?,'sync_failed','error','open',?,?)
                """,
                (str(uuid.uuid4()), spec.key, "tushare", symbol, start_date, end_date, json_dump(details), now),
            )
    return {"symbol": symbol, **details}


def _resolve_sync_failure(spec: DatasetSpec, symbol: str | None, batch_id: str) -> None:
    with db() as connection:
        connection.execute(
            """
            update data_record_issues
            set status='resolved', resolved_at=?, resolution_batch_id=?
            where dataset_key=? and coalesce(instrument_code, '')=coalesce(?, '')
              and source='tushare' and issue_code='sync_failed' and status='open'
            """,
            (utc_now(), batch_id, spec.key, symbol),
        )


def _open_sync_failure_instruments(spec: DatasetSpec) -> set[str]:
    if spec.scope != "instrument":
        return set()
    with db() as connection:
        rows = connection.execute(
            """
            select distinct instrument_code from data_record_issues
            where dataset_key=? and source='tushare' and issue_code='sync_failed'
              and status='open' and instrument_code is not null
            """,
            (spec.key,),
        ).fetchall()
    return {str(row["instrument_code"]) for row in rows if row["instrument_code"]}


def _changed_adjustment_factor_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only missing/provider-corrected factors for an idempotent rebuild."""
    if not rows:
        return []
    symbols = sorted({str(row["symbol"]) for row in rows})
    placeholders = ",".join("?" for _ in symbols)
    first_date = min(str(row["trade_date"]) for row in rows)
    last_date = max(str(row["trade_date"]) for row in rows)
    with db() as connection:
        existing_rows = connection.execute(
            f"""
            select symbol,trade_date,adj_factor from adjustment_factors
            where source='tushare' and symbol in ({placeholders})
              and trade_date>=? and trade_date<=?
            """,
            [*symbols, first_date, last_date],
        ).fetchall()
    existing = {
        (str(row["symbol"]), str(row["trade_date"])): float(row["adj_factor"])
        for row in existing_rows
    }
    changed: list[dict[str, Any]] = []
    for row in rows:
        key = (str(row["symbol"]), str(row["trade_date"]))
        previous = existing.get(key)
        value = float(row["adj_factor"])
        if previous is None or abs(previous - value) > max(1e-10, abs(value) * 1e-12):
            changed.append(row)
    return changed


def _flush_adj_factor_batch(
    spec: DatasetSpec,
    batch_id: str,
    entries: list[tuple[str, list[dict[str, Any]]]],
) -> tuple[int, int, int, dict[str, int]]:
    rows = [row for _, values in entries for row in values]
    if spec.retain_raw:
        raw_rows = [
            _raw_row_for_symbol(spec, row, str(row.get("symbol") or work_key))
            for work_key, values in entries
            for row in values
        ]
        inserted, updated = _save_raw(spec, raw_rows, batch_id)
    else:
        # Normalized factors are the canonical cache. Keeping an additional
        # JSON copy more than doubles space and write amplification.
        inserted, updated = len(rows), 0
    changed_rows = _changed_adjustment_factor_rows(rows)
    if changed_rows:
        upsert_adjustment_factors(changed_rows, source="tushare", batch_id=batch_id, bulk=True)
    counts = {work_key: len(values) for work_key, values in entries}
    return inserted, updated, len(rows), counts


def _sync_adj_factor_fast(
    adapter: TushareAdapter,
    spec: DatasetSpec,
    run_id: str,
    batch_id: str,
    end_date: str,
    task_id: str | None,
    *,
    full_refresh: bool,
    minimum_start_date: str | None = None,
) -> tuple[int, int, int, int]:
    """Concurrent provider reads with one sequential, chunked database writer."""
    state = _item_state(run_id, spec.key)
    checkpoint = state.get("checkpoint") or {}
    legacy_resume = max(0, int(checkpoint.get("index") or 0))
    processed = int(state.get("processed") or 0)
    inserted = int(state.get("inserted") or 0)
    updated = int(state.get("updated") or 0)
    failed = int(state.get("failed") or 0)
    started = time.monotonic()
    api_before = _api_snapshot(adapter)
    endpoint_calls: dict[str, int] = {}
    api_calls = 0
    downloaded = 0
    committed = 0
    fetched_units = processed
    chunk_rows = _sync_batch_rows("LEAN_DATA_SYNC_CHUNK_ROWS")
    concurrency = max(1, min(32, int(os.environ.get("LEAN_TUSHARE_FETCH_CONCURRENCY", "16"))))

    existing_statuses = _work_status(run_id, spec.key)
    resumed_symbol_work = any(
        len(key) != 10 or key[4:5] != "-" or key[7:8] != "-"
        for key in existing_statuses
    )
    date_mode = hasattr(adapter, "adjustment_factors_for_date") and not resumed_symbol_work
    if date_mode:
        if full_refresh or _latest_raw_date(spec) is None:
            securities = _listed_securities()
            first_date = min(
                max(str(item.get("listed_date") or "1990-12-19"), minimum_start_date or "1990-12-19")
                for item in securities
            )
            start_after = (date.fromisoformat(first_date) - timedelta(days=1)).isoformat()
        else:
            start_after = _latest_raw_date(spec) or "1990-12-18"
        with db() as connection:
            dates = connection.execute(
                """
                select trade_date from trade_calendar
                where market='china' and is_open=1 and trade_date>? and trade_date<=?
                order by trade_date
                """,
                (start_after, end_date),
            ).fetchall()
        work = [(str(row["trade_date"]), index) for index, row in enumerate(dates, start=1)]
        _ensure_work_items(run_id, spec.key, work)
        statuses = _work_status(run_id, spec.key)
        pending = [(key, sequence) for key, sequence in work if statuses.get(key) != "committed"]
        processed = sum(1 for key, _ in work if statuses.get(key) == "committed")

        def fetch_date(work_key: str) -> list[dict[str, Any]]:
            if hasattr(adapter, "adjustment_factors_for_date"):
                return _call_with_retry(lambda: adapter.adjustment_factors_for_date(work_key))
            return []

        total = max(processed + len(pending), len(work))
        fetcher: Callable[[str], list[dict[str, Any]]] = fetch_date
    else:
        securities = _listed_securities()
        work = [
            (str(item["symbol"]), index)
            for index, item in enumerate(securities, start=1)
            if existing_statuses or index > legacy_resume
        ]
        listed_dates = {
            str(item["symbol"]): max(
                str(item.get("listed_date") or "1990-01-01"),
                minimum_start_date or "1990-01-01",
            )
            for item in securities
        }
        _ensure_work_items(run_id, spec.key, work)
        statuses = _work_status(run_id, spec.key)
        pending = [(key, sequence) for key, sequence in work if statuses.get(key) != "committed"]
        if existing_statuses:
            processed = sum(1 for key, _ in work if statuses.get(key) == "committed")

        def fetch_symbol(work_key: str) -> list[dict[str, Any]]:
            method = getattr(adapter, "adjustment_factors_full", None) or adapter.adjustment_factors
            factors = _call_with_retry(lambda: method(work_key, listed_dates[work_key], end_date))
            return [
                {
                    "symbol": work_key,
                    "trade_date": trade_date,
                    "adj_factor": factor,
                    "source": "tushare",
                }
                for trade_date, factor in sorted(factors.items())
            ]

        total = len(securities)
        fetcher = fetch_symbol

    session_processed_base = processed
    if not pending:
        return processed, inserted, updated, failed

    entries: list[tuple[str, list[dict[str, Any]]]] = []
    buffered_rows = 0
    batch_units = _sync_batch_units("LEAN_DATA_SYNC_BATCH_UNITS", 16)
    failure_samples: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal entries, buffered_rows, inserted, updated, processed, committed
        if not entries:
            return
        _item(
            run_id,
            spec.key,
            metrics=_throughput_metrics(
                started,
                phase="load",
                api_calls=api_calls,
                downloaded=downloaded,
                committed=committed,
                processed_units=processed,
                fetched_units=fetched_units,
                total_units=total,
                validated=downloaded,
                endpoint_calls=endpoint_calls,
                rate_units=processed - session_processed_base,
            ),
        )
        metadata_entries: list[dict[str, Any]] = []
        for work_key, values in entries:
            audit_rows = [_raw_row_for_symbol(spec, row, str(row.get("symbol") or work_key)) for row in values]
            validation = _validate_dataset_rows(spec, audit_rows)
            request_start = listed_dates[work_key] if not date_mode else work_key
            metadata_entries.append(
                {
                    "work_key": work_key,
                    "scope_key": work_key,
                    "start": request_start,
                    "end": end_date if not date_mode else work_key,
                    "coverage_start": request_start,
                    "coverage_end": end_date if not date_mode else work_key,
                    "request": {
                        "workKey": work_key,
                        "startDate": request_start,
                        "endDate": end_date if not date_mode else work_key,
                    },
                    "rows": values,
                    "raw_rows": audit_rows,
                    "validation": validation,
                    "write_watermark": not date_mode,
                }
            )
        estimated_bytes = sum(
            len(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
            for _, values in entries
            for row in values
        ) * 3
        _assert_disk_capacity(estimated_bytes)
        add, change, written, counts = _flush_adj_factor_batch(spec, batch_id, entries)
        if not date_mode:
            _persist_instrument_batch_metadata(
                run_id=run_id,
                spec=spec,
                entries=metadata_entries,
                endpoint_counts=endpoint_calls,
                row_counts=counts,
                batch_id=batch_id,
            )
        else:
            _persist_trade_date_batch_metadata(
                run_id=run_id,
                spec=spec,
                entries=metadata_entries,
                endpoint_counts=endpoint_calls,
                row_counts=counts,
                batch_id=batch_id,
            )
        keys = [key for key, _ in entries]
        inserted += add
        updated += change
        processed += len(keys)
        committed += written
        last_key = keys[-1]
        item_error = json_dump({"failed": failed, "samples": failure_samples}) if failed else ""
        _item(
            run_id,
            spec.key,
            processed=processed,
            inserted=inserted,
            updated=updated,
            failed=failed,
            error=item_error,
            checkpoint={"index": processed, "total": total, "symbol": last_key},
            metrics=_throughput_metrics(
                started,
                phase="load",
                api_calls=api_calls,
                downloaded=downloaded,
                committed=committed,
                queue_depth=0,
                processed_units=processed,
                total_units=total,
                validated=downloaded,
                endpoint_calls=endpoint_calls,
                rate_units=processed - session_processed_base,
            ),
        )
        entries = []
        buffered_rows = 0

    _item(
        run_id,
        spec.key,
        metrics=_throughput_metrics(
            started,
            phase="fetch",
            api_calls=api_calls,
            downloaded=downloaded,
            committed=committed,
            processed_units=processed,
            fetched_units=fetched_units,
            total_units=total,
            endpoint_calls=endpoint_calls,
            rate_units=processed - session_processed_base,
        ),
    )
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="tushare-adj") as executor:
        # Do not submit the whole market at once. Completed futures keep their
        # response lists alive while a database flush is running and used to
        # accumulate an entire dataset in RAM.
        futures: dict[int, Any] = {}
        submit_cursor = 0
        read_ahead = min(concurrency, 16)
        while submit_cursor < min(len(pending), read_ahead):
            key, sequence = pending[submit_cursor]
            futures[sequence] = executor.submit(fetcher, key)
            submit_cursor += 1
        for key, sequence in pending:
            if _cancelled(run_id, task_id):
                for pending_future in futures.values():
                    pending_future.cancel()
                break
            future = futures.pop(sequence)
            try:
                rows = future.result()
                endpoint_calls = _api_delta(api_before, _api_snapshot(adapter))
                api_calls = sum(endpoint_calls.values())
                downloaded += len(rows)
                fetched_units += 1
                entries.append((key, rows))
                buffered_rows += len(rows)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                sample = _record_sync_failure(spec, None if date_mode else key, key, end_date, exc)
                if len(failure_samples) < 10:
                    failure_samples.append(sample)
                _mark_work_items(run_id, spec.key, [key], status="failed", error=str(exc))
                processed += 1
                _item(
                    run_id,
                    spec.key,
                    processed=processed,
                    inserted=inserted,
                    updated=updated,
                    failed=failed,
                    error=json_dump({"failed": failed, "samples": failure_samples}),
                    checkpoint={"index": processed, "total": total, "symbol": key},
                    metrics=_throughput_metrics(
                        started,
                        phase="fetch",
                        api_calls=api_calls,
                        downloaded=downloaded,
                        committed=committed,
                        processed_units=processed,
                        total_units=total,
                        endpoint_calls=endpoint_calls,
                        rate_units=processed - session_processed_base,
                    ),
                )
            else:
                if buffered_rows >= chunk_rows or len(entries) >= batch_units:
                    flush()
            finally:
                if submit_cursor < len(pending):
                    next_key, next_sequence = pending[submit_cursor]
                    futures[next_sequence] = executor.submit(fetcher, next_key)
                    submit_cursor += 1
        flush()

    _item(
        run_id,
        spec.key,
        metrics=_throughput_metrics(
            started,
            phase="validate",
            api_calls=api_calls,
            downloaded=downloaded,
            committed=committed,
            processed_units=processed,
            fetched_units=fetched_units,
            total_units=total,
            validated=downloaded,
            endpoint_calls=endpoint_calls,
            rate_units=processed - session_processed_base,
        ),
    )
    return processed, inserted, updated, failed


def _advance_sparse_market_watermarks(
    spec: DatasetSpec,
    securities: list[dict[str, Any]],
    *,
    coverage_end: str,
    run_id: str,
) -> None:
    """Record market-wide sparse endpoint coverage for every active security."""
    now = utc_now()
    parameters = []
    for item in securities:
        if str(item.get("status") or "listed") != "listed":
            continue
        listed_date = str(item.get("listed_date") or "1990-01-01")
        if listed_date > coverage_end:
            continue
        parameters.append(
            (
                spec.key,
                str(item["symbol"]),
                listed_date,
                coverage_end,
                None,
                run_id,
                1 if spec.normalizer == "suspend_d" else 0,
                "passed",
                now,
            )
        )
    if not parameters:
        return
    with bulk_db() as connection:
        connection.executemany(
            """
            insert into provider_dataset_watermarks
                (provider,dataset_key,scope_key,coverage_start,coverage_end,last_data_date,
                 last_run_id,empty_result,validation_status,updated_at)
            values ('tushare',?,?,?,?,?,?,?,?,?)
            on conflict(provider,dataset_key,scope_key) do update set
                coverage_start=case
                    when provider_dataset_watermarks.coverage_start is null then excluded.coverage_start
                    when excluded.coverage_start<provider_dataset_watermarks.coverage_start
                        then excluded.coverage_start
                    else provider_dataset_watermarks.coverage_start end,
                coverage_end=case
                    when excluded.coverage_end>provider_dataset_watermarks.coverage_end
                        then excluded.coverage_end
                    else provider_dataset_watermarks.coverage_end end,
                last_run_id=excluded.last_run_id,
                validation_status=excluded.validation_status,
                updated_at=excluded.updated_at
            """,
            parameters,
        )


def _sync_instrument_dataset_fast(
    adapter: TushareAdapter,
    spec: DatasetSpec,
    run_id: str,
    batch_id: str,
    end_date: str,
    task_id: str | None,
    *,
    full_refresh: bool,
    minimum_start_date: str | None = None,
) -> tuple[int, int, int, int]:
    """Batch instrument history and use market-wide daily increments when supported."""
    state = _item_state(run_id, spec.key)
    checkpoint = state.get("checkpoint") or {}
    legacy_resume = max(0, int(checkpoint.get("index") or 0))
    processed = int(state.get("processed") or 0)
    inserted = int(state.get("inserted") or 0)
    updated = int(state.get("updated") or 0)
    failed = int(state.get("failed") or 0)
    session_processed_base = processed
    started = time.monotonic()
    api_before = _api_snapshot(adapter)
    endpoint_calls: dict[str, int] = {}
    api_calls = 0
    downloaded = 0
    committed = 0
    fetched_units = processed
    validated = 0
    empty_units = 0
    timings = {"fetchWait": 0.0, "validate": 0.0, "mysqlWrite": 0.0, "metadata": 0.0}
    chunk_rows = _sync_batch_rows("LEAN_DATA_SYNC_CHUNK_ROWS")
    batch_units = _sync_batch_units("LEAN_DATA_SYNC_BATCH_UNITS", 16)
    general_concurrency = int(os.environ.get("LEAN_TUSHARE_FETCH_CONCURRENCY", "16"))
    concurrency_key = {
        "suspend_d": "LEAN_SUSPEND_FETCH_CONCURRENCY",
        "daily_basic": "LEAN_DAILY_BASIC_FETCH_CONCURRENCY",
        "dividend": "LEAN_DIVIDEND_FETCH_CONCURRENCY",
    }.get(spec.normalizer, "LEAN_STK_LIMIT_FETCH_CONCURRENCY")
    high_latency_dataset = spec.normalizer in {"daily_basic", "dividend"}
    default_concurrency = 32 if high_latency_dataset else min(16, general_concurrency)
    max_concurrency = 32 if high_latency_dataset else 16
    concurrency = max(
        1,
        min(max_concurrency, int(os.environ.get(concurrency_key, str(default_concurrency)))),
    )

    securities = _listed_securities()
    coverage_by_scope = {} if full_refresh else _coverage_watermarks(spec)
    active_securities = [
        item for item in securities
        if str(item.get("status") or "listed") == "listed"
    ]
    active_scope_keys = {str(item["symbol"]) for item in active_securities}
    active_coverage = {
        symbol: coverage_by_scope[symbol]
        for symbol in active_scope_keys
        if symbol in coverage_by_scope
    }
    market_start_after = min(active_coverage.values()) if active_coverage else None
    uncovered_active = [
        item
        for item in active_securities
        if str(item["symbol"]) not in active_coverage
    ]
    uncovered_started_after_frontier = bool(
        market_start_after
        and all(str(item.get("listed_date") or "") > market_start_after for item in uncovered_active)
    )
    retry_failed_only = bool(checkpoint.get("retryFailedOnly"))
    date_fetch_name = {
        "suspend_d": "suspend_rows_for_date",
        "daily_basic": "daily_basic_rows_for_date",
        "stk_limit": "limit_prices_for_date",
        "dividend": "dividend_rows_for_date",
    }.get(spec.normalizer)
    existing_statuses = _work_status(run_id, spec.key)
    resumed_symbol_work = any(
        len(key) != 10 or key[4:5] != "-" or key[7:8] != "-"
        for key in existing_statuses
    )
    date_mode_start_after: str | None = None
    if (
        date_fetch_name
        and full_refresh
        and not retry_failed_only
        and not resumed_symbol_work
        and active_scope_keys
        and hasattr(adapter, str(date_fetch_name))
    ):
        first_date = min(
            max(str(item.get("listed_date") or "1990-12-19"), minimum_start_date or "1990-12-19")
            for item in active_securities
        )
        date_mode_start_after = (date.fromisoformat(first_date) - timedelta(days=1)).isoformat()
    elif (
        date_fetch_name
        and not full_refresh
        and not retry_failed_only
        and not resumed_symbol_work
        and active_scope_keys
        and market_start_after
        and (not uncovered_active or uncovered_started_after_frontier)
        and hasattr(adapter, str(date_fetch_name))
    ):
        date_mode_start_after = market_start_after
    date_mode = bool(date_mode_start_after)
    work: list[dict[str, Any]] = []

    if date_mode:
        with db() as connection:
            dates = connection.execute(
                """
                select trade_date from trade_calendar
                where market='china' and is_open=1 and trade_date>? and trade_date<=?
                order by trade_date
                """,
                (date_mode_start_after, end_date),
            ).fetchall()
        for sequence, row in enumerate(dates, start=1):
            trade_date = str(row["trade_date"])
            work.append(
                {
                    "work_key": trade_date,
                    "sequence": sequence,
                    "scope_key": f"trade_date:{trade_date}",
                    "start": trade_date,
                    "end": trade_date,
                    "initial": True,
                }
            )
        total = len(work)

        def fetch(entry: dict[str, Any]) -> list[dict[str, Any]]:
            method = getattr(adapter, str(date_fetch_name))
            return _call_with_retry(lambda: method(str(entry["work_key"])))

    else:
        selected = securities
        if retry_failed_only:
            retry_symbols = _open_sync_failure_instruments(spec)
            selected = [item for item in securities if str(item["symbol"]) in retry_symbols]
            legacy_resume = 0
            processed = 0
            session_processed_base = 0
        latest_by_instrument = _latest_raw_dates_by_instrument(spec)
        for sequence, item in enumerate(selected, start=1):
            if not existing_statuses and sequence <= legacy_resume:
                continue
            symbol = str(item["symbol"])
            persisted_latest = coverage_by_scope.get(symbol) or latest_by_instrument.get(symbol)
            latest = None if full_refresh else persisted_latest
            start = (
                (date.fromisoformat(latest) + timedelta(days=1)).isoformat()
                if latest
                else str(item.get("listed_date") or "1990-01-01")
            )
            if minimum_start_date:
                start = max(start, minimum_start_date)
            delisted_date = str(item.get("delisted_date") or "")
            symbol_end = min(end_date, delisted_date) if delisted_date else end_date
            work.append(
                {
                    "work_key": symbol,
                    "sequence": sequence,
                    "scope_key": symbol,
                    "start": start,
                    "end": symbol_end,
                    "initial": persisted_latest is None and not full_refresh,
                }
            )
        total = len(selected)

        def fetch(entry: dict[str, Any]) -> list[dict[str, Any]]:
            if str(entry["start"]) > str(entry["end"]):
                return []
            symbol = str(entry["work_key"])
            rows = _normalized_rows(adapter, spec, symbol, str(entry["start"]), str(entry["end"]))
            return rows or []

    _ensure_work_items(
        run_id,
        spec.key,
        [(str(entry["work_key"]), int(entry["sequence"])) for entry in work],
    )
    statuses = _work_status(run_id, spec.key)
    pending_work = [entry for entry in work if statuses.get(str(entry["work_key"])) != "committed"]
    if existing_statuses:
        processed = sum(1 for entry in work if statuses.get(str(entry["work_key"])) == "committed")
        session_processed_base = processed
    if not pending_work:
        _item(
            run_id,
            spec.key,
            metrics=_throughput_metrics(
                started,
                phase="validate",
                api_calls=0,
                downloaded=0,
                committed=0,
                processed_units=processed,
                total_units=total,
                rate_units=0,
            ),
        )
        return processed, inserted, updated, failed

    buffered: list[dict[str, Any]] = []
    buffered_rows = 0
    failure_samples: list[dict[str, Any]] = []
    last_committed_date: str | None = None

    def changed_status_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if spec.normalizer != "stk_limit" or not rows:
            return rows
        symbols = sorted({str(row["symbol"]) for row in rows})
        placeholders = ",".join("?" for _ in symbols)
        first_date = min(str(row["trade_date"]) for row in rows)
        last_date = max(str(row["trade_date"]) for row in rows)
        parameters = [*symbols, first_date, last_date]
        with db() as connection:
            market_rows = connection.execute(
                f"""
                select symbol,trade_date,limit_up,limit_down from market_trade_status
                where source='tushare:stk_limit' and asset_class='equity'
                  and market='china' and venue='china' and symbol in ({placeholders})
                  and trade_date>=? and trade_date<=?
                """,
                parameters,
            ).fetchall()

        def values(items: list[Any]) -> dict[tuple[str, str], tuple[float | None, float | None]]:
            return {
                (str(item["symbol"]), str(item["trade_date"])): (
                    float(item["limit_up"]) if item["limit_up"] is not None else None,
                    float(item["limit_down"]) if item["limit_down"] is not None else None,
                )
                for item in items
            }

        market = values(market_rows)

        def same(left: tuple[float | None, float | None] | None, row: dict[str, Any]) -> bool:
            if left is None:
                return False
            right = (row.get("limit_up"), row.get("limit_down"))
            for previous, current in zip(left, right, strict=True):
                if previous is None or current is None:
                    if previous is not None or current is not None:
                        return False
                elif abs(previous - float(current)) > max(1e-8, abs(float(current)) * 1e-10):
                    return False
            return True

        return [
            row for row in rows
            if not same(market.get((str(row["symbol"]), str(row["trade_date"]))), row)
        ]

    def flush() -> None:
        nonlocal buffered, buffered_rows, inserted, updated, processed, committed, validated, empty_units
        nonlocal last_committed_date
        if not buffered:
            return
        _item(
            run_id,
            spec.key,
            metrics=_throughput_metrics(
                started,
                phase="load",
                api_calls=api_calls,
                downloaded=downloaded,
                committed=committed,
                processed_units=processed,
                fetched_units=fetched_units,
                total_units=total,
                empty_units=empty_units,
                validated=validated,
                endpoint_calls=endpoint_calls,
                timings=timings,
                rate_units=processed - session_processed_base,
            ),
        )
        stage_started = time.perf_counter()
        metadata_entries: list[dict[str, Any]] = []
        all_rows: list[dict[str, Any]] = []
        all_raw_rows: list[dict[str, Any]] = []
        row_counts: dict[str, int] = {}
        for entry in buffered:
            rows = list(entry["rows"])
            raw_rows = [
                _raw_row_for_symbol(spec, row, str(row.get("symbol") or entry["work_key"]))
                for row in rows
            ]
            validation = _validate_dataset_rows(spec, raw_rows)
            validated += len(raw_rows)
            empty_units += int(not rows)
            all_rows.extend(rows)
            all_raw_rows.extend(raw_rows)
            work_key = str(entry["work_key"])
            row_counts[work_key] = len(rows)
            metadata_entries.append(
                {
                    **entry,
                    "raw_rows": raw_rows,
                    "validation": validation,
                    "request": {
                        "workKey": work_key,
                        "startDate": entry["start"],
                        "endDate": entry["end"],
                    },
                    "coverage_start": entry["start"],
                    "coverage_end": entry["end"],
                    "write_watermark": str(entry["start"]) <= str(entry["end"]),
                }
            )
        timings["validate"] += (time.perf_counter() - stage_started) * 1000
        stage_started = time.perf_counter()
        assume_new = all(bool(entry.get("initial")) for entry in buffered)
        if spec.retain_raw:
            add, change = _save_raw(spec, all_raw_rows, batch_id, assume_new=assume_new)
        else:
            add, change = len(all_rows), 0
        _normalize_optional(spec, changed_status_rows(all_rows), batch_id, bulk=True)
        timings["mysqlWrite"] += (time.perf_counter() - stage_started) * 1000
        stage_started = time.perf_counter()
        if date_mode:
            _persist_trade_date_batch_metadata(
                run_id=run_id,
                spec=spec,
                entries=metadata_entries,
                endpoint_counts=endpoint_calls,
                row_counts=row_counts,
                batch_id=batch_id,
            )
            last_committed_date = str(metadata_entries[-1]["work_key"])
        else:
            _persist_instrument_batch_metadata(
                run_id=run_id,
                spec=spec,
                entries=metadata_entries,
                endpoint_counts=endpoint_calls,
                row_counts=row_counts,
                batch_id=batch_id,
            )
        timings["metadata"] += (time.perf_counter() - stage_started) * 1000
        inserted += add
        updated += change
        processed += len(buffered)
        committed += len(all_rows)
        last_key = str(buffered[-1]["work_key"])
        _item(
            run_id,
            spec.key,
            processed=processed,
            inserted=inserted,
            updated=updated,
            failed=failed,
            error=json_dump({"failed": failed, "samples": failure_samples}) if failed else "",
            checkpoint={"index": processed, "total": total, "symbol": last_key},
            metrics=_throughput_metrics(
                started,
                phase="load",
                api_calls=api_calls,
                downloaded=downloaded,
                committed=committed,
                processed_units=processed,
                total_units=total,
                empty_units=empty_units,
                validated=validated,
                endpoint_calls=endpoint_calls,
                timings=timings,
                rate_units=processed - session_processed_base,
            ),
        )
        buffered = []
        buffered_rows = 0

    _item(
        run_id,
        spec.key,
        metrics=_throughput_metrics(
            started,
            phase="fetch",
            api_calls=api_calls,
            downloaded=downloaded,
            committed=committed,
            processed_units=processed,
            fetched_units=fetched_units,
            total_units=total,
            endpoint_calls=endpoint_calls,
            rate_units=processed - session_processed_base,
        ),
    )
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix=f"tushare-{spec.key}") as executor:
        pending: dict[int, Any] = {}
        submit_cursor = 0
        stop_submission = False
        while submit_cursor < min(len(pending_work), concurrency, max(batch_units, 16)):
            entry = pending_work[submit_cursor]
            pending[int(entry["sequence"])] = executor.submit(fetch, entry)
            submit_cursor += 1

        for entry in pending_work:
            if not buffered and _cancelled(run_id, task_id):
                for future in pending.values():
                    future.cancel()
                break
            sequence = int(entry["sequence"])
            future = pending.pop(sequence)
            try:
                stage_started = time.perf_counter()
                rows = future.result()
                timings["fetchWait"] += (time.perf_counter() - stage_started) * 1000
            except Exception as exc:  # noqa: BLE001
                flush()
                failed += 1
                work_key = str(entry["work_key"])
                failure_symbol = None if date_mode else work_key
                sample = _record_sync_failure(
                    spec,
                    failure_symbol,
                    str(entry["start"]),
                    str(entry["end"]),
                    exc,
                )
                if len(failure_samples) < 10:
                    failure_samples.append(sample)
                _mark_work_items(run_id, spec.key, [work_key], status="failed", error=str(exc))
                processed += 1
                _item(
                    run_id,
                    spec.key,
                    processed=processed,
                    inserted=inserted,
                    updated=updated,
                    failed=failed,
                    error=json_dump({"failed": failed, "samples": failure_samples}),
                    checkpoint={"index": processed, "total": total, "symbol": work_key},
                    metrics=_throughput_metrics(
                        started,
                        phase="fetch",
                        api_calls=api_calls,
                        downloaded=downloaded,
                        committed=committed,
                        processed_units=processed,
                        total_units=total,
                        endpoint_calls=endpoint_calls,
                        timings=timings,
                        rate_units=processed - session_processed_base,
                    ),
                )
                if date_mode:
                    stop_submission = True
                    for pending_future in pending.values():
                        pending_future.cancel()
                    break
            else:
                endpoint_calls = _api_delta(api_before, _api_snapshot(adapter))
                api_calls = sum(endpoint_calls.values())
                downloaded += len(rows)
                fetched_units += 1
                buffered.append({**entry, "rows": rows})
                buffered_rows += len(rows)
                if len(buffered) >= batch_units or buffered_rows >= chunk_rows:
                    flush()
            finally:
                if not stop_submission and submit_cursor < len(pending_work):
                    next_entry = pending_work[submit_cursor]
                    pending[int(next_entry["sequence"])] = executor.submit(fetch, next_entry)
                    submit_cursor += 1
        flush()

    if date_mode and last_committed_date:
        _advance_sparse_market_watermarks(
            spec,
            securities,
            coverage_end=last_committed_date,
            run_id=run_id,
        )

    return processed, inserted, updated, failed


def _sync_suspend_by_trade_date(
    adapter: TushareAdapter,
    spec: DatasetSpec,
    run_id: str,
    batch_id: str,
    end_date: str,
    task_id: str | None,
    coverage_by_scope: dict[str, str],
) -> tuple[int, int, int, int]:
    """Increment suspend_d with one market-wide call per missing trade date."""
    start_after = min(coverage_by_scope.values())
    with db() as connection:
        dates = connection.execute(
            """
            select trade_date from trade_calendar
            where market='china' and is_open=1 and trade_date>? and trade_date<=?
            order by trade_date
            """,
            (start_after, end_date),
        ).fetchall()
    work_dates = [str(row["trade_date"]) for row in dates]
    state = _item_state(run_id, spec.key)
    processed = int(state.get("processed") or 0)
    session_processed_base = processed
    inserted = int(state.get("inserted") or 0)
    updated = int(state.get("updated") or 0)
    failed = int(state.get("failed") or 0)
    started = time.monotonic()
    api_before = _api_snapshot(adapter)
    endpoint_calls: dict[str, int] = {}
    downloaded = 0
    committed = 0
    empty_units = 0
    validated = 0
    if not work_dates:
        _item(
            run_id,
            spec.key,
            metrics=_throughput_metrics(
                started,
                phase="validate",
                api_calls=0,
                downloaded=0,
                committed=0,
                processed_units=processed,
                total_units=processed,
                endpoint_calls={},
                rate_units=0,
            ),
        )
        return processed, inserted, updated, failed

    for index, trade_date in enumerate(work_dates, start=1):
        if _cancelled(run_id, task_id):
            break
        try:
            rows = _call_with_retry(lambda: adapter.suspend_rows_for_date(trade_date))
            endpoint_calls = _api_delta(api_before, _api_snapshot(adapter))
            downloaded += len(rows)
            raw_rows = [
                _raw_row_for_symbol(spec, row, str(row.get("symbol") or ""))
                for row in rows
            ]
            validation = _validate_dataset_rows(spec, raw_rows)
            validated += len(raw_rows)
            add, change = _save_raw(spec, raw_rows, batch_id, assume_new=True)
            _normalize_optional(spec, rows, batch_id, bulk=True)
            inserted += add
            updated += change
            committed += len(rows)
            empty_units += int(not rows)
            _record_ingestion_manifest(
                run_id=run_id,
                spec=spec,
                scope_key=f"trade_date:{trade_date}",
                request={"tradeDate": trade_date},
                rows=raw_rows,
                validation=validation,
                endpoint_counts=endpoint_calls,
                coverage_start=trade_date,
                coverage_end=trade_date,
            )
            with db() as connection:
                connection.execute(
                    """
                    update provider_dataset_watermarks
                    set coverage_end=?,last_run_id=?,validation_status=?,updated_at=?
                    where provider='tushare' and dataset_key=?
                    """,
                    (trade_date, run_id, validation["status"], utc_now(), spec.key),
                )
                if rows:
                    connection.executemany(
                        """
                        update provider_dataset_watermarks set last_data_date=?,empty_result=0
                        where provider='tushare' and dataset_key=? and scope_key=?
                        """,
                        [(trade_date, spec.key, str(row["symbol"])) for row in rows],
                    )
        except Exception as exc:  # noqa: BLE001 - preserve a contiguous coverage watermark
            failed += 1
            _record_sync_failure(spec, None, trade_date, trade_date, exc)
            processed += 1
            _item(
                run_id,
                spec.key,
                processed=processed,
                inserted=inserted,
                updated=updated,
                failed=failed,
                error=json_dump({"failed": failed, "date": trade_date, "error": str(exc)}),
                checkpoint={
                    "index": processed,
                    "total": session_processed_base + len(work_dates),
                    "symbol": trade_date,
                },
                metrics=_throughput_metrics(
                    started,
                    phase="fetch",
                    api_calls=sum(endpoint_calls.values()),
                    downloaded=downloaded,
                    committed=committed,
                    processed_units=processed,
                    total_units=session_processed_base + len(work_dates),
                    empty_units=empty_units,
                    validated=validated,
                    endpoint_calls=endpoint_calls,
                    rate_units=processed - session_processed_base,
                ),
            )
            break
        processed += 1
        _item(
            run_id,
            spec.key,
            processed=processed,
            inserted=inserted,
            updated=updated,
            failed=failed,
            checkpoint={
                "index": processed,
                "total": session_processed_base + len(work_dates),
                "symbol": trade_date,
            },
            metrics=_throughput_metrics(
                started,
                phase="load",
                api_calls=sum(endpoint_calls.values()),
                downloaded=downloaded,
                committed=committed,
                processed_units=processed,
                total_units=session_processed_base + len(work_dates),
                empty_units=empty_units,
                validated=validated,
                endpoint_calls=endpoint_calls,
                rate_units=processed - session_processed_base,
            ),
        )
    return processed, inserted, updated, failed


def _sync_generic(
    adapter: TushareAdapter,
    spec: DatasetSpec,
    run_id: str,
    batch_id: str,
    end_date: str,
    task_id: str | None = None,
    full_refresh: bool = False,
    minimum_start_date: str | None = None,
) -> tuple[int, int, int, int]:
    if spec.normalizer == "adj_factor":
        return _sync_adj_factor_fast(
            adapter,
            spec,
            run_id,
            batch_id,
            end_date,
            task_id,
            full_refresh=full_refresh,
            minimum_start_date=minimum_start_date,
        )
    if spec.normalizer in {"daily_basic", "stk_limit", "suspend_d", "dividend"}:
        return _sync_instrument_dataset_fast(
            adapter,
            spec,
            run_id,
            batch_id,
            end_date,
            task_id,
            full_refresh=full_refresh,
            minimum_start_date=minimum_start_date,
        )
    if spec.normalizer == "suspend_d" and not full_refresh and hasattr(adapter, "suspend_rows_for_date"):
        listed_securities = _listed_securities()
        coverage_by_scope = _coverage_watermarks(spec)
        bootstrapped = False
        if not coverage_by_scope:
            coverage_by_scope = _bootstrap_sparse_watermarks_from_legacy_checkpoint(spec, listed_securities)
            bootstrapped = bool(coverage_by_scope)
        listed_scope_keys = {str(item["symbol"]) for item in listed_securities}
        if listed_scope_keys and listed_scope_keys.issubset(coverage_by_scope):
            return _sync_suspend_by_trade_date(
                adapter,
                spec,
                run_id,
                batch_id,
                end_date,
                task_id,
                coverage_by_scope,
            )
        if bootstrapped:
            completed = len(listed_scope_keys & set(coverage_by_scope))
            _item(
                run_id,
                spec.key,
                processed=completed,
                checkpoint={"index": completed, "total": len(listed_securities), "symbol": listed_securities[completed - 1]["symbol"]},
            )
    state = _item_state(run_id, spec.key)
    checkpoint = state.get("checkpoint") or {}
    resume_after = max(0, int(checkpoint.get("index") or 0))
    processed = int(state.get("processed") or 0)
    inserted = int(state.get("inserted") or 0)
    updated = int(state.get("updated") or 0)
    failed = int(state.get("failed") or 0)
    failure_samples: list[dict[str, Any]] = []
    session_processed_base = processed
    symbols = _listed_securities() if spec.scope == "instrument" else [None]
    if checkpoint.get("retryFailedOnly") and spec.scope == "instrument":
        retry_symbols = _open_sync_failure_instruments(spec)
        symbols = [item for item in symbols if str(item["symbol"]) in retry_symbols]
    latest_by_instrument = _latest_raw_dates_by_instrument(spec) if spec.scope == "instrument" else {}
    global_latest = _latest_raw_date(spec) if spec.scope != "instrument" else None
    coverage_by_scope = {} if full_refresh else _coverage_watermarks(spec)
    started = time.monotonic()
    api_before = _api_snapshot(adapter)
    api_calls = 0
    endpoint_calls: dict[str, int] = {}
    downloaded = 0
    committed = 0
    empty_units = 0
    validated = 0
    quarantined = 0
    timings = {"fetch": 0.0, "validate": 0.0, "mysqlWrite": 0.0}
    for index, item in enumerate(symbols, start=1):
        if index <= resume_after:
            continue
        if _cancelled(run_id, task_id):
            break
        symbol = str(item["symbol"]) if item else None
        scope_key = symbol or "global"
        persisted_latest = coverage_by_scope.get(scope_key) or (
            latest_by_instrument.get(symbol) if symbol else global_latest
        )
        # Deployments created before the multi-benchmark catalog have a global
        # CSI 300 watermark.  Do not let that watermark make newly introduced
        # index codes start at yesterday; one incremental run must backfill the
        # missing histories from the configured initial boundary.
        if spec.key == "index_daily" and _missing_default_index_daily_codes():
            persisted_latest = None
        latest = None if full_refresh else persisted_latest
        initial_start = str(item.get("listed_date") or "1990-01-01") if item else "1990-01-01"
        if minimum_start_date:
            initial_start = max(initial_start, minimum_start_date)
        start = (date.fromisoformat(latest) + timedelta(days=1)).isoformat() if latest else initial_start
        rows: list[dict[str, Any]] = []
        try:
            request = _generic_params(spec, start, end_date, symbol)
            stage_started = time.perf_counter()
            if spec.date_field and start > end_date:
                rows = []
            elif spec.normalizer == "index_weight":
                normalized = _call_with_retry(lambda: adapter.index_weight_rows("000300", start, end_date))
                rows = normalized
            else:
                if symbol:
                    if spec.normalizer == "suspend_d":
                        try:
                            normalized = _call_with_retry(
                                lambda: adapter.suspend_rows(
                                    symbol,
                                    start,
                                    end_date,
                                    include_legacy=persisted_latest is None,
                                )
                            )
                        except TypeError:
                            normalized = _call_with_retry(lambda: adapter.suspend_rows(symbol, start, end_date))
                    else:
                        normalized = _call_with_retry(lambda: _normalized_rows(adapter, spec, symbol, start, end_date))
                else:
                    normalized = None
                rows = normalized if normalized is not None else _call_with_retry(
                    lambda: _complete_global_query(
                        adapter.pro,
                        spec,
                        request,
                    )
                )
            timings["fetch"] += (time.perf_counter() - stage_started) * 1000
            endpoint_calls = _api_delta(api_before, _api_snapshot(adapter))
            api_calls = sum(endpoint_calls.values())
            downloaded += len(rows)
            raw_rows = [_raw_row_for_symbol(spec, row, symbol) for row in rows]
            stage_started = time.perf_counter()
            validation = _validate_dataset_rows(spec, raw_rows)
            validated += len(raw_rows)
            timings["validate"] += (time.perf_counter() - stage_started) * 1000
            stage_started = time.perf_counter()
            if spec.retain_raw:
                add, change = _save_raw(
                    spec,
                    raw_rows,
                    batch_id,
                    assume_new=persisted_latest is None,
                )
            else:
                add, change = len(rows), 0
            # Provider-derived canonical data is rebuildable. Always use the
            # dedicated bulk loader so generic datasets do not silently fall
            # back to binlogged, per-symbol business transactions.
            _normalize_optional(spec, rows, batch_id, bulk=True)
            committed += len(rows)
            timings["mysqlWrite"] += (time.perf_counter() - stage_started) * 1000
            _resolve_sync_failure(spec, symbol, batch_id)
            inserted += add
            updated += change
            if not rows:
                empty_units += 1
            _record_ingestion_manifest(
                run_id=run_id,
                spec=spec,
                scope_key=scope_key,
                request=request,
                rows=raw_rows,
                validation=validation,
                endpoint_counts=endpoint_calls,
                coverage_start=start,
                coverage_end=end_date,
            )
            if not spec.date_field or start <= end_date:
                _set_coverage_watermark(
                    spec,
                    scope_key=scope_key,
                    coverage_start=start,
                    coverage_end=end_date,
                    rows=raw_rows,
                    run_id=run_id,
                    validation_status=str(validation["status"]),
                )
        except Exception as exc:  # noqa: BLE001 - continue other instruments, but persist the cause
            failed += 1
            quarantined += len(rows)
            sample = _record_sync_failure(spec, symbol, start, end_date, exc)
            if len(failure_samples) < 10:
                failure_samples.append(sample)
        processed += 1
        if not _current_task(run_id, task_id):
            break
        item_error = json_dump({"failed": failed, "samples": failure_samples}) if failed else ""
        _item(
            run_id,
            spec.key,
            processed=processed,
            inserted=inserted,
            updated=updated,
            failed=failed,
            error=item_error,
            checkpoint={"index": index, "total": len(symbols), "symbol": symbol},
            metrics=_throughput_metrics(
                started,
                phase="load",
                api_calls=api_calls,
                downloaded=downloaded,
                committed=committed,
                processed_units=processed,
                total_units=len(symbols),
                empty_units=empty_units,
                validated=validated,
                quarantined=quarantined,
                endpoint_calls=endpoint_calls,
                timings=timings,
                rate_units=processed - session_processed_base,
            ),
        )
    return processed, inserted, updated, failed


def _set_catalog_coverage(spec: DatasetSpec) -> None:
    with db() as connection:
        if spec.key == "stock_basic":
            aggregate = connection.execute(
                """
                select count(distinct symbol) as count,min(start_date) as first_date,
                       max(coalesce(end_date,start_date)) as last_date
                from universe_membership
                where universe_code='ALL_A' and source='tushare:stock_basic'
                """
            ).fetchone()
        elif spec.key == "daily":
            aggregate = connection.execute(
                """
                select count(*) as count, min(trade_date) as first_date, max(trade_date) as last_date
                from market_daily_bars
                where source='tushare' and adjust='raw'
                  and asset_class='equity' and market='china' and venue='china'
                  and resolution='daily' and data_type='trade'
                """
            ).fetchone()
        elif spec.key == "adj_factor":
            aggregate = connection.execute(
                """
                select count(*) as count, min(trade_date) as first_date, max(trade_date) as last_date
                from adjustment_factors where source='tushare'
                """
            ).fetchone()
        elif spec.key == "stk_limit":
            aggregate = connection.execute(
                """
                select count(*) as count,min(trade_date) as first_date,max(trade_date) as last_date
                from market_trade_status
                where source='tushare:stk_limit' and asset_class='equity'
                  and market='china' and venue='china'
                """
            ).fetchone()
        elif spec.normalizer == "namechange":
            aggregate = connection.execute(
                """
                select count(*) as count,min(start_date) as first_date,
                       max(coalesce(end_date,start_date)) as last_date
                from security_name_history where source='tushare:namechange'
                """
            ).fetchone()
        elif spec.normalizer == "daily_basic":
            aggregate = connection.execute(
                """
                select count(*) as count,min(trade_date) as first_date,max(trade_date) as last_date
                from (
                    select symbol,trade_date from daily_basic_values
                    union
                    select symbol,trade_date from factor_values
                    where source='tushare:daily_basic'
                ) daily_basic_rows
                """
            ).fetchone()
        elif spec.normalizer == "dividend":
            aggregate = connection.execute(
                """
                select count(*) as count,min(ex_date) as first_date,max(ex_date) as last_date
                from corporate_actions where source='tushare:dividend'
                """
            ).fetchone()
        elif spec.normalizer == "financial":
            aggregate = connection.execute(
                """
                select count(*) as count,min(announce_date) as first_date,max(announce_date) as last_date
                from financial_statements where source=?
                """,
                (f"tushare:{spec.api_name}",),
            ).fetchone()
        elif spec.normalizer == "index_weight":
            aggregate = connection.execute(
                """
                select count(*) as count,min(trade_date) as first_date,max(trade_date) as last_date
                from index_weights where source='tushare:index_weight'
                """
            ).fetchone()
        else:
            aggregate = connection.execute(
                """
                select count(*) as count, min(business_date) as first_date, max(business_date) as last_date
                from provider_raw_records where provider='tushare' and dataset_key=?
                """,
                (spec.key,),
            ).fetchone()
        connection.execute(
            """
            update provider_dataset_catalog
            set row_count=?, first_data_date=?, last_data_date=?, last_synced_at=?
            where provider='tushare' and dataset_key=?
            """,
            (aggregate["count"], aggregate["first_date"], aggregate["last_date"], utc_now(), spec.key),
        )
    if spec.key == "stock_basic" and int(aggregate["count"] or 0) > 0:
        from .universe_coverage import record_universe_coverage

        record_universe_coverage(
            "ALL_A",
            coverage_start=aggregate["first_date"],
            coverage_end=date.today().isoformat(),
            status="complete",
            source="tushare:stock_basic",
            validation={"securityMasterRows": int(aggregate["count"] or 0), "listStatuses": ["L", "D", "P"]},
        )


def _sync_completion_evidence(run_id: str, selected_keys: set[str]) -> dict[str, Any]:
    specs = {spec.key: spec for spec in DATASET_REGISTRY if spec.key in selected_keys}
    with db() as connection:
        item_rows = connection.execute(
            "select dataset_key,status,failed,canonical_status from data_sync_items where run_id=?",
            (run_id,),
        ).fetchall()
        manifest_rows = connection.execute(
            """
            select dataset_key,count(*) as manifest_count,
                   sum(response_rows) as response_rows,sum(rejected_rows) as rejected_rows,
                   sum(case when status='success' then 0 else 1 end) as failed_manifests
            from provider_ingestion_manifests where run_id=? group by dataset_key
            """,
            (run_id,),
        ).fetchall()
        watermark_rows = connection.execute(
            """
            select dataset_key,count(*) as watermark_count
            from provider_dataset_watermarks where last_run_id=? group by dataset_key
            """,
            (run_id,),
        ).fetchall()
        archive_rows = connection.execute(
            """
            select a.dataset_key,count(*) as archive_count,sum(a.row_count) as archived_rows,
                   sum(case when o.id is null then 1 else 0 end) as orphan_count
            from provider_raw_archives a
            left join stored_objects o on o.id=a.object_id
            where a.run_id=? group by a.dataset_key
            """,
            (run_id,),
        ).fetchall()
    items = {str(row["dataset_key"]): dict(row) for row in item_rows}
    manifests = {str(row["dataset_key"]): dict(row) for row in manifest_rows}
    watermarks = {str(row["dataset_key"]): dict(row) for row in watermark_rows}
    archives = {str(row["dataset_key"]): dict(row) for row in archive_rows}
    evidence_items: list[dict[str, Any]] = []
    for key in sorted(selected_keys):
        spec = specs.get(key)
        item = items.get(key) or {}
        manifest = manifests.get(key) or {}
        watermark = watermarks.get(key) or {}
        archive = archives.get(key) or {}
        response_rows = int(manifest.get("response_rows") or 0)
        watermark_required = bool(spec and spec.date_field)
        archive_required = bool(spec and spec.retain_raw and response_rows > 0)
        issues: list[str] = []
        if item.get("status") != "success" or item.get("canonical_status") not in {None, "ready"}:
            issues.append("dataset_item_not_ready")
        if int(item.get("failed") or 0) > 0:
            issues.append("dataset_item_failed_units")
        if int(manifest.get("manifest_count") or 0) <= 0:
            issues.append("ingestion_manifest_missing")
        if int(manifest.get("failed_manifests") or 0) > 0 or int(manifest.get("rejected_rows") or 0) > 0:
            issues.append("ingestion_manifest_failed_or_rejected")
        if watermark_required and int(watermark.get("watermark_count") or 0) <= 0:
            issues.append("dataset_watermark_missing")
        if archive_required and int(archive.get("archive_count") or 0) <= 0:
            issues.append("raw_archive_missing")
        if int(archive.get("orphan_count") or 0) > 0:
            issues.append("raw_archive_object_missing")
        evidence_items.append(
            {
                "datasetKey": key,
                "passed": not issues,
                "issues": issues,
                "status": item.get("status"),
                "canonicalStatus": item.get("canonical_status"),
                "manifestCount": int(manifest.get("manifest_count") or 0),
                "responseRows": response_rows,
                "rejectedRows": int(manifest.get("rejected_rows") or 0),
                "watermarkRequired": watermark_required,
                "watermarkCount": int(watermark.get("watermark_count") or 0),
                "archiveRequired": archive_required,
                "archiveCount": int(archive.get("archive_count") or 0),
                "archivedRows": int(archive.get("archived_rows") or 0),
            }
        )
    return {
        "schemaVersion": 1,
        "passed": bool(evidence_items) and all(item["passed"] for item in evidence_items),
        "items": evidence_items,
    }


def run_sync(
    run_id: str,
    *,
    adapter: TushareAdapter | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    batch_id = run_id
    today = date.today()
    end_date = today.isoformat()
    with db() as connection:
        run_row = connection.execute("select * from data_sync_runs where id=?", (run_id,)).fetchone()
        if not run_row:
            raise KeyError("Data sync run not found.")
        if task_id and run_row["task_id"] != task_id:
            return {"status": "cancelled", "cancelled": True, "superseded": True, "datasets": {}}
        if run_row["cancel_requested"] or run_row["status"] == "cancelled":
            return {"status": "cancelled", "cancelled": True, "datasets": {}}
        if run_row["status"] not in {"queued", "running"}:
            return {"status": str(run_row["status"]), "cancelled": False, "datasets": {}}
        if task_id:
            connection.execute(
                "update data_sync_runs set status='running', started_at=coalesce(started_at,?), heartbeat_at=?, error=null where id=? and task_id=?",
                (utc_now(), utc_now(), run_id, task_id),
            )
        else:
            connection.execute(
                "update data_sync_runs set status='running', started_at=coalesce(started_at,?), heartbeat_at=?, error=null where id=?",
                (utc_now(), utc_now(), run_id),
            )
        run_row = connection.execute("select * from data_sync_runs where id=?", (run_id,)).fetchone()
    run_record = row_to_dict(run_row) or {}
    adapter = adapter or TushareAdapter()
    selected_keys = set(run_record.get("requestedDatasets") or [spec.key for spec in DATASET_REGISTRY])
    sync_mode = str(run_record.get("mode") or "incremental")
    resume_base_mode = str((run_record.get("summary") or {}).get("resumeBaseMode") or "")
    full_refresh = sync_mode in {"initial_full", "full_rebuild", "screen_backfill"} or resume_base_mode in {"initial_full", "full_rebuild", "screen_backfill"}
    reconcile_full_snapshot = sync_mode == "full_rebuild" or resume_base_mode == "full_rebuild"
    scoped_backfill = sync_mode in {"universe_backfill", "screen_backfill"} or resume_base_mode in {
        "universe_backfill",
        "screen_backfill",
    }
    request_scope = run_record.get("requestScope") or {}
    minimum_start_date: str | None = None
    if sync_mode == "screen_backfill" or resume_base_mode == "screen_backfill":
        requested_as_of = str(request_scope.get("asOfDate") or end_date)
        end_date = min(today, date.fromisoformat(requested_as_of)).isoformat()
        history_bars = max(250, min(750, int(request_scope.get("minHistoryBars") or 500)))
        minimum_start_date = (
            date.fromisoformat(end_date) - timedelta(days=history_bars * 8 // 5 + 60)
        ).isoformat()
    try:
        # The legacy-source audit scans A-share daily bars and is relevant only
        # when that dataset participates in the run.  Running it for a targeted
        # index or contract-catalog refresh needlessly scans the largest table
        # and can exhaust a workstation MySQL instance before the requested
        # dataset is touched.
        audit = audit_existing_data() if "daily" in selected_keys else {"detected": 0}
        probe_keys = _permission_probe_keys(selected_keys)
        if probe_keys:
            probe_permissions(adapter, only=probe_keys, run_id=run_id, task_id=task_id)
        permissions = _permission_summary(selected_keys)
        market_end_date = _latest_open_trade_date(end_date)
        with db() as connection:
            permission_rows = connection.execute(
                "select dataset_key, permission_status, permission_reason from provider_dataset_catalog where provider='tushare'"
            ).fetchall()
            item_rows = connection.execute(
                "select * from data_sync_items where run_id=?",
                (run_id,),
            ).fetchall()
        item_records = rows_to_dicts(item_rows)
        permission_by_dataset = {
            str(row["dataset_key"]): (str(row["permission_status"] or "unknown"), row["permission_reason"])
            for row in permission_rows
        }
        allowed = {
            key for key, (status, _) in permission_by_dataset.items()
            if status in {"available", "empty"}
        }
        completed = {
            row["dataset_key"]
            for row in item_records
            if row["status"] == "success" or (row["status"] == "partial" and _checkpoint_complete(row))
        }
        summaries: dict[str, Any] = {
            row["dataset_key"]: {
                "processed": int(row.get("processed") or 0),
                "inserted": int(row.get("inserted") or 0),
                "updated": int(row.get("updated") or 0),
                "failed": int(row.get("failed") or 0),
                "preserved": True,
            }
            for row in item_records
            if row["status"] == "partial" and _checkpoint_complete(row)
        }
        infrastructure_failure: dict[str, Any] | None = None
        for spec in DATASET_REGISTRY:
            if spec.key not in selected_keys:
                continue
            if _cancelled(run_id, task_id):
                break
            if spec.key in completed:
                continue
            # Runs created before the policy migration may still contain HK/US
            # items.  Enforce the current policy at execution time as well as
            # at run creation so a resumed legacy run cannot consume a 1/hour
            # endpoint or stall the full-database worker.
            if spec.sync_policy == "on_demand" and not scoped_backfill:
                _item(
                    run_id,
                    spec.key,
                    status="skipped",
                    finished_at=utc_now(),
                    error="Skipped by bulk policy: fetched on demand when requested by a market-data workflow.",
                )
                continue
            if spec.key not in allowed:
                permission_status, permission_reason = permission_by_dataset.get(spec.key, ("unknown", None))
                _item(
                    run_id,
                    spec.key,
                    status="skipped",
                    finished_at=utc_now(),
                    error=_permission_skip_message(permission_status, permission_reason),
                )
                continue
            _item(run_id, spec.key, status="running", started_at=utc_now(), error="")
            dataset_started = time.monotonic()
            dataset_api_before = _api_snapshot(adapter)
            try:
                if spec.key == "stock_basic":
                    values = _sync_stock_basic(adapter, batch_id)
                    result = (*values, 0)
                elif spec.key == "trade_cal":
                    values = _sync_calendar(adapter, batch_id, end_date, full_refresh=full_refresh)
                    result = (*values, 0)
                    # The run may have started with a stale local calendar.
                    # Recompute the market cutoff after trade_cal is refreshed
                    # so the same click can fetch all newly known sessions.
                    market_end_date = _latest_open_trade_date(end_date)
                elif spec.key == "daily":
                    result = _sync_daily(
                        adapter,
                        run_id,
                        batch_id,
                        market_end_date,
                        task_id,
                        full_refresh=full_refresh,
                        reconcile_full_snapshot=reconcile_full_snapshot,
                        minimum_start_date=minimum_start_date,
                    )
                else:
                    dataset_end_date = (
                        market_end_date
                        if spec.key in {"adj_factor", "daily_basic", "suspend_d", "stk_limit", "index_daily"}
                        else end_date
                    )
                    result = _sync_generic(
                        adapter,
                        spec,
                        run_id,
                        batch_id,
                        dataset_end_date,
                        task_id,
                        full_refresh=full_refresh,
                        minimum_start_date=minimum_start_date,
                    )
                processed, inserted, updated, failed = result
                if spec.key in {"stock_basic", "trade_cal"}:
                    endpoint_calls = _api_delta(dataset_api_before, _api_snapshot(adapter))
                    _item(
                        run_id,
                        spec.key,
                        metrics=_throughput_metrics(
                            dataset_started,
                            phase="validate",
                            api_calls=sum(endpoint_calls.values()),
                            downloaded=processed,
                            committed=inserted + updated,
                            processed_units=1,
                            total_units=1,
                            empty_units=1 if processed == 0 else 0,
                            validated=processed,
                            endpoint_calls=endpoint_calls,
                        ),
                    )
                if _cancelled(run_id, task_id):
                    if _current_task(run_id, task_id):
                        _item(
                            run_id,
                            spec.key,
                            status="cancelled",
                            processed=processed,
                            inserted=inserted,
                            updated=updated,
                            failed=failed,
                            finished_at=utc_now(),
                        )
                    summaries[spec.key] = {
                        "processed": processed,
                        "inserted": inserted,
                        "updated": updated,
                        "failed": failed,
                        "cancelled": True,
                    }
                    break
                status = "success" if failed == 0 else "partial"
                _item(
                    run_id,
                    spec.key,
                    status=status,
                    processed=processed,
                    inserted=inserted,
                    updated=updated,
                    failed=failed,
                    canonical_status="ready" if failed == 0 else "partial",
                    derived_status_json=json_dump(
                        {"status": "pending"}
                        if spec.key == "daily"
                        else {"status": "not_required"}
                    ),
                    finished_at=utc_now(),
                )
                _set_catalog_coverage(spec)
                summaries[spec.key] = {"processed": processed, "inserted": inserted, "updated": updated, "failed": failed}
            except Exception as exc:  # noqa: BLE001
                if _mysql_infrastructure_failure(exc):
                    infrastructure_failure = {
                        "code": "MYSQL_CONNECTION_LOST",
                        "dataset": spec.key,
                        "message": str(exc),
                        "retryable": True,
                    }
                    _item(
                        run_id,
                        spec.key,
                        status="paused",
                        failed=0,
                        canonical_status="partial",
                        error=json_dump(infrastructure_failure),
                        finished_at=utc_now(),
                    )
                    summaries[spec.key] = {
                        "error": str(exc),
                        "paused": True,
                        "retryable": True,
                    }
                    break
                _item(
                    run_id,
                    spec.key,
                    status="failed",
                    failed=1,
                    canonical_status="failed",
                    error=str(exc),
                    finished_at=utc_now(),
                )
                summaries[spec.key] = {"error": str(exc)}
        if infrastructure_failure is not None:
            summary = {
                "status": "paused",
                "permissions": permissions,
                "audit": audit,
                "datasets": summaries,
                "endDate": end_date,
                "marketDataEndDate": market_end_date,
                "cancelled": False,
                "mode": sync_mode,
                "resumeBaseMode": resume_base_mode or None,
                "infrastructureFailure": infrastructure_failure,
            }
            with db() as connection:
                parameters = (
                    json_dump(summary),
                    "MySQL connection lost; synchronization paused at the durable checkpoint.",
                    json_dump({"status": "blocked", "reason": "mysql_connection_lost"}),
                    utc_now(),
                    run_id,
                )
                task_guard = " and task_id=?" if task_id else ""
                if task_id:
                    parameters = (*parameters, task_id)
                connection.execute(
                    f"""update data_sync_runs
                        set status='paused',summary_json=?,error=?,canonical_status='partial',
                            derived_status_json=?,finished_at=?
                        where id=?{task_guard}""",
                    parameters,
                )
            return summary
        cancelled = _cancelled(run_id, task_id)
        completion_evidence = _sync_completion_evidence(run_id, selected_keys)
        degraded = (
            any(item.get("error") or int(item.get("failed") or 0) > 0 for item in summaries.values())
            or not completion_evidence["passed"]
        )
        final_status = "cancelled" if cancelled else "partial" if degraded else "success"
        canonical_status = "cancelled" if cancelled else "partial" if degraded else "ready"
        daily_summary = summaries.get("daily") or {}
        should_materialize = bool(
            not cancelled
            and final_status == "success"
            and completion_evidence["passed"]
            and "daily" in selected_keys
            and not daily_summary.get("error")
            and int(daily_summary.get("failed") or 0) == 0
        )
        with db() as connection:
            existing_run = connection.execute(
                "select derived_status_json from data_sync_runs where id=?",
                (run_id,),
            ).fetchone()
        try:
            existing_derived = json.loads((dict(existing_run) if existing_run else {}).get("derived_status_json") or "{}")
        except (TypeError, ValueError, AttributeError):
            existing_derived = {}
        existing_derived_status = str(existing_derived.get("status") or "")
        materialization_already_scheduled = existing_derived_status in {"queued", "running", "ready"}
        enqueue_materialization = should_materialize and not materialization_already_scheduled
        if should_materialize and materialization_already_scheduled:
            derived_status = existing_derived
        elif should_materialize:
            derived_status = {"status": "queued", "total": None, "completed": 0, "failed": 0}
        else:
            derived_status = {"status": "not_required" if "daily" not in selected_keys else "blocked"}
        summary = {
            "status": final_status, "permissions": permissions, "audit": audit,
            "datasets": summaries, "endDate": end_date, "marketDataEndDate": market_end_date, "cancelled": cancelled,
            "mode": sync_mode, "resumeBaseMode": resume_base_mode or None,
            "completionEvidence": completion_evidence,
        }
        with db() as connection:
            if task_id:
                connection.execute(
                    """update data_sync_runs
                       set status=?, summary_json=?, canonical_status=?, canonical_ready_at=?,
                           derived_status_json=?, finished_at=?
                       where id=? and task_id=?""",
                    (
                        final_status,
                        json_dump(summary),
                        canonical_status,
                        utc_now() if canonical_status == "ready" else None,
                        json_dump(derived_status),
                        utc_now(),
                        run_id,
                        task_id,
                    ),
                )
            else:
                connection.execute(
                    """update data_sync_runs
                       set status=?, summary_json=?, canonical_status=?, canonical_ready_at=?,
                           derived_status_json=?, finished_at=? where id=?""",
                    (
                        final_status,
                        json_dump(summary),
                        canonical_status,
                        utc_now() if canonical_status == "ready" else None,
                        json_dump(derived_status),
                        utc_now(),
                        run_id,
                    ),
                )
        if enqueue_materialization:
            try:
                from ..tasks.worker import materialize_sync_data_task

                materialize_sync_data_task.apply_async(args=[run_id], queue="data-demand")
            except Exception as exc:  # Derived enqueue failure must not revoke canonical readiness.
                with db() as connection:
                    connection.execute(
                        "update data_sync_runs set derived_status_json=? where id=?",
                        (json_dump({"status": "enqueue_failed", "error": str(exc)[:500]}), run_id),
                    )
        return summary
    except Exception as exc:
        with db() as connection:
            if task_id:
                connection.execute(
                    "update data_sync_runs set status='failed', canonical_status='failed', error=?, finished_at=? where id=? and task_id=?",
                    (str(exc), utc_now(), run_id, task_id),
                )
            else:
                connection.execute(
                    "update data_sync_runs set status='failed', canonical_status='failed', error=?, finished_at=? where id=?",
                    (str(exc), utc_now(), run_id),
                )
        raise


def create_sync_run(
    *, requested: list[str] | None = None, mode: str = "auto", request_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_catalog()
    if mode not in {"auto", "incremental", "full_rebuild", "universe_backfill", "screen_backfill"}:
        raise ValueError("Data sync mode must be auto, incremental, full_rebuild, universe_backfill, or screen_backfill.")
    if mode == "universe_backfill":
        scope_type = str((request_scope or {}).get("type") or "")
        if scope_type != "pit_universe_union":
            raise ValueError("universe_backfill requires scope.type=pit_universe_union.")
    if mode == "screen_backfill":
        from .ashare_swing_screen import REQUIRED_DATASETS as SCREEN_DATASETS

        scope_type = str((request_scope or {}).get("type") or "")
        if scope_type != "ashare_swing_screen":
            raise ValueError("screen_backfill requires scope.type=ashare_swing_screen.")
        unsupported = sorted(set(requested or []) - set(SCREEN_DATASETS))
        if unsupported:
            raise ValueError("screen_backfill only accepts A-share screening datasets: " + ", ".join(unsupported))
    with db() as connection:
        active = connection.execute(
            "select * from data_sync_runs where status in ('queued','running','cancelling') order by created_at desc limit 1"
        ).fetchone()
        if active:
            raise ValueError("A full database update is already queued or running.")
        completed_initial_sync = connection.execute(
            """
            select id from data_sync_runs
            where status = 'success' and coalesce(canonical_status, 'ready') = 'ready'
            order by finished_at desc limit 1
            """
        ).fetchone()
    resolved_mode = mode
    if mode == "auto":
        resolved_mode = "incremental" if completed_initial_sync else "initial_full"
    known = {spec.key for spec in DATASET_REGISTRY}
    unknown = sorted(set(requested or []) - known)
    if unknown:
        raise ValueError(f"Unknown TuShare datasets: {', '.join(unknown)}")
    run_id = str(uuid.uuid4())
    now = utc_now()
    selected = [
        spec
        for spec in DATASET_REGISTRY
        if (requested and spec.key in requested) or (not requested and spec.sync_policy != "on_demand")
    ]
    on_demand_requested = [spec.key for spec in selected if spec.sync_policy == "on_demand"]
    if on_demand_requested and mode not in {"universe_backfill", "screen_backfill"}:
        raise ValueError(
            "On-demand datasets cannot be included in a full database update: "
            + ", ".join(on_demand_requested)
        )
    with db() as connection:
        connection.execute(
            """
            insert into data_sync_runs
                (id,provider,mode,scope,status,requested_datasets_json,
                 canonical_status,derived_status_json,created_at,request_scope_json)
            values (?,'tushare',?,?,'queued',?,'pending',?,?,?)
            """,
            (
                run_id,
                resolved_mode,
                "pit_universe_union" if mode == "universe_backfill" else "ashare_swing_screen" if mode == "screen_backfill" else "all_entitled_low_frequency",
                json_dump([item.key for item in selected]),
                json_dump({"leanCache": "pending", "clickHouse": "pending"}),
                now,
                json_dump(request_scope or {}),
            ),
        )
        for spec in selected:
            connection.execute(
                "insert into data_sync_items (id,run_id,dataset_key,status) values (?,?,?,'queued')",
                (str(uuid.uuid4()), run_id, spec.key),
            )
    return sync_run(run_id) or {}


def sync_run(run_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from data_sync_runs where id=?", (run_id,)).fetchone()
        items = connection.execute("select * from data_sync_items where run_id=? order by dataset_key", (run_id,)).fetchall()
    result = row_to_dict(row)
    if result:
        item_payloads = rows_to_dicts(items)
        for item in item_payloads:
            metrics = dict(item.get("metrics") or {})
            metrics.pop("_rateSamples", None)
            if "writeRowsPerSecond" in metrics:
                metrics["canonicalWriteRowsPerSecond"] = metrics["writeRowsPerSecond"]
            if "queueDepth" in metrics:
                metrics["loadQueueDepth"] = metrics["queueDepth"]
            if "committedRows" in metrics:
                metrics["spooledRows"] = metrics["committedRows"]
            checkpoint = item.get("checkpoint") or {}
            work_key = str(checkpoint.get("symbol") or "")
            metrics["fetchStrategy"] = (
                "market_date"
                if len(work_key) == 10 and work_key[4:5] == "-" and work_key[7:8] == "-"
                else "instrument"
                if work_key
                else "global"
            )
            try:
                metrics.update(lineage_metrics(run_id, str(item["dataset_key"])))
            except Exception:
                # Older test schemas and partially applied deployments do not
                # have the additive lineage table yet.
                pass
            if (
                database_backend() == "mysql"
                and item.get("status") in {"checking", "running"}
                and "apiCalls" in metrics
            ):
                try:
                    metrics.update(global_tushare_quota_status())
                except Exception:
                    pass
            item["metrics"] = metrics
        result["items"] = item_payloads
    return result


def sync_validation(run_id: str, *, limit: int = 500) -> dict[str, Any]:
    run = sync_run(run_id)
    if not run:
        raise KeyError("Data sync run not found.")
    safe_limit = max(1, min(int(limit), 5_000))
    with db() as connection:
        manifests = connection.execute(
            """
            select * from provider_ingestion_manifests
            where run_id=? order by created_at desc limit ?
            """,
            (run_id, safe_limit),
        ).fetchall()
        summary_rows = connection.execute(
            """
            select dataset_key,status,count(*) as scopes,sum(response_rows) as response_rows,
                   sum(normalized_rows) as normalized_rows,sum(rejected_rows) as rejected_rows
            from provider_ingestion_manifests where run_id=?
            group by dataset_key,status order by dataset_key,status
            """,
            (run_id,),
        ).fetchall()
        watermarks = connection.execute(
            """
            select * from provider_dataset_watermarks
            where last_run_id=? order by dataset_key,scope_key limit ?
            """,
            (run_id, safe_limit),
        ).fetchall()
        issues = connection.execute(
            """
            select * from data_record_issues
            where resolution_batch_id=? or (
                detected_at>=coalesce(?,'0000-01-01') and detected_at<=coalesce(?,?)
                and dataset_key in (
                    select dataset_key from data_sync_items where run_id=?
                )
            )
            order by detected_at desc limit ?
            """,
            (
                run_id,
                run.get("started_at"),
                run.get("finished_at"),
                utc_now(),
                run_id,
                safe_limit,
            ),
        ).fetchall()
    return {
        "runId": run_id,
        "canonicalStatus": run.get("canonical_status"),
        "summary": rows_to_dicts(summary_rows),
        "manifests": rows_to_dicts(manifests),
        "watermarks": rows_to_dicts(watermarks),
        "issues": rows_to_dicts(issues),
        "limit": safe_limit,
    }


def download_on_demand_dataset(
    *,
    task_id: str,
    dataset_key: str,
    storage_target: str,
    relative_path: str | None,
    file_format: str,
    start_date: str | None = None,
    end_date: str | None = None,
    symbol: str | None = None,
    parameters: dict[str, Any] | None = None,
    adapter: TushareAdapter | None = None,
) -> dict[str, Any]:
    spec = next((item for item in DATASET_REGISTRY if item.key == dataset_key), None)
    if not spec:
        raise ValueError(f"Unknown TuShare dataset: {dataset_key}")
    if spec.sync_policy != "on_demand":
        raise ValueError(f"{dataset_key} participates in managed synchronization; use the dataset sync controls instead.")
    if spec.scope == "instrument" and not str(symbol or "").strip():
        raise ValueError(f"{dataset_key} requires a symbol.")
    resolved_end = date.fromisoformat(end_date).isoformat() if end_date else date.today().isoformat()
    resolved_start = (
        date.fromisoformat(start_date).isoformat()
        if start_date
        else (date.fromisoformat(resolved_end) - timedelta(days=30)).isoformat()
    )
    if resolved_start > resolved_end:
        raise ValueError("startDate must not be after endDate.")
    export_format = str(file_format or "parquet").strip().lower()
    if export_format not in {"parquet", "jsonl"}:
        raise ValueError("format must be parquet or jsonl.")
    output_dir, display_dir = _on_demand_destination(storage_target, relative_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    adapter = adapter or TushareAdapter()
    api_before = _api_snapshot(adapter)
    normalized: list[dict[str, Any]] | None = None
    selected_symbol = str(symbol or "").strip()
    if selected_symbol and spec.normalizer:
        normalized = _call_with_retry(
            lambda: _normalized_rows(adapter, spec, selected_symbol, resolved_start, resolved_end)
        )
    request_params = _generic_params(spec, resolved_start, resolved_end, selected_symbol or None)
    for key, value in (parameters or {}).items():
        clean_key = str(key).strip()
        if not clean_key.isidentifier():
            raise ValueError(f"Invalid TuShare parameter name: {clean_key!r}")
        if value not in (None, ""):
            request_params[clean_key] = value
    rows = normalized if normalized is not None else _call_with_retry(
        lambda: _query(adapter.pro, spec, request_params)
    )
    raw_rows = [
        _raw_row_for_symbol(spec, row, selected_symbol or str(row.get("symbol") or ""))
        for row in rows
    ]
    validation = _validate_dataset_rows(spec, raw_rows)
    endpoint_counts = _api_delta(api_before, _api_snapshot(adapter))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = "parquet" if export_format == "parquet" else "jsonl"
    file_name = f"tushare-{spec.key}-{stamp}-{task_id[:8]}.{suffix}"
    output_path = output_dir / file_name
    if export_format == "jsonl":
        with output_path.open("w", encoding="utf-8") as handle:
            for row in raw_rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    else:
        try:
            import polars as pl
        except Exception as exc:  # pragma: no cover - deployment dependency guard.
            raise RuntimeError("polars is required for Parquet on-demand exports.") from exc
        parquet_rows = [
            {
                key: json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
                if isinstance(value, (dict, list, tuple, set))
                else value.item() if hasattr(value, "item")
                else value
                for key, value in row.items()
            }
            for row in raw_rows
        ]
        if parquet_rows:
            frame = pl.DataFrame(parquet_rows, infer_schema_length=None)
        else:
            fields = list(dict.fromkeys([*spec.key_fields, *([spec.date_field] if spec.date_field else [])]))
            frame = pl.DataFrame(schema={field: pl.String for field in fields})
        frame.write_parquet(output_path, compression=os.environ.get("LEAN_PARQUET_COMPRESSION", "zstd"))

    digest = hashlib.sha256()
    with output_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    _record_ingestion_manifest(
        run_id=task_id,
        spec=spec,
        scope_key=selected_symbol or "custom",
        request={
            "startDate": resolved_start,
            "endDate": resolved_end,
            "symbol": selected_symbol or None,
            "parameters": request_params,
            "storageTarget": storage_target,
            "relativePath": str(relative_path or "tushare-on-demand"),
            "format": export_format,
        },
        rows=raw_rows,
        validation=validation,
        endpoint_counts=endpoint_counts,
        coverage_start=resolved_start if spec.date_field else None,
        coverage_end=resolved_end if spec.date_field else None,
    )
    return {
        "taskId": task_id,
        "dataset": spec.key,
        "rows": len(raw_rows),
        "format": export_format,
        "path": str(output_path),
        "displayPath": str(display_dir / file_name),
        "bytes": output_path.stat().st_size,
        "sha256": digest.hexdigest(),
        "apiCalls": sum(endpoint_counts.values()),
        "endpointCalls": endpoint_counts,
        "validation": validation,
    }


def materialize_daily_run(run_id: str) -> dict[str, Any]:
    """Build derivatives once per sync run, resuming a durable symbol checkpoint."""
    if database_backend() != "mysql":
        return _materialize_daily_run_locked(run_id)

    lock_name = f"lean:materialize:{run_id}"[:64]
    with db() as lease_connection:
        lock_row = lease_connection.execute(
            "select get_lock(?, 0) as acquired",
            (lock_name,),
        ).fetchone()
        if int((lock_row or {}).get("acquired") or 0) != 1:
            with db() as connection:
                row = connection.execute(
                    "select derived_status_json from data_sync_runs where id=?",
                    (run_id,),
                ).fetchone()
            try:
                status = json.loads((dict(row) if row else {}).get("derived_status_json") or "{}")
            except (TypeError, ValueError, AttributeError):
                status = {}
            return {"runId": run_id, "status": "already_running", "derivedStatus": status}
        try:
            return _materialize_daily_run_locked(run_id, lease_connection=lease_connection)
        finally:
            lease_connection.execute("select release_lock(?)", (lock_name,))


def _materialize_daily_run_locked(run_id: str, *, lease_connection: Any | None = None) -> dict[str, Any]:
    """Build LEAN/object/ClickHouse derivatives after canonical MySQL commit."""
    from .data import record_data_asset
    from .lean_cache import rebuild_ashare_lean_cache_from_db
    from .market_data import mirror_rows_batch, query_database_bars

    with db() as connection:
        rows = connection.execute(
            """
            select distinct scope_key from provider_ingestion_manifests
            where run_id=? and dataset_key='daily' and status='success' and response_rows>0
            order by scope_key
            """,
            (run_id,),
        ).fetchall()
        run_row = connection.execute(
            "select derived_status_json from data_sync_runs where id=?",
            (run_id,),
        ).fetchone()
    symbols = [str(row["scope_key"]) for row in rows]
    try:
        previous_status = json.loads((dict(run_row) if run_row else {}).get("derived_status_json") or "{}")
    except (TypeError, ValueError, AttributeError):
        previous_status = {}
    if (
        previous_status.get("status") == "ready"
        and int(previous_status.get("completed") or 0) >= len(symbols)
        and bool((previous_status.get("parquet") or {}).get("passed"))
    ):
        return {"runId": run_id, **previous_status}

    resumable = previous_status.get("status") in {"queued", "running"}
    completed = min(int(previous_status.get("completed") or 0), len(symbols)) if resumable else 0
    failure_count = int(previous_status.get("failed") or 0) if resumable else 0
    failure_samples: list[dict[str, str]] = list(previous_status.get("failureSamples") or [])[:10] if resumable else []
    parquet_result: dict[str, Any] | None = None
    parquet_progress: dict[str, Any] | None = None
    pending: list[tuple[dict[str, Any], list[dict[str, str]]]] = []
    pending_rows = 0

    def record_failure(*, symbol: str, stage: str, error: str) -> None:
        nonlocal failure_count
        failure_count += 1
        if len(failure_samples) < 10:
            failure_samples.append({"symbol": symbol, "stage": stage, "error": error[:500]})

    def persist_progress(status: str) -> None:
        payload = {
            "status": status,
            "total": len(symbols),
            "completed": completed,
            "failed": failure_count,
            "failureSamples": failure_samples,
            "checkpointScope": symbols[completed - 1] if completed else None,
            "heartbeatAt": utc_now(),
            "parquet": {
                "rebuiltCount": int((parquet_result or {}).get("rebuiltCount") or 0),
                "certifiedDatasetIds": (parquet_result or {}).get("certifiedDatasetIds") or [],
                "reportId": ((parquet_result or {}).get("consistencyReport") or {}).get("reportId"),
                "passed": bool(((parquet_result or {}).get("consistencyReport") or {}).get("passed")),
            },
            "parquetProgress": parquet_progress,
        }
        with db() as connection:
            connection.execute(
                "update data_sync_runs set derived_status_json=? where id=?",
                (json_dump(payload), run_id),
            )
            connection.execute(
                "update data_sync_items set derived_status_json=? where run_id=? and dataset_key='daily'",
                (json_dump(payload), run_id),
            )
        if lease_connection is not None:
            lease_connection.execute("select 1")

    def flush_pending() -> None:
        nonlocal completed, pending, pending_rows
        if not pending:
            return
        clickhouse_results = mirror_rows_batch(pending)
        for (metadata, _bars), clickhouse in zip(pending, clickhouse_results, strict=True):
            metadata["clickhouse"] = clickhouse
            try:
                record_data_asset(metadata)
            except Exception as exc:  # noqa: BLE001 - keep the checkpoint retryable
                record_failure(symbol=str(metadata.get("symbol") or "?"), stage="data_asset", error=str(exc))
            if clickhouse.get("error"):
                record_failure(
                    symbol=str(metadata.get("symbol") or "?"),
                    stage="clickhouse",
                    error=str(clickhouse["error"]),
                )
            completed += 1
            if completed % 25 == 0:
                persist_progress("running")
        pending = []
        pending_rows = 0

    persist_progress("running")
    for symbol in symbols[completed:]:
        try:
            metadata = rebuild_ashare_lean_cache_from_db(
                symbol,
                source="tushare",
                adjust="raw",
                market="china",
                batch_id=run_id,
            )
            metadata.update(
                {
                    "asset_class": "equity",
                    "venue": "china",
                    "resolution": "daily",
                    "data_type": "trade",
                    "provider": "tushare",
                    "market": "china",
                    "adjust": "raw",
                    "batch_id": run_id,
                }
            )
            bars = query_database_bars(
                asset_class="equity",
                symbol=symbol,
                market="china",
                venue="china",
                resolution="daily",
                data_type="trade",
                provider_source="tushare",
                limit=0,
            )["items"]
            pending.append((metadata, bars))
            pending_rows += len(bars)
            if len(pending) >= 10 or pending_rows >= MAX_SYNC_BATCH_ROWS:
                flush_pending()
        except Exception as exc:  # noqa: BLE001 - derivatives are independently retryable
            flush_pending()
            record_failure(symbol=symbol, stage="materialize", error=str(exc))
            completed += 1
            if completed % 25 == 0:
                persist_progress("running")
    flush_pending()
    try:
        from .parquet_lake import rebuild_all_market_parquet

        def record_parquet_progress(progress: dict[str, Any]) -> None:
            nonlocal parquet_progress
            parquet_progress = progress
            persist_progress("running")

        parquet_result = rebuild_all_market_parquet(
            asset_class="equity",
            market="china",
            venue="china",
            resolution="daily",
            data_type="trade",
            adjust="raw",
            sources=["tushare"],
            include_research_sources=False,
            continue_on_error=False,
            persist_report=True,
            progress_callback=record_parquet_progress,
        )
        if not (parquet_result.get("consistencyReport") or {}).get("passed"):
            record_failure(
                symbol="*",
                stage="parquet_consistency",
                error="Parquet/MySQL/DuckDB consistency validation did not pass.",
            )
        if not parquet_result.get("certifiedDatasetIds"):
            record_failure(
                symbol="*",
                stage="source_certification",
                error="No TuShare dataset was certified after consistency validation.",
            )
    except Exception as exc:  # noqa: BLE001 - certification is fail-closed and retryable
        record_failure(symbol="*", stage="parquet", error=str(exc))
    final_status = "ready" if failure_count == 0 else "partial"
    persist_progress(final_status)
    return {
        "runId": run_id,
        "status": final_status,
        "total": len(symbols),
        "completed": completed,
        "failed": failure_count,
        "failureSamples": failure_samples,
        "parquet": {
            "rebuiltCount": int((parquet_result or {}).get("rebuiltCount") or 0),
            "certifiedDatasetIds": (parquet_result or {}).get("certifiedDatasetIds") or [],
            "reportId": ((parquet_result or {}).get("consistencyReport") or {}).get("reportId"),
            "passed": bool(((parquet_result or {}).get("consistencyReport") or {}).get("passed")),
        },
    }


def list_sync_runs(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    bounded_limit = max(1, min(int(limit), 100))
    bounded_offset = max(0, int(offset))
    with db() as connection:
        total = connection.execute("select count(*) as count from data_sync_runs").fetchone()
        rows = connection.execute(
            "select * from data_sync_runs order by created_at desc limit ? offset ?",
            (bounded_limit, bounded_offset),
        ).fetchall()
    return {
        "items": rows_to_dicts(rows),
        "count": int(total["count"] or 0),
        "limit": bounded_limit,
        "offset": bounded_offset,
    }


def mark_run_failed(run_id: str, error: str) -> None:
    with db() as connection:
        connection.execute(
            "update data_sync_runs set status='failed', canonical_status='failed', error=?, finished_at=? where id=?",
            (error, utc_now(), run_id),
        )


def bind_task(run_id: str, task_id: str) -> None:
    with db() as connection:
        connection.execute("update data_sync_runs set task_id=? where id=?", (task_id, run_id))


def queue_stale_run_for_recovery(run_id: str) -> bool:
    with db() as connection:
        current = connection.execute(
            "select status,cancel_requested from data_sync_runs where id=?",
            (run_id,),
        ).fetchone()
        if not current or current["status"] not in {"queued", "running"} or current["cancel_requested"]:
            return False
        connection.execute("update data_sync_runs set status='queued', error=null where id=?", (run_id,))
    return True


def queue_stale_derived_for_recovery(run_id: str, payload: dict[str, Any]) -> bool:
    with db() as connection:
        current = connection.execute(
            "select canonical_status,derived_status_json from data_sync_runs where id=?",
            (run_id,),
        ).fetchone()
        if not current or current["canonical_status"] != "ready":
            return False
        try:
            current_payload = json.loads(current["derived_status_json"] or "{}")
        except (TypeError, ValueError):
            return False
        if current_payload.get("status") not in {"queued", "running"}:
            return False
        encoded = json_dump(payload)
        connection.execute("update data_sync_runs set derived_status_json=? where id=?", (encoded, run_id))
        connection.execute(
            "update data_sync_items set derived_status_json=? where run_id=? and dataset_key='daily'",
            (encoded, run_id),
        )
    return True


def request_cancel(run_id: str) -> dict[str, Any]:
    item = sync_run(run_id)
    if not item:
        raise KeyError("Data sync run not found.")
    if item["status"] not in {"queued", "running", "cancelling"}:
        return item

    with db() as connection:
        connection.execute(
            "update data_sync_runs set cancel_requested=1,status='cancelling' where id=? and status in ('queued','running','cancelling')",
            (run_id,),
        )
    task_id = item.get("task_id")
    if task_id:
        try:
            from .tasks import cancel_task

            cancel_task(str(task_id))
        except KeyError:
            pass

    now = utc_now()
    message = "Cancellation requested by user."
    with db() as connection:
        connection.execute(
            """
            update data_sync_runs
            set status='cancelled', cancel_requested=1,
                error=coalesce(error, ?), finished_at=coalesce(finished_at, ?)
            where id=? and status in ('queued','running','cancelling')
            """,
            (message, now, run_id),
        )
        connection.execute(
            """
            update data_sync_items
            set status='cancelled', error=coalesce(error, ?),
                finished_at=coalesce(finished_at, ?)
            where run_id=? and status in ('queued','running','checking','cancelling')
            """,
            (message, now, run_id),
        )
    return sync_run(run_id) or {}


def prepare_resume(run_id: str) -> dict[str, Any]:
    item = sync_run(run_id)
    if not item:
        raise KeyError("Data sync run not found.")
    incomplete_items = [
        entry
        for entry in item.get("items") or []
        if entry.get("checkpoint")
        and not _checkpoint_complete(entry)
    ]
    if item["status"] not in {"failed", "cancelled", "partial", "paused"} and not incomplete_items:
        raise ValueError("Only failed, cancelled, partial, or paused data updates can be resumed.")
    summary = dict(item.get("summary") or {})
    summary["resumeBaseMode"] = summary.get("resumeBaseMode") or item.get("mode") or "incremental"
    refresh_completed_catalogs = summary["resumeBaseMode"] == "incremental"
    with db() as connection:
        active = connection.execute("select id from data_sync_runs where id<>? and status in ('queued','running','cancelling') limit 1", (run_id,)).fetchone()
        if active:
            raise ValueError("Another full database update is active.")
        connection.execute(
            """
            update data_sync_runs
            set status='queued', mode='resume_checkpoint', cancel_requested=0,
                summary_json=?, error=null, started_at=null, finished_at=null
            where id=?
            """,
            (json_dump(summary), run_id),
        )
        connection.execute(
            """
            update data_sync_items
            set status='queued', error=null, finished_at=null
            where run_id=? and status='cancelled'
            """,
            (run_id,),
        )
        connection.execute(
            """
            update data_sync_items
            set status='queued', failed=0, error=null,
                started_at=null, finished_at=null
            where run_id=? and status='paused'
            """,
            (run_id,),
        )
        for entry in incomplete_items:
            connection.execute(
                """
                update data_sync_items
                set status='queued', failed=0, error=null,
                    started_at=null, finished_at=null
                where run_id=? and dataset_key=?
                """,
                (run_id, entry["dataset_key"]),
            )
        reset_items = [
            entry
            for entry in item.get("items") or []
            if (
                entry.get("status") == "failed"
                and not (
                    entry.get("dataset_key") == "daily"
                    and entry.get("checkpoint")
                    and (
                        int(entry.get("failed") or 0) == 0
                        or _mysql_infrastructure_failure(RuntimeError(str(entry.get("error") or "")))
                    )
                )
            )
            or (entry.get("status") == "partial" and not _checkpoint_complete(entry))
            or (
                entry.get("dataset_key") == "daily"
                and int(entry.get("failed") or 0) > 0
                and not (
                    entry.get("checkpoint")
                    and _mysql_infrastructure_failure(RuntimeError(str(entry.get("error") or "")))
                )
            )
        ]
        for entry in reset_items:
            if entry.get("dataset_key") == "adj_factor":
                connection.execute(
                    """
                    update data_sync_items
                    set status='queued', failed=0, error=null,
                        started_at=null, finished_at=null
                    where run_id=? and dataset_key=?
                    """,
                    (run_id, entry["dataset_key"]),
                )
            elif entry.get("dataset_key") == "suspend_d":
                spec = next(item for item in DATASET_REGISTRY if item.key == "suspend_d")
                retry_count = len(_open_sync_failure_instruments(spec))
                if retry_count:
                    connection.execute(
                        """
                        update data_sync_items
                        set status='queued', processed=0, inserted=0, updated=0, failed=0,
                            checkpoint_json=?, metrics_json=null, error=null,
                            started_at=null, finished_at=null
                        where run_id=? and dataset_key=?
                        """,
                        (
                            json_dump({"index": 0, "total": retry_count, "retryFailedOnly": True}),
                            run_id,
                            entry["dataset_key"],
                        ),
                    )
                else:
                    connection.execute(
                        """
                        update data_sync_items
                        set status='queued', processed=0, inserted=0, updated=0, failed=0,
                            checkpoint_json=null, metrics_json=null, error=null,
                            started_at=null, finished_at=null
                        where run_id=? and dataset_key=?
                        """,
                        (run_id, entry["dataset_key"]),
                    )
            else:
                connection.execute(
                    """
                    update data_sync_items
                    set status='queued', processed=0, inserted=0, updated=0, failed=0,
                        checkpoint_json=null, metrics_json=null, error=null,
                        started_at=null, finished_at=null
                    where run_id=? and dataset_key=?
                    """,
                    (run_id, entry["dataset_key"]),
                )
        if refresh_completed_catalogs:
            specs = {spec.key: spec for spec in DATASET_REGISTRY}
            refresh_keys = [
                str(entry["dataset_key"])
                for entry in item.get("items") or []
                if entry.get("status") in {"success", "partial"}
                and _checkpoint_complete(entry)
                and (
                    specs.get(str(entry["dataset_key"])).date_field
                    or specs.get(str(entry["dataset_key"])).catalog_date_field
                )
            ]
            for dataset_key in refresh_keys:
                connection.execute(
                    """
                    update data_sync_items
                    set status='queued',processed=0,inserted=0,updated=0,failed=0,
                        checkpoint_json=null,metrics_json=null,error=null,
                        started_at=null,finished_at=null
                    where run_id=? and dataset_key=?
                    """,
                    (run_id, dataset_key),
                )
                # Persistent work items belong to the previous cutoff. A
                # resumed incremental run must rebuild its work list so newly
                # opened trade dates are not mistaken for completed work.
                connection.execute(
                    "delete from data_sync_work_items where run_id=? and dataset_key=?",
                    (run_id, dataset_key),
                )
    return sync_run(run_id) or {}
