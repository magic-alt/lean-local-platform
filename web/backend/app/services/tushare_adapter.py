from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from ..core.errors import LeanWebError
from ..lean import normalize_symbol
from .ashare_repository import import_security_master, infer_exchange, upsert_trade_calendar


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", False):
        return []
    if isinstance(frame, list):
        return [dict(item) for item in frame]
    if hasattr(frame, "to_dict"):
        return [dict(item) for item in frame.to_dict("records")]
    return []


def _compact_date(value: str | None, field: str) -> str:
    if not value:
        raise LeanWebError(f"{field} is required.")
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return text
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError as exc:
        raise LeanWebError(f"Invalid {field}: {value!r}; expected YYYY-MM-DD or YYYYMMDD.") from exc


def _iso_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _near(value: float | None, target: float | None, tolerance: float = 0.001) -> bool:
    return value is not None and target is not None and abs(value - target) <= tolerance


def _exchange_suffix(symbol: str) -> str:
    exchange = infer_exchange(symbol)
    return {"SSE": "SH", "SZSE": "SZ", "BSE": "BJ"}.get(exchange, "SH")


def to_tushare_stock_code(symbol: str) -> str:
    raw = symbol.strip().upper()
    if "." in raw:
        return raw
    ticker = normalize_symbol(raw, "china")
    return f"{ticker}.{_exchange_suffix(ticker)}"


def to_tushare_index_code(symbol: str) -> str:
    raw = symbol.strip().upper()
    if "." in raw:
        return raw
    ticker = normalize_symbol(raw, "china")
    suffix = "SZ" if ticker.startswith("399") else "SH"
    return f"{ticker}.{suffix}"


def from_tushare_code(ts_code: str) -> str:
    return str(ts_code).strip().upper().split(".")[0]


def _status(value: Any) -> str:
    return {"L": "listed", "D": "delisted", "P": "pending"}.get(str(value or "L").upper(), "listed")


