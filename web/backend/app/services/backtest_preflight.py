from __future__ import annotations

from typing import Any, Callable

from ..lean_engine.config import validate_backtest_parameters
from ..lean_engine.errors import LeanPlatformError
from .ashare_multisource import quality_gate_range
from .ashare_repository import assert_ashare_ready, assert_benchmark_ready, data_coverage
from .benchmark import fetch_and_import_benchmark
from .data import fetch_and_import_symbol
from .data_provider_manager import DATA_PROVIDER_MANAGER
from .source_gate import DEFAULT_PRODUCTION_SOURCE, apply_source_context, resolve_source_context
from .market_repository import get_instrument, market_data_coverage
from .trading_config import merge_ashare_trading_config, merge_hk_trading_config


def _parameters(request_data: dict[str, Any]) -> dict[str, Any]:
    template_parameters = dict(request_data.get("parameters") or {})
    if request_data.get("fast") is not None:
        template_parameters["fast"] = request_data["fast"]
    if request_data.get("slow") is not None:
        template_parameters["slow"] = request_data["slow"]
    for key, value in (request_data.get("extra") or {}).items():
        template_parameters.setdefault(key, value)
    return validate_backtest_parameters(
        {
            "ticker": request_data["symbol"],
            "assetClass": request_data.get("assetClass", "equity"),
            "market": request_data.get("market", "usa"),
            "venue": request_data.get("venue"),
            "resolution": request_data.get("resolution", "daily"),
            "dataType": request_data.get("dataType", "trade"),
            "start": request_data["start"],
            "end": request_data["end"],
            "cash": request_data.get("cash", 100000),
            **template_parameters,
        }
    )


def _coverage(symbol: str, parameters: dict[str, Any], source: str) -> dict[str, Any]:
    market = str(parameters.get("market") or parameters.get("venue") or "china").lower()
    if market != "china":
        value = market_data_coverage(
            symbol,
            parameters["start"],
            parameters["end"],
            asset_class=str(parameters.get("assetClass") or "equity"),
            market=market,
            venue=str(parameters.get("venue") or market),
            resolution=str(parameters.get("resolution") or "daily"),
            data_type=str(parameters.get("dataType") or "trade"),
            adjust=str(parameters.get("adjust") or "raw"),
            source=source,
        )
        return {
            "symbol": symbol,
            "source": source,
            "rows": int(value.get("bar_count") or 0),
            "statusRows": 0,
            "firstDate": value.get("first_date"),
            "lastDate": value.get("last_date"),
        }
    value = data_coverage(
        symbol,
        parameters["start"],
        parameters["end"],
        adjust=str(parameters.get("adjust") or "raw"),
        source=source,
    )
    return {
        "symbol": symbol,
        "source": source,
        "rows": max(int(value.get("bar_count") or 0), int(value.get("market_bar_count") or 0)),
        "statusRows": int(value.get("status_count") or 0),
        "firstDate": value.get("market_first_date") or value.get("first_date"),
        "lastDate": value.get("market_last_date") or value.get("last_date"),
    }


