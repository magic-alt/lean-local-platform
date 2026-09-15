from __future__ import annotations

import math
from typing import Any

from ..core.errors import LeanWebError
from .provider_contracts import (
    CanonicalBatch,
    CanonicalUnits,
    ProviderAuthContract,
    ProviderDataClass,
    ProviderDescriptor,
    ProviderErrorCode,
    ProviderIssue,
    QuarantinedRecord,
)


BAOSTOCK_DAILY_DESCRIPTOR = ProviderDescriptor(
    provider="baostock",
    adapter_version="1",
    data_classes=(ProviderDataClass.HISTORICAL_DATA,),
    asset_classes=("equity",),
    markets=("china",),
    frequencies=("1d",),
    historical_coverage="provider_defined",
    adjustment_modes=("raw", "qfq", "hfq"),
    pit_availability="end_of_day_provider_snapshot",
    transports=("historical",),
    pagination="provider_cursor",
    rate_limit="provider_defined",
    license="provider_terms",
    redistribution="not_asserted_by_adapter",
    auth=ProviderAuthContract(
        mode="anonymous_login",
        required=False,
        account_scope="anonymous",
        entitlement_scope=("china_equity_daily",),
    ),
    health="runtime_probe_required",
    cross_source_caveats=(
        "Baostock is research/cross-source QA only and is not China production-certified.",
        "Adjustment and volume semantics must be reconciled before cross-provider comparison.",
    ),
    production_certified=False,
)


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


def _baostock_units(adjust: str) -> CanonicalUnits:
    return CanonicalUnits(
        price_currency="CNY",
        volume_unit="share",
        amount_unit="CNY",
        timezone="Asia/Shanghai",
        adjustment=adjust or "raw",
    )


def _numeric_issue(
    value: Any,
    *,
    field: str,
    positive: bool,
    allow_negative: bool = False,
) -> tuple[float | None, ProviderIssue | None]:
    if value in (None, ""):
        return None, ProviderIssue(
            code=ProviderErrorCode.MISSING_FIELD,
            message=f"Provider row is missing required numeric field {field}.",
            field=field,
        )
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None, ProviderIssue(
            code=ProviderErrorCode.INVALID_VALUE,
            message=f"Provider row contains a non-numeric value for {field}.",
            field=field,
        )
    if not math.isfinite(parsed):
        return None, ProviderIssue(
            code=ProviderErrorCode.NON_FINITE_VALUE,
            message=f"Provider row contains a non-finite value for {field}.",
            field=field,
        )
    if positive and parsed <= 0:
        return None, ProviderIssue(
            code=ProviderErrorCode.INVALID_VALUE,
            message=f"Provider row requires {field} to be greater than zero.",
            field=field,
        )
    if not positive and not allow_negative and parsed < 0:
        return None, ProviderIssue(
            code=ProviderErrorCode.INVALID_VALUE,
            message=f"Provider row requires {field} to be non-negative.",
            field=field,
        )
    return parsed, None


def _optional_numeric_issue(
    value: Any,
    *,
    field: str,
    positive: bool = False,
    allow_negative: bool = False,
) -> tuple[float | None, ProviderIssue | None]:
    if value in (None, ""):
        return None, None
    return _numeric_issue(
        value,
        field=field,
        positive=positive,
        allow_negative=allow_negative,
    )


