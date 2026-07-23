from __future__ import annotations

import gzip
import json
import math
from functools import lru_cache
from typing import Any

from ..db import db, rows_to_dicts
from ..lean_engine.symbols import normalize_symbol
from .db_object_store import read_bytes


PREVIEW_DATASETS = {
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

ARCHIVE_DATASETS = {"index_basic", "index_daily", "fut_basic", "opt_basic"}
DATE_FIELDS = {
    "index_basic": "list_date",
    "index_daily": "trade_date",
    "fut_basic": "list_date",
    "opt_basic": "list_date",
}


def _iso_date(value: Any) -> str | None:
    text = str(value or "").strip().replace("-", "")
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return None


def _safe_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    return value


@lru_cache(maxsize=16)
def _archive_rows(object_id: str) -> tuple[dict[str, Any], ...]:
    payload = gzip.decompress(read_bytes(object_id))
    decoded = json.loads(payload)
    if not isinstance(decoded, list):
        return ()
    return tuple(_safe_value(dict(row)) for row in decoded if isinstance(row, dict))


def _latest_archive(dataset: str) -> tuple[list[dict[str, Any]], str | None]:
    with db() as connection:
        archive = connection.execute(
            """
            select a.object_id, a.created_at
            from provider_raw_archives a
            join stored_objects o on o.id = a.object_id
            where a.provider='tushare' and a.dataset_key=?
              and exists (select 1 from stored_object_chunks c where c.object_id = o.id)
            order by a.created_at desc limit 1
            """,
            (dataset,),
        ).fetchone()
    if not archive:
        return [], None
    return [dict(row) for row in _archive_rows(str(archive["object_id"]))], archive["created_at"]


def _like_keyword(row: dict[str, Any], keyword: str) -> bool:
    if not keyword:
        return True
    query = keyword.casefold()
    return any(query in str(value or "").casefold() for value in row.values())


def _archive_preview(
    dataset: str,
    *,
    keyword: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[list[dict[str, Any]], str | None]:
    rows, updated_at = _latest_archive(dataset)
    date_field = DATE_FIELDS[dataset]
    filtered: list[dict[str, Any]] = []
    for row in rows:
        normalized_date = _iso_date(row.get(date_field))
        if start_date and normalized_date and normalized_date < start_date:
            continue
        if end_date and normalized_date and normalized_date > end_date:
            continue
        if not _like_keyword(row, keyword):
            continue
        item = dict(row)
        for field in ("trade_date", "list_date", "delist_date", "maturity_date", "last_ddate", "last_edate", "base_date"):
            if item.get(field) not in (None, ""):
                item[field] = _iso_date(item[field]) or item[field]
        filtered.append(item)
    if dataset == "index_daily":
        filtered.sort(key=lambda row: str(row.get("trade_date") or ""), reverse=True)
    else:
        filtered.sort(key=lambda row: str(row.get("ts_code") or row.get("symbol") or ""))
    return filtered, updated_at


def _sql_preview(
    dataset: str,
    *,
    keyword: str,
    start_date: str | None,
    end_date: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int]:
    clauses: list[str] = []
    values: list[Any] = []
    date_column: str | None = None
    if dataset == "stock_basic":
        table = "securities"
        select = "symbol,name,exchange,market,listed_date,delisted_date,status,is_st,industry,updated_at"
        if keyword:
            clauses.append("(symbol like ? or name like ? or coalesce(industry,'') like ?)")
            values.extend([f"%{keyword}%"] * 3)
        date_column = "listed_date"
        order_by = "symbol"
    elif dataset == "trade_cal":
        table = "trade_calendar"
        select = "market,trade_date,is_open,prev_trade_date,next_trade_date,source"
        date_column = "trade_date"
        order_by = "trade_date desc"
        if keyword:
            clauses.append("(market like ? or source like ?)")
            values.extend([f"%{keyword}%", f"%{keyword}%"])
    elif dataset == "daily":
        table = "ashare_daily_bars"
        select = "symbol,trade_date,open,high,low,close,prev_close,pct_change,volume,amount,adjust,source"
        date_column = "trade_date"
        order_by = "trade_date desc"
        clauses.append("adjust='raw'")
        if keyword:
            normalized = normalize_symbol(keyword, "china")
            if normalized.isdigit() and len(normalized) == 6:
                clauses.append("symbol = ?")
                values.append(normalized)
            else:
                clauses.append("symbol like ?")
                values.append(f"%{normalized}%")
    elif dataset == "adj_factor":
        table = "adjustment_factors"
        select = "symbol,trade_date,adj_factor,source"
        date_column = "trade_date"
        order_by = "trade_date desc"
        if keyword:
            normalized = normalize_symbol(keyword, "china")
            clauses.append("symbol = ?" if normalized.isdigit() and len(normalized) == 6 else "symbol like ?")
            values.append(normalized if normalized.isdigit() and len(normalized) == 6 else f"%{normalized}%")
    elif dataset == "suspend_d":
        table = "ashare_trade_status"
        select = "symbol,trade_date,is_suspended,can_buy,can_sell,source"
        date_column = "trade_date"
        order_by = "trade_date desc"
        clauses.append("source='tushare:suspend_d'")
        if keyword:
            normalized = normalize_symbol(keyword, "china")
            clauses.append("symbol = ?" if normalized.isdigit() and len(normalized) == 6 else "symbol like ?")
            values.append(normalized if normalized.isdigit() and len(normalized) == 6 else f"%{normalized}%")
    elif dataset == "stk_limit":
        table = "ashare_trade_status"
        select = "symbol,trade_date,limit_up,limit_down,can_buy,can_sell,is_st,source"
        date_column = "trade_date"
        order_by = "trade_date desc"
        clauses.append("source='tushare:stk_limit'")
        if keyword:
            normalized = normalize_symbol(keyword, "china")
            clauses.append("symbol = ?" if normalized.isdigit() and len(normalized) == 6 else "symbol like ?")
            values.append(normalized if normalized.isdigit() and len(normalized) == 6 else f"%{normalized}%")
    else:  # pragma: no cover - guarded by caller
        return [], 0
    if start_date and date_column:
        clauses.append(f"{date_column} >= ?")
        values.append(start_date)
    if end_date and date_column:
        clauses.append(f"{date_column} <= ?")
        values.append(end_date)
    where = f" where {' and '.join(clauses)}" if clauses else ""
    with db() as connection:
        count = int(connection.execute(
            f"select count(*) as count from {table}{where}",
            values,
        ).fetchone()["count"] or 0)
        rows = rows_to_dicts(connection.execute(
            f"select {select} from {table}{where} order by {order_by} limit ? offset ?",
            [*values, limit, offset],
        ).fetchall())
    return rows, count


def dataset_preview(
    dataset: str,
    *,
    keyword: str = "",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    if dataset not in PREVIEW_DATASETS:
        raise ValueError(f"Dataset preview is not supported: {dataset}")
    bounded_limit = max(1, min(int(limit), 500))
    bounded_offset = max(0, int(offset))
    selected_keyword = str(keyword or "").strip()
    if dataset in ARCHIVE_DATASETS:
        rows, updated_at = _archive_preview(
            dataset,
            keyword=selected_keyword,
            start_date=start_date,
            end_date=end_date,
        )
        storage = "compressed_archive"
    else:
        selected, count = _sql_preview(
            dataset,
            keyword=selected_keyword,
            start_date=start_date,
            end_date=end_date,
            limit=bounded_limit,
            offset=bounded_offset,
        )
        updated_at = None
        storage = "canonical_table"
        return {
            "dataset": dataset,
            "items": selected,
            "count": count,
            "limit": bounded_limit,
            "offset": bounded_offset,
            "storage": storage,
            "updatedAt": updated_at,
        }
    return {
        "dataset": dataset,
        "items": rows[bounded_offset : bounded_offset + bounded_limit],
        "count": len(rows),
        "limit": bounded_limit,
        "offset": bounded_offset,
        "storage": storage,
        "updatedAt": updated_at,
    }
