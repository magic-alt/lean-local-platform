from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import shutil
import time
import uuid
from typing import Any, Callable, TypeVar

from ..db import bulk_db, database_backend, db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..research.factors import upsert_factor_values
from .ashare_repository import (
    import_security_master,
    upsert_adjustment_factors,
    upsert_corporate_actions,
    upsert_index_weights,
    upsert_trade_status,
)
from .data import import_ashare_research_data
from .pit_data import import_financial_statements
from .tushare_adapter import TushareAdapter
from .tushare_rate_limit import DEFAULT_CALLS_PER_MINUTE


T = TypeVar("T")


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


# Versioned low-frequency registry for the local 5,000-point TuShare entitlement.
# A successful probe is authoritative because some endpoints require separate grants.
DATASET_REGISTRY: tuple[DatasetSpec, ...] = (
    DatasetSpec("stock_basic", "stock_basic", "A股/基础", probe={"list_status": "L"}, key_fields=("ts_code",), normalizer="stock_basic"),
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
    DatasetSpec("index_basic", "index_basic", "指数", probe={"market": "SSE"}, key_fields=("ts_code",)),
    DatasetSpec("index_daily", "index_daily", "指数", "window", probe={"ts_code": "000300.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("index_weight", "index_weight", "指数", "window", "monthly", {"index_code": "000300.SH", "start_date": "20260101", "end_date": "20260331"}, ("index_code", "con_code", "trade_date"), "trade_date", normalizer="index_weight"),
    DatasetSpec("fund_basic", "fund_basic", "基金", probe={"market": "E"}, key_fields=("ts_code",)),
    DatasetSpec("fund_daily", "fund_daily", "基金", "window", probe={"trade_date": "20260109"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("fund_nav", "fund_nav", "基金", "window", probe={"nav_date": "20260109"}, key_fields=("ts_code", "nav_date", "end_date", "ann_date"), date_field="nav_date"),
    DatasetSpec("fund_portfolio", "fund_portfolio", "基金", "window", "quarterly", {"ann_date": "20260331"}, ("ts_code", "symbol", "end_date", "ann_date"), "ann_date"),
    DatasetSpec("cb_basic", "cb_basic", "可转债", probe={}, key_fields=("ts_code",)),
    DatasetSpec("cb_daily", "cb_daily", "可转债", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("cb_call", "cb_call", "可转债", "window", probe={"ann_date": "20260110"}, key_fields=("ts_code", "ann_date", "call_type"), date_field="ann_date"),
    DatasetSpec("fut_basic", "fut_basic", "期货", probe={"exchange": "CFFEX"}, key_fields=("ts_code",)),
    DatasetSpec("fut_daily", "fut_daily", "期货", "window", probe={"trade_date": "20260109"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("fut_mapping", "fut_mapping", "期货", "window", probe={"trade_date": "20260109"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("opt_basic", "opt_basic", "期权", probe={"exchange": "SSE"}, key_fields=("ts_code",)),
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
    "suspend_d",
    "stk_limit",
    "index_basic",
    "index_daily",
    "fut_basic",
    "opt_basic",
}
DATASET_REGISTRY = tuple(
    replace(
        spec,
        sync_policy="on_demand" if spec.key not in BULK_DATASET_KEYS else "bulk",
        retain_raw=False if spec.key in {"adj_factor", "daily_basic"} else spec.retain_raw,
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
    return {
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
    }


def ensure_catalog() -> None:
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
    items = rows_to_dicts(rows)
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
    }


def _query(pro: Any, spec: DatasetSpec, params: dict[str, Any]) -> list[dict[str, Any]]:
    if hasattr(pro, "query"):
        return _records(pro.query(spec.api_name, **params))
    return _records(getattr(pro, spec.api_name)(**params))


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
        values = [json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)]
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


def _save_raw(
    spec: DatasetSpec,
    rows: list[dict[str, Any]],
    batch_id: str,
    *,
    assume_new: bool = False,
) -> tuple[int, int]:
    now = utc_now()
    prepared: dict[str, tuple[Any, ...]] = {}
    digests: dict[str, str] = {}
    for raw in rows:
        row = {key: (value.item() if hasattr(value, "item") else value) for key, value in raw.items()}
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        key = _record_key(spec, row)
        instrument = (str(row.get(spec.instrument_field) or "") or None) if spec.instrument_field else None
        prepared[key] = (
            "tushare",
            spec.key,
            key,
            _iso(row.get(spec.date_field)) if spec.date_field else None,
            instrument,
            payload,
            digest,
            batch_id,
            row.get("update_time") or row.get("ann_date"),
            now,
        )
        digests[key] = digest
    if not prepared:
        return 0, 0

    _assert_disk_capacity(sum(len(str(value[5]).encode("utf-8")) for value in prepared.values()) * 3)

    with bulk_db() as connection:
        existing: dict[str, str] = {}
        keys = list(prepared)
        if not assume_new:
            lookup_size = 4000 if database_backend() == "mysql" else 500
            for offset in range(0, len(keys), lookup_size):
                chunk = keys[offset : offset + lookup_size]
                placeholders = ",".join("?" for _ in chunk)
                records = connection.execute(
                    f"""
                    select record_key, content_sha256 from provider_raw_records
                    where provider='tushare' and dataset_key=? and record_key in ({placeholders})
                    """,
                    [spec.key, *chunk],
                ).fetchall()
                existing.update({str(record["record_key"]): str(record["content_sha256"]) for record in records})

        changed_keys = [key for key in keys if existing.get(key) != digests[key]]
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
            from ashare_daily_bars
            where source in ('test', 'manual', 'csv')
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


def _item(run_id: str, dataset: str, **fields: Any) -> None:
    checkpoint = fields.pop("checkpoint", None)
    metrics = fields.pop("metrics", None)
    if metrics is not None:
        fields["metrics_json"] = json_dump(metrics)
    if checkpoint is not None:
        with db() as connection:
            existing_row = connection.execute(
                "select * from data_sync_items where run_id=? and dataset_key=?",
                (run_id, dataset),
            ).fetchone()
        existing = row_to_dict(existing_row) or {}
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


def _disk_metrics() -> dict[str, Any]:
    path = os.environ.get("LEAN_DATA_SYNC_SPOOL_DIR") or str(os.environ.get("LEAN_RUNTIME_DIR") or "/tmp")
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        usage = shutil.disk_usage("/")
    metrics = {
        "diskFreeBytes": usage.free,
        "diskTotalBytes": usage.total,
        "diskFreePercent": round(usage.free * 100 / max(usage.total, 1), 2),
    }
    metrics.update(_database_storage_metrics())
    return metrics


_DATABASE_SIZE_CACHE: tuple[float, dict[str, Any]] = (0.0, {})


def _database_storage_metrics() -> dict[str, Any]:
    global _DATABASE_SIZE_CACHE
    limit = int(float(os.environ.get("LEAN_MYSQL_MAX_DATABASE_GB", "50")) * 1024**3)
    if database_backend() != "mysql":
        return {"databaseBytes": 0, "databaseLimitBytes": limit, "databaseUsagePercent": 0.0}
    checked_at, cached = _DATABASE_SIZE_CACHE
    if cached and time.monotonic() - checked_at < 30:
        return cached
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
    database_bytes = int(row["table_bytes"] or 0) + binlog_bytes + 2 * 1024**3
    result = {
        "databaseBytes": database_bytes,
        "databaseLimitBytes": limit,
        "databaseUsagePercent": round(database_bytes * 100 / max(limit, 1), 2),
    }
    _DATABASE_SIZE_CACHE = (time.monotonic(), result)
    return result


def _assert_disk_capacity(estimated_write_bytes: int = 0) -> None:
    metrics = _disk_metrics()
    free = int(metrics["diskFreeBytes"])
    total = int(metrics["diskTotalBytes"])
    hard_reserve = max(20 * 1024**3, int(total * 0.10))
    database_bytes = int(metrics.get("databaseBytes") or 0)
    database_limit = int(metrics.get("databaseLimitBytes") or 0)
    if database_limit and database_bytes + max(0, estimated_write_bytes) > database_limit:
        raise RuntimeError(
            "data_sync_database_guard: local MySQL 50GB cache limit reached; "
            f"database={database_bytes}, estimatedWrite={estimated_write_bytes}, limit={database_limit}. "
            "Use on-demand retrieval or move LEAN_MYSQL_DATA_DIR to external storage."
        )
    if free - max(0, estimated_write_bytes) < hard_reserve:
        raise RuntimeError(
            "data_sync_disk_guard: insufficient free space; "
            f"free={free}, estimatedWrite={estimated_write_bytes}, reserve={hard_reserve}"
        )


def _throughput_metrics(
    started: float,
    *,
    phase: str,
    api_calls: int,
    downloaded: int,
    committed: int,
    queue_depth: int = 0,
) -> dict[str, Any]:
    elapsed = max(0.001, time.monotonic() - started)
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
        "elapsedSeconds": round(elapsed, 2),
        **_disk_metrics(),
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
        str(item.get("dataset_key") or "") not in {"daily", "adj_factor"}
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
            "select max(trade_date) as trade_date from ashare_daily_bars where symbol=? and adjust='raw' and source='tushare'",
            (symbol,),
        ).fetchone()
    return str(row["trade_date"]) if row and row["trade_date"] else None


def _latest_bars_by_symbol() -> dict[str, str]:
    with db() as connection:
        rows = connection.execute(
            """
            select symbol,max(trade_date) as trade_date
            from ashare_daily_bars
            where adjust='raw' and source='tushare'
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
    if spec.normalizer == "dividend":
        result.setdefault("ann_date", (row.get("metadata") or {}).get("announce_date") or row.get("ex_date"))
        result.setdefault("end_date", row.get("ex_date"))
        result.setdefault("div_proc", (row.get("metadata") or {}).get("process"))
    elif spec.normalizer == "financial":
        result.setdefault("end_date", row.get("report_date"))
        result.setdefault("ann_date", row.get("announce_date"))
        result.setdefault("report_type", row.get("statement_type"))
    return result


def _sync_stock_basic(adapter: TushareAdapter, batch_id: str) -> tuple[int, int, int]:
    records = adapter.stock_basic(["L", "D", "P"])
    spec = next(item for item in DATASET_REGISTRY if item.key == "stock_basic")
    raw_rows = []
    for item in records:
        raw_rows.append({**item, "ts_code": item.get("ts_code") or item.get("symbol")})
    inserted, updated = _save_raw(spec, raw_rows, batch_id)
    # The endpoint returns the full security master on every request. Avoid
    # thousands of row-by-row master/instrument upserts when its content hash
    # is unchanged; a normal incremental run should complete this dataset in
    # one provider call and no database rewrite.
    if inserted or updated:
        import_security_master(records, source="tushare:stock_basic", universe_code="ALL_A")
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
        return 0, 0, 0
    rows = adapter.trade_calendar(start_date, end_date, exchange="SSE")
    raw = [{**item, "cal_date": str(item.get("trade_date") or "").replace("-", ""), "exchange": "SSE"} for item in rows]
    inserted, updated = _save_raw(spec, raw, batch_id)
    from .ashare_repository import upsert_trade_calendar
    open_dates = [str(item["trade_date"]) for item in rows if item.get("is_open")]
    upsert_trade_calendar("china", open_dates, source="tushare:trade_cal:SSE", batch_id=batch_id)
    return len(rows), inserted, updated


def _sync_daily(
    adapter: TushareAdapter,
    run_id: str,
    batch_id: str,
    end_date: str,
    task_id: str | None = None,
    full_refresh: bool = False,
) -> tuple[int, int, int, int]:
    state = _item_state(run_id, "daily")
    checkpoint = state.get("checkpoint") or {}
    resume_after = max(0, int(checkpoint.get("index") or 0))
    processed = int(state.get("processed") or 0)
    inserted = int(state.get("inserted") or 0)
    updated = int(state.get("updated") or 0)
    failed = int(state.get("failed") or 0)
    securities = _listed_securities()
    latest_by_symbol = {} if full_refresh else _latest_bars_by_symbol()
    started = time.monotonic()
    api_calls = 0
    downloaded = 0
    committed = 0
    concurrency = max(1, min(32, int(os.environ.get("LEAN_TUSHARE_FETCH_CONCURRENCY", "16"))))

    work: list[tuple[int, dict[str, Any], str, str, str]] = []
    for index, security in enumerate(securities, start=1):
        if index <= resume_after:
            continue
        symbol = str(security["symbol"])
        latest = latest_by_symbol.get(symbol)
        start = (date.fromisoformat(latest) + timedelta(days=1)).isoformat() if latest else str(security.get("listed_date") or "1990-01-01")
        delisted_date = str(security.get("delisted_date") or "")
        symbol_end = min(end_date, delisted_date) if delisted_date else end_date
        work.append((index, security, symbol, start, symbol_end))

    def fetch(item: tuple[int, dict[str, Any], str, str, str]) -> list[dict[str, Any]]:
        _, _, symbol, start, symbol_end = item
        if start > symbol_end:
            return []
        try:
            return _call_with_retry(
                lambda: adapter.daily_rows(
                    symbol,
                    start,
                    symbol_end,
                    adjust="raw",
                    include_limits=False,
                    include_adjustments=False,
                    include_index_fallback=False,
                )
            )
        except TypeError:
            return _call_with_retry(lambda: adapter.daily_rows(symbol, start, symbol_end, adjust="raw"))

    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="tushare-daily") as executor:
        pending: dict[int, Any] = {}
        submit_cursor = 0
        while submit_cursor < min(len(work), concurrency * 2):
            item = work[submit_cursor]
            pending[item[0]] = executor.submit(fetch, item)
            submit_cursor += 1

        for index, security, symbol, start, symbol_end in work:
            if _cancelled(run_id, task_id):
                for future in pending.values():
                    future.cancel()
                break
            future = pending.pop(index)
            try:
                rows = future.result()
                api_calls += int(start <= symbol_end)
                downloaded += len(rows)
                if rows:
                    estimated_bytes = sum(
                        len(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
                        for row in rows
                    ) * 10
                    _assert_disk_capacity(estimated_bytes)
                    result = import_ashare_research_data(
                        symbol=symbol, provider="tushare", market="china", rows=rows,
                        source="tushare", overwrite=True, adjust="raw", outputsize="full",
                        asset_class="equity", venue="china", resolution="daily", data_type="trade",
                        start_date=start, end_date=symbol_end,
                        repair_ohlc_errors=True,
                        infer_suspensions_from_authoritative_absence=True,
                    )
                    inserted += int(result.get("rows") or len(rows))
                    committed += int(result.get("rows") or len(rows))
                    with db() as connection:
                        connection.execute(
                            """
                            update data_record_issues
                            set status='resolved', resolved_at=?, resolution_batch_id=?
                            where dataset_key='daily' and instrument_code=? and status='open'
                              and issue_code in ('untrusted_source','sync_failed')
                            """,
                            (utc_now(), str(result.get("batch_id") or batch_id), symbol),
                        )
            except Exception as exc:  # noqa: BLE001
                failed += 1
                with db() as connection:
                    connection.execute(
                        """
                        insert into data_record_issues
                            (id,dataset_key,source,instrument_code,start_date,end_date,issue_code,severity,status,details_json,detected_at)
                        values (?, 'daily', 'tushare', ?, ?, ?, 'sync_failed', 'error', 'open', ?, ?)
                        """,
                        (str(uuid.uuid4()), symbol, start, symbol_end, json_dump({"error": str(exc)}), utc_now()),
                    )
            processed += 1
            if submit_cursor < len(work):
                next_item = work[submit_cursor]
                pending[next_item[0]] = executor.submit(fetch, next_item)
                submit_cursor += 1
            if not _current_task(run_id, task_id):
                break
            _item(
                run_id,
                "daily",
                processed=processed,
                inserted=inserted,
                failed=failed,
                checkpoint={"symbol": symbol, "index": index, "total": len(securities)},
                metrics=_throughput_metrics(
                    started,
                    phase="load",
                    api_calls=api_calls,
                    downloaded=downloaded,
                    committed=committed,
                    queue_depth=len(pending),
                ),
            )
    return processed, inserted, updated, failed


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
    elif spec.normalizer == "daily_basic":
        factors = []
        for row in rows:
            for name, value in (row.get("factors") or {}).items():
                if value is not None:
                    factors.append({"symbol": row["symbol"], "trade_date": row["trade_date"], "factor_name": name, "value": value})
        if factors:
            upsert_factor_values(
                factors,
                source="tushare:daily_basic",
                batch_id=batch_id,
                bulk=bulk,
            )
    elif spec.normalizer == "dividend":
        upsert_corporate_actions(rows, source="tushare:dividend", batch_id=batch_id)
    elif spec.normalizer == "financial":
        import_financial_statements(rows, source=f"tushare:{spec.api_name}")
    elif spec.normalizer == "index_weight":
        upsert_index_weights(rows, source="tushare:index_weight", batch_id=batch_id)
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
            upsert_trade_status(statuses, source="tushare:suspend_d", batch_id=batch_id)
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
            upsert_trade_status(statuses, source="tushare:stk_limit", batch_id=batch_id)


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
    if rows:
        upsert_adjustment_factors(rows, source="tushare", batch_id=batch_id, bulk=True)
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
) -> tuple[int, int, int, int]:
    """Concurrent provider reads with one sequential, chunked database writer."""
    if not full_refresh and _latest_raw_date(spec) is None:
        full_refresh = True
    state = _item_state(run_id, spec.key)
    checkpoint = state.get("checkpoint") or {}
    legacy_resume = max(0, int(checkpoint.get("index") or 0))
    processed = int(state.get("processed") or 0)
    inserted = int(state.get("inserted") or 0)
    updated = int(state.get("updated") or 0)
    failed = int(state.get("failed") or 0)
    started = time.monotonic()
    api_calls = 0
    downloaded = 0
    committed = 0
    chunk_rows = max(10_000, int(os.environ.get("LEAN_DATA_SYNC_CHUNK_ROWS", "100000")))
    concurrency = max(1, min(32, int(os.environ.get("LEAN_TUSHARE_FETCH_CONCURRENCY", "16"))))

    if not full_refresh:
        latest = _latest_raw_date(spec)
        with db() as connection:
            dates = connection.execute(
                """
                select trade_date from trade_calendar
                where market='china' and is_open=1 and trade_date>? and trade_date<=?
                order by trade_date
                """,
                (latest or "1990-01-01", end_date),
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
        existing_statuses = _work_status(run_id, spec.key)
        work = [
            (str(item["symbol"]), index)
            for index, item in enumerate(securities, start=1)
            if existing_statuses or index > legacy_resume
        ]
        listed_dates = {str(item["symbol"]): str(item.get("listed_date") or "1990-01-01") for item in securities}
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

    if not pending:
        return processed, inserted, updated, failed

    entries: list[tuple[str, list[dict[str, Any]]]] = []
    buffered_rows = 0
    failure_samples: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal entries, buffered_rows, inserted, updated, processed, committed
        if not entries:
            return
        estimated_bytes = sum(
            len(json.dumps(row, ensure_ascii=False, default=str).encode("utf-8"))
            for _, values in entries
            for row in values
        ) * 3
        _assert_disk_capacity(estimated_bytes)
        add, change, written, counts = _flush_adj_factor_batch(spec, batch_id, entries)
        keys = [key for key, _ in entries]
        _mark_work_items(run_id, spec.key, keys, status="committed", row_counts=counts)
        for key in keys:
            _resolve_sync_failure(spec, key if full_refresh else None, batch_id)
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
            ),
        )
        entries = []
        buffered_rows = 0

    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="tushare-adj") as executor:
        futures = {executor.submit(fetcher, key): key for key, _ in pending}
        for future in as_completed(futures):
            key = futures[future]
            api_calls += 1
            if _cancelled(run_id, task_id):
                for pending_future in futures:
                    pending_future.cancel()
                break
            try:
                rows = future.result()
                downloaded += len(rows)
                entries.append((key, rows))
                buffered_rows += len(rows)
                if buffered_rows >= chunk_rows or len(entries) >= concurrency * 2:
                    flush()
            except Exception as exc:  # noqa: BLE001
                failed += 1
                sample = _record_sync_failure(spec, key if full_refresh else None, key, end_date, exc)
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
                    ),
                )
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
        )
    state = _item_state(run_id, spec.key)
    checkpoint = state.get("checkpoint") or {}
    resume_after = max(0, int(checkpoint.get("index") or 0))
    processed = int(state.get("processed") or 0)
    inserted = int(state.get("inserted") or 0)
    updated = int(state.get("updated") or 0)
    failed = int(state.get("failed") or 0)
    failure_samples: list[dict[str, Any]] = []
    symbols = _listed_securities() if spec.scope == "instrument" else [None]
    latest_by_instrument = _latest_raw_dates_by_instrument(spec) if spec.scope == "instrument" else {}
    global_latest = _latest_raw_date(spec) if spec.scope != "instrument" else None
    for index, item in enumerate(symbols, start=1):
        if index <= resume_after:
            continue
        if _cancelled(run_id, task_id):
            break
        symbol = str(item["symbol"]) if item else None
        persisted_latest = latest_by_instrument.get(symbol) if symbol else global_latest
        latest = None if full_refresh else persisted_latest
        initial_start = str(item.get("listed_date") or "1990-01-01") if item else "1990-01-01"
        start = (date.fromisoformat(latest) + timedelta(days=1)).isoformat() if latest else initial_start
        try:
            if spec.date_field and start > end_date:
                rows = []
            elif spec.normalizer == "index_weight":
                normalized = _call_with_retry(lambda: adapter.index_weight_rows("000300", start, end_date))
                rows = normalized
            else:
                if symbol:
                    normalized = _call_with_retry(lambda: _normalized_rows(adapter, spec, symbol, start, end_date))
                else:
                    normalized = None
                rows = normalized if normalized is not None else _call_with_retry(
                    lambda: _query(
                        adapter.pro,
                        spec,
                        _generic_params(spec, start, end_date, symbol),
                    )
                )
            raw_rows = [_raw_row_for_symbol(spec, row, symbol) for row in rows]
            add, change = _save_raw(
                spec,
                raw_rows,
                batch_id,
                assume_new=persisted_latest is None,
            )
            _normalize_optional(spec, rows, batch_id)
            _resolve_sync_failure(spec, symbol, batch_id)
            inserted += add
            updated += change
        except Exception as exc:  # noqa: BLE001 - continue other instruments, but persist the cause
            failed += 1
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
        )
        if spec.scope == "instrument":
            time.sleep(0.03)
    return processed, inserted, updated, failed


def _set_catalog_coverage(spec: DatasetSpec) -> None:
    with db() as connection:
        if spec.key == "daily":
            aggregate = connection.execute(
                """
                select count(*) as count, min(trade_date) as first_date, max(trade_date) as last_date
                from ashare_daily_bars
                where source='tushare' and adjust='raw'
                """
            ).fetchone()
        elif spec.key == "adj_factor":
            aggregate = connection.execute(
                """
                select count(*) as count, min(trade_date) as first_date, max(trade_date) as last_date
                from adjustment_factors where source='tushare'
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


def run_sync(
    run_id: str,
    *,
    adapter: TushareAdapter | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    batch_id = run_id
    end_date = date.today().isoformat()
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
                "update data_sync_runs set status='running', started_at=coalesce(started_at,?), error=null where id=? and task_id=?",
                (utc_now(), run_id, task_id),
            )
        else:
            connection.execute(
                "update data_sync_runs set status='running', started_at=coalesce(started_at,?), error=null where id=?",
                (utc_now(), run_id),
            )
        run_row = connection.execute("select * from data_sync_runs where id=?", (run_id,)).fetchone()
    run_record = row_to_dict(run_row) or {}
    adapter = adapter or TushareAdapter()
    selected_keys = set(run_record.get("requestedDatasets") or [spec.key for spec in DATASET_REGISTRY])
    sync_mode = str(run_record.get("mode") or "incremental")
    resume_base_mode = str((run_record.get("summary") or {}).get("resumeBaseMode") or "")
    full_refresh = sync_mode in {"initial_full", "full_rebuild"} or resume_base_mode in {"initial_full", "full_rebuild"}
    try:
        audit = audit_existing_data()
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
            if spec.sync_policy == "on_demand":
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
            try:
                if spec.key == "stock_basic":
                    values = _sync_stock_basic(adapter, batch_id)
                    result = (*values, 0)
                elif spec.key == "trade_cal":
                    values = _sync_calendar(adapter, batch_id, end_date, full_refresh=full_refresh)
                    result = (*values, 0)
                elif spec.key == "daily":
                    result = _sync_daily(
                        adapter,
                        run_id,
                        batch_id,
                        market_end_date,
                        task_id,
                        full_refresh=full_refresh,
                    )
                else:
                    dataset_end_date = (
                        market_end_date
                        if spec.key in {"adj_factor", "suspend_d", "stk_limit", "index_daily"}
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
                    )
                processed, inserted, updated, failed = result
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
                _item(run_id, spec.key, status=status, processed=processed, inserted=inserted, updated=updated, failed=failed, finished_at=utc_now())
                _set_catalog_coverage(spec)
                summaries[spec.key] = {"processed": processed, "inserted": inserted, "updated": updated, "failed": failed}
            except Exception as exc:  # noqa: BLE001
                _item(run_id, spec.key, status="failed", failed=1, error=str(exc), finished_at=utc_now())
                summaries[spec.key] = {"error": str(exc)}
        cancelled = _cancelled(run_id, task_id)
        degraded = any(item.get("error") or int(item.get("failed") or 0) > 0 for item in summaries.values())
        final_status = "cancelled" if cancelled else "partial" if degraded else "success"
        summary = {
            "status": final_status, "permissions": permissions, "audit": audit,
            "datasets": summaries, "endDate": end_date, "marketDataEndDate": market_end_date, "cancelled": cancelled,
            "mode": sync_mode, "resumeBaseMode": resume_base_mode or None,
        }
        with db() as connection:
            if task_id:
                connection.execute(
                    "update data_sync_runs set status=?, summary_json=?, finished_at=? where id=? and task_id=?",
                    (final_status, json_dump(summary), utc_now(), run_id, task_id),
                )
            else:
                connection.execute(
                    "update data_sync_runs set status=?, summary_json=?, finished_at=? where id=?",
                    (final_status, json_dump(summary), utc_now(), run_id),
                )
        return summary
    except Exception as exc:
        with db() as connection:
            if task_id:
                connection.execute(
                    "update data_sync_runs set status='failed', error=?, finished_at=? where id=? and task_id=?",
                    (str(exc), utc_now(), run_id, task_id),
                )
            else:
                connection.execute(
                    "update data_sync_runs set status='failed', error=?, finished_at=? where id=?",
                    (str(exc), utc_now(), run_id),
                )
        raise


def create_sync_run(*, requested: list[str] | None = None, mode: str = "auto") -> dict[str, Any]:
    ensure_catalog()
    if mode not in {"auto", "incremental", "full_rebuild"}:
        raise ValueError("Data sync mode must be auto, incremental, or full_rebuild.")
    with db() as connection:
        active = connection.execute(
            "select * from data_sync_runs where status in ('queued','running','cancelling') order by created_at desc limit 1"
        ).fetchone()
        if active:
            raise ValueError("A full database update is already queued or running.")
        existing = connection.execute(
            """
            select
                (select count(*) from ashare_daily_bars) +
                (select count(*) from provider_raw_records) as row_count
            """
        ).fetchone()
    resolved_mode = mode
    if mode == "auto":
        resolved_mode = "incremental" if existing and int(existing["row_count"] or 0) > 0 else "initial_full"
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
    if on_demand_requested:
        raise ValueError(
            "On-demand datasets cannot be included in a full database update: "
            + ", ".join(on_demand_requested)
        )
    with db() as connection:
        connection.execute(
            """
            insert into data_sync_runs
                (id,provider,mode,scope,status,requested_datasets_json,created_at)
            values (?,'tushare',?,'all_entitled_low_frequency','queued',?,?)
            """,
            (run_id, resolved_mode, json_dump([item.key for item in selected]), now),
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
        result["items"] = rows_to_dicts(items)
    return result


def list_sync_runs(limit: int = 20) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute("select * from data_sync_runs order by created_at desc limit ?", (max(1, min(limit, 100)),)).fetchall()
    return rows_to_dicts(rows)


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
    if item["status"] not in {"failed", "cancelled", "partial"} and not incomplete_items:
        raise ValueError("Only failed or cancelled data updates can be resumed.")
    summary = dict(item.get("summary") or {})
    summary["resumeBaseMode"] = summary.get("resumeBaseMode") or item.get("mode") or "incremental"
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
        for entry in incomplete_items:
            connection.execute(
                """
                update data_sync_items
                set status='queued', error=null, finished_at=null
                where run_id=? and dataset_key=?
                """,
                (run_id, entry["dataset_key"]),
            )
        reset_items = [
            entry
            for entry in item.get("items") or []
            if entry.get("status") == "failed"
            or (entry.get("status") == "partial" and not _checkpoint_complete(entry))
            or (entry.get("dataset_key") == "daily" and int(entry.get("failed") or 0) > 0)
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
    return sync_run(run_id) or {}
