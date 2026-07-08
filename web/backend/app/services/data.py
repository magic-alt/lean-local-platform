import time
from pathlib import Path
from typing import Any

from ..core.config import REPO_ROOT
from ..db import db, json_dump, utc_now
from ..lean_engine.data_paths import list_local_symbols
from ..lean_engine.data_writers import (
    write_lean_crypto_daily_zip,
    write_lean_daily_zip,
)
from ..lean_engine.providers import (
    fetch_binance_crypto_rows,
)
from ..lean_engine.symbols import (
    market_key,
    normalize_symbol,
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
from .lean_cache import rebuild_ashare_lean_cache_from_db
from .market_repository import upsert_market_daily_bars
from .data_provider_manager import DATA_PROVIDER_MANAGER, provider_requirements
from .source_gate import jqdata_entitlement
from .ashare_source_adapters import fetch_adata_rows, fetch_baostock_rows
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


PROVIDER_REQUIREMENTS: dict[str, dict[str, Any]] = provider_requirements()


def markets() -> list[dict[str, Any]]:
    return [
        {
            "key": "usa",
            "name": "US Equity",
            "currency": "USD",
            "defaultProvider": "yfinance",
            "providers": ["yfinance", "yahoo", "stooq", "alpha_vantage", "finnhub", "longbridge", "akshare", "sina"],
        },
        {
            "key": "china",
            "name": "A Share",
            "currency": "CNY",
            "defaultProvider": "jqdata",
            "providers": [
                "jqdata",
                "akshare",
                "efinance",
                "tencent",
                "tushare",
                "tickflow",
                "pytdx",
                "baostock",
                "adata",
                "eastmoney",
                "sina",
                "tonghuashun",
                "yfinance",
                "rqdata",
            ],
        },
        {
            "key": "hongkong",
            "name": "Hong Kong",
            "currency": "HKD",
            "defaultProvider": "akshare",
            "providers": ["akshare", "sina", "eastmoney", "longbridge", "yfinance"],
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
            "defaultVenue": "binance",
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
    return DATA_PROVIDER_MANAGER.providers()


def provider_availability(provider: str | None = None) -> dict[str, Any]:
    provider_filter = provider.strip().lower() if provider else None
    items = DATA_PROVIDER_MANAGER.availability([provider_filter] if provider_filter else None)
    return {
        "items": items,
        "count": len(items),
        "checkedAt": utc_now(),
        "networkChecked": False,
    }


def record_data_asset(metadata: dict[str, Any]) -> dict[str, Any]:
    created_at = utc_now()
    asset_class = metadata.get("asset_class") or metadata.get("assetClass") or "equity"
    venue = metadata.get("venue") or metadata.get("market")
    resolution = metadata.get("resolution") or "daily"
    data_type = metadata.get("data_type") or metadata.get("dataType") or "trade"
    metadata = {**metadata, "created_at": created_at, "status": "active"}
    with db() as connection:
        cursor = connection.execute(
            """
            insert into data_assets
                (symbol, asset_class, venue, resolution, data_type, source, rows, first_date, last_date,
                 lean_file, lean_object_id, factor_object_id, status, metadata_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                metadata["symbol"],
                asset_class,
                venue,
                resolution,
                data_type,
                metadata["source"],
                metadata["rows"],
                metadata["first_date"],
                metadata["last_date"],
                metadata["lean_file"],
                metadata.get("lean_object_id"),
                metadata.get("factor_object_id"),
                "active",
                json_dump(metadata),
                created_at,
            ),
        )
        metadata["id"] = cursor.lastrowid
        connection.execute(
            """
            update data_assets
            set status = 'superseded',
                superseded_by = ?,
                superseded_at = ?,
                superseded_reason = 'newer_asset_recorded'
            where id <> ?
              and symbol = ?
              and asset_class = ?
              and coalesce(venue, '') = coalesce(?, '')
              and resolution = ?
              and data_type = ?
              and source = ?
              and coalesce(status, 'active') = 'active'
            """,
            (
                metadata["id"],
                created_at,
                metadata["id"],
                metadata["symbol"],
                asset_class,
                venue,
                resolution,
                data_type,
                metadata["source"],
            ),
        )
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
    provider_key = str(provider or "").strip().lower()
    if provider_key == "adata":
        if market_key(market) != "china":
            raise ValueError("AData only supports China A-share imports in this platform.")
        return fetch_adata_rows(symbol, start=start_date, end=end_date, adjust=adjust or "raw")
    if provider_key == "baostock":
        if market_key(market) != "china":
            raise ValueError("Baostock only supports China A-share imports in this platform.")
        return fetch_baostock_rows(symbol, start=start_date, end=end_date, adjust=adjust or "raw")
    return DATA_PROVIDER_MANAGER.fetch_provider_rows(
        provider,
        symbol,
        market=market,
        asset_class=asset_class,
        api_key=api_key,
        outputsize=outputsize,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )


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


def _format_source_attempts(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return attempts


def _build_source_attempt(
    source: str,
    status: str,
    *,
    rows: int = 0,
    error: str | None = None,
    duration_ms: float | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source": source,
        "status": status,
        "rows": rows,
    }
    if error is not None:
        record["error"] = error
    if duration_ms is not None:
        record["durationMs"] = round(duration_ms, 2)
    return record


def _provider_chain_for_window(requested: str, start_date: str | None, end_date: str | None) -> list[str]:
    return DATA_PROVIDER_MANAGER.chain(
        requested,
        market="china",
        asset_class="equity",
        start_date=start_date,
        end_date=end_date,
    )


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
        has_official_trade_status = _has_official_trade_status(normalized_rows)
        if has_official_trade_status:
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
        status_source = f"{source}:official_status" if has_official_trade_status else f"{source}:ohlcv_inferred"
        upsert_daily_bars(normalized_rows, source=source, batch_id=batch_id, adjust=adjust or "raw")
        upsert_trade_status(trade_status, source=status_source, batch_id=batch_id)
        upsert_adjustment_factors(normalized_rows, source=source, batch_id=batch_id)
        upsert_universe_membership("ALL_A", symbol, first_date, None, source=source, batch_id=batch_id)

        lean_rows = _ashare_rows_for_lean(normalized_rows)
        metadata = rebuild_ashare_lean_cache_from_db(
            symbol,
            source=source,
            adjust=adjust or "raw",
            market=market,
            batch_id=batch_id,
        )
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
        metadata["research_tables"] = {
            "security": True,
            "daily_bars": len(normalized_rows),
            "trade_status": len(trade_status),
            "trade_status_source": status_source,
            "adjustment_factors": len(normalized_rows),
            "universe": "ALL_A",
            "first_date": first_date,
            "last_date": last_date,
        }
        try:
            metadata["clickhouse"] = mirror_rows(metadata, lean_rows)
        except Exception as exc:
            metadata["clickhouse"] = {"enabled": True, "inserted": 0, "error": str(exc)}
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
    source_attempts: list[dict[str, Any]] = []
    if asset_class == "equity":
        market = market_key(market)
        venue = market
        symbol = normalize_symbol(symbol, market)
        source_policy = {
            "requestedSource": provider,
            "sourceChain": DATA_PROVIDER_MANAGER.chain(
                provider,
                market=market,
                asset_class=asset_class,
                start_date=start_date,
                end_date=end_date,
            ),
        }
        provider_error: Exception | None = None
        selected_provider: str | None = None
        selected_rows: list[dict[str, Any]] | None = None
        for source in source_policy["sourceChain"]:
            t0 = time.perf_counter()
            availability = DATA_PROVIDER_MANAGER.availability([source], start_date=start_date, end_date=end_date)[0]
            if not availability.get("available"):
                source_attempts.append(
                    _build_source_attempt(
                        source,
                        "skipped",
                        rows=0,
                        error=availability.get("unavailableReason") or availability.get("reason"),
                        duration_ms=(time.perf_counter() - t0) * 1000,
                    )
                )
                continue
            try:
                candidate_rows = fetch_provider_rows(
                    source,
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
                if candidate_rows:
                    selected_provider = source
                    selected_rows = candidate_rows
                    source_attempts.append(_build_source_attempt(source, "success", rows=len(candidate_rows), duration_ms=(time.perf_counter() - t0) * 1000))
                    break
                source_attempts.append(_build_source_attempt(source, "empty", rows=0, duration_ms=(time.perf_counter() - t0) * 1000))
            except Exception as exc:  # noqa: BLE001
                provider_error = exc
                source_attempts.append(_build_source_attempt(source, "failed", rows=0, error=str(exc), duration_ms=(time.perf_counter() - t0) * 1000))
        if selected_rows is None:
            raise ValueError(
                "No active source returned data; attempted: "
                + ", ".join(f"{item['source']}:{item['status']}" for item in source_attempts)
            ) from provider_error
        rows = selected_rows
        provider = selected_provider or provider
        source_policy["effectiveSource"] = provider
        source_policy["fallbackApplied"] = provider != source_policy["requestedSource"]
        source_policy["fallbackReason"] = "provider_fallback" if source_policy["fallbackApplied"] else None
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
    if asset_class == "equity" and market == "china":
        source_attempts = _format_source_attempts(source_attempts) if source_attempts else [
            _build_source_attempt(provider, "success", rows=len(rows), duration_ms=0.0)
        ]
        source_policy = locals().get("source_policy") or DATA_PROVIDER_MANAGER.chain(provider, market=market, asset_class=asset_class, start_date=start_date, end_date=end_date)
        if isinstance(source_policy, list):
            source_policy = {"requestedSource": provider, "effectiveSource": provider, "sourceChain": source_policy}
        source_policy["attemptedSources"] = [item["source"] for item in source_attempts]
        source_policy["sourceAttempts"] = source_attempts
        source = f"{provider}:{outputsize}" if provider == "alpha_vantage" else provider
    else:
        source = f"{provider}:{outputsize}" if provider == "alpha_vantage" else provider
    source = f"{provider}:{outputsize}" if provider == "alpha_vantage" else provider
    if asset_class == "equity" and market == "china":
        result = import_ashare_research_data(
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
        result["sourcePolicy"] = source_policy
        result["sourceAttempts"] = source_attempts
        return result
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
    if source_attempts:
        metadata["sourceAttempts"] = source_attempts
    if asset_class == "equity" and locals().get("source_policy"):
        metadata["sourcePolicy"] = source_policy
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
