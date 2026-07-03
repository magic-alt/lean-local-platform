import os
from typing import Any

from ..db import db, json_dump, utc_now
from ..lean import (
    fetch_alpha_vantage_rows,
    fetch_stooq_rows,
    fetch_yahoo_rows,
    list_local_symbols,
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


def djia_universe() -> dict[str, Any]:
    local = set(list_local_symbols())
    components = [{**item, "hasLocalData": item["symbol"] in local} for item in DJIA_COMPONENTS]
    return {"key": "djia", "name": "Dow Jones Industrial Average", "asOf": DJIA_AS_OF, "source": DJIA_SOURCE, "components": components}


def data_providers() -> list[dict[str, Any]]:
    return [
        {
            "key": "yahoo",
            "name": "Yahoo Finance",
            "requiresApiKey": False,
            "supportsBatch": True,
            "notes": "Free chart endpoint when not rate-limited. Use for local demos only; review terms and data quality.",
        },
        {
            "key": "stooq",
            "name": "Stooq",
            "requiresApiKey": False,
            "supportsBatch": True,
            "notes": "Free daily OHLCV CSV. Suitable for local demos; review data quality before production research.",
        },
        {
            "key": "alpha_vantage",
            "name": "Alpha Vantage",
            "requiresApiKey": True,
            "supportsBatch": True,
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
    api_key: str | None = None,
    outputsize: str = "compact",
) -> list[dict[str, str]]:
    if provider == "stooq":
        return fetch_stooq_rows(symbol)
    if provider == "yahoo":
        return fetch_yahoo_rows(symbol)
    if provider == "alpha_vantage":
        key = api_key or os.environ.get("ALPHAVANTAGE_API_KEY")
        if not key:
            raise ValueError("Alpha Vantage API key is required.")
        return fetch_alpha_vantage_rows(symbol, key, outputsize)
    raise ValueError(f"Unsupported data provider: {provider}")


def fetch_and_import_symbol(
    symbol: str,
    provider: str,
    overwrite: bool = False,
    api_key: str | None = None,
    outputsize: str = "compact",
) -> dict[str, Any]:
    rows = fetch_provider_rows(provider, symbol, api_key=api_key, outputsize=outputsize)
    source = f"{provider}:{outputsize}" if provider == "alpha_vantage" else provider
    metadata = write_lean_daily_zip(symbol, rows, source, overwrite=overwrite)
    metadata["provider"] = provider
    metadata["outputsize"] = outputsize if provider == "alpha_vantage" else None
    return record_data_asset(metadata)
