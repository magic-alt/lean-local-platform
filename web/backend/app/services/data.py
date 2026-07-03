import os
from typing import Any

from ..db import db, json_dump, utc_now
from ..lean import (
    fetch_akshare_rows,
    fetch_alpha_vantage_rows,
    fetch_eastmoney_rows,
    fetch_sina_rows,
    fetch_stooq_rows,
    fetch_tonghuashun_rows,
    fetch_yahoo_rows,
    list_local_symbols,
    market_key,
    normalize_symbol,
    write_lean_daily_zip,
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
            "defaultProvider": "eastmoney",
            "providers": ["eastmoney", "sina", "akshare", "tonghuashun"],
        },
        {
            "key": "hongkong",
            "name": "Hong Kong",
            "currency": "HKD",
            "defaultProvider": "sina",
            "providers": ["eastmoney", "sina", "akshare"],
        },
    ]


def djia_universe() -> dict[str, Any]:
    local = set(list_local_symbols("usa"))
    components = [{**item, "hasLocalData": item["symbol"] in local} for item in DJIA_COMPONENTS]
    return {"key": "djia", "name": "Dow Jones Industrial Average", "asOf": DJIA_AS_OF, "source": DJIA_SOURCE, "components": components}


def data_providers() -> list[dict[str, Any]]:
    return [
        {
            "key": "eastmoney",
            "name": "EastMoney",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["china", "hongkong"],
            "notes": "Direct EastMoney daily K-line endpoint for A-share equities; Hong Kong availability depends on network/provider behavior.",
        },
        {
            "key": "sina",
            "name": "Sina Finance",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["usa", "china", "hongkong"],
            "notes": "Uses AKShare's Sina adapters. Public endpoints may throttle or change.",
        },
        {
            "key": "akshare",
            "name": "AKShare",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["usa", "china", "hongkong"],
            "notes": "Requires the Python akshare package. Uses AKShare adapters for public US/CN/HK daily data.",
        },
        {
            "key": "tonghuashun",
            "name": "TongHuaShun",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["china"],
            "notes": "A-share daily data only in v1; Hong Kong should use EastMoney, Sina, or AKShare.",
        },
        {
            "key": "yahoo",
            "name": "Yahoo Finance",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["usa"],
            "notes": "Free chart endpoint when not rate-limited. Use for local demos only; review terms and data quality.",
        },
        {
            "key": "stooq",
            "name": "Stooq",
            "requiresApiKey": False,
            "supportsBatch": True,
            "markets": ["usa"],
            "notes": "Free daily OHLCV CSV. Suitable for local demos; review data quality before production research.",
        },
        {
            "key": "alpha_vantage",
            "name": "Alpha Vantage",
            "requiresApiKey": True,
            "supportsBatch": True,
            "markets": ["usa"],
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
                (symbol, source, rows, first_date, last_date, lean_file, metadata_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata["symbol"],
                metadata["source"],
                metadata["rows"],
                metadata["first_date"],
                metadata["last_date"],
                metadata["lean_file"],
                json_dump(metadata),
                created_at,
            ),
        )
        metadata["id"] = cursor.lastrowid
    return metadata


def fetch_provider_rows(
    provider: str,
    symbol: str,
    market: str = "usa",
    api_key: str | None = None,
    outputsize: str = "compact",
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "",
) -> list[dict[str, str]]:
    market = market_key(market)
    symbol = normalize_symbol(symbol, market)
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


def fetch_and_import_symbol(
    symbol: str,
    provider: str,
    market: str = "usa",
    overwrite: bool = False,
    api_key: str | None = None,
    outputsize: str = "compact",
    start_date: str | None = None,
    end_date: str | None = None,
    adjust: str = "",
) -> dict[str, Any]:
    market = market_key(market)
    symbol = normalize_symbol(symbol, market)
    rows = fetch_provider_rows(
        provider,
        symbol,
        market=market,
        api_key=api_key,
        outputsize=outputsize,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )
    source = f"{provider}:{outputsize}" if provider == "alpha_vantage" else provider
    metadata = write_lean_daily_zip(symbol, rows, source, overwrite=overwrite, market=market)
    metadata["provider"] = provider
    metadata["market"] = market
    metadata["adjust"] = adjust or "raw"
    metadata["outputsize"] = outputsize if provider == "alpha_vantage" else None
    return record_data_asset(metadata)
