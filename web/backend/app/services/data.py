import os
from pathlib import Path
from typing import Any

from ..core.config import REPO_ROOT
from ..db import db, json_dump, utc_now
from ..lean import (
    fetch_akshare_rows,
    fetch_alpha_vantage_rows,
    fetch_binance_crypto_rows,
    fetch_eastmoney_rows,
    fetch_sina_rows,
    fetch_stooq_rows,
    fetch_tonghuashun_rows,
    fetch_yahoo_rows,
    list_local_symbols,
    market_key,
    normalize_symbol,
    write_equity_factor_file,
    write_lean_crypto_daily_zip,
    write_lean_daily_zip,
)
from ..domain.assets import (
    asset_class_key,
    asset_request,
    data_type_key,
    list_local_data_files,
    list_local_symbols_for_asset,
    resolution_key,
    venue_key,
)
from .market_data import mirror_rows
from .db_object_store import put_file
from .market_repository import upsert_market_daily_bars
from .tushare_adapter import fetch_tushare_rows
from .ashare_repository import (
    create_import_batch,
    finish_import_batch,
    infer_exchange,
    trade_dates_between,
    upsert_adjustment_factors,
    upsert_daily_bars,
    upsert_security,
    upsert_trade_calendar,
    upsert_trade_status,
    upsert_universe_membership,
)
from .data_quality import (
    DataQualityError,
    assert_quality_passed,
    build_ashare_trade_status,
    normalize_ashare_daily_rows,
    validate_ashare_daily_rows,
)


DJIA_AS_OF = "2026-06-29"
DJIA_SOURCE = "S&P Dow Jones Indices announcement reported by major financial media; Alphabet replaced Verizon before market open on 2026-06-29."
DJIA_COMPONENTS = [
    {"symbol": "MMM", "name": "3M", "sector": "Industrials", "exchange": "NYSE"},
    {"symbol": "AXP", "name": "American Express", "sector": "Financials", "exchange": "NYSE"},
    {"symbol": "AMGN", "name": "Amgen", "sector": "Health Care", "exchange": "NASDAQ"},
    {"symbol": "AMZN", "name": "Amazon", "sector": "Consumer Discretionary", "exchange": "NASDAQ"},
    {"symbol": "AAPL", "name": "Apple", "sector": "Information Technology", "exchange": "NASDAQ"},
    {"symbol": "GOOGL", "name": "Alphabet", "sector": "Communication Services", "exchange": "NASDAQ"},
    {"symbol": "BA", "name": "Boeing", "sector": "Industrials", "exchange": "NYSE"},
    {"symbol": "CAT", "name": "Caterpillar", "sector": "Industrials", "exchange": "NYSE"},
    {"symbol": "CVX", "name": "Chevron", "sector": "Energy", "exchange": "NYSE"},
    {"symbol": "CSCO", "name": "Cisco", "sector": "Information Technology", "exchange": "NASDAQ"},
    {"symbol": "KO", "name": "Coca-Cola", "sector": "Consumer Staples", "exchange": "NYSE"},
    {"symbol": "DIS", "name": "Disney", "sector": "Communication Services", "exchange": "NYSE"},
    {"symbol": "GS", "name": "Goldman Sachs", "sector": "Financials", "exchange": "NYSE"},
    {"symbol": "HD", "name": "Home Depot", "sector": "Consumer Discretionary", "exchange": "NYSE"},
    {"symbol": "HON", "name": "Honeywell", "sector": "Industrials", "exchange": "NASDAQ"},
    {"symbol": "IBM", "name": "IBM", "sector": "Information Technology", "exchange": "NYSE"},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "sector": "Health Care", "exchange": "NYSE"},
    {"symbol": "JPM", "name": "JPMorgan Chase", "sector": "Financials", "exchange": "NYSE"},
    {"symbol": "MCD", "name": "McDonald's", "sector": "Consumer Discretionary", "exchange": "NYSE"},
    {"symbol": "MRK", "name": "Merck", "sector": "Health Care", "exchange": "NYSE"},
    {"symbol": "MSFT", "name": "Microsoft", "sector": "Information Technology", "exchange": "NASDAQ"},
    {"symbol": "NKE", "name": "Nike", "sector": "Consumer Discretionary", "exchange": "NYSE"},
    {"symbol": "NVDA", "name": "Nvidia", "sector": "Information Technology", "exchange": "NASDAQ"},
    {"symbol": "PG", "name": "Procter & Gamble", "sector": "Consumer Staples", "exchange": "NYSE"},
    {"symbol": "CRM", "name": "Salesforce", "sector": "Information Technology", "exchange": "NYSE"},
    {"symbol": "SHW", "name": "Sherwin-Williams", "sector": "Materials", "exchange": "NYSE"},
    {"symbol": "TRV", "name": "Travelers", "sector": "Financials", "exchange": "NYSE"},
    {"symbol": "UNH", "name": "UnitedHealth Group", "sector": "Health Care", "exchange": "NYSE"},
    {"symbol": "V", "name": "Visa", "sector": "Financials", "exchange": "NYSE"},
    {"symbol": "WMT", "name": "Walmart", "sector": "Consumer Staples", "exchange": "NASDAQ"},
]