def normalize_baostock_daily_batch(
    symbol: str,
    rows: list[dict[str, Any]],
    *,
    adjust: str = "raw",
) -> CanonicalBatch[dict[str, str]]:
    """Normalize Baostock daily bars without converting invalid values to valid zeros."""

    normalized: list[dict[str, str]] = []
    quarantined: list[QuarantinedRecord] = []
    for row_index, row in enumerate(rows):
        issues: list[ProviderIssue] = []
        date_value = _first_value(row, "date", "trade_date")
        normalized_date: str | None = None
        if date_value in (None, ""):
            issues.append(
                ProviderIssue(
                    code=ProviderErrorCode.MISSING_FIELD,
                    message="Provider row is missing required date field.",
                    field="date",
                )
            )
        else:
            try:
                normalized_date = _date(date_value)
            except LeanWebError:
                issues.append(
                    ProviderIssue(
                        code=ProviderErrorCode.INVALID_VALUE,
                        message="Provider row contains an invalid date value.",
                        field="date",
                    )
                )

        values: dict[str, float | None] = {}
        numeric_fields = {
            "open": (_first_value(row, "open"), True),
            "high": (_first_value(row, "high"), True),
            "low": (_first_value(row, "low"), True),
            "close": (_first_value(row, "close"), True),
            "volume": (_first_value(row, "volume", "vol"), False),
        }
        for field, (raw_value, positive) in numeric_fields.items():
            parsed, issue = _numeric_issue(raw_value, field=field, positive=positive)
            values[field] = parsed
            if issue:
                issues.append(issue)

        optional_fields = {
            "amount": (_first_value(row, "amount"), False, False),
            "prev_close": (_first_value(row, "preclose", "prev_close", "pre_close"), True, False),
            "pct_change": (_first_value(row, "pctChg", "pct_change"), False, True),
            "turnover_rate": (_first_value(row, "turn", "turnover_rate"), False, False),
        }
        for field, (raw_value, positive, allow_negative) in optional_fields.items():
            parsed, issue = _optional_numeric_issue(
                raw_value,
                field=field,
                positive=positive,
                allow_negative=allow_negative,
            )
            values[field] = parsed
            if issue:
                issues.append(issue)

        if issues:
            quarantined.append(
                QuarantinedRecord(
                    row_index=row_index,
                    issues=tuple(issues),
                    source_fields=tuple(sorted(str(key) for key in row.keys())),
                )
            )
            continue

        item = {
            "symbol": _symbol6(symbol),
            "date": normalized_date or "",
            "open": str(values["open"]),
            "high": str(values["high"]),
            "low": str(values["low"]),
            "close": str(values["close"]),
            "volume": str(values["volume"]),
        }
        for field in ("amount", "prev_close", "pct_change", "turnover_rate"):
            if values[field] is not None:
                item[field] = str(values[field])
        normalized.append(item)

    normalized.sort(key=lambda item: item["date"])
    return CanonicalBatch(
        provider="baostock",
        operation="historical_daily_bars",
        descriptor=BAOSTOCK_DAILY_DESCRIPTOR,
        units=_baostock_units(adjust),
        records=normalized,
        quarantined=quarantined,
        source_metadata={
            "symbol": _symbol6(symbol),
            "inputRows": len(rows),
            "acceptedRows": len(normalized),
            "quarantinedRows": len(quarantined),
        },
    )


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


def fetch_baostock_batch(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    adjust: str = "raw",
) -> CanonicalBatch[dict[str, str]]:
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
            raise LeanWebError(
                f"Baostock login failed: {getattr(login, 'error_msg', '')}",
                error_code=ProviderErrorCode.UPSTREAM_ERROR.value.upper(),
                category="data_provider",
                retryable=True,
                status_code=503,
                details={"provider": "baostock", "operation": "login"},
            )
        result = bs.query_history_k_data_plus(
            _baostock_symbol(symbol),
            "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg",
            start_date=start or "",
            end_date=end or "",
            frequency="d",
            adjustflag=adjust_map[adjust],
        )
        if getattr(result, "error_code", "0") != "0":
            raise LeanWebError(
                f"Baostock daily query failed: {getattr(result, 'error_msg', '')}",
                error_code=ProviderErrorCode.UPSTREAM_ERROR.value.upper(),
                category="data_provider",
                retryable=True,
                status_code=503,
                details={"provider": "baostock", "operation": "historical_daily_bars"},
            )
        rows: list[dict[str, Any]] = []
        fields = list(getattr(result, "fields", []))
        while result.next():
            rows.append(dict(zip(fields, result.get_row_data())))
        return normalize_baostock_daily_batch(symbol, rows, adjust=adjust or "raw")
    finally:
        try:
            bs.logout()
        except Exception:
            pass


def fetch_baostock_rows(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    adjust: str = "raw",
) -> list[dict[str, str]]:
    """Backward-compatible row view over the audited CanonicalBatch adapter."""

    return fetch_baostock_batch(symbol, start=start, end=end, adjust=adjust).records
