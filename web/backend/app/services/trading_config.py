from __future__ import annotations

from typing import Any


ASHARE_DEFAULTS: dict[str, Any] = {
    "ashareRules": True,
    "ashareStatusFile": "/Lean/Run/ashare_trade_status.json",
    "benchmarkSymbol": "000300",
    "benchmarkMarket": "china",
    "executionPolicy": "next_open",
    "calendarMarket": "china",
    "lotSize": 100,
    "commissionRate": 0.0001,
    "minCommission": 5.0,
    "stampTaxSell": 0.0005,
    "transferFeeRate": 0.00001,
    "slippageBps": 5.0,
    "nextOpenGapBufferBps": 2000.0,
    "maxPositions": None,
    "maxPositionWeight": None,
    "minCash": 0.0,
    "cashBuffer": 0.0,
    "blacklist": [],
    "watchlist": [],
    "observeOnlySymbols": [],
    "allowStBuy": False,
    "constraintVersion": 3,
}


HK_DEFAULTS: dict[str, Any] = {
    "hkRules": True,
    "benchmarkSymbol": "02800",
    "benchmarkMarket": "hongkong",
    "executionPolicy": "next_open",
    "calendarMarket": "hongkong",
    "lotSize": 1,
    "commissionRate": 0.0003,
    "minCommission": 3.0,
    "stampTaxBuy": 0.001,
    "stampTaxSell": 0.001,
    "sfcLevyRate": 0.000027,
    "afrcLevyRate": 0.0000015,
    "exchangeTradingFeeRate": 0.0000565,
    "settlementFeeRate": 0.000042,
    "slippageBps": 5.0,
    # Hong Kong has no mainland-style daily price limit. Reserve the same
    # conservative overnight capacity used by the A-share next-open path.
    "nextOpenGapBufferBps": 2000.0,
    "minCash": 0.0,
    "cashBuffer": 0.0,
    "feeScheduleVersion": "hkex-2026",
    "constraintVersion": 1,
}


def _first_value(primary: dict[str, Any], fallback: dict[str, Any] | None, *keys: str, default: Any = None) -> Any:
    for source in (primary, fallback or {}):
        for key in keys:
            if key in source and source.get(key) not in (None, ""):
                return source[key]
    return default


def _float_value(primary: dict[str, Any], fallback: dict[str, Any] | None, *keys: str, default: float | None = None) -> float | None:
    value = _first_value(primary, fallback, *keys, default=default)
    return None if value is None else float(value)


def _int_value(primary: dict[str, Any], fallback: dict[str, Any] | None, *keys: str, default: int | None = None) -> int | None:
    value = _first_value(primary, fallback, *keys, default=default)
    return None if value is None else int(float(value))


def _bool_value(primary: dict[str, Any], fallback: dict[str, Any] | None, key: str, default: bool = False) -> bool:
    value = _first_value(primary, fallback, key, default=default)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _symbol_list(primary: dict[str, Any], fallback: dict[str, Any] | None, *keys: str) -> list[str]:
    value = _first_value(primary, fallback, *keys, default=[])
    if value is None:
        return []
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        items = value
    else:
        items = [value]
    return sorted({str(item).strip().upper() for item in items if str(item).strip()})