def markets() -> list[dict[str, Any]]:
    return [
        {
            "key": "usa",
            "name": "US Equity",
            "currency": "USD",
            "defaultProvider": "yahoo",
            "providers": ["yahoo", "stooq", "alpha_vantage", "akshare", "sina"],
        },
        {
            "key": "china",
            "name": "A Share",
            "currency": "CNY",
            "defaultProvider": "tushare",
            "providers": ["tushare", "eastmoney", "sina", "akshare", "tonghuashun"],
        },
        {
            "key": "hongkong",
            "name": "Hong Kong",
            "currency": "HKD",
            "defaultProvider": "sina",
            "providers": ["eastmoney", "sina", "akshare"],
        },
    ]


def asset_classes() -> list[dict[str, Any]]:
    return [
        {
            "key": "equity",
            "name": "Equity",
            "defaultVenue": "usa",
            "defaultResolution": "daily",
            "venues": ["usa", "china", "hongkong"],
            "dataTypes": ["trade"],
            "notes": "US, A-share, and Hong Kong daily equities are supported by public providers and CSV import.",
        },
        {
            "key": "crypto",
            "name": "Crypto",
            "defaultVenue": "coinbase",
            "defaultResolution": "daily",
            "venues": ["coinbase", "binance", "bybit", "bitfinex", "kraken"],
            "dataTypes": ["trade", "quote"],
            "notes": "LEAN sample data is available locally; Binance daily OHLCV import is enabled for spot pairs.",
        },
        {
            "key": "crypto_future",
            "name": "Crypto Future",
            "defaultVenue": "binance",
            "defaultResolution": "minute",
            "venues": ["binance", "bybit"],
            "dataTypes": ["trade", "quote", "open_interest"],
            "notes": "Scans local LEAN-format data. Public import adapters should be added per exchange contract type.",
        },
        {
            "key": "future",
            "name": "Future",
            "defaultVenue": "comex",
            "defaultResolution": "daily",
            "venues": ["comex", "cme", "cbot", "nymex", "ice", "eurex", "hkfe", "sgx"],
            "dataTypes": ["trade", "quote", "open_interest"],
            "notes": "Uses local LEAN-format futures data and CSV import. Complete public futures data needs vendor-quality contract metadata.",
        },
    ]


def local_data_index(asset_class: str | None = None, venue: str | None = None) -> list[dict[str, Any]]:
    items = list_local_data_files()
    if asset_class:
        key = asset_class_key(asset_class)
        items = [item for item in items if item["assetClass"] == key]
    if venue:
        venue_value = venue.strip().lower()
        items = [item for item in items if item["venue"] == venue_value]
    return items


def symbols_for_asset(
    asset_class: str = "equity",
    venue: str | None = None,
    market: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
) -> list[str]:
    if asset_class_key(asset_class) == "equity":
        return list_local_symbols(market or venue or "usa")
    return list_local_symbols_for_asset(asset_class, venue=venue, market=market, resolution=resolution, data_type=data_type)


def djia_universe() -> dict[str, Any]:
    local = set(list_local_symbols("usa"))
    components = [{**item, "hasLocalData": item["symbol"] in local} for item in DJIA_COMPONENTS]
    return {"key": "djia", "name": "Dow Jones Industrial Average", "asOf": DJIA_AS_OF, "source": DJIA_SOURCE, "components": components}


