from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from ..core.errors import LeanWebError
from ..db import db, utc_now
from .market_repository import optional_float, upsert_instrument


def _timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise LeanWebError("timestamp is required.")
    text = text.replace("T", " ").replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d %H:%M:%S", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt).isoformat(sep=" ")
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None).isoformat(sep=" ")
    except ValueError as exc:
        raise LeanWebError(f"Invalid timestamp: {value!r}") from exc


def _frequency(value: str) -> str:
    text = value.strip().lower()
    allowed = {"1m", "5m", "15m", "30m", "60m", "minute"}
    if text not in allowed:
        raise LeanWebError(f"Unsupported intraday frequency: {value!r}")
    return "1m" if text == "minute" else text


def import_intraday_bars(
    records: list[dict[str, Any]],
    *,
    symbol: str,
    asset_class: str,
    market: str,
    venue: str | None = None,
    frequency: str = "5m",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = "manual",
) -> dict[str, Any]:
    if not records:
        return {"count": 0}
    symbol_key = symbol.strip().upper()
    asset_key = asset_class.strip().lower()
    market_key = market.strip().lower()
    venue_key = (venue or market).strip().lower()
    frequency_key = _frequency(frequency)
    instrument_id = upsert_instrument(
        symbol=symbol_key,
        asset_class=asset_key,
        market=market_key,
        venue=venue_key,
        source=source,
    )
    batch_id = str(uuid.uuid4())
    now = utc_now()
    count = 0
    with db() as connection:
        for record in records:
            high = optional_float(record.get("high"))
            low = optional_float(record.get("low"))
            if high is not None and low is not None and high < low:
                raise LeanWebError("Intraday high cannot be lower than low.")
            connection.execute(
                """
                insert into market_intraday_bars
                    (instrument_id, symbol, asset_class, market, venue, timestamp, frequency,
                     data_type, open, high, low, close, volume, amount, open_interest,
                     adjust, source, batch_id, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(instrument_id, timestamp, frequency, data_type, adjust, source) do update set
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    amount = excluded.amount,
                    open_interest = excluded.open_interest,
                    batch_id = excluded.batch_id,
                    created_at = excluded.created_at
                """,
                (
                    instrument_id,
                    symbol_key,
                    asset_key,
                    market_key,
                    venue_key,
                    _timestamp(record.get("timestamp") or record.get("datetime") or record.get("time")),
                    frequency_key,
                    data_type,
                    optional_float(record.get("open")),
                    high,
                    low,
                    optional_float(record.get("close")),
                    optional_float(record.get("volume")),
                    optional_float(record.get("amount")),
                    optional_float(record.get("open_interest") or record.get("openInterest") or record.get("close_oi")),
                    adjust or "raw",
                    source,
                    batch_id,
                    now,
                ),
            )
            count += 1
    return {"batchId": batch_id, "count": count, "symbol": symbol_key, "frequency": frequency_key}