class TushareAdapter:
    def __init__(self, token: str | None = None, pro: Any | None = None):
        self.token = token or os.environ.get("TUSHARE_TOKEN")
        if pro is not None:
            self.pro = pro
            return
        if not self.token:
            raise LeanWebError("TUSHARE_TOKEN is required. Put it in local .env or pass apiKey.")
        try:
            import tushare as ts  # type: ignore
        except ImportError as exc:
            raise LeanWebError("tushare is not installed. Install web/backend requirements first.") from exc
        self.pro = ts.pro_api(self.token)

    def trade_calendar(self, start_date: str, end_date: str, exchange: str = "SSE") -> list[dict[str, Any]]:
        frame = self.pro.trade_cal(
            exchange=exchange,
            start_date=_compact_date(start_date, "start_date"),
            end_date=_compact_date(end_date, "end_date"),
            fields="exchange,cal_date,is_open,pretrade_date",
        )
        return [
            {
                "exchange": item.get("exchange") or exchange,
                "trade_date": _iso_date(item.get("cal_date")),
                "is_open": bool(int(item.get("is_open") or 0)),
                "prev_trade_date": _iso_date(item.get("pretrade_date")),
            }
            for item in _records(frame)
        ]

    def stock_basic(self, list_statuses: list[str] | None = None) -> list[dict[str, Any]]:
        statuses = list_statuses or ["L", "D", "P"]
        records: list[dict[str, Any]] = []
        fields = "ts_code,symbol,name,area,industry,market,list_date,delist_date,list_status"
        for status in statuses:
            frame = self.pro.stock_basic(exchange="", list_status=status, fields=fields)
            for item in _records(frame):
                symbol = from_tushare_code(item.get("ts_code") or item.get("symbol"))
                delisted_date = _iso_date(item.get("delist_date"))
                records.append(
                    {
                        "symbol": symbol,
                        "name": item.get("name") or symbol,
                        "exchange": infer_exchange(symbol),
                        "listed_date": _iso_date(item.get("list_date")),
                        "delisted_date": delisted_date,
                        "status": "delisted" if delisted_date else _status(item.get("list_status")),
                        "industry": item.get("industry"),
                        "source": "tushare:stock_basic",
                    }
                )
        return records

    def adjustment_factors(self, symbol: str, start_date: str, end_date: str) -> dict[str, float]:
        frame = self.pro.adj_factor(
            ts_code=to_tushare_stock_code(symbol),
            start_date=_compact_date(start_date, "start_date"),
            end_date=_compact_date(end_date, "end_date"),
            fields="ts_code,trade_date,adj_factor",
        )
        result: dict[str, float] = {}
        for item in _records(frame):
            trade_date = _iso_date(item.get("trade_date"))
            factor = _float(item.get("adj_factor"))
            if trade_date and factor and factor > 0:
                result[trade_date] = factor
        return result

    def limit_prices(self, symbol: str, start_date: str, end_date: str) -> dict[str, dict[str, float | None]]:
        try:
            frame = self.pro.stk_limit(
                ts_code=to_tushare_stock_code(symbol),
                start_date=_compact_date(start_date, "start_date"),
                end_date=_compact_date(end_date, "end_date"),
                fields="ts_code,trade_date,up_limit,down_limit",
            )
        except Exception:
            return {}
        result: dict[str, dict[str, float | None]] = {}
        for item in _records(frame):
            trade_date = _iso_date(item.get("trade_date"))
            if trade_date:
                result[trade_date] = {
                    "limitUp": _float(item.get("up_limit")),
                    "limitDown": _float(item.get("down_limit")),
                }
        return result

    def daily_rows(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        *,
        adjust: str = "raw",
        include_limits: bool = True,
    ) -> list[dict[str, Any]]:
        if adjust and adjust.lower() not in {"", "raw"}:
            raise LeanWebError("TuShare adapter imports raw daily bars plus adj_factor; do not request qfq/hfq here.")
        start = _compact_date(start_date, "start_date")
        end = _compact_date(end_date, "end_date")
        frame = self.pro.daily(
            ts_code=to_tushare_stock_code(symbol),
            start_date=start,
            end_date=end,
            fields="ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount",
        )
        is_index = False
        records = _records(frame)
        if not records:
            try:
                frame = self.pro.index_daily(
                    ts_code=to_tushare_index_code(symbol),
                    start_date=start,
                    end_date=end,
                    fields="ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount",
                )
                records = _records(frame)
                is_index = True
            except Exception:
                records = []
        if not records:
            return []

        ticker = from_tushare_code(records[0].get("ts_code") or symbol)
        try:
            adj_factors = {} if is_index else self.adjustment_factors(ticker, start_date, end_date)
        except Exception:
            adj_factors = {}
        limits = {} if is_index or not include_limits else self.limit_prices(ticker, start_date, end_date)
        rows: list[dict[str, Any]] = []
        for item in records:
            trade_date = _iso_date(item.get("trade_date"))
            if not trade_date:
                continue
            close = _float(item.get("close"))
            high = _float(item.get("high"))
            low = _float(item.get("low"))
            limit = limits.get(trade_date, {})
            limit_up = limit.get("limitUp")
            limit_down = limit.get("limitDown")
            is_limit_up = _near(close, limit_up) or _near(high, limit_up)
            is_limit_down = _near(close, limit_down) or _near(low, limit_down)
            rows.append(
                {
                    "date": trade_date,
                    "open": item.get("open"),
                    "high": item.get("high"),
                    "low": item.get("low"),
                    "close": item.get("close"),
                    "volume": int((_float(item.get("vol")) or 0) * 100),
                    "amount": (_float(item.get("amount")) or 0) * 1000,
                    "prev_close": item.get("pre_close"),
                    "pct_change": item.get("pct_chg"),
                    "adj_factor": adj_factors.get(trade_date, 1.0),
                    "limitUp": limit_up,
                    "limitDown": limit_down,
                    "isLimitUp": is_limit_up if limit_up is not None else None,
                    "isLimitDown": is_limit_down if limit_down is not None else None,
                    "canBuy": False if is_limit_up else None,
                    "canSell": False if is_limit_down else None,
                }
            )
        return sorted(rows, key=lambda row: row["date"])


def fetch_tushare_rows(
    symbol: str,
    start_date: str | None,
    end_date: str | None,
    *,
    token: str | None = None,
    adjust: str = "raw",
) -> list[dict[str, Any]]:
    if not start_date or not end_date:
        raise LeanWebError("TuShare imports require startDate and endDate.")
    return TushareAdapter(token=token).daily_rows(symbol, start_date, end_date, adjust=adjust)


def import_tushare_stock_basic(
    *,
    adapter: TushareAdapter | None = None,
    list_statuses: list[str] | None = None,
    universe_code: str = "ALL_A",
) -> dict[str, Any]:
    adapter = adapter or TushareAdapter()
    records = adapter.stock_basic(list_statuses)
    return import_security_master(records, source="tushare:stock_basic", universe_code=universe_code)


def import_tushare_trade_calendar(
    *,
    start_date: str,
    end_date: str,
    exchange: str = "SSE",
    adapter: TushareAdapter | None = None,
) -> dict[str, Any]:
    adapter = adapter or TushareAdapter()
    rows = adapter.trade_calendar(start_date, end_date, exchange=exchange)
    open_dates = [str(item["trade_date"]) for item in rows if item.get("is_open") and item.get("trade_date")]
    upsert_trade_calendar("china", open_dates, source=f"tushare:trade_cal:{exchange}")
    return {
        "source": "tushare:trade_cal",
        "exchange": exchange,
        "startDate": start_date,
        "endDate": end_date,
        "rows": len(rows),
        "openDates": len(open_dates),
    }