def data_providers() -> list[dict[str, Any]]:
    return [
        {
            "key": "binance",
            "name": "Binance",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["crypto"],
            "assetClasses": ["crypto"],
            "venues": ["binance"],
            "notes": "Public spot kline endpoint for crypto OHLCV. Availability depends on region, symbol, and Binance limits.",
        },
        {
            "key": "tushare",
            "name": "TuShare Pro",
            "requiresApiKey": True,
            "supportsBatch": True,
            "markets": ["china"],
            "assetClasses": ["equity"],
            "venues": ["china"],
            "notes": "Uses TUSHARE_TOKEN from local .env or request apiKey. Current minimum permission is pro.daily; adj_factor, stk_limit, trade_cal, and stock_basic are opportunistic or later-stage permissions.",
        },
        {
            "key": "eastmoney",
            "name": "EastMoney",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["china", "hongkong"],
            "assetClasses": ["equity"],
            "venues": ["china", "hongkong"],
            "notes": "Direct EastMoney daily K-line endpoint for A-share equities; Hong Kong availability depends on network/provider behavior.",
        },
        {
            "key": "sina",
            "name": "Sina Finance",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["usa", "china", "hongkong"],
            "assetClasses": ["equity"],
            "venues": ["usa", "china", "hongkong"],
            "notes": "Uses AKShare's Sina adapters. Public endpoints may throttle or change.",
        },
        {
            "key": "akshare",
            "name": "AKShare",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["usa", "china", "hongkong"],
            "assetClasses": ["equity"],
            "venues": ["usa", "china", "hongkong"],
            "notes": "Requires the Python akshare package. Uses AKShare adapters for public US/CN/HK daily data.",
        },
        {
            "key": "tonghuashun",
            "name": "TongHuaShun",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["china"],
            "assetClasses": ["equity"],
            "venues": ["china"],
            "notes": "A-share daily data only in v1; Hong Kong should use EastMoney, Sina, or AKShare.",
        },
        {
            "key": "yahoo",
            "name": "Yahoo Finance",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["usa"],
            "assetClasses": ["equity"],
            "venues": ["usa"],
            "notes": "Free chart endpoint when not rate-limited. Use for local demos only; review terms and data quality.",
        },
        {
            "key": "stooq",
            "name": "Stooq",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["usa"],
            "assetClasses": ["equity"],
            "venues": ["usa"],
            "notes": "Free daily OHLCV CSV. Suitable for local demos; review data quality before production research.",
        },
        {
            "key": "alpha_vantage",
            "name": "Alpha Vantage",
            "requiresApiKey": True,
            "supportsBatch": True,
            "markets": ["usa"],
            "assetClasses": ["equity"],
            "venues": ["usa"],
            "notes": "Daily OHLCV API. Free keys are rate-limited and may not allow full history.",
        },
    ]


