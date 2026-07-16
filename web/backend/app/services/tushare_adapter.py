from __future__ import annotations

import os
import math
from datetime import datetime, timedelta
from typing import Any

from ..core.errors import LeanWebError
from ..lean_engine.symbols import normalize_symbol
from .ashare_repository import import_security_master, infer_exchange, upsert_trade_calendar


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
                        "is_st": _is_st_name(item.get("name")),
                        "industry": item.get("industry"),
                        "source": "tushare:stock_basic",
                    }
                )
        return records

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
        delisted_date = _iso_date(item.get("delist_date"))
        return {
            "symbol": code, "name": item.get("name") or code, "exchange": infer_exchange(code),
            "listed_date": _iso_date(item.get("list_date")), "delisted_date": delisted_date,
            "status": "delisted" if delisted_date else _status(item.get("list_status")),
            "is_st": _is_st_name(item.get("name")), "industry": item.get("industry"),
            "source": "tushare:stock_basic",
        }

    def daily_basic_rows(self, symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        frame = self.pro.daily_basic(
            ts_code=to_tushare_stock_code(symbol),
            start_date=_compact_date(start_date, "start_date"),
            end_date=_compact_date(end_date, "end_date"),
            fields=(
                "ts_code,trade_date,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,"
                "ps,ps_ttm,dv_ratio,dv_ttm,total_share,float_share,free_share,total_mv,circ_mv"
            ),
        )
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
                        "symbol": from_tushare_code(item.get("ts_code") or symbol),
                        "trade_date": trade_date,
                        "factors": factors,
                        "source": "tushare:daily_basic",
                    }
                )
        return sorted(rows, key=lambda row: (row["trade_date"], row["symbol"]))

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

    def suspend_rows(self, symbol: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        frame = self.pro.suspend_d(
            ts_code=to_tushare_stock_code(symbol),
            start_date=_compact_date(start_date, "start_date"),
            end_date=_compact_date(end_date, "end_date"),
            fields="ts_code,suspend_date,resume_date,ann_date,suspend_reason,reason_type",
        )
        rows: list[dict[str, Any]] = []
        for item in _records(frame):
            suspend_date = _iso_date(item.get("suspend_date"))
            if not suspend_date:
                continue
            rows.append(
                {
                    "symbol": from_tushare_code(item.get("ts_code") or symbol),
                    "suspend_date": suspend_date,
                    "resume_date": _iso_date(item.get("resume_date")),
                    "announce_date": _iso_date(item.get("ann_date")),
                    "reason": item.get("suspend_reason"),
                    "reason_type": item.get("reason_type"),
                    "source": "tushare:suspend_d",
                }
            )
        return sorted(rows, key=lambda row: (row["suspend_date"], row["symbol"]))

    def limit_prices(self, symbol: str, start_date: str, end_date: str) -> dict[str, dict[str, float | None]]:
        result: dict[str, dict[str, float | None]] = {}
        try:
            for window_start, window_end in _date_windows(start_date, end_date):
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
            return {}
        return result

    def _daily_market_records(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        *,
        index: bool = False,
    ) -> list[dict[str, Any]]:
        endpoint = self.pro.index_daily if index else self.pro.daily
        code = to_tushare_index_code(symbol) if index else to_tushare_stock_code(symbol)
        records_by_date: dict[str, dict[str, Any]] = {}
        for window_start, window_end in _date_windows(start_date, end_date):
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
                    "symbol": from_tushare_code(item.get("ts_code") or symbol),
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
        return sorted(rows, key=lambda row: (row["ex_date"], row["symbol"]))

    def index_weight_rows(self, index_code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
        frame = self.pro.index_weight(
            index_code=to_tushare_index_code(index_code),
            start_date=_compact_date(start_date, "start_date"),
            end_date=_compact_date(end_date, "end_date"),
            fields="index_code,con_code,trade_date,weight",
        )
        rows: list[dict[str, Any]] = []
        for item in _records(frame):
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
    ) -> list[dict[str, Any]]:
        if adjust and adjust.lower() not in {"", "raw"}:
            raise LeanWebError("TuShare adapter imports raw daily bars plus adj_factor; do not request qfq/hfq here.")
        is_index = False
        records = self._daily_market_records(symbol, start_date, end_date)
        if not records:
            try:
                records = self._daily_market_records(symbol, start_date, end_date, index=True)
                is_index = True
            except Exception:
                records = []
        if not records:
            return []

        ticker = from_tushare_code(records[0].get("ts_code") or symbol)
        adj_factor_verified = is_index
        try:
            adj_factors = {} if is_index else self.adjustment_factors(ticker, start_date, end_date)
            adj_factor_verified = is_index or len(adj_factors) >= len(records)
        except Exception:
            adj_factors = {}
            adj_factor_verified = False
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

    def sector_daily_rows(self, keywords: list[str], start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Resolve DC first, then THS industry/concept indexes, and return matched index bars."""
        matches: list[dict[str, Any]] = []
        providers = (
            ("dc", lambda: self.pro.dc_index(fields="ts_code,name,publisher,category")),
            ("ths", lambda: self.pro.ths_index(exchange="A", type="N", fields="ts_code,name,count,exchange,list_date,type")),
        )
        for provider, catalogue_call in providers:
            try:
                catalogue = _records(catalogue_call())
            except Exception:
                continue
            for keyword in keywords:
                found = next((item for item in catalogue if keyword.lower() in str(item.get("name") or "").lower()), None)
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
                    matches.append({
                        "keyword": keyword, "code": ts_code, "name": found.get("name") or keyword,
                        "source": f"tushare:{provider}_daily", "rows": sorted(bars, key=lambda row: row["date"]),
                    })
            if matches:
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
