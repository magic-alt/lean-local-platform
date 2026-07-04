from __future__ import annotations

from datetime import datetime
from typing import Any


class DataQualityError(ValueError):
    def __init__(self, report: dict[str, Any]):
        self.report = report
        super().__init__(self._message(report))

    @staticmethod
    def _message(report: dict[str, Any]) -> str:
        errors = report.get("errors") or []
        if not errors:
            return "Data quality validation failed."
        return "Data quality validation failed: " + "; ".join(str(item) for item in errors[:5])


def _date(value: Any) -> str:
    raw = str(value or "").strip()[:10]
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date().isoformat()
    except ValueError:
        try:
            return datetime.strptime(str(value).strip()[:8], "%Y%m%d").date().isoformat()
        except ValueError as exc:
            raise ValueError(f"invalid date {value!r}") from exc


def _float(value: Any, field: str) -> float:
    if value is None or value == "":
        raise ValueError(f"{field} is required")
    return float(value)


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "y", "on"}:
            return True
        if text in {"0", "false", "no", "n", "off"}:
            return False
    return bool(value)


def _limit_rate(symbol: str, is_st: bool) -> float:
    if is_st:
        return 0.05
    if symbol.startswith(("300", "301", "688", "689")):
        return 0.20
    return 0.10


def _near(value: float, target: float | None, tolerance: float = 0.011) -> bool:
    return target is not None and abs(value - target) <= tolerance


def normalize_ashare_daily_rows(
    symbol: str,
    rows: list[dict[str, Any]],
    *,
    source: str,
    batch_id: str,
    adjust: str = "raw",
    is_st: bool = False,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    previous_close: float | None = None
    for row in rows:
        trade_date = _date(row.get("trade_date") or row.get("date") or row.get("timestamp"))
        open_price = _float(row.get("open"), "open")
        high = _float(row.get("high"), "high")
        low = _float(row.get("low"), "low")
        close = _float(row.get("close"), "close")
        volume = _float(row.get("volume", 0), "volume")
        prev_close = _optional_float(row.get("prev_close")) or previous_close
        pct_change = _optional_float(row.get("pct_change"))
        if pct_change is None and prev_close:
            pct_change = (close / prev_close - 1.0) * 100.0
        adj_factor = _optional_float(row.get("adj_factor"))
        if adj_factor is None:
            adj_factor = 1.0
        normalized.append(
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
                "amount": _optional_float(row.get("amount")),
                "turnover_rate": _optional_float(row.get("turnover_rate")),
                "prev_close": prev_close,
                "pct_change": pct_change,
                "adj_factor": adj_factor,
                "adjust": adjust or "raw",
                "source": source,
                "batch_id": batch_id,
                "is_st": bool(row.get("is_st", is_st)),
                "is_suspended": _optional_bool(row.get("is_suspended") if "is_suspended" in row else row.get("isSuspended")),
                "limit_up": _optional_float(row.get("limit_up") if "limit_up" in row else row.get("limitUp")),
                "limit_down": _optional_float(row.get("limit_down") if "limit_down" in row else row.get("limitDown")),
                "is_limit_up": _optional_bool(row.get("is_limit_up") if "is_limit_up" in row else row.get("isLimitUp")),
                "is_limit_down": _optional_bool(row.get("is_limit_down") if "is_limit_down" in row else row.get("isLimitDown")),
                "is_one_word_limit_up": _optional_bool(row.get("is_one_word_limit_up") if "is_one_word_limit_up" in row else row.get("isOneWordLimitUp")),
                "is_one_word_limit_down": _optional_bool(row.get("is_one_word_limit_down") if "is_one_word_limit_down" in row else row.get("isOneWordLimitDown")),
                "can_buy": _optional_bool(row.get("can_buy") if "can_buy" in row else row.get("canBuy")),
                "can_sell": _optional_bool(row.get("can_sell") if "can_sell" in row else row.get("canSell")),
            }
        )
        previous_close = close
    normalized.sort(key=lambda item: item["trade_date"])
    return normalized


