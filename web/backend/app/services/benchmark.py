from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from ..lean import LeanPlatformError
from .lean_cache import rebuild_ashare_lean_cache_from_db
from .market_repository import upsert_market_daily_bars
from .data import record_data_asset


def _benchmark_rows(rows: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        normalized.append(
            {
                "symbol": symbol,
                "date": row.get("trade_date") or row.get("date"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume") or 0,
                "amount": row.get("amount"),
                "adj_factor": row.get("adj_factor") or 1.0,
            }
        )
    return normalized


def import_benchmark_rows(
    *,
    symbol: str,
    rows: list[dict[str, Any]],
    source: str = "akshare",
    market: str = "china",
    adjust: str = "raw",
    batch_id: str | None = None,
) -> dict[str, Any]:
    symbol = symbol.upper()
    batch = batch_id or str(uuid.uuid4())
    normalized = _benchmark_rows(rows, symbol)
    if not normalized:
        raise LeanPlatformError(f"No benchmark rows supplied for {symbol}.")
    upsert_market_daily_bars(
        normalized,
        symbol=symbol,
        asset_class="equity",
        market=market,
        venue=market,
        source=source,
        batch_id=batch,
        resolution="daily",
        data_type="trade",
        adjust=adjust,
    )
    cache = rebuild_ashare_lean_cache_from_db(symbol, source=source, adjust=adjust, market=market, batch_id=batch)
    cache.update(
        {
            "asset_class": "equity",
            "venue": market,
            "resolution": "daily",
            "data_type": "trade",
            "provider": source,
            "market": market,
            "adjust": adjust,
            "batch_id": batch,
            "benchmark": True,
            "research_tables": {
                "market_daily_bars": len(normalized),
                "first_date": cache["first_date"],
                "last_date": cache["last_date"],
            },
        }
    )
    return record_data_asset(cache)


def import_csi300_benchmark_from_akshare(start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    try:
        import akshare as ak  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency/environment specific.
        raise LeanPlatformError("AKShare is required to import CSI300 benchmark data.") from exc
    start_value = (start_date or "1990-01-01").replace("-", "")
    end_value = (end_date or date.today().isoformat()).replace("-", "")
    try:
        frame = ak.index_zh_a_hist(symbol="000300", period="daily", start_date=start_value, end_date=end_value)
    except Exception:
        frame = ak.stock_zh_index_daily(symbol="sh000300")
    rows = []
    columns = {str(column).lower(): column for column in getattr(frame, "columns", [])}
    zh = {"date": "日期", "open": "开盘", "high": "最高", "low": "最低", "close": "收盘", "volume": "成交量", "amount": "成交额"}
    en = {"date": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume", "amount": "amount"}
    mapping = zh if zh["date"] in getattr(frame, "columns", []) else {key: columns.get(value) for key, value in en.items()}
    for _, row in frame.iterrows():
        item = {
            "date": str(row[mapping["date"]])[:10],
            "open": row[mapping["open"]],
            "high": row[mapping["high"]],
            "low": row[mapping["low"]],
            "close": row[mapping["close"]],
            "volume": row[mapping["volume"]] if mapping.get("volume") else 0,
            "amount": row[mapping["amount"]] if mapping.get("amount") else None,
            "adj_factor": 1.0,
        }
        if item["date"].replace("-", "") < start_value or item["date"].replace("-", "") > end_value:
            continue
        rows.append(item)
    return import_benchmark_rows(symbol="000300", rows=rows, source="akshare", market="china", adjust="raw")
