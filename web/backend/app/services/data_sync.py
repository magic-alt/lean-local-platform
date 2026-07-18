from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import time
import uuid
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..research.factors import upsert_factor_values
from .ashare_repository import (
    import_security_master,
    upsert_corporate_actions,
    upsert_index_weights,
)
from .data import import_ashare_research_data
from .pit_data import import_financial_statements
from .tushare_adapter import TushareAdapter


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


# Versioned low-frequency registry for the local 5,000-point TuShare entitlement.
# A successful probe is authoritative because some endpoints require separate grants.
DATASET_REGISTRY: tuple[DatasetSpec, ...] = (
    DatasetSpec("stock_basic", "stock_basic", "A股/基础", probe={"list_status": "L"}, key_fields=("ts_code",), normalizer="stock_basic"),
    DatasetSpec("trade_cal", "trade_cal", "A股/基础", probe={"exchange": "SSE", "start_date": "20260101", "end_date": "20260110"}, key_fields=("exchange", "cal_date"), date_field="cal_date", normalizer="trade_cal"),
    DatasetSpec("daily", "daily", "A股/行情", "instrument", probe={"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date", normalizer="daily"),
    DatasetSpec("adj_factor", "adj_factor", "A股/行情", "instrument", probe={"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("daily_basic", "daily_basic", "A股/行情", "instrument", probe={"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date", normalizer="daily_basic"),
    DatasetSpec("suspend_d", "suspend_d", "A股/交易状态", "instrument", probe={"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "suspend_date", "suspend_timing"), date_field="suspend_date"),
    DatasetSpec("stk_limit", "stk_limit", "A股/交易状态", "instrument", probe={"ts_code": "600519.SH", "start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
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
    DatasetSpec("fund_daily", "fund_daily", "基金", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("fund_nav", "fund_nav", "基金", "window", probe={"end_date": "20260110"}, key_fields=("ts_code", "end_date", "ann_date"), date_field="end_date"),
    DatasetSpec("fund_portfolio", "fund_portfolio", "基金", "window", "quarterly", {"ann_date": "20260331"}, ("ts_code", "symbol", "end_date", "ann_date"), "ann_date"),
    DatasetSpec("cb_basic", "cb_basic", "可转债", probe={}, key_fields=("ts_code",)),
    DatasetSpec("cb_daily", "cb_daily", "可转债", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("cb_call", "cb_call", "可转债", "window", probe={"ann_date": "20260110"}, key_fields=("ts_code", "ann_date", "call_type"), date_field="ann_date"),
    DatasetSpec("fut_basic", "fut_basic", "期货", probe={"exchange": "DCE"}, key_fields=("ts_code",)),
    DatasetSpec("fut_daily", "fut_daily", "期货", "window", probe={"trade_date": "20260109"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("fut_mapping", "fut_mapping", "期货", "window", probe={"trade_date": "20260109"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("opt_basic", "opt_basic", "期权", probe={"exchange": "SSE"}, key_fields=("ts_code",)),
    DatasetSpec("opt_daily", "opt_daily", "期权", "window", probe={"trade_date": "20260109"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("hk_basic", "hk_basic", "港股", probe={"list_status": "L"}, key_fields=("ts_code",)),
    DatasetSpec("hk_daily", "hk_daily", "港股", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("us_basic", "us_basic", "美股", probe={}, key_fields=("ts_code",)),
    DatasetSpec("us_daily", "us_daily", "美股", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("fx_obasic", "fx_obasic", "外汇", probe={}, key_fields=("ts_code",)),
    DatasetSpec("fx_daily", "fx_daily", "外汇", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("ts_code", "trade_date"), date_field="trade_date"),
    DatasetSpec("shibor", "shibor", "宏观", "window", probe={"start_date": "20260101", "end_date": "20260110"}, key_fields=("date",), date_field="date"),
    DatasetSpec("lpr", "lpr", "宏观", "window", "monthly", {"start_date": "20250101", "end_date": "20261231"}, ("date",), "date"),
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
    if any(token in lowered for token in ("频率", "rate", "too many", "timeout", "temporar", "connection")):
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
    }


def ensure_catalog() -> None:
    with db() as connection:
        for spec in DATASET_REGISTRY:
            connection.execute(
                """
                insert into provider_dataset_catalog
                    (provider, dataset_key, api_name, category, scope_type, cadence,
                     permission_status, row_count, metadata_json)
                values ('tushare', ?, ?, ?, ?, ?, 'unknown', 0, ?)
                on conflict(provider, dataset_key) do update set
                    api_name = excluded.api_name,
                    category = excluded.category,
                    scope_type = excluded.scope_type,
                    cadence = excluded.cadence,
                    metadata_json = excluded.metadata_json
                """,
                (spec.key, spec.api_name, spec.category, spec.scope, spec.cadence, json_dump(_catalog_metadata(spec))),
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
    items = rows_to_dicts(rows)
    return {
        "provider": "tushare",
        "entitlementPoints": 5000,
        "boundary": "low_frequency",
        "items": items,
        "count": len(items),
        "available": sum(item.get("permission_status") in {"available", "empty"} for item in items),
        "activeRun": row_to_dict(active),
    }


def _query(pro: Any, spec: DatasetSpec, params: dict[str, Any]) -> list[dict[str, Any]]:
    if hasattr(pro, "query"):
        return _records(pro.query(spec.api_name, **params))
    return _records(getattr(pro, spec.api_name)(**params))


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


def _record_key(spec: DatasetSpec, row: dict[str, Any]) -> str:
    values = [str(row.get(field) or "") for field in spec.key_fields]
    if not values or not any(values):
        values = [json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)]
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


def _save_raw(spec: DatasetSpec, rows: list[dict[str, Any]], batch_id: str) -> tuple[int, int]:
    inserted = 0
    updated = 0
    now = utc_now()
    with db() as connection:
        for raw in rows:
            row = {key: (value.item() if hasattr(value, "item") else value) for key, value in raw.items()}
            payload = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
            digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            key = _record_key(spec, row)
            existing = connection.execute(
                "select content_sha256 from provider_raw_records where provider='tushare' and dataset_key=? and record_key=?",
                (spec.key, key),
            ).fetchone()
            if existing and existing["content_sha256"] == digest:
                continue
            connection.execute(
                """
                insert into provider_raw_records
                    (provider, dataset_key, record_key, business_date, instrument_code,
                     payload_json, content_sha256, batch_id, source_updated_at, ingested_at)
                values ('tushare', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(provider, dataset_key, record_key) do update set
                    business_date=excluded.business_date,
                    instrument_code=excluded.instrument_code,
                    payload_json=excluded.payload_json,
                    content_sha256=excluded.content_sha256,
                    batch_id=excluded.batch_id,
                    source_updated_at=excluded.source_updated_at,
                    ingested_at=excluded.ingested_at
                """,
                (
                    spec.key, key, _iso(row.get(spec.date_field)) if spec.date_field else None,
                    str(row.get(spec.instrument_field) or "") or None if spec.instrument_field else None,
                    payload, digest, batch_id, row.get("update_time") or row.get("ann_date"), now,
                ),
            )
            if existing:
                updated += 1
            else:
                inserted += 1
    return inserted, updated


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


def _item_state(run_id: str, dataset: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute(
            "select * from data_sync_items where run_id=? and dataset_key=?",
            (run_id, dataset),
        ).fetchone()
    return row_to_dict(row) or {}


def _listed_securities() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select symbol, listed_date, status from securities where status in ('listed','delisted','pending') order by symbol"
        ).fetchall()
    return rows_to_dicts(rows)


def _latest_bar(symbol: str) -> str | None:
    with db() as connection:
        row = connection.execute(
            "select max(trade_date) as trade_date from ashare_daily_bars where symbol=? and adjust='raw' and source='tushare'",
            (symbol,),
        ).fetchone()
    return str(row["trade_date"]) if row and row["trade_date"] else None


def _latest_raw_date(spec: DatasetSpec, symbol: str | None = None) -> str | None:
    with db() as connection:
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
    imported = import_security_master(records, source="tushare:stock_basic", universe_code="ALL_A")
    return len(records), inserted, updated + int(imported.get("count") or 0)


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
    for index, security in enumerate(securities, start=1):
        if index <= resume_after:
            continue
        if _cancelled(run_id, task_id):
            break
        symbol = str(security["symbol"])
        latest = None if full_refresh else _latest_bar(symbol)
        start = (date.fromisoformat(latest) + timedelta(days=1)).isoformat() if latest else str(security.get("listed_date") or "1990-01-01")
        if start <= end_date:
            try:
                rows = adapter.daily_rows(symbol, start, end_date, adjust="raw")
                if rows:
                    result = import_ashare_research_data(
                        symbol=symbol, provider="tushare", market="china", rows=rows,
                        source="tushare", overwrite=True, adjust="raw", outputsize="full",
                        asset_class="equity", venue="china", resolution="daily", data_type="trade",
                        start_date=start, end_date=end_date,
                        repair_ohlc_errors=True,
                    )
                    inserted += int(result.get("rows") or len(rows))
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
                        (str(uuid.uuid4()), symbol, start, end_date, json_dump({"error": str(exc)}), utc_now()),
                    )
        processed += 1
        _item(run_id, "daily", processed=processed, inserted=inserted, failed=failed, checkpoint={"symbol": symbol, "index": index, "total": len(securities)})
        time.sleep(0.05)
    return processed, inserted, updated, failed


def _generic_params(
    spec: DatasetSpec,
    start_date: str,
    end_date: str,
    symbol: str | None = None,
) -> dict[str, Any]:
    params = dict(spec.probe)
    for key in list(params):
        if key == "start_date":
            params[key] = _compact(date.fromisoformat(start_date))
        elif key in {"end_date", "trade_date", "ann_date"}:
            params[key] = _compact(end)
    if symbol and spec.instrument_field:
        suffix = ".SH" if symbol.startswith(("5", "6", "9")) else ".BJ" if symbol.startswith(("4", "8")) else ".SZ"
        params[spec.instrument_field] = f"{symbol}{suffix}"
    return params


def _normalized_rows(adapter: TushareAdapter, spec: DatasetSpec, symbol: str, start: str, end: str) -> list[dict[str, Any]] | None:
    if spec.normalizer == "daily_basic":
        return adapter.daily_basic_rows(symbol, start, end)
    if spec.normalizer == "dividend":
        return adapter.dividend_rows(symbol, start, end)
    if spec.normalizer == "financial":
        return getattr(adapter, f"{spec.api_name}_rows")(symbol, start, end)
    return None


def _normalize_optional(spec: DatasetSpec, rows: list[dict[str, Any]], batch_id: str) -> None:
    if not rows:
        return
    if spec.normalizer == "daily_basic":
        factors = []
        for row in rows:
            for name, value in (row.get("factors") or {}).items():
                if value is not None:
                    factors.append({"symbol": row["symbol"], "trade_date": row["trade_date"], "factor_name": name, "value": value})
        if factors:
            upsert_factor_values(factors, source="tushare:daily_basic", batch_id=batch_id)
    elif spec.normalizer == "dividend":
        upsert_corporate_actions(rows, source="tushare:dividend", batch_id=batch_id)
    elif spec.normalizer == "financial":
        import_financial_statements(rows, source=f"tushare:{spec.api_name}")
    elif spec.normalizer == "index_weight":
        upsert_index_weights(rows, source="tushare:index_weight", batch_id=batch_id)


def _sync_generic(
    adapter: TushareAdapter,
    spec: DatasetSpec,
    run_id: str,
    batch_id: str,
    end_date: str,
    task_id: str | None = None,
    full_refresh: bool = False,
) -> tuple[int, int, int, int]:
    state = _item_state(run_id, spec.key)
    checkpoint = state.get("checkpoint") or {}
    resume_after = max(0, int(checkpoint.get("index") or 0))
    processed = int(state.get("processed") or 0)
    inserted = int(state.get("inserted") or 0)
    updated = int(state.get("updated") or 0)
    failed = int(state.get("failed") or 0)
    symbols = _listed_securities() if spec.scope == "instrument" else [None]
    for index, item in enumerate(symbols, start=1):
        if index <= resume_after:
            continue
        if _cancelled(run_id, task_id):
            break
        symbol = str(item["symbol"]) if item else None
        latest = None if full_refresh else _latest_raw_date(spec, symbol)
        initial_start = str(item.get("listed_date") or "1990-01-01") if item else "1990-01-01"
        start = (date.fromisoformat(latest) + timedelta(days=1)).isoformat() if latest else initial_start
        try:
            if spec.date_field and start > end_date:
                rows = []
            elif spec.normalizer == "index_weight":
                normalized = adapter.index_weight_rows("000300", start, end_date)
                rows = normalized
            else:
                normalized = _normalized_rows(adapter, spec, symbol, start, end_date) if symbol else None
                rows = normalized if normalized is not None else _query(
                    adapter.pro,
                    spec,
                    _generic_params(spec, start, end_date, symbol),
                )
            raw_rows = [_raw_row_for_symbol(spec, row, symbol) for row in rows]
            add, change = _save_raw(spec, raw_rows, batch_id)
            _normalize_optional(spec, rows, batch_id)
            inserted += add
            updated += change
        except Exception:  # dataset-level errors remain visible without aborting the full run
            failed += 1
        processed += 1
        _item(run_id, spec.key, processed=processed, inserted=inserted, updated=updated, failed=failed, checkpoint={"index": index, "total": len(symbols), "symbol": symbol})
        if spec.scope == "instrument":
            time.sleep(0.03)
    return processed, inserted, updated, failed


def _set_catalog_coverage(spec: DatasetSpec) -> None:
    with db() as connection:
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
        with db() as connection:
            allowed_rows = connection.execute(
                "select dataset_key from provider_dataset_catalog where provider='tushare' and permission_status in ('available','empty')"
            ).fetchall()
            item_rows = connection.execute(
                "select dataset_key, status from data_sync_items where run_id=?",
                (run_id,),
            ).fetchall()
        allowed = {row["dataset_key"] for row in allowed_rows}
        completed = {row["dataset_key"] for row in item_rows if row["status"] == "success"}
        summaries: dict[str, Any] = {}
        for spec in DATASET_REGISTRY:
            if spec.key not in selected_keys:
                continue
            if _cancelled(run_id, task_id):
                break
            if spec.key in completed:
                continue
            if spec.key not in allowed:
                _item(run_id, spec.key, status="skipped", finished_at=utc_now(), error="Permission unavailable or not verified.")
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
                        end_date,
                        task_id,
                        full_refresh=full_refresh,
                    )
                else:
                    result = _sync_generic(
                        adapter,
                        spec,
                        run_id,
                        batch_id,
                        end_date,
                        task_id,
                        full_refresh=full_refresh,
                    )
                processed, inserted, updated, failed = result
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
            "datasets": summaries, "endDate": end_date, "cancelled": cancelled,
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
    selected = [spec for spec in DATASET_REGISTRY if not requested or spec.key in requested]
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
    if item["status"] not in {"failed", "cancelled", "partial"}:
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
        connection.execute(
            """
            update data_sync_items
            set status='queued', processed=0, inserted=0, updated=0, failed=0,
                checkpoint_json=null, error=null, started_at=null, finished_at=null
            where run_id=? and status in ('failed','partial')
            """,
            (run_id,),
        )
    return sync_run(run_id) or {}