def record_data_asset(metadata: dict[str, Any]) -> dict[str, Any]:
    created_at = utc_now()
    metadata = {**metadata, "created_at": created_at}
    with db() as connection:
        cursor = connection.execute(
            """
            insert into data_assets
                (symbol, asset_class, venue, resolution, data_type, source, rows, first_date, last_date,
                 lean_file, lean_object_id, factor_object_id, metadata_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata["symbol"],
                metadata.get("asset_class") or metadata.get("assetClass") or "equity",
                metadata.get("venue") or metadata.get("market"),
                metadata.get("resolution") or "daily",
                metadata.get("data_type") or metadata.get("dataType") or "trade",
                metadata["source"],
                metadata["rows"],
                metadata["first_date"],
                metadata["last_date"],
                metadata["lean_file"],
                metadata.get("lean_object_id"),
                metadata.get("factor_object_id"),
                json_dump(metadata),
                created_at,
            ),
        )
        metadata["id"] = cursor.lastrowid
    return metadata


def _repo_path(relative_or_absolute: str | None) -> Path | None:
    if not relative_or_absolute:
        return None
    path = Path(relative_or_absolute)
    return path if path.is_absolute() else REPO_ROOT / path


def attach_database_objects(metadata: dict[str, Any]) -> dict[str, Any]:
    lean_path = _repo_path(metadata.get("lean_file"))
    if lean_path and lean_path.exists():
        stored = put_file(
            "lean-data",
            metadata["lean_file"],
            lean_path,
            metadata={
                "symbol": metadata.get("symbol"),
                "asset_class": metadata.get("asset_class") or metadata.get("assetClass"),
                "venue": metadata.get("venue") or metadata.get("market"),
                "resolution": metadata.get("resolution"),
                "data_type": metadata.get("data_type") or metadata.get("dataType"),
                "source": metadata.get("source"),
                "batch_id": metadata.get("batch_id"),
            },
        )
        metadata["lean_object_id"] = stored.get("id")
    factor_file = metadata.get("factor_file")
    if isinstance(factor_file, dict):
        factor_path = _repo_path(factor_file.get("factor_file"))
        if factor_path and factor_path.exists():
            stored = put_file(
                "lean-factor-files",
                factor_file["factor_file"],
                factor_path,
                content_type="text/csv",
                metadata={"symbol": metadata.get("symbol"), "source": metadata.get("source"), "batch_id": metadata.get("batch_id")},
            )
            metadata["factor_object_id"] = stored.get("id")
    return metadata


def fetch_provider_rows(
    provider: str,
    symbol: str,
    market: str = "usa",
    asset_class: str = "equity",
    venue: str | None = None,
    resolution: str = "daily",
    api_key: str | None = None,
    outputsize: str = "compact",
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "",
) -> list[dict[str, str]]:
    asset_class = asset_class_key(asset_class)
    if asset_class == "crypto":
        request = asset_request(symbol, asset_class, venue=venue or market, resolution=resolution)
        if provider == "binance":
            if request.resolution != "daily":
                raise ValueError("Binance import currently writes LEAN crypto daily bars only; use local sample data for intraday.")
            return fetch_binance_crypto_rows(request.symbol, start=start_date, end=end_date, interval="1d")
        raise ValueError(f"Unsupported crypto data provider: {provider}")
    if asset_class != "equity":
        raise ValueError(f"Provider downloads are not enabled for asset class {asset_class}; use local LEAN data or CSV import.")
    market = market_key(market)
    symbol = normalize_symbol(symbol, market)
    if provider == "tushare":
        if market != "china":
            raise ValueError("TuShare Pro only supports China A-share imports in this platform.")
        return fetch_tushare_rows(symbol, start_date, end_date, token=api_key, adjust=adjust)
    if provider == "eastmoney":
        return fetch_eastmoney_rows(symbol, market, start=start_date, end=end_date, adjust=adjust)
    if provider == "sina":
        return fetch_sina_rows(symbol, market, start=start_date, end=end_date, adjust=adjust)
    if provider == "akshare":
        return fetch_akshare_rows(symbol, market, start=start_date, end=end_date, adjust=adjust)
    if provider == "tonghuashun":
        return fetch_tonghuashun_rows(symbol, market, start=start_date, end=end_date, adjust=adjust)
    if provider == "stooq":
        if market != "usa":
            raise ValueError("Stooq only supports US equities in this platform.")
        return fetch_stooq_rows(symbol)
    if provider == "yahoo":
        if market != "usa":
            raise ValueError("Yahoo only supports US equities in this platform.")
        return fetch_yahoo_rows(symbol, start=start_date or "2000-01-01", end=end_date)
    if provider == "alpha_vantage":
        if market != "usa":
            raise ValueError("Alpha Vantage only supports US equities in this platform.")
        key = api_key or os.environ.get("ALPHAVANTAGE_API_KEY")
        if not key:
            raise ValueError("Alpha Vantage API key is required.")
        return fetch_alpha_vantage_rows(symbol, key, outputsize)
    raise ValueError(f"Unsupported data provider: {provider}")


def _ashare_rows_for_lean(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "date": str(row["trade_date"]),
            "open": str(row["open"]),
            "high": str(row["high"]),
            "low": str(row["low"]),
            "close": str(row["close"]),
            "volume": str(row["volume"]),
        }
        for row in rows
    ]


def _has_official_trade_status(rows: list[dict[str, Any]]) -> bool:
    status_fields = {
        "is_suspended",
        "limit_up",
        "limit_down",
        "is_limit_up",
        "is_limit_down",
        "can_buy",
        "can_sell",
    }
    return any(any(row.get(field) is not None for field in status_fields) for row in rows)


def _repair_ohlc_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repaired = []
    for row in rows:
        prices = [row["open"], row["high"], row["low"], row["close"]]
        high = max(prices)
        low = min(prices)
        if high != row["high"] or low != row["low"]:
            repaired.append(
                {
                    "symbol": row["symbol"],
                    "trade_date": row["trade_date"],
                    "old_high": row["high"],
                    "old_low": row["low"],
                    "new_high": high,
                    "new_low": low,
                }
            )
            row["high"] = high
            row["low"] = low
    return repaired


def import_ashare_research_data(
    *,
    symbol: str,
    provider: str,
    market: str,
    rows: list[dict[str, str]],
    source: str,
    overwrite: bool,
    adjust: str,
    outputsize: str,
    asset_class: str,
    venue: str,
    resolution: str,
    data_type: str,
    start_date: str | None,
    end_date: str | None,
    allow_missing_trade_dates: bool = False,
    repair_ohlc_errors: bool = False,
) -> dict[str, Any]:
    batch = create_import_batch(
        provider,
        market,
        asset_class,
        {
            "symbol": symbol,
            "provider": provider,
            "market": market,
            "venue": venue,
            "resolution": resolution,
            "dataType": data_type,
            "startDate": start_date,
            "endDate": end_date,
            "adjust": adjust or "raw",
            "overwrite": overwrite,
        },
    )
    batch_id = batch["id"]
    qa_report: dict[str, Any] | None = None
    try:
        normalized_rows = normalize_ashare_daily_rows(
            symbol,
            rows,
            source=source,
            batch_id=batch_id,
            adjust=adjust or "raw",
        )
        repaired_ohlc_rows = _repair_ohlc_rows(normalized_rows) if repair_ohlc_errors else []
        row_dates = [row["trade_date"] for row in normalized_rows]
        calendar_dates = trade_dates_between(market, min(row_dates), max(row_dates)) if row_dates else []
        if not calendar_dates and row_dates:
            upsert_trade_calendar(market, row_dates, source=f"{source}:inferred", batch_id=batch_id)
            calendar_dates = row_dates
        qa_report = validate_ashare_daily_rows(
            normalized_rows,
            calendar_dates=calendar_dates,
            source=source,
            batch_id=batch_id,
        )
        warnings = qa_report.setdefault("warnings", [])
        if _has_official_trade_status(normalized_rows):
            warnings.append("trade_status_official_fields_used")
        else:
            warnings.append("trade_status_inferred_from_ohlcv")
        if repaired_ohlc_rows:
            warnings.append(f"ohlc_rows_repaired={repaired_ohlc_rows[:10]}")
        if allow_missing_trade_dates and qa_report.get("missing_trade_dates"):
            remaining_errors = [error for error in qa_report.get("errors", []) if not str(error).startswith("missing_trade_dates=")]
            if len(remaining_errors) != len(qa_report.get("errors", [])):
                qa_report["errors"] = remaining_errors
                qa_report["passed"] = not remaining_errors
                warnings.append(f"missing_trade_dates_allowed={qa_report['missing_trade_dates'][:10]}")
        assert_quality_passed(qa_report)
        first_date = normalized_rows[0]["trade_date"]
        last_date = normalized_rows[-1]["trade_date"]
        upsert_security(
            symbol=symbol,
            name=symbol,
            exchange=infer_exchange(symbol),
            listed_date=first_date,
            status="listed",
            is_st=any(bool(row.get("is_st")) for row in normalized_rows),
        )
        trade_status = build_ashare_trade_status(normalized_rows)
        upsert_daily_bars(normalized_rows, source=source, batch_id=batch_id, adjust=adjust or "raw")
        upsert_trade_status(trade_status, source=source, batch_id=batch_id)
        upsert_adjustment_factors(normalized_rows, source=source, batch_id=batch_id)
        upsert_universe_membership("ALL_A", symbol, first_date, None, source=source, batch_id=batch_id)

        lean_rows = _ashare_rows_for_lean(normalized_rows)
        metadata = write_lean_daily_zip(symbol, lean_rows, source, overwrite=overwrite, market=market)
        factor_metadata = write_equity_factor_file(symbol, normalized_rows, market=market)
        metadata["asset_class"] = "equity"
        metadata["venue"] = market
        metadata["resolution"] = "daily"
        metadata["data_type"] = "trade"
        metadata["provider"] = provider
        metadata["market"] = market
        metadata["adjust"] = adjust or "raw"
        metadata["outputsize"] = outputsize if provider == "alpha_vantage" else None
        metadata["batch_id"] = batch_id
        metadata["qa_report"] = qa_report
        metadata["factor_file"] = factor_metadata
        metadata["research_tables"] = {
            "security": True,
            "daily_bars": len(normalized_rows),
            "trade_status": len(trade_status),
            "adjustment_factors": len(normalized_rows),
            "universe": "ALL_A",
            "first_date": first_date,
            "last_date": last_date,
        }
        try:
            metadata["clickhouse"] = mirror_rows(metadata, lean_rows)
        except Exception as exc:
            metadata["clickhouse"] = {"enabled": True, "inserted": 0, "error": str(exc)}
        attach_database_objects(metadata)
        asset = record_data_asset(metadata)
        finish_import_batch(batch_id, "success", qa_report=qa_report)
        return asset
    except DataQualityError as exc:
        finish_import_batch(batch_id, "failed", qa_report=exc.report, error=str(exc))
        raise
    except Exception as exc:
        finish_import_batch(batch_id, "failed", qa_report=qa_report, error=str(exc))
        raise


def fetch_and_import_symbol(
    symbol: str,
    provider: str,
    market: str = "usa",
    asset_class: str = "equity",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    overwrite: bool = False,
    api_key: str | None = None,
    outputsize: str = "compact",
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "",
    allow_missing_trade_dates: bool = False,
    repair_ohlc_errors: bool = False,
) -> dict[str, Any]:
    asset_class = asset_class_key(asset_class)
    resolution = resolution_key(resolution)
    data_type = data_type_key(data_type)
    if asset_class == "equity":
        market = market_key(market)
        venue = market
        symbol = normalize_symbol(symbol, market)
    else:
        request = asset_request(symbol, asset_class, venue=venue or market, resolution=resolution, data_type=data_type)
        market = request.venue
        venue = request.venue
        symbol = request.symbol
    rows = fetch_provider_rows(
        provider,
        symbol,
        market=market,
        asset_class=asset_class,
        venue=venue,
        resolution=resolution,
        api_key=api_key,
        outputsize=outputsize,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )
    source = f"{provider}:{outputsize}" if provider == "alpha_vantage" else provider
    if asset_class == "equity" and market == "china":
        return import_ashare_research_data(
            symbol=symbol,
            provider=provider,
            market=market,
            rows=rows,
            source=source,
            overwrite=overwrite,
            adjust=adjust or "raw",
            outputsize=outputsize,
            asset_class=asset_class,
            venue=venue or market,
            resolution=resolution,
            data_type=data_type,
            start_date=start_date,
            end_date=end_date,
            allow_missing_trade_dates=allow_missing_trade_dates,
            repair_ohlc_errors=repair_ohlc_errors,
        )
    if asset_class == "crypto":
        metadata = write_lean_crypto_daily_zip(symbol, rows, source, overwrite=overwrite, venue=venue or market, data_type=data_type)
    else:
        metadata = write_lean_daily_zip(symbol, rows, source, overwrite=overwrite, market=market)
        metadata["asset_class"] = "equity"
        metadata["venue"] = market
        metadata["resolution"] = "daily"
        metadata["data_type"] = "trade"
    metadata["provider"] = provider
    metadata["market"] = market
    metadata["asset_class"] = asset_class
    metadata["venue"] = venue or market
    metadata["resolution"] = resolution
    metadata["data_type"] = data_type
    metadata["adjust"] = adjust or "raw"
    metadata["outputsize"] = outputsize if provider == "alpha_vantage" else None
    upsert_market_daily_bars(
        rows,
        symbol=symbol,
        asset_class=asset_class,
        market=market,
        venue=venue or market,
        source=source,
        resolution=resolution,
        data_type=data_type,
        adjust=adjust or "raw",
    )
    try:
        metadata["clickhouse"] = mirror_rows(metadata, rows)
    except Exception as exc:
        metadata["clickhouse"] = {"enabled": True, "inserted": 0, "error": str(exc)}
    attach_database_objects(metadata)
    return record_data_asset(metadata)
