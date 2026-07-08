from __future__ import annotations

from typing import Any

from ..lean_engine.symbols import market_key, normalize_symbol
from .ashare_multisource import compare_ashare_daily_sources
from .data import fetch_and_import_symbol
from .parquet_lake import export_market_daily_bars


DEFAULT_ASHARE_PROVIDERS = ["jqdata", "akshare", "efinance", "tencent", "tushare", "tickflow", "pytdx", "baostock", "adata", "eastmoney", "sina", "tonghuashun", "yfinance", "rqdata"]


def import_ashare_daily_sample(
    *,
    symbols: list[str],
    start_date: str,
    end_date: str,
    providers: list[str] | None = None,
    adjust: str = "raw",
    primary_provider: str = "jqdata",
    export_parquet: bool = True,
    compare_sources: bool = True,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    provider_list = [item.strip().lower() for item in (providers or DEFAULT_ASHARE_PROVIDERS) if item.strip()]
    if not provider_list:
        raise ValueError("At least one provider is required.")
    symbol_list = [normalize_symbol(symbol, market_key("china")).upper() for symbol in symbols if symbol.strip()]
    if not symbol_list:
        raise ValueError("At least one symbol is required.")

    imports: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for symbol in symbol_list:
        for provider in provider_list:
            try:
                imports.append(
                    {
                        "symbol": symbol,
                        "provider": provider,
                        "result": fetch_and_import_symbol(
                            symbol,
                            provider,
                            market="china",
                            asset_class="equity",
                            venue="china",
                            resolution="daily",
                            data_type="trade",
                            start_date=start_date,
                            end_date=end_date,
                            adjust=adjust,
                            overwrite=True,
                        ),
                    }
                )
            except Exception as exc:
                error = {"symbol": symbol, "provider": provider, "error": str(exc)}
                errors.append(error)
                if not continue_on_error:
                    raise

    reports: list[dict[str, Any]] = []
    if compare_sources:
        for symbol in symbol_list:
            available_sources = [provider for provider in provider_list if not any(err["symbol"] == symbol and err["provider"] == provider for err in errors)]
            if len(available_sources) < 2:
                continue
            reports.append(
                compare_ashare_daily_sources(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    sources=available_sources,
                    adjust=adjust,
                    persist=True,
                )
            )

    parquet: dict[str, Any] | None = None
    if export_parquet:
        parquet = export_market_daily_bars(
            asset_class="equity",
            market="china",
            venue="china",
            resolution="daily",
            data_type="trade",
            adjust=adjust,
            source=primary_provider,
            start_date=start_date,
            end_date=end_date,
        )

    return {
        "symbols": symbol_list,
        "providers": provider_list,
        "startDate": start_date,
        "endDate": end_date,
        "adjust": adjust,
        "importCount": len(imports),
        "errorCount": len(errors),
        "imports": imports,
        "errors": errors,
        "qualityReports": reports,
        "parquet": parquet,
    }