def ashare_trading_config(parameters: dict[str, Any] | None = None, request_data: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(parameters or {})
    request = dict(request_data or {})
    min_cash = _float_value(params, request, "minCash", "min_cash", "cashFloor", default=ASHARE_DEFAULTS["minCash"])
    cash_buffer = _float_value(params, request, "cashBuffer", "cash_buffer", default=min_cash or ASHARE_DEFAULTS["cashBuffer"])
    return {
        "ashareRules": True,
        "ashareStatusFile": str(_first_value(params, request, "ashareStatusFile", default=ASHARE_DEFAULTS["ashareStatusFile"])),
        "benchmarkSymbol": str(_first_value(params, request, "benchmarkSymbol", default=ASHARE_DEFAULTS["benchmarkSymbol"])).upper(),
        "benchmarkMarket": "china",
        "executionPolicy": str(_first_value(params, request, "executionPolicy", "execution_policy", default=ASHARE_DEFAULTS["executionPolicy"])),
        "calendarMarket": "china",
        "lotSize": _int_value(params, request, "lotSize", "lot_size", default=ASHARE_DEFAULTS["lotSize"]),
        "commissionRate": _float_value(params, request, "commissionRate", "commission_rate", default=ASHARE_DEFAULTS["commissionRate"]),
        "minCommission": _float_value(params, request, "minCommission", "min_commission", default=ASHARE_DEFAULTS["minCommission"]),
        "stampTaxSell": _float_value(params, request, "stampTaxSell", "stamp_tax_sell", default=ASHARE_DEFAULTS["stampTaxSell"]),
        "transferFeeRate": _float_value(params, request, "transferFeeRate", "transfer_fee_rate", default=ASHARE_DEFAULTS["transferFeeRate"]),
        "slippageBps": _float_value(params, request, "slippageBps", "slippage_bps", default=ASHARE_DEFAULTS["slippageBps"]),
        "nextOpenGapBufferBps": _float_value(
            params,
            request,
            "nextOpenGapBufferBps",
            "next_open_gap_buffer_bps",
            default=ASHARE_DEFAULTS["nextOpenGapBufferBps"],
        ),
        "maxPositions": _int_value(params, request, "maxPositions", "max_positions", "maxHoldings", default=ASHARE_DEFAULTS["maxPositions"]),
        "maxPositionWeight": _float_value(params, request, "maxPositionWeight", "max_position_weight", "singleStockMaxWeight", default=ASHARE_DEFAULTS["maxPositionWeight"]),
        "minCash": min_cash,
        "cashBuffer": cash_buffer,
        "blacklist": _symbol_list(params, request, "blacklist", "blacklistSymbols", "blockedSymbols"),
        "watchlist": _symbol_list(params, request, "watchlist", "watchlistSymbols", "observableSymbols"),
        "observeOnlySymbols": _symbol_list(params, request, "observeOnlySymbols", "observe_only_symbols", "observeOnly"),
        "allowStBuy": _bool_value(params, request, "allowStBuy", default=ASHARE_DEFAULTS["allowStBuy"]),
        "constraintVersion": ASHARE_DEFAULTS["constraintVersion"],
    }


def merge_ashare_trading_config(parameters: dict[str, Any], request_data: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(parameters)
    merged.update(ashare_trading_config(merged, request_data))
    return merged


def hk_trading_config(parameters: dict[str, Any] | None = None, request_data: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(parameters or {})
    request = dict(request_data or {})
    min_cash = _float_value(params, request, "minCash", "min_cash", "cashFloor", default=HK_DEFAULTS["minCash"])
    cash_buffer = _float_value(params, request, "cashBuffer", "cash_buffer", default=min_cash or HK_DEFAULTS["cashBuffer"])
    return {
        "hkRules": True,
        "benchmarkSymbol": str(_first_value(params, request, "benchmarkSymbol", default=HK_DEFAULTS["benchmarkSymbol"])).upper(),
        "benchmarkMarket": "hongkong",
        "executionPolicy": str(_first_value(params, request, "executionPolicy", "execution_policy", default=HK_DEFAULTS["executionPolicy"])),
        "calendarMarket": "hongkong",
        "lotSize": _int_value(params, request, "lotSize", "lot_size", default=HK_DEFAULTS["lotSize"]),
        "commissionRate": _float_value(params, request, "commissionRate", "commission_rate", default=HK_DEFAULTS["commissionRate"]),
        "minCommission": _float_value(params, request, "minCommission", "min_commission", default=HK_DEFAULTS["minCommission"]),
        "stampTaxBuy": _float_value(params, request, "stampTaxBuy", "stamp_tax_buy", default=HK_DEFAULTS["stampTaxBuy"]),
        "stampTaxSell": _float_value(params, request, "stampTaxSell", "stamp_tax_sell", default=HK_DEFAULTS["stampTaxSell"]),
        "sfcLevyRate": _float_value(params, request, "sfcLevyRate", "sfc_levy_rate", default=HK_DEFAULTS["sfcLevyRate"]),
        "afrcLevyRate": _float_value(params, request, "afrcLevyRate", "afrc_levy_rate", default=HK_DEFAULTS["afrcLevyRate"]),
        "exchangeTradingFeeRate": _float_value(
            params, request, "exchangeTradingFeeRate", "exchange_trading_fee_rate", default=HK_DEFAULTS["exchangeTradingFeeRate"]
        ),
        "settlementFeeRate": _float_value(params, request, "settlementFeeRate", "settlement_fee_rate", default=HK_DEFAULTS["settlementFeeRate"]),
        "slippageBps": _float_value(params, request, "slippageBps", "slippage_bps", default=HK_DEFAULTS["slippageBps"]),
        "nextOpenGapBufferBps": _float_value(
            params, request, "nextOpenGapBufferBps", "next_open_gap_buffer_bps", default=HK_DEFAULTS["nextOpenGapBufferBps"]
        ),
        "minCash": min_cash,
        "cashBuffer": cash_buffer,
        "feeScheduleVersion": HK_DEFAULTS["feeScheduleVersion"],
        "constraintVersion": HK_DEFAULTS["constraintVersion"],
    }


def merge_hk_trading_config(parameters: dict[str, Any], request_data: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(parameters)
    merged.update(hk_trading_config(merged, request_data))
    return merged
