from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from ..core.errors import LeanWebError
from ..db import utc_now
from .market_repository import optional_float, upsert_instrument
from . import market_lake


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
    rows = []
    for record in records:
        high = optional_float(record.get("high"))
        low = optional_float(record.get("low"))
        if high is not None and low is not None and high < low:
            raise LeanWebError("Intraday high cannot be lower than low.")
        rows.append(
            {
                "instrument_id": instrument_id, "symbol": symbol_key,
                "timestamp": _timestamp(record.get("timestamp") or record.get("datetime") or record.get("time")),
                "open": optional_float(record.get("open")), "high": high, "low": low,
                "close": optional_float(record.get("close")), "volume": optional_float(record.get("volume")),
                "amount": optional_float(record.get("amount")),
                "open_interest": optional_float(record.get("open_interest") or record.get("openInterest") or record.get("close_oi")),
                "batch_id": batch_id, "created_at": now,
            }
        )
    result = market_lake.upsert_rows(
        rows, kind="bars", asset_class=asset_key, market=market_key, venue=venue_key,
        resolution=frequency_key, data_type=data_type, adjust=adjust or "raw", source=source,
    )
    return {"batchId": batch_id, "count": len(rows), "symbol": symbol_key, "frequency": frequency_key, **result}
