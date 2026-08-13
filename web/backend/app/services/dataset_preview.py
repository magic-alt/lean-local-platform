from __future__ import annotations

import gzip
import json
import math
from datetime import datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from ..db import db, rows_to_dicts
from ..lean_engine.symbols import normalize_symbol
from .db_object_store import read_bytes
from . import market_lake


PREVIEW_DATASETS = {
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

ARCHIVE_DATASETS = {"index_basic", "fut_basic", "opt_basic"}
CURRENT_CONTRACT_DATASETS = {"fut_basic", "opt_basic"}
DATE_FIELDS = {
    "index_basic": "list_date",
    "index_daily": "trade_date",
    "fut_basic": "list_date",
    "opt_basic": "list_date",
}
CONTRACT_LIFECYCLE_FIELDS = {
    "fut_basic": (
        ("list_date", "listed_date"),
        ("last_ddate", "last_trade_date", "delist_date"),
    ),
    "opt_basic": (
        ("list_date", "listed_date"),
        ("last_ddate", "last_trade_date", "last_edate", "maturity_date", "expiry_date", "delist_date"),
    ),
}

LOCAL_INDEXES = (
    ("000001.SH", "上证指数", "SSE", "SSE"),
    ("000016.SH", "上证50", "SSE", "SSE"),
    ("000300.SH", "沪深300", "CSI", "CSI"),
    ("000905.SH", "中证500", "CSI", "CSI"),
    ("000852.SH", "中证1000", "CSI", "CSI"),
    ("399001.SZ", "深证成指", "SZSE", "SZSE"),
    ("399006.SZ", "创业板指", "SZSE", "SZSE"),
)


def _current_market_date() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


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


def _first_date(row: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        normalized = _iso_date(row.get(field))
        if normalized:
            return normalized
    return None


def _is_current_contract(dataset: str, row: dict[str, Any], as_of_date: str) -> bool:
    start_fields, end_fields = CONTRACT_LIFECYCLE_FIELDS[dataset]
    listed_date = _first_date(row, start_fields)
    last_trade_date = _first_date(row, end_fields)
    return bool(listed_date and last_trade_date and listed_date <= as_of_date <= last_trade_date)


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
              and (o.storage_mode='filesystem' or exists (
                  select 1 from stored_object_chunks c where c.object_id = o.id
              ))
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
    as_of_date: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    rows, updated_at = _latest_archive(dataset)
    date_field = DATE_FIELDS[dataset]
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if as_of_date and not _is_current_contract(dataset, row, as_of_date):
            continue
        normalized_date = _iso_date(row.get(date_field))
        if start_date and normalized_date and normalized_date < start_date:
            continue
        if end_date and normalized_date and normalized_date > end_date:
            continue
        if not _like_keyword(row, keyword):
            continue
        item = dict(row)
        for field in (
            "trade_date",
            "list_date",
            "listed_date",
            "delist_date",
            "maturity_date",
            "last_ddate",
            "last_edate",
            "last_trade_date",
            "expiry_date",
            "base_date",
        ):
            if item.get(field) not in (None, ""):
                item[field] = _iso_date(item[field]) or item[field]
        filtered.append(item)
    if dataset == "index_daily":
        filtered.sort(key=lambda row: str(row.get("trade_date") or ""), reverse=True)
    else:
        filtered.sort(key=lambda row: str(row.get("ts_code") or row.get("symbol") or ""))
    return filtered, updated_at


def _local_index_basic_preview(*, keyword: str) -> list[dict[str, Any]]:
    query = keyword.casefold()
    items: list[dict[str, Any]] = []
    for ts_code, name, market, publisher in LOCAL_INDEXES:
        code, suffix = ts_code.split(".", 1)
        path = market_lake.PARQUET_DIR / "gold" / "qlib_staging" / "full" / f"{suffix}{code}.parquet"
        if not path.is_file():
            continue
        item = {
            "ts_code": ts_code,
            "name": name,
            "market": market,
            "publisher": publisher,
            "category": "综合指数",
            "base_date": None,
            "list_date": None,
        }
        if not query or _like_keyword(item, query):
            items.append(item)
    return items


def _sql_preview(
    dataset: str,
    *,
    keyword: str,
    start_date: str | None,
    end_date: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, Any]], int | None, bool]:
    lake_scope = {
        "daily": ("bars", "equity", "trade", "tushare"),
        "index_daily": ("bars", "index", "trade", "tushare"),
        "adj_factor": ("adjustment_factor", "equity", "factor", "tushare"),
        "daily_basic": ("daily_basic", "equity", "metric", "tushare:daily_basic"),
        "suspend_d": ("trade_status", "equity", "status", "tushare:suspend_d"),
        "stk_limit": ("trade_status", "equity", "status", "tushare:stk_limit"),
    }.get(dataset)
    if lake_scope:
        kind, asset_class, data_type, source = lake_scope
        predicates: list[str] = []
        parameters: list[Any] = []
        if start_date:
            predicates.append("trade_date>=?")
            parameters.append(start_date)
        if end_date:
            predicates.append("trade_date<=?")
            parameters.append(end_date)
        factor_filter = keyword if dataset == "daily_basic" and keyword in market_lake.DAILY_BASIC_COLUMNS else ""
        if keyword and not factor_filter:
            normalized = normalize_symbol(keyword, "china")
            predicates.append("symbol=?" if normalized.isdigit() and len(normalized) == 6 else "symbol like ?")
            parameters.append(normalized if normalized.isdigit() and len(normalized) == 6 else f"%{normalized}%")
        if dataset == "daily_basic":
            factor_names = [factor_filter] if factor_filter else list(market_lake.DAILY_BASIC_COLUMNS[2:-3])
            selected, has_more = market_lake.query_daily_basic_preview(
                factor_names=factor_names,
                predicates=predicates,
                parameters=parameters,
                limit=limit,
                offset=offset,
            )
        else:
            exact_symbol = any(predicate.replace(" ", "").lower() == "symbol=?" for predicate in predicates)
            recent_partitions = None
            if dataset != "index_daily" and not start_date and not end_date:
                if not exact_symbol and dataset in {"suspend_d", "stk_limit"}:
                    recent_partitions = max(64, offset + limit + 2)
                elif not exact_symbol:
                    recent_partitions = max(1, (offset + limit + 1) // 4000 + 1)
            selected = market_lake.query_matching(
                kind=kind, asset_class=asset_class, market="china", resolution="daily",
                data_type=data_type, adjust="raw", source=source,
                predicates=predicates, parameters=parameters,
                order_by="trade_date desc,symbol", limit=limit + 1, offset=offset,
                recent_partitions=recent_partitions,
            )
            has_more = len(selected) > limit
            selected = selected[:limit]
        if dataset == "index_daily":
            for row in selected:
                symbol = str(row.pop("symbol", "") or "")
                row["ts_code"] = f"{symbol}.{'SZ' if symbol.startswith('399') else 'SH'}"
                row["pct_chg"] = row.pop("pct_change", None)
                row["vol"] = row.pop("volume", None)
        count = None if has_more else offset + len(selected)
        return [_safe_value(row) for row in selected], count, has_more
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
    elif dataset == "dividend":
        table = "corporate_actions"
        select = (
            "symbol,ex_date,action_type,cash_dividend,stock_dividend,split_ratio,"
            "allotment_ratio,allotment_price,source"
        )
        date_column = "ex_date"
        order_by = "ex_date desc, symbol"
        clauses.append("source='tushare:dividend'")
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
    return rows, count, offset + len(rows) < count


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
    if dataset == "index_basic":
        rows = _local_index_basic_preview(keyword=selected_keyword)
        return {
            "dataset": dataset,
            "items": rows[bounded_offset : bounded_offset + bounded_limit],
            "count": len(rows),
            "countExact": True,
            "hasMore": bounded_offset + bounded_limit < len(rows),
            "limit": bounded_limit,
            "offset": bounded_offset,
            "storage": "local_parquet",
            "updatedAt": None,
        }
    if dataset == "index_daily" and not selected_keyword:
        selected_keyword = "000300.SH"
    if dataset in ARCHIVE_DATASETS:
        as_of_date = _current_market_date() if dataset in CURRENT_CONTRACT_DATASETS else None
        rows, updated_at = _archive_preview(
            dataset,
            keyword=selected_keyword,
            start_date=start_date,
            end_date=end_date,
            as_of_date=as_of_date,
        )
        storage = "compressed_archive"
    else:
        selected, count, has_more = _sql_preview(
            dataset,
            keyword=selected_keyword,
            start_date=start_date,
            end_date=end_date,
            limit=bounded_limit,
            offset=bounded_offset,
        )
        updated_at = None
        storage = "local_parquet" if dataset in {"daily", "index_daily", "adj_factor", "daily_basic", "suspend_d", "stk_limit"} else "control_metadata"
        return {
            "dataset": dataset,
            "items": selected,
            "count": count,
            "countExact": count is not None,
            "hasMore": has_more,
            "limit": bounded_limit,
            "offset": bounded_offset,
            "storage": storage,
            "updatedAt": updated_at,
        }
    return {
        "dataset": dataset,
        "items": rows[bounded_offset : bounded_offset + bounded_limit],
        "count": len(rows),
        "countExact": True,
        "hasMore": bounded_offset + bounded_limit < len(rows),
        "limit": bounded_limit,
        "offset": bounded_offset,
        "storage": storage,
        "updatedAt": updated_at,
        "scope": "currently_tradable" if dataset in CURRENT_CONTRACT_DATASETS else None,
        "asOfDate": as_of_date,
    }