def _source(request_data: dict[str, Any], parameters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    requested = (
        request_data.get("source")
        or request_data.get("providerSource")
        or request_data.get("provider")
        or (request_data.get("parameters") or {}).get("source")
        or DEFAULT_PRODUCTION_SOURCE
    )
    context = resolve_source_context(
        parameters,
        source=str(requested),
        allow_research_source=bool(request_data.get("allowResearchSource") or parameters.get("allowResearchSource")),
        asset_class=str(parameters.get("assetClass") or "equity"),
        market=str(parameters.get("market") or "china"),
        venue=str(parameters.get("venue") or parameters.get("market") or "china"),
    )
    source = str(context["source"])
    availability = DATA_PROVIDER_MANAGER.availability(
        [source],
        start_date=parameters["start"],
        end_date=parameters["end"],
    )[0]
    if not availability.get("available"):
        raise LeanPlatformError(
            f"data_source_unavailable:{source}:"
            f"{availability.get('unavailableReason') or availability.get('reason') or 'unavailable'}"
        )
    return source, context


def _target_gate(parameters: dict[str, Any], source: str) -> None:
    market = str(parameters.get("market") or parameters.get("venue") or "china").lower()
    if market != "china":
        assert_benchmark_ready(
            str(parameters["ticker"]).upper(),
            parameters["start"],
            parameters["end"],
            asset_class=str(parameters.get("assetClass") or "equity"),
            market=market,
            venue=str(parameters.get("venue") or market),
            resolution=str(parameters.get("resolution") or "daily"),
            data_type=str(parameters.get("dataType") or "trade"),
            adjust=str(parameters.get("adjust") or "raw"),
            source=source,
            allow_truncated=bool(parameters.get("allowTruncatedData")),
        )
        return
    assert_ashare_ready(
        str(parameters["ticker"]).upper(),
        parameters["start"],
        parameters["end"],
        adjust=str(parameters.get("adjust") or "raw"),
        source=source,
        allow_truncated=bool(parameters.get("allowTruncatedData")),
    )


def _benchmark_gate(parameters: dict[str, Any], source: str) -> None:
    assert_benchmark_ready(
        str(parameters.get("benchmarkSymbol") or "").upper(),
        parameters["start"],
        parameters["end"],
        asset_class=str(parameters.get("assetClass") or "equity"),
        market=str(parameters.get("market") or "china"),
        venue=str(parameters.get("venue") or parameters.get("market") or "china"),
        resolution=str(parameters.get("resolution") or "daily"),
        data_type=str(parameters.get("dataType") or "trade"),
        adjust=str(parameters.get("adjust") or "raw"),
        source=source,
        allow_truncated=bool(parameters.get("allowTruncatedData")),
    )


def _repair_symbol(symbol: str, parameters: dict[str, Any], source: str, role: str) -> dict[str, Any]:
    market = str(parameters.get("market") or "china").lower()
    if role == "benchmark" and market == "china":
        return fetch_and_import_benchmark(
            symbol,
            source,
            start_date=parameters["start"],
            end_date=parameters["end"],
            market=str(parameters.get("market") or "china"),
        )
    return fetch_and_import_symbol(
        symbol,
        source,
        market=str(parameters.get("market") or "china"),
        asset_class=str(parameters.get("assetClass") or "equity"),
        venue=str(parameters.get("venue") or parameters.get("market") or "china"),
        resolution=str(parameters.get("resolution") or "daily"),
        data_type=str(parameters.get("dataType") or "trade"),
        overwrite=False,
        outputsize="full",
        start_date=parameters["start"],
        end_date=parameters["end"],
        adjust=str(parameters.get("adjust") or "raw"),
    )


def _ensure_ready(
    *,
    role: str,
    symbol: str,
    parameters: dict[str, Any],
    source: str,
    gate: Callable[[dict[str, Any], str], None],
    repair: bool,
) -> dict[str, Any]:
    before = _coverage(symbol, parameters, source)
    try:
        gate(parameters, source)
        return {"role": role, "repaired": False, "before": before, "after": before}
    except Exception as initial_error:
        if not repair:
            raise
        try:
            asset = _repair_symbol(symbol, parameters, source, role)
        except Exception as repair_error:
            raise LeanPlatformError(
                f"{role}_data_repair_failed:{symbol}:{repair_error}"
            ) from repair_error
        try:
            gate(parameters, source)
        except Exception as final_error:
            raise LeanPlatformError(
                f"{role}_data_repair_failed:{symbol}:{final_error}"
            ) from final_error
        return {
            "role": role,
            "repaired": True,
            "reason": str(initial_error),
            "asset": {
                "rows": asset.get("rows"),
                "firstDate": asset.get("first_date"),
                "lastDate": asset.get("last_date"),
                "batchId": asset.get("batch_id"),
            },
            "before": before,
            "after": _coverage(symbol, parameters, source),
        }


def prepare_backtest_request(request_data: dict[str, Any], *, repair: bool = True) -> dict[str, Any]:
    parameters = _parameters(request_data)
    market = str(parameters.get("market") or parameters.get("venue") or "").lower()
    is_supported_equity = (
        parameters.get("assetClass") == "equity"
        and market in {"china", "hongkong"}
    )
    report: dict[str, Any] = {
        "ready": True,
        "market": parameters.get("market"),
        "assetClass": parameters.get("assetClass"),
        "repaired": [],
        "items": [],
    }
    if not is_supported_equity:
        return {"parameters": parameters, "preflight": report}

    parameters = (
        merge_ashare_trading_config(parameters, request_data)
        if market == "china"
        else merge_hk_trading_config(parameters, request_data)
    )
    source, context = _source(request_data, parameters)
    parameters = apply_source_context(parameters, context)
    parameters["source"] = source
    benchmark = str(parameters.get("benchmarkSymbol") or "").upper()
    target = str(parameters["ticker"]).upper()
    checks = [
        _ensure_ready(
            role="symbol",
            symbol=target,
            parameters=parameters,
            source=source,
            gate=_target_gate,
            repair=repair,
        ),
        _ensure_ready(
            role="benchmark",
            symbol=benchmark,
            parameters=parameters,
            source=source,
            gate=_benchmark_gate,
            repair=repair,
        ),
    ]
    if market == "hongkong":
        instrument = get_instrument(
            target,
            asset_class=str(parameters.get("assetClass") or "equity"),
            market=market,
            venue=str(parameters.get("venue") or market),
        )
        if instrument and instrument.get("lot_size"):
            parameters["lotSize"] = max(1, int(float(instrument["lot_size"])))
    if market == "china":
        # Multi-source daily QA is an equity report.  The benchmark has its own
        # index-aware fail-closed gate above and must not be interpreted as an
        # equity merely because its code is numeric (for example CSI 300).
        quality = quality_gate_range(target, parameters["start"], parameters["end"])
        if not quality["passed"]:
            report_id = quality["blockingReports"][0].get("id") if quality["blockingReports"] else None
            detail = f"qa_failed:{report_id}" if report_id else "qa_failed"
            raise LeanPlatformError(f"A-share data QA critical gate blocked backtest for {target}: {detail}")
        if not bool(context.get("allowResearchSource")):
            from .data_coverage import ashare_coverage

            coverage = ashare_coverage(
                symbols=[target],
                benchmark=benchmark,
                start_date=parameters["start"],
                end_date=parameters["end"],
                source=source,
            )
            if not coverage.get("passed"):
                issues = ",".join(str(item) for item in coverage.get("issues") or []) or "unknown"
                raise LeanPlatformError(f"ashare_reference_gate_failed:{issues}")
    report.update(
        {
            "effectiveSource": source,
            "items": checks,
            "repaired": [item["role"] for item in checks if item["repaired"]],
            "ready": True,
        }
    )
    return {"parameters": parameters, "preflight": report}