def build_ashare_trade_status(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for row in rows:
        is_st = bool(row.get("is_st"))
        prev_close = row.get("prev_close")
        rate = _limit_rate(row["symbol"], is_st)
        inferred_limit_up = round(prev_close * (1.0 + rate), 2) if prev_close else None
        inferred_limit_down = round(prev_close * (1.0 - rate), 2) if prev_close else None
        limit_up = row.get("limit_up") if row.get("limit_up") is not None else inferred_limit_up
        limit_down = row.get("limit_down") if row.get("limit_down") is not None else inferred_limit_down
        is_suspended = row.get("is_suspended") if row.get("is_suspended") is not None else row["volume"] == 0
        inferred_limit_up_flag = _near(row["close"], limit_up) or _near(row["high"], limit_up)
        inferred_limit_down_flag = _near(row["close"], limit_down) or _near(row["low"], limit_down)
        is_limit_up = row.get("is_limit_up") if row.get("is_limit_up") is not None else inferred_limit_up_flag
        is_limit_down = row.get("is_limit_down") if row.get("is_limit_down") is not None else inferred_limit_down_flag
        inferred_one_word_up = is_limit_up and _near(row["open"], limit_up) and _near(row["low"], limit_up)
        inferred_one_word_down = is_limit_down and _near(row["open"], limit_down) and _near(row["high"], limit_down)
        is_one_word_limit_up = row.get("is_one_word_limit_up") if row.get("is_one_word_limit_up") is not None else inferred_one_word_up
        is_one_word_limit_down = row.get("is_one_word_limit_down") if row.get("is_one_word_limit_down") is not None else inferred_one_word_down
        can_buy = row.get("can_buy") if row.get("can_buy") is not None else not is_suspended and not is_limit_up
        can_sell = row.get("can_sell") if row.get("can_sell") is not None else not is_suspended and not is_limit_down
        statuses.append(
            {
                "symbol": row["symbol"],
                "trade_date": row["trade_date"],
                "is_suspended": is_suspended,
                "limit_up": limit_up,
                "limit_down": limit_down,
                "is_limit_up": is_limit_up,
                "is_limit_down": is_limit_down,
                "is_one_word_limit_up": is_one_word_limit_up,
                "is_one_word_limit_down": is_one_word_limit_down,
                "can_buy": can_buy,
                "can_sell": can_sell,
                "is_st": is_st,
            }
        )
    return statuses


def validate_ashare_daily_rows(
    rows: list[dict[str, Any]],
    *,
    calendar_dates: list[str] | None = None,
    source: str,
    batch_id: str,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    duplicate_dates: list[str] = []
    ohlc_errors: list[dict[str, Any]] = []
    negative_or_zero_price_rows: list[str] = []
    negative_volume_rows: list[str] = []
    adj_factor_errors: list[str] = []
    volume_zero_rows: list[str] = []

    if not rows:
        errors.append("empty_dataset")

    seen: set[str] = set()
    row_dates: set[str] = set()
    for row in rows:
        trade_date = row.get("trade_date")
        row_dates.add(trade_date)
        if trade_date in seen:
            duplicate_dates.append(trade_date)
        seen.add(trade_date)
        if min(row["open"], row["high"], row["low"], row["close"]) <= 0:
            negative_or_zero_price_rows.append(trade_date)
        if row["volume"] < 0:
            negative_volume_rows.append(trade_date)
        if row["high"] < row["low"] or row["open"] > row["high"] or row["open"] < row["low"] or row["close"] > row["high"] or row["close"] < row["low"]:
            ohlc_errors.append(
                {
                    "trade_date": trade_date,
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                }
            )
        if row.get("adj_factor") is not None and row["adj_factor"] <= 0:
            adj_factor_errors.append(trade_date)
        if row["volume"] == 0:
            volume_zero_rows.append(trade_date)

    if duplicate_dates:
        errors.append(f"duplicate_dates={duplicate_dates[:10]}")
    if ohlc_errors:
        errors.append(f"ohlc_errors={len(ohlc_errors)}")
    if negative_or_zero_price_rows:
        errors.append(f"non_positive_prices={negative_or_zero_price_rows[:10]}")
    if negative_volume_rows:
        errors.append(f"negative_volume={negative_volume_rows[:10]}")
    if adj_factor_errors:
        errors.append(f"invalid_adj_factor={adj_factor_errors[:10]}")

    missing_trade_dates: list[str] = []
    if calendar_dates and row_dates:
        first_date = min(row_dates)
        last_date = max(row_dates)
        expected = {item for item in calendar_dates if first_date <= item <= last_date}
        missing_trade_dates = sorted(expected - row_dates)
        if missing_trade_dates:
            errors.append(f"missing_trade_dates={missing_trade_dates[:10]}")
    else:
        warnings.append("trade_calendar_inferred_from_import_rows")
    if volume_zero_rows:
        warnings.append(f"zero_volume_rows={volume_zero_rows[:10]}")

    return {
        "source": source,
        "batch_id": batch_id,
        "row_count": len(rows),
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "duplicate_dates": duplicate_dates,
        "missing_trade_dates": missing_trade_dates,
        "ohlc_errors": ohlc_errors[:100],
        "negative_or_zero_price_rows": negative_or_zero_price_rows,
        "negative_volume_rows": negative_volume_rows,
        "adj_factor_errors": adj_factor_errors,
        "volume_zero_rows": volume_zero_rows,
    }


def assert_quality_passed(report: dict[str, Any]) -> None:
    if not report.get("passed", False):
        raise DataQualityError(report)
