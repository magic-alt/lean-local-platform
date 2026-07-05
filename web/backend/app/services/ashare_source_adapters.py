from __future__ import annotations

from typing import Any

from ..core.errors import LeanWebError


def _date(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    raise LeanWebError(f"Invalid A-share date value from provider: {value!r}")


def _float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _symbol6(symbol: str) -> str:
    value = symbol.strip().upper()
    if value.startswith(("SH", "SZ", "BJ")):
        return value[2:]
    if "." in value:
        return value.split(".", 1)[0]
    return value


def _baostock_symbol(symbol: str) -> str:
    value = _symbol6(symbol)
    if value.startswith(("6", "9")):
        return f"sh.{value}"
    return f"sz.{value}"


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row:
            return row[key]
        value = lowered.get(key.lower())
        if value is not None:
            return value
    return None


def _records(frame_or_records: Any) -> list[dict[str, Any]]:
    if frame_or_records is None:
        return []
    if isinstance(frame_or_records, list):
        return [dict(item) for item in frame_or_records]
    if hasattr(frame_or_records, "to_dict"):
        try:
            return [dict(item) for item in frame_or_records.to_dict("records")]
        except TypeError:
            value = frame_or_records.to_dict()
            if isinstance(value, list):
                return [dict(item) for item in value]
            if isinstance(value, dict):
                return [dict(zip(value.keys(), values)) for values in zip(*value.values())]
    raise LeanWebError("Provider returned an unsupported table shape.")


def _normalize_daily_records(symbol: str, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for row in rows:
        date_value = _first_value(row, "trade_date", "date", "trade_time", "datetime", "time")
        open_value = _first_value(row, "open", "开盘", "open_price")
        high_value = _first_value(row, "high", "最高", "high_price")
        low_value = _first_value(row, "low", "最低", "low_price")
        close_value = _first_value(row, "close", "收盘", "close_price")
        volume_value = _first_value(row, "volume", "vol", "成交量")
        amount_value = _first_value(row, "amount", "成交额")
        if date_value is None or open_value is None or high_value is None or low_value is None or close_value is None:
            continue
        item = {
            "symbol": _symbol6(symbol),
            "date": _date(date_value),
            "open": str(_float(open_value, 0) or 0),
            "high": str(_float(high_value, 0) or 0),
            "low": str(_float(low_value, 0) or 0),
            "close": str(_float(close_value, 0) or 0),
            "volume": str(_float(volume_value, 0) or 0),
        }
        amount = _float(amount_value)
        if amount is not None:
            item["amount"] = str(amount)
        prev_close = _float(_first_value(row, "prev_close", "preclose", "pre_close", "昨收"))
        if prev_close is not None:
            item["prev_close"] = str(prev_close)
        pct_change = _float(_first_value(row, "pct_change", "pctChg", "涨跌幅"))
        if pct_change is not None:
            item["pct_change"] = str(pct_change)
        turnover_rate = _float(_first_value(row, "turnover_rate", "turn", "换手率"))
        if turnover_rate is not None:
            item["turnover_rate"] = str(turnover_rate)
        normalized.append(item)
    normalized.sort(key=lambda item: item["date"])
    return normalized


def fetch_adata_rows(symbol: str, start: str | None = None, end: str | None = None, adjust: str = "raw") -> list[dict[str, str]]:
    if adjust and adjust != "raw":
        raise LeanWebError("AData adapter currently only imports raw A-share daily bars to avoid mixed adjustment modes.")
    try:
        import adata  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency.
        raise LeanWebError("adata is not installed. Install it before using provider=adata.") from exc
    symbol6 = _symbol6(symbol)
    market_api = getattr(getattr(getattr(adata, "stock", None), "market", None), "get_market", None)
    if market_api is None:
        raise LeanWebError("Installed adata package does not expose adata.stock.market.get_market.")
    attempts = [
        {"stock_code": symbol6, "start_date": start, "end_date": end, "k_type": 1, "adjust_type": 0},
        {"stock_code": symbol6, "start_date": start, "end_date": end, "k_type": 1},
        {"stock_code": symbol6, "start_date": start, "end_date": end},
        {"stock_code": symbol6},
    ]
    last_error: Exception | None = None
    for params in attempts:
        clean_params = {key: value for key, value in params.items() if value is not None}
        try:
            return _normalize_daily_records(symbol6, _records(market_api(**clean_params)))
        except TypeError as exc:
            last_error = exc
            continue
    raise LeanWebError(f"AData market API call failed: {last_error}") from last_error


def fetch_baostock_rows(symbol: str, start: str | None = None, end: str | None = None, adjust: str = "raw") -> list[dict[str, str]]:
    adjust_map = {"raw": "3", "": "3", "qfq": "2", "hfq": "1"}
    if adjust not in adjust_map:
        raise LeanWebError(f"Unsupported Baostock adjust value: {adjust!r}")
    try:
        import baostock as bs  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency.
        raise LeanWebError("baostock is not installed. Install it before using provider=baostock.") from exc
    login = bs.login()
    try:
        if getattr(login, "error_code", "0") != "0":
            raise LeanWebError(f"Baostock login failed: {getattr(login, 'error_msg', '')}")
        result = bs.query_history_k_data_plus(
            _baostock_symbol(symbol),
            "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg",
            start_date=start or "",
            end_date=end or "",
            frequency="d",
            adjustflag=adjust_map[adjust],
        )
        if getattr(result, "error_code", "0") != "0":
            raise LeanWebError(f"Baostock daily query failed: {getattr(result, 'error_msg', '')}")
        rows: list[dict[str, Any]] = []
        fields = list(getattr(result, "fields", []))
        while result.next():
            rows.append(dict(zip(fields, result.get_row_data())))
        return _normalize_daily_records(symbol, rows)
    finally:
        try:
            bs.logout()
        except Exception:
            pass
