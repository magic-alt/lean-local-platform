from __future__ import annotations

import os
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any
import hashlib
import json

from ..core.errors import LeanWebError
from ..lean_engine.symbols import normalize_symbol
from .ashare_repository import import_security_master, infer_exchange, upsert_trade_calendar
from .tushare_rate_limit import RateLimitedProProxy


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", False):
        return []
    if isinstance(frame, list):
        return [dict(item) for item in frame]
    if hasattr(frame, "to_dict"):
        return [dict(item) for item in frame.to_dict("records")]
    return []


def _blank(value: Any) -> bool:
    if value in (None, "") or (isinstance(value, float) and math.isnan(value)):
        return True
    if isinstance(value, str) and value.strip().lower() in {"nan", "nat", "none", "null"}:
        return True
    return False


def _compact_date(value: str | None, field: str) -> str:
    if _blank(value):
        raise LeanWebError(f"{field} is required.")
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return text
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").strftime("%Y%m%d")
    except ValueError as exc:
        raise LeanWebError(f"Invalid {field}: {value!r}; expected YYYY-MM-DD or YYYYMMDD.") from exc


def _optional_compact_date(value: str | None) -> str | None:
    return _compact_date(value, "date") if value else None


def _date_windows(start_date: str, end_date: str, *, max_days: int = 3650) -> list[tuple[str, str]]:
    start = datetime.strptime(_compact_date(start_date, "start_date"), "%Y%m%d").date()
    end = datetime.strptime(_compact_date(end_date, "end_date"), "%Y%m%d").date()
    if end < start:
        raise LeanWebError("end_date must be on or after start_date.")
    windows: list[tuple[str, str]] = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=max_days - 1), end)
        windows.append((cursor.strftime("%Y%m%d"), window_end.strftime("%Y%m%d")))
        cursor = window_end + timedelta(days=1)
    return windows


def _first_non_blank(*values: Any) -> Any:
    for value in values:
        if not _blank(value):
            return value
    return None


def _iso_date(value: Any) -> str | None:
    if _blank(value):
        return None
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()


def _float(value: Any) -> float | None:
    if _blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _finite_float(value: Any, *, multiplier: float = 1.0) -> float | None:
    number = _float(value)
    if number is None:
        return None
    number *= multiplier
    return number if math.isfinite(number) else None


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


def to_tushare_hk_code(symbol: str) -> str:
    raw = normalize_symbol(symbol, "hongkong")
    return f"{raw}.HK"


def from_tushare_code(ts_code: str) -> str:
    return str(ts_code).strip().upper().split(".")[0]


def _status(value: Any) -> str:
    return {"L": "listed", "D": "delisted", "P": "pending"}.get(str(value or "L").upper(), "listed")


def _is_st_name(value: Any) -> bool:
    name = str(value or "").strip().upper().replace(" ", "")
    return name.startswith(("ST", "*ST", "S*ST", "SST")) or "退" in name


DAILY_BASIC_FACTORS: dict[str, tuple[str, float]] = {
    "turnover_rate": ("turnover_rate", 1.0),
    "turnover_rate_f": ("turnover_rate_float", 1.0),
    "volume_ratio": ("volume_ratio", 1.0),
    "pe": ("pe", 1.0),
    "pe_ttm": ("pe_ttm", 1.0),
    "pb": ("pb", 1.0),
    "ps": ("ps", 1.0),
    "ps_ttm": ("ps_ttm", 1.0),
    "dv_ratio": ("dividend_yield", 1.0),
    "dv_ttm": ("dividend_yield_ttm", 1.0),
    "total_share": ("total_share_shares", 10000.0),
    "float_share": ("float_share_shares", 10000.0),
    "free_share": ("free_share_shares", 10000.0),
    "total_mv": ("total_mv_cny", 10000.0),
    "circ_mv": ("circ_mv_cny", 10000.0),
}


