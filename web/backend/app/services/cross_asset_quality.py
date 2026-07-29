from __future__ import annotations

from datetime import datetime
import json
import math
from typing import Any

from ..db import db, rows_to_dicts


CROSS_ASSET_DATASETS = {
    "fund_basic",
    "fund_daily",
    "fund_nav",
    "cb_basic",
    "cb_daily",
    "cb_call",
    "fut_basic",
    "fut_daily",
    "fut_mapping",
    "opt_basic",
    "opt_daily",
}
DAILY_DATASETS = {"fund_daily", "cb_daily", "fut_daily", "opt_daily"}
DERIVATIVE_DAILY_DATASETS = {"fut_daily", "opt_daily"}
VALID_FUTURES_EXCHANGES = {"CFFEX", "DCE", "CZCE", "SHFE", "INE", "GFEX"}
VALID_OPTION_EXCHANGES = {"SSE", "SZSE", *VALID_FUTURES_EXCHANGES}


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        output = float(value)
    except (TypeError, ValueError):
        return None
    return output if math.isfinite(output) else None


def _date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt, candidate in (("%Y-%m-%d", text[:10]), ("%Y%m%d", text[:8])):
        try:
            return datetime.strptime(candidate, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _value(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value in (None, ""):
            continue
        if isinstance(value, float) and not math.isfinite(value):
            continue
        if isinstance(value, str) and value.strip().lower() in {"nan", "nat", "none", "null"}:
            continue
        return value
    return None


def _issue(row: int, code: str, **details: Any) -> dict[str, Any]:
    return {"row": row, "code": code, **details}


def _positive(
    errors: list[dict[str, Any]],
    row_index: int,
    row: dict[str, Any],
    field: str,
    *aliases: str,
    required: bool = True,
) -> float | None:
    raw = _value(row, field, *aliases)
    value = _number(raw)
    if raw in (None, "") and not required:
        return None
    if value is None or value <= 0:
        errors.append(_issue(row_index, "invalid_positive_value", field=field, value=str(raw)[:80]))
    return value


def _non_negative(
    errors: list[dict[str, Any]],
    row_index: int,
    row: dict[str, Any],
    field: str,
    *aliases: str,
    required: bool = False,
) -> float | None:
    raw = _value(row, field, *aliases)
    value = _number(raw)
    if raw in (None, ""):
        if required:
            errors.append(_issue(row_index, "missing_required_metric", field=field))
        return None
    if value is None or value < 0:
        errors.append(_issue(row_index, "invalid_non_negative_value", field=field, value=str(raw)[:80]))
    return value


def _date_order(
    errors: list[dict[str, Any]],
    row_index: int,
    row: dict[str, Any],
    start_names: tuple[str, ...],
    end_names: tuple[str, ...],
    code: str,
    *,
    required: bool = False,
) -> None:
    start_raw = _value(row, *start_names)
    end_raw = _value(row, *end_names)
    start = _date(start_raw)
    end = _date(end_raw)
    if required and start is None:
        errors.append(_issue(row_index, "missing_or_invalid_date", field=start_names[0], value=str(start_raw)[:80]))
    if required and end is None:
        errors.append(_issue(row_index, "missing_or_invalid_date", field=end_names[0], value=str(end_raw)[:80]))
    if start and end and start > end:
        errors.append(_issue(row_index, code, start=start, end=end))


def _daily_gate(dataset_key: str, rows: list[dict[str, Any]], errors: list[dict[str, Any]]) -> None:
    for index, row in enumerate(rows):
        open_price = _positive(errors, index, row, "open")
        high = _positive(errors, index, row, "high")
        low = _positive(errors, index, row, "low")
        close = _positive(errors, index, row, "close")
        if all(value is not None and value > 0 for value in (open_price, high, low, close)):
            if high < low or not low <= open_price <= high or not low <= close <= high:
                errors.append(
                    _issue(
                        index,
                        "ohlc_invariant_failed",
                        open=open_price,
                        high=high,
                        low=low,
                        close=close,
                    )
                )
        _non_negative(errors, index, row, "volume", "vol", required=True)
        _non_negative(errors, index, row, "amount")
        if dataset_key in DERIVATIVE_DAILY_DATASETS:
            _positive(errors, index, row, "settle", "settle_price")
            _non_negative(errors, index, row, "open_interest", "oi", required=True)


def validate_cross_asset_rows(dataset_key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply fail-closed ETF, convertible-bond, futures and options rules."""
    key = str(dataset_key or "").strip().lower()
    if key not in CROSS_ASSET_DATASETS:
        return {"applied": False, "assetClass": None, "criticalErrors": [], "warnings": [], "checkedRows": len(rows)}

    asset_class = (
        "etf"
        if key.startswith("fund_")
        else "convertible_bond"
        if key.startswith("cb_")
        else "future"
        if key.startswith("fut_")
        else "option"
    )
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    if key in DAILY_DATASETS:
        _daily_gate(key, rows, errors)

    for index, row in enumerate(rows):
        if key == "fund_basic":
            name = str(_value(row, "name", "fund_name") or "")
            fund_type = str(_value(row, "fund_type", "type", "invest_type") or "")
            is_etf = "ETF" in name.upper() or "ETF" in fund_type.upper() or str(row.get("market") or "").upper() == "E"
            if is_etf:
                if _date(_value(row, "list_date", "listed_date")) is None:
                    errors.append(_issue(index, "etf_list_date_missing"))
                if not name:
                    errors.append(_issue(index, "etf_name_missing"))
            else:
                warnings.append(_issue(index, "non_etf_fund_row"))
            _date_order(
                errors,
                index,
                row,
                ("list_date", "listed_date"),
                ("delist_date", "delisted_date"),
                "fund_lifecycle_invalid",
            )
        elif key == "fund_nav":
            _positive(errors, index, row, "unit_nav", "nav", required=True)
            accumulated = _number(_value(row, "accum_nav", "accumulated_nav"))
            unit_nav = _number(_value(row, "unit_nav", "nav"))
            if accumulated is not None and unit_nav is not None and accumulated + 1e-9 < unit_nav:
                errors.append(_issue(index, "accumulated_nav_below_unit_nav", unitNav=unit_nav, accumulatedNav=accumulated))
        elif key == "cb_basic":
            if not _value(row, "stk_code", "stock_code", "underlying_symbol"):
                errors.append(_issue(index, "convertible_underlying_missing"))
            _positive(errors, index, row, "conv_price", "first_conv_price", "conversion_price")
            _positive(errors, index, row, "par", "par_value")
            _date_order(
                errors,
                index,
                row,
                ("list_date", "listed_date"),
                ("maturity_date", "delist_date"),
                "convertible_lifecycle_invalid",
                required=True,
            )
            _date_order(
                errors,
                index,
                row,
                ("conv_start_date",),
                ("conv_end_date",),
                "conversion_window_invalid",
                required=True,
            )
        elif key == "cb_daily":
            _positive(errors, index, row, "close")
            premium = _number(_value(row, "premium_rate", "cb_over_rate"))
            if premium is not None and abs(premium) > 5:
                errors.append(_issue(index, "convertible_premium_out_of_range", value=premium))
            remaining = _number(_value(row, "remain_size", "remaining_size"))
            if remaining is not None and remaining < 0:
                errors.append(_issue(index, "negative_remaining_size", value=remaining))
        elif key == "cb_call":
            if not _date(_value(row, "ann_date", "announce_date")):
                errors.append(_issue(index, "call_announce_date_missing"))
            if not _value(row, "call_type", "status"):
                errors.append(_issue(index, "call_type_missing"))
        elif key == "fut_basic":
            exchange = str(row.get("exchange") or "").upper()
            if exchange not in VALID_FUTURES_EXCHANGES:
                errors.append(_issue(index, "unsupported_futures_exchange", exchange=exchange))
            listed = _date(_value(row, "list_date", "listed_date"))
            delisted = _date(_value(row, "last_ddate", "last_trade_date", "delist_date"))
            if listed or delisted:
                _positive(errors, index, row, "multiplier", "per_unit")
                _date_order(
                    errors,
                    index,
                    row,
                    ("list_date", "listed_date"),
                    ("last_ddate", "last_trade_date", "delist_date"),
                    "futures_lifecycle_invalid",
                    required=True,
                )
            else:
                # TuShare includes continuous/main-contract aliases in
                # fut_basic. They are useful catalog entries but do not carry
                # an individual contract lifecycle or contract unit.
                warnings.append(_issue(index, "futures_continuous_catalog_row"))
        elif key == "fut_mapping":
            if not _value(row, "mapping_ts_code", "mapping_code", "main_symbol", "con_code"):
                errors.append(_issue(index, "mapped_contract_missing"))
        elif key == "opt_basic":
            exchange = str(row.get("exchange") or "").upper()
            if exchange not in VALID_OPTION_EXCHANGES:
                errors.append(_issue(index, "unsupported_option_exchange", exchange=exchange))
            call_put = str(_value(row, "call_put", "option_right") or "").upper()
            if call_put not in {"C", "P", "CALL", "PUT", "认购", "认沽"}:
                errors.append(_issue(index, "option_right_invalid", value=call_put))
            _positive(errors, index, row, "exercise_price", "strike")
            _positive(errors, index, row, "per_unit", "multiplier")
            _positive(errors, index, row, "min_price_chg", "tick_size")
            _date_order(
                errors,
                index,
                row,
                ("list_date", "listed_date"),
                ("last_edate", "maturity_date", "expiry_date"),
                "option_lifecycle_invalid",
                required=True,
            )

    return {
        "applied": True,
        "assetClass": asset_class,
        "status": "failed" if errors else "warning" if warnings else "passed",
        "criticalErrors": errors[:100],
        "warnings": warnings[:100],
        "checkedRows": len(rows),
        "rejectedRows": len({item["row"] for item in errors}),
        "rulesVersion": "cross-asset-quality-v1",
    }


def latest_cross_asset_quality_status() -> dict[str, Any]:
    """Expose the latest persisted manifest gate for every governed dataset."""
    with db() as connection:
        rows = connection.execute(
            """
            select m.dataset_key,m.run_id,m.scope_key,m.response_rows,m.rejected_rows,
                   m.status,m.validation_json,m.coverage_start,m.coverage_end,m.created_at
            from provider_ingestion_manifests m
            where m.dataset_key in (
                'fund_basic','fund_daily','fund_nav','cb_basic','cb_daily','cb_call',
                'fut_basic','fut_daily','fut_mapping','opt_basic','opt_daily'
            )
              and m.created_at=(
                  select max(m2.created_at) from provider_ingestion_manifests m2
                  where m2.dataset_key=m.dataset_key
              )
            order by m.dataset_key
            """
        ).fetchall()
    items = rows_to_dicts(rows)
    by_key = {str(item["dataset_key"]): item for item in items}
    output = []
    for key in sorted(CROSS_ASSET_DATASETS):
        item = by_key.get(key)
        if not item:
            output.append({"datasetKey": key, "status": "missing", "passed": False, "rulesVersion": "cross-asset-quality-v1"})
            continue
        validation = item.get("validation") or {}
        asset_gate = validation.get("assetQuality") or {}
        output.append(
            {
                "datasetKey": key,
                "runId": item.get("run_id"),
                "scopeKey": item.get("scope_key"),
                "status": asset_gate.get("status") or item.get("status"),
                "passed": bool(asset_gate.get("applied") and not asset_gate.get("criticalErrors")),
                "checkedRows": asset_gate.get("checkedRows"),
                "rejectedRows": asset_gate.get("rejectedRows", item.get("rejected_rows")),
                "coverageStart": item.get("coverage_start"),
                "coverageEnd": item.get("coverage_end"),
                "createdAt": item.get("created_at"),
                "rulesVersion": asset_gate.get("rulesVersion") or "cross-asset-quality-v1",
                "criticalErrors": asset_gate.get("criticalErrors") or [],
                "warnings": asset_gate.get("warnings") or [],
            }
        )
    return {
        "rulesVersion": "cross-asset-quality-v1",
        "passed": all(item["passed"] for item in output),
        "items": output,
        "count": len(output),
    }