FINANCIAL_ID_FIELDS = {
    "ts_code",
    "ann_date",
    "f_ann_date",
    "end_date",
    "report_type",
    "comp_type",
    "end_type",
    "update_flag",
}


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
        self.pro = RateLimitedProProxy(ts.pro_api(self.token))

    @staticmethod
    def _paged_records(endpoint: Any, *, page_size: int, **params: Any) -> list[dict[str, Any]]:
        """Read a provider partition completely instead of accepting a capped page."""
        records: list[dict[str, Any]] = []
        offset = 0
        while True:
            try:
                page = _records(endpoint(**params, limit=page_size, offset=offset))
            except TypeError:
                if offset:
                    raise
                return _records(endpoint(**params))
            records.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
            if offset > page_size * 1_000:
                raise LeanWebError("TuShare pagination exceeded the bounded partition limit.")
        return records

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
        concurrency = max(1, min(len(statuses), int(os.environ.get("LEAN_TUSHARE_FETCH_CONCURRENCY", "16"))))

        def fetch(status: str) -> list[dict[str, Any]]:
            return _records(self.pro.stock_basic(exchange="", list_status=status, fields=fields))

        with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="tushare-stock-basic") as executor:
            futures = [executor.submit(fetch, status) for status in statuses]
            frames = [future.result() for future in futures]
        for frame_records in frames:
            for item in frame_records:
                symbol = from_tushare_code(item.get("ts_code") or item.get("symbol"))
                if len(symbol) != 6 or not symbol.isdigit():
                    continue
                delisted_date = _iso_date(item.get("delist_date"))
                raw_name = item.get("name")
                raw_industry = item.get("industry")
                name = symbol if _blank(raw_name) else str(raw_name)
                records.append(
                    {
                        "symbol": symbol,
                        "name": name,
                        "exchange": infer_exchange(symbol),
                        "listed_date": _iso_date(item.get("list_date")),
                        "delisted_date": delisted_date,
                        "status": "delisted" if delisted_date else _status(item.get("list_status")),
                        "is_st": _is_st_name(name),
                        "industry": None if _blank(raw_industry) else str(raw_industry),
                        "source": "tushare:stock_basic",
                    }
                )
        return sorted(records, key=lambda item: (str(item["symbol"]), str(item["status"])))

    def namechange_rows(self, symbol: str) -> list[dict[str, Any]]:
        frame = self.pro.namechange(
            ts_code=to_tushare_stock_code(symbol),
            fields="ts_code,name,start_date,end_date,change_reason",
        )
        rows = []
        for item in _records(frame):
            start_date = _iso_date(item.get("start_date"))
            name = str(item.get("name") or "").strip()
            if not start_date or not name:
                continue
            rows.append({
                "symbol": from_tushare_code(item.get("ts_code") or symbol),
                "name": name,
                "start_date": start_date,
                "end_date": _iso_date(item.get("end_date")),
                "is_st": _is_st_name(name),
                "change_reason": item.get("change_reason"),
                "source": "tushare:namechange",
            })
        return sorted(rows, key=lambda row: (row["start_date"], row["name"]))

    def sw_industry_membership_rows(self, symbol: str) -> list[dict[str, Any]]:
        """Return both current and exited SW2021 memberships with effective intervals."""
        records: dict[tuple[str, str, str], dict[str, Any]] = {}
        for is_new in ("Y", "N"):
            frame = self.pro.index_member_all(
                ts_code=to_tushare_stock_code(symbol), is_new=is_new,
                fields="l1_code,l1_name,l2_code,l2_name,l3_code,l3_name,ts_code,name,in_date,out_date,is_new",
            )
            for item in _records(frame):
                in_date = _iso_date(item.get("in_date"))
                industry_code = str(item.get("l1_code") or "").strip()
                if not in_date or not industry_code:
                    continue
                row = {
                    "symbol": from_tushare_code(item.get("ts_code") or symbol),
                    "industry_code": industry_code,
                    "industry_name": item.get("l1_name"),
                    "taxonomy": "SW2021",
                    "level_no": 1,
                    "in_date": in_date,
                    "out_date": _iso_date(item.get("out_date")),
                    "source": "tushare:index_member_all",
                }
                records[(row["symbol"], industry_code, in_date)] = row
        return sorted(records.values(), key=lambda row: (row["in_date"], row["industry_code"]))

    def hk_basic(self, list_statuses: list[str] | None = None) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        fields = "ts_code,name,fullname,enname,market,list_status,list_date,delist_date,trade_unit,curr_type"
        for status in list_statuses or ["L", "D", "P"]:
            frame = self.pro.hk_basic(list_status=status, fields=fields)
            for item in _records(frame):
                symbol = from_tushare_code(item.get("ts_code"))
                if not symbol.isdigit():
                    continue
                symbol = symbol.zfill(5)
                records.append(
                    {
                        "symbol": symbol,
                        "name": item.get("name") or symbol,
                        "full_name": item.get("fullname"),
                        "english_name": item.get("enname"),
                        "exchange": "HKEX",
                        "market": "hongkong",
                        "currency": item.get("curr_type") or "HKD",
                        "listed_date": _iso_date(item.get("list_date")),
                        "delisted_date": _iso_date(item.get("delist_date")),
                        "status": _status(item.get("list_status")),
                        "lot_size": int(_float(item.get("trade_unit")) or 1),
                        "source": "tushare:hk_basic",
                    }
                )
        return records

    def hk_security(self, symbol: str) -> dict[str, Any] | None:
        frame = self.pro.hk_basic(
            ts_code=to_tushare_hk_code(symbol),
            fields="ts_code,name,fullname,enname,market,list_status,list_date,delist_date,trade_unit,curr_type",
        )
        records = _records(frame)
        if not records:
            return None
        item = records[0]
        return {
            "symbol": from_tushare_code(item.get("ts_code") or symbol).zfill(5),
            "name": item.get("name") or normalize_symbol(symbol, "hongkong"),
            "exchange": "HKEX",
            "market": "hongkong",
            "currency": item.get("curr_type") or "HKD",
            "listed_date": _iso_date(item.get("list_date")),
            "delisted_date": _iso_date(item.get("delist_date")),
            "status": _status(item.get("list_status")),
            "lot_size": int(_float(item.get("trade_unit")) or 1),
            "source": "tushare:hk_basic",
        }

    def hk_trade_calendar(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        frame = self.pro.hk_tradecal(
            start_date=_compact_date(start_date, "start_date"),
            end_date=_compact_date(end_date, "end_date"),
        )
        return [
            {
                "exchange": "HKEX",
                "trade_date": _iso_date(item.get("cal_date") or item.get("trade_date")),
                "is_open": bool(int(item.get("is_open") or 0)),
                "prev_trade_date": _iso_date(item.get("pretrade_date") or item.get("pre_trade_date")),
                "source": "tushare:hk_tradecal",
            }
            for item in _records(frame)
            if _iso_date(item.get("cal_date") or item.get("trade_date"))
        ]

    def hk_daily_rows(self, symbol: str, start_date: str, end_date: str, adjust: str = "raw") -> list[dict[str, Any]]:
        api_name = "hk_daily_adj" if str(adjust or "raw").lower() not in {"", "raw"} else "hk_daily"
        api = getattr(self.pro, api_name)
        rows: list[dict[str, Any]] = []
        for window_start, window_end in _date_windows(start_date, end_date):
            frame = api(
                ts_code=to_tushare_hk_code(symbol),
                start_date=window_start,
                end_date=window_end,
            )
            for item in _records(frame):
                trade_date = _iso_date(item.get("trade_date"))
                if not trade_date:
                    continue
                rows.append(
                    {
                        "date": trade_date,
                        "open": item.get("open"),
                        "high": item.get("high"),
                        "low": item.get("low"),
                        "close": item.get("close"),
                        "volume": _first_non_blank(item.get("vol"), item.get("volume"), 0),
                        "amount": item.get("amount"),
                        "prev_close": item.get("pre_close"),
                        "pct_change": _first_non_blank(item.get("pct_chg"), item.get("pct_change")),
                        "turnover_rate": item.get("turnover_rate"),
                        "adj_factor": _first_non_blank(item.get("adj_factor"), 1.0),
                        "source": f"tushare:{api_name}",
                    }
                )
        unique = {str(row["date"]): row for row in rows}
        return [unique[key] for key in sorted(unique)]

    def stock_by_code(self, symbol: str) -> dict[str, Any] | None:
        frame = self.pro.stock_basic(
            ts_code=to_tushare_stock_code(symbol),
            fields="ts_code,symbol,name,area,industry,market,list_date,delist_date,list_status",
        )
        records = _records(frame)
        if not records:
            return None
        item = records[0]
        code = from_tushare_code(item.get("ts_code") or symbol)
        if len(code) != 6 or not code.isdigit():
            return None
        delisted_date = _iso_date(item.get("delist_date"))
        raw_name = item.get("name")
        raw_industry = item.get("industry")
        name = code if _blank(raw_name) else str(raw_name)
        return {
            "symbol": code, "name": name, "exchange": infer_exchange(code),
            "listed_date": _iso_date(item.get("list_date")), "delisted_date": delisted_date,
            "status": "delisted" if delisted_date else _status(item.get("list_status")),
            "is_st": _is_st_name(name), "industry": None if _blank(raw_industry) else str(raw_industry),
            "source": "tushare:stock_basic",
        }

    @staticmethod
    def _normalize_daily_basic_rows(frame: Any, fallback_symbol: str = "") -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in _records(frame):
            trade_date = _iso_date(item.get("trade_date"))
            if not trade_date:
                continue
            factors: dict[str, float] = {}
            for raw_name, (factor_name, multiplier) in DAILY_BASIC_FACTORS.items():
                value = _finite_float(item.get(raw_name), multiplier=multiplier)
                if value is not None:
                    factors[factor_name] = value
            if factors:
                rows.append(
                    {
                        "symbol": from_tushare_code(item.get("ts_code") or fallback_symbol),
                        "trade_date": trade_date,
                        "factors": factors,
                        "source": "tushare:daily_basic",
                    }
                )
        return sorted(rows, key=lambda row: (row["trade_date"], row["symbol"]))

    def daily_basic_rows(self, symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        records_by_date: dict[str, dict[str, Any]] = {}
        # The endpoint caps responses at 6,000 rows. An 8,000-calendar-day
        # window remains below that ceiling for one A-share and cuts a
        # 1990-present history from four provider calls to two.
        for window_start, window_end in _date_windows(start_date, end_date, max_days=8000):
            frame = self.pro.daily_basic(
                ts_code=to_tushare_stock_code(symbol),
                start_date=window_start,
                end_date=window_end,
                fields=(
                    "ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,"
                    "ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv"
                ),
            )
            for item in _records(frame):
                trade_date = _iso_date(item.get("trade_date"))
                if trade_date:
                    records_by_date[trade_date] = item
        return self._normalize_daily_basic_rows(list(records_by_date.values()), symbol)

    def daily_basic_rows_for_date(self, trade_date: str) -> list[dict[str, Any]]:
        compact_date = _compact_date(trade_date, "trade_date")
        frame = self._paged_records(
            self.pro.daily_basic,
            page_size=6_000,
            trade_date=compact_date,
            fields=(
                "ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,"
                "ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv"
            ),
        )
        return self._normalize_daily_basic_rows(frame)

    def adjustment_factors(self, symbol: str, start_date: str, end_date: str) -> dict[str, float]:
        result: dict[str, float] = {}
        for window_start, window_end in _date_windows(start_date, end_date):
            frame = self.pro.adj_factor(
                ts_code=to_tushare_stock_code(symbol),
                start_date=window_start,
                end_date=window_end,
                fields="ts_code,trade_date,adj_factor",
            )
            for item in _records(frame):
                trade_date = _iso_date(item.get("trade_date"))
                factor = _float(item.get("adj_factor"))
                if trade_date and factor and factor > 0:
                    result[trade_date] = factor
        return result

    def adjustment_factors_full(self, symbol: str, start_date: str, end_date: str) -> dict[str, float]:
        """Fetch one instrument in one request.

        TuShare documents ``adj_factor`` as supporting the complete history of
        one stock.  The legacy ten-year windows multiplied first-fill calls and
        prevented the 5,000-point account from approaching its 500/minute cap.
        """
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

    def adjustment_factors_for_date(self, trade_date: str) -> list[dict[str, Any]]:
        """Fetch the full A-share market for a single incremental trade day."""
        day = _compact_date(trade_date, "trade_date")
        frame = self._paged_records(
            self.pro.adj_factor,
            page_size=6_000,
            ts_code="",
            trade_date=day,
            fields="ts_code,trade_date,adj_factor",
        )
        rows: list[dict[str, Any]] = []
        for item in _records(frame):
            factor = _float(item.get("adj_factor"))
            normalized_date = _iso_date(item.get("trade_date"))
            symbol = from_tushare_code(item.get("ts_code") or "")
            if symbol and normalized_date and factor and factor > 0:
                rows.append(
                    {
                        "symbol": symbol,
                        "trade_date": normalized_date,
                        "adj_factor": factor,
                        "source": "tushare",
                    }
                )
        return rows

    def suspend_rows(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        *,
        include_legacy: bool = True,
    ) -> list[dict[str, Any]]:
        """Return full-day suspension intervals with auditable TuShare provenance.

        ``suspend_d`` is an event/daily-status endpoint.  Its current schema is
        ``trade_date/suspend_type/suspend_timing``; older code incorrectly asked
        it for the legacy ``suspend_date/resume_date`` fields and consequently
        normalized every response to an empty list.  The legacy ``suspend``
        endpoint is still useful for long historical intervals, so both sources
        are combined here.
        """
        frame = self.pro.suspend_d(
            ts_code=to_tushare_stock_code(symbol),
            start_date=_compact_date(start_date, "start_date"),
            end_date=_compact_date(end_date, "end_date"),
            fields="ts_code,trade_date,suspend_timing,suspend_type",
        )
        rows: list[dict[str, Any]] = []
        for item in _records(frame):
            trade_date = _iso_date(item.get("trade_date"))
            if not trade_date or str(item.get("suspend_type") or "S").upper() != "S":
                continue
            timing = str(item.get("suspend_timing") or "").strip() or None
            next_calendar_date = (date.fromisoformat(trade_date) + timedelta(days=1)).isoformat()
            rows.append(
                {
                    "symbol": from_tushare_code(item.get("ts_code") or symbol),
                    "suspend_date": trade_date,
                    "resume_date": next_calendar_date,
                    "suspend_timing": timing,
                    "is_full_day": timing is None,
                    "reason": "daily_suspend_event",
                    "reason_type": "S",
                    "source": "tushare:suspend_d",
                }
            )

        legacy = getattr(self.pro, "suspend", None) if include_legacy else None
        if callable(legacy):
            legacy_frame = legacy(
                ts_code=to_tushare_stock_code(symbol),
                fields="ts_code,suspend_date,resume_date,ann_date,suspend_reason,reason_type",
            )
            for item in _records(legacy_frame):
                suspend_date = _iso_date(item.get("suspend_date"))
                resume_date = _iso_date(item.get("resume_date"))
                if not suspend_date:
                    continue
                interval_end = resume_date or end_date
                if interval_end < start_date or suspend_date > end_date:
                    continue
                rows.append(
                    {
                        "symbol": from_tushare_code(item.get("ts_code") or symbol),
                        "suspend_date": suspend_date,
                        "resume_date": resume_date,
                        "announce_date": _iso_date(item.get("ann_date")),
                        "suspend_timing": None,
                        "is_full_day": True,
                        "reason": item.get("suspend_reason"),
                        "reason_type": item.get("reason_type"),
                        "source": "tushare:suspend",
                    }
                )

        unique: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            # ``suspend_d`` and the legacy ``suspend`` endpoint can describe
            # the same first suspension day. The canonical dataset key does
            # not include provider endpoint, so retain the first (official
            # suspend_d) record instead of manufacturing a duplicate key.
            key = (str(row["suspend_date"]), str(row.get("suspend_timing") or ""))
            unique.setdefault(key, row)
        return sorted(unique.values(), key=lambda row: (row["suspend_date"], row["symbol"], row["source"]))

    def suspend_rows_for_date(self, trade_date: str) -> list[dict[str, Any]]:
        """Fetch the authoritative market-wide suspension set for one date."""
        frame = self._paged_records(
            self.pro.suspend_d,
            page_size=5_000,
            trade_date=_compact_date(trade_date, "trade_date"),
            fields="ts_code,trade_date,suspend_timing,suspend_type",
        )
        rows: list[dict[str, Any]] = []
        for item in _records(frame):
            event_date = _iso_date(item.get("trade_date"))
            if not event_date or str(item.get("suspend_type") or "S").upper() != "S":
                continue
            timing = str(item.get("suspend_timing") or "").strip() or None
            rows.append(
                {
                    "symbol": from_tushare_code(item.get("ts_code")),
                    "suspend_date": event_date,
                    "resume_date": (date.fromisoformat(event_date) + timedelta(days=1)).isoformat(),
                    "suspend_timing": timing,
                    "is_full_day": timing is None,
                    "reason": "daily_suspend_event",
                    "reason_type": "S",
                    "source": "tushare:suspend_d",
                }
            )
        return sorted(rows, key=lambda row: (row["suspend_date"], row["symbol"]))

    def limit_prices(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        *,
        strict: bool = False,
    ) -> dict[str, dict[str, float | None]]:
        result: dict[str, dict[str, float | None]] = {}
        try:
            # 7,000 calendar days contain fewer than the provider's 5,000-row
            # cap of A-share sessions. This halves full-history calls for old
            # listings compared with the generic ten-year window.
            for window_start, window_end in _date_windows(start_date, end_date, max_days=7000):
                frame = self.pro.stk_limit(
                    ts_code=to_tushare_stock_code(symbol),
                    start_date=window_start,
                    end_date=window_end,
                    fields="ts_code,trade_date,up_limit,down_limit",
                )
                for item in _records(frame):
                    trade_date = _iso_date(item.get("trade_date"))
                    if trade_date:
                        result[trade_date] = {
                            "limitUp": _float(item.get("up_limit")),
                            "limitDown": _float(item.get("down_limit")),
                        }
        except Exception:
            if strict:
                raise
            return {}
        return result

    def limit_prices_for_date(self, trade_date: str) -> list[dict[str, Any]]:
        """Fetch the full A-share price-limit set for one incremental day."""
        day = _compact_date(trade_date, "trade_date")
        frame = self._paged_records(
            self.pro.stk_limit,
            page_size=5_800,
            ts_code="",
            trade_date=day,
            fields="ts_code,trade_date,up_limit,down_limit",
        )
        rows: list[dict[str, Any]] = []
        for item in _records(frame):
            normalized_date = _iso_date(item.get("trade_date"))
            symbol = from_tushare_code(item.get("ts_code") or "")
            if symbol and normalized_date:
                rows.append(
                    {
                        "symbol": symbol,
                        "trade_date": normalized_date,
                        "limit_up": _float(item.get("up_limit")),
                        "limit_down": _float(item.get("down_limit")),
                        "source": "tushare:stk_limit",
                    }
                )
        return sorted(rows, key=lambda row: (row["trade_date"], row["symbol"]))

    def _daily_market_records(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        *,
        index: bool = False,
        max_window_days: int = 3650,
    ) -> list[dict[str, Any]]:
        endpoint = self.pro.index_daily if index else self.pro.daily
        code = to_tushare_index_code(symbol) if index else to_tushare_stock_code(symbol)
        records_by_date: dict[str, dict[str, Any]] = {}
        for window_start, window_end in _date_windows(start_date, end_date, max_days=max_window_days):
            frame = endpoint(
                ts_code=code,
                start_date=window_start,
                end_date=window_end,
                fields="ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount",
            )
            for item in _records(frame):
                trade_date = _iso_date(item.get("trade_date"))
                if trade_date:
                    records_by_date[trade_date] = item
        return [records_by_date[key] for key in sorted(records_by_date)]

    def dividend_rows(self, symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        frame = self.pro.dividend(
            ts_code=to_tushare_stock_code(symbol),
            ann_date="",
            record_date="",
            ex_date="",
            fields=(
                "ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,cash_div,"
                "cash_div_tax,record_date,ex_date,pay_date,div_listdate,imp_ann_date,base_date,base_share"
            ),
        )
        return self._normalize_dividend_rows(frame, start_date, end_date, symbol)

    def dividend_rows_for_date(self, ex_date: str) -> list[dict[str, Any]]:
        """Fetch the full market's ex-dividend actions for one trade date."""
        compact_date = _compact_date(ex_date, "ex_date")
        frame = self._paged_records(
            self.pro.dividend,
            page_size=5_000,
            ts_code="",
            ann_date="",
            record_date="",
            ex_date=compact_date,
            fields=(
                "ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,cash_div,"
                "cash_div_tax,record_date,ex_date,pay_date,div_listdate,imp_ann_date,base_date,base_share"
            ),
        )
        return self._normalize_dividend_rows(frame, ex_date, ex_date, "")

    @staticmethod
    def _normalize_dividend_rows(
        frame: Any,
        start_date: str,
        end_date: str,
        fallback_symbol: str,
    ) -> list[dict[str, Any]]:
        start = _compact_date(start_date, "start_date")
        end = _compact_date(end_date, "end_date")
        rows: list[dict[str, Any]] = []
        for item in _records(frame):
            ex_date_raw = _first_non_blank(item.get("ex_date"), item.get("div_listdate"), item.get("record_date"), item.get("ann_date"))
            if not ex_date_raw:
                continue
            compact_ex_date = _compact_date(str(ex_date_raw), "ex_date")
            if compact_ex_date < start or compact_ex_date > end:
                continue
            stock_dividend = _finite_float(item.get("stk_div"), multiplier=0.1)
            if stock_dividend is None:
                bonus = _finite_float(item.get("stk_bo_rate"), multiplier=0.1) or 0.0
                conversion = _finite_float(item.get("stk_co_rate"), multiplier=0.1) or 0.0
                stock_dividend = bonus + conversion if bonus or conversion else None
            rows.append(
                {
                    "symbol": from_tushare_code(item.get("ts_code") or fallback_symbol),
                    "ex_date": _iso_date(compact_ex_date),
                    "action_type": "dividend",
                    "cash_dividend": _finite_float(item.get("cash_div_tax") or item.get("cash_div"), multiplier=0.1),
                    "stock_dividend": stock_dividend,
                    "split_ratio": None,
                    "allotment_ratio": None,
                    "allotment_price": None,
                    "source": "tushare:dividend",
                    "metadata": {
                        "announce_date": _iso_date(item.get("ann_date")),
                        "record_date": _iso_date(item.get("record_date")),
                        "pay_date": _iso_date(item.get("pay_date")),
                        "process": item.get("div_proc"),
                    },
                }
            )
        # `corporate_actions` intentionally models one economic action per
        # symbol/ex-date/type. TuShare can return repeated proposal/implementation
        # revisions for that same action (and occasionally exact duplicates) in a
        # market-wide ex-date response. Keep the most authoritative revision so
        # the validation gate sees the same natural key as the canonical table.
        def revision_rank(row: dict[str, Any]) -> tuple[int, int, int, str, str]:
            metadata = row.get("metadata") or {}
            process = str(metadata.get("process") or "").strip()
            completed = int(process in {"实施", "实施方案", "实施完成", "实施中"})
            economic_fields = ("cash_dividend", "stock_dividend", "split_ratio", "allotment_ratio")
            economic_values = sum(int(row.get(field) is not None) for field in economic_fields)
            pay_date = str(metadata.get("pay_date") or "")
            announce_date = str(metadata.get("announce_date") or "")
            return completed, economic_values, int(bool(pay_date)), pay_date, announce_date

        deduplicated: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            key = (str(row["symbol"]), str(row["ex_date"]), str(row["action_type"]))
            current = deduplicated.get(key)
            if current is None or revision_rank(row) > revision_rank(current):
                deduplicated[key] = row
        return sorted(deduplicated.values(), key=lambda row: (row["ex_date"], row["symbol"], row["action_type"]))

    def index_weight_rows(self, index_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        records_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for window_start, window_end in _date_windows(start_date, end_date, max_days=365):
            frame = self.pro.index_weight(
                index_code=to_tushare_index_code(index_code),
                start_date=window_start,
                end_date=window_end,
                fields="index_code,con_code,trade_date,weight",
            )
            for item in _records(frame):
                trade_date = _iso_date(item.get("trade_date"))
                symbol = str(item.get("con_code") or "")
                if trade_date and symbol:
                    records_by_key[(trade_date, symbol)] = item
        rows: list[dict[str, Any]] = []
        for item in records_by_key.values():
            trade_date = _iso_date(item.get("trade_date"))
            symbol = item.get("con_code")
            weight = _finite_float(item.get("weight"))
            if not trade_date or not symbol or weight is None:
                continue
            rows.append(
                {
                    "universe_code": "CSI300" if from_tushare_code(str(item.get("index_code") or index_code)) == "000300" else from_tushare_code(str(item.get("index_code") or index_code)),
                    "symbol": from_tushare_code(str(symbol)),
                    "trade_date": trade_date,
                    "weight": weight,
                    "source": "tushare:index_weight",
                }
            )
        return sorted(rows, key=lambda row: (row["trade_date"], row["symbol"]))

    def _financial_rows(self, endpoint: str, symbol: str, start_date: str | None, end_date: str | None) -> list[dict[str, Any]]:
        method = getattr(self.pro, endpoint)
        kwargs = {"ts_code": to_tushare_stock_code(symbol)}
        start = _optional_compact_date(start_date)
        end = _optional_compact_date(end_date)
        if start:
            kwargs["start_date"] = start
        if end:
            kwargs["end_date"] = end
        frame = method(**kwargs)
        rows: list[dict[str, Any]] = []
        for item in _records(frame):
            report_date = _iso_date(item.get("end_date"))
            announce_date = _iso_date(item.get("ann_date") or item.get("f_ann_date"))
            if not report_date or not announce_date:
                continue
            if start and _compact_date(report_date, "report_date") < start:
                continue
            if end and _compact_date(report_date, "report_date") > end:
                continue
            fields = {key: value for key, value in item.items() if key not in FINANCIAL_ID_FIELDS}
            rows.append(
                {
                    "symbol": from_tushare_code(item.get("ts_code") or symbol),
                    "statement_type": endpoint,
                    "report_date": report_date,
                    "announce_date": announce_date,
                    "effective_date": _iso_date(item.get("f_ann_date")) or announce_date,
                    "fiscal_period": report_date,
                    "currency": "CNY",
                    "fields": fields,
                    "source": f"tushare:{endpoint}",
                    "report_type": None if _blank(item.get("report_type")) else str(item.get("report_type")),
                    "update_flag": None if _blank(item.get("update_flag")) else str(item.get("update_flag")),
                    "payload_hash": hashlib.sha256(
                        json.dumps(item, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
                    ).hexdigest(),
                }
            )
        return sorted(rows, key=lambda row: (row["report_date"], row["announce_date"], row["symbol"]))

    def income_rows(self, symbol: str, start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
        return self._financial_rows("income", symbol, start_date, end_date)

    def balancesheet_rows(self, symbol: str, start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
        return self._financial_rows("balancesheet", symbol, start_date, end_date)

    def cashflow_rows(self, symbol: str, start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
        return self._financial_rows("cashflow", symbol, start_date, end_date)

    def fina_indicator_rows(self, symbol: str, start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
        return self._financial_rows("fina_indicator", symbol, start_date, end_date)

    def daily_rows(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        *,
        adjust: str = "raw",
        include_limits: bool = True,
        include_adjustments: bool = True,
        include_index_fallback: bool = True,
        max_window_days: int = 3650,
    ) -> list[dict[str, Any]]:
        if adjust and adjust.lower() not in {"", "raw"}:
            raise LeanWebError("TuShare adapter imports raw daily bars plus adj_factor; do not request qfq/hfq here.")
        is_index = False
        records = self._daily_market_records(symbol, start_date, end_date, max_window_days=max_window_days)
        if not records and include_index_fallback:
            try:
                records = self._daily_market_records(
                    symbol, start_date, end_date, index=True, max_window_days=max_window_days
                )
                is_index = True
            except Exception:
                records = []
        if not records:
            return []

        ticker = from_tushare_code(records[0].get("ts_code") or symbol)
        adj_factor_verified = is_index
        if include_adjustments:
            try:
                adj_factors = {} if is_index else self.adjustment_factors(ticker, start_date, end_date)
                adj_factor_verified = is_index or len(adj_factors) >= len(records)
            except Exception:
                adj_factors = {}
                adj_factor_verified = False
        else:
            adj_factors = {}
            adj_factor_verified = is_index
        limits = {} if is_index or not include_limits else self.limit_prices(ticker, start_date, end_date)
        rows: list[dict[str, Any]] = []
        for item in records:
            trade_date = _iso_date(item.get("trade_date"))
            if not trade_date:
                continue
            close = _finite_float(item.get("close"))
            high = _finite_float(item.get("high"))
            low = _finite_float(item.get("low"))
            open_price = _finite_float(item.get("open"))
            if None in {open_price, high, low, close}:
                continue
            limit = limits.get(trade_date, {})
            limit_up = limit.get("limitUp")
            limit_down = limit.get("limitDown")
            is_limit_up = _near(close, limit_up) or _near(high, limit_up)
            is_limit_down = _near(close, limit_down) or _near(low, limit_down)
            rows.append(
                {
                    "date": trade_date,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": int((_float(item.get("vol")) or 0) * 100),
                    "amount": (_float(item.get("amount")) or 0) * 1000,
                    "prev_close": _finite_float(item.get("pre_close")),
                    "pct_change": _finite_float(item.get("pct_chg")),
                    "adj_factor": adj_factors.get(trade_date, 1.0),
                    "adj_factor_verified": adj_factor_verified,
                    "limitUp": limit_up,
                    "limitDown": limit_down,
                    "isLimitUp": is_limit_up if limit_up is not None else None,
                    "isLimitDown": is_limit_down if limit_down is not None else None,
                    "canBuy": False if is_limit_up else None,
                    "canSell": False if is_limit_down else None,
                }
            )
        return sorted(rows, key=lambda row: row["date"])

    def daily_rows_for_date(self, trade_date: str) -> list[dict[str, Any]]:
        """Fetch raw daily bars for the full A-share market in one request."""
        compact_date = _compact_date(trade_date, "trade_date")
        frame = self._paged_records(
            self.pro.daily,
            page_size=6_000,
            ts_code="",
            trade_date=compact_date,
            fields="ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount",
        )
        rows: list[dict[str, Any]] = []
        for item in _records(frame):
            normalized_date = _iso_date(item.get("trade_date"))
            symbol = from_tushare_code(item.get("ts_code") or "")
            close = _finite_float(item.get("close"))
            high = _finite_float(item.get("high"))
            low = _finite_float(item.get("low"))
            open_price = _finite_float(item.get("open"))
            if not symbol or not normalized_date or None in {open_price, high, low, close}:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "date": normalized_date,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": int((_float(item.get("vol")) or 0) * 100),
                    "amount": (_float(item.get("amount")) or 0) * 1000,
                    "prev_close": _finite_float(item.get("pre_close")),
                    "pct_change": _finite_float(item.get("pct_chg")),
                    "adj_factor": 1.0,
                    "adj_factor_verified": False,
                    "limitUp": None,
                    "limitDown": None,
                    "isLimitUp": None,
                    "isLimitDown": None,
                    "canBuy": None,
                    "canSell": None,
                }
            )
        return sorted(rows, key=lambda row: row["symbol"])

    def index_daily_rows(self, symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Fetch an index explicitly so overlapping stock codes cannot be mistaken for an index."""
        frame = self.pro.index_daily(
            ts_code=to_tushare_index_code(symbol),
            start_date=_compact_date(start_date, "start_date"),
            end_date=_compact_date(end_date, "end_date"),
            fields="ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount",
        )
        rows: list[dict[str, Any]] = []
        for item in _records(frame):
            trade_date = _iso_date(item.get("trade_date"))
            if not trade_date:
                continue
            rows.append({
                "date": trade_date, "open": item.get("open"), "high": item.get("high"),
                "low": item.get("low"), "close": item.get("close"),
                "volume": int((_float(item.get("vol")) or 0) * 100),
                "amount": (_float(item.get("amount")) or 0) * 1000,
                "prev_close": item.get("pre_close"), "pct_change": item.get("pct_chg"),
                "adj_factor": 1.0,
            })
        return sorted(rows, key=lambda row: row["date"])

    def announcement_directory_rows(self, symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Optional TuShare announcement catalogue; official exchange URLs remain the evidence source."""
        frame = self.pro.anns_d(
            ts_code=to_tushare_stock_code(symbol),
            start_date=_compact_date(start_date, "start_date"),
            end_date=_compact_date(end_date, "end_date"),
            fields="ann_date,ts_code,name,title,url,rec_time",
        )
        rows = []
        for item in _records(frame):
            ann_date = _iso_date(item.get("ann_date"))
            if ann_date:
                rows.append({
                    "date": ann_date, "code": from_tushare_code(item.get("ts_code") or symbol),
                    "title": item.get("title"), "url": item.get("url"), "source": "tushare:anns_d",
                })
        return sorted(rows, key=lambda row: (row["date"], str(row.get("title") or "")))

    def sector_daily_rows(
        self,
        topics: list[dict[str, Any]] | list[str],
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        """Resolve every canonical topic independently across DC and THS catalogues."""
        matches: list[dict[str, Any]] = []
        providers = (
            ("dc", lambda: self.pro.dc_index(fields="ts_code,name,publisher,category")),
            ("ths", lambda: self.pro.ths_index(exchange="A", type="N", fields="ts_code,name,count,exchange,list_date,type")),
        )
        normalized = [
            item if isinstance(item, dict) else {"keyword": str(item), "aliases": [str(item)]}
            for item in topics
        ]
        catalogues: dict[str, list[dict[str, Any]]] = {}
        for provider, catalogue_call in providers:
            try:
                catalogues[provider] = _records(catalogue_call())
            except Exception:
                catalogues[provider] = []
        used_codes: set[str] = set()
        for topic in normalized:
            keyword = str(topic["keyword"])
            resolved = False
            for alias in topic.get("aliases") or [keyword]:
                for provider, _ in providers:
                    catalogue = catalogues.get(provider) or []
                    found = next(
                        (
                            item for item in catalogue
                            if str(item.get("ts_code") or "") not in used_codes
                            and str(alias).lower() in str(item.get("name") or "").lower()
                        ),
                        None,
                    )
                    if not found:
                        continue
                    ts_code = str(found.get("ts_code") or "")
                    try:
                        if provider == "dc":
                            frame = self.pro.dc_daily(
                                ts_code=ts_code, start_date=_compact_date(start_date, "start_date"),
                                end_date=_compact_date(end_date, "end_date"),
                                fields="ts_code,trade_date,open,high,low,close,change,pct_change,vol,amount,turnover_rate",
                            )
                        else:
                            frame = self.pro.ths_daily(
                                ts_code=ts_code, start_date=_compact_date(start_date, "start_date"),
                                end_date=_compact_date(end_date, "end_date"),
                                fields="ts_code,trade_date,open,high,low,close,pct_change,vol,turnover_rate,total_mv,float_mv",
                            )
                    except Exception:
                        continue
                    bars = []
                    for item in _records(frame):
                        trade_date = _iso_date(item.get("trade_date"))
                        if not trade_date:
                            continue
                        bars.append({
                            "date": trade_date, "open": item.get("open"), "high": item.get("high"), "low": item.get("low"),
                            "close": item.get("close"), "volume": (_float(item.get("vol")) or 0) * 100,
                            "amount": (_float(item.get("amount")) or 0) * 1000,
                            "turnover_rate": item.get("turnover_rate"), "adj_factor": 1.0,
                        })
                    if bars:
                        used_codes.add(ts_code)
                        matches.append({
                            "keyword": keyword, "code": ts_code, "name": found.get("name") or keyword,
                            "matchedName": found.get("name") or keyword,
                            "matchedKeyword": str(alias),
                            "matchRule": "canonical" if str(alias) == keyword else "alias",
                            "source": f"tushare:{provider}_daily", "rows": sorted(bars, key=lambda row: row["date"]),
                        })
                        resolved = True
                        break
                if resolved:
                    break
        return matches


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


def fetch_tushare_hk_rows(
    symbol: str,
    start_date: str | None,
    end_date: str | None,
    *,
    token: str | None = None,
    adjust: str = "raw",
) -> list[dict[str, Any]]:
    if not start_date or not end_date:
        raise LeanWebError("TuShare Hong Kong imports require startDate and endDate.")
    return TushareAdapter(token=token).hk_daily_rows(symbol, start_date, end_date, adjust=adjust)


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
