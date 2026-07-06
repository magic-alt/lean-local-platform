from __future__ import annotations

import csv
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

from ..core.config import REPO_ROOT
from ..domain.assets import asset_request
from .data_paths import (
    crypto_daily_zip_path,
    daily_zip_path,
    ensure_crypto_dirs,
    ensure_equity_dirs,
    ensure_future_dirs,
    future_daily_zip_path,
    write_auxiliary_files,
)
from .errors import LeanPlatformError
from .symbols import market_key, normalize_symbol, parse_date, symbol_key

def lean_price(value: str | float) -> str:
    return str(int(round(float(value) * 10000)))

def normalize_rows(rows: list[dict[str, str]]) -> list[tuple[date, float, float, float, float, int]]:
    normalized: list[tuple[date, float, float, float, float, int]] = []
    seen_dates: set[date] = set()
    for row in rows:
        try:
            item_date = parse_date(row["date"][:10])
            open_price = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            volume = int(float(row["volume"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise LeanPlatformError(f"Invalid OHLCV row: {row}") from exc
        if item_date in seen_dates:
            raise LeanPlatformError(f"Duplicate OHLCV row for {item_date.isoformat()}.")
        seen_dates.add(item_date)
        if min(open_price, high, low, close) <= 0:
            raise LeanPlatformError(f"OHLCV row has non-positive price: {row}")
        if volume < 0:
            raise LeanPlatformError(f"OHLCV row has negative volume: {row}")
        if high < low or open_price > high or open_price < low or close > high or close < low:
            raise LeanPlatformError(f"OHLCV row violates high/low bounds: {row}")
        normalized.append((item_date, open_price, high, low, close, volume))

    normalized.sort(key=lambda item: item[0])
    if not normalized:
        raise LeanPlatformError("No valid OHLCV rows found.")
    return normalized


def write_lean_daily_zip(
    symbol: str,
    rows: list[dict[str, str]],
    source: str,
    overwrite: bool = False,
    market: str | None = None,
) -> dict[str, Any]:
    market = market_key(market)
    ticker = symbol_key(normalize_symbol(symbol, market))
    normalized = normalize_rows(rows)
    ensure_equity_dirs(market)
    write_auxiliary_files(ticker, normalized[0][0], market)

    output = daily_zip_path(ticker, market)
    if output.exists() and not overwrite:
        raise LeanPlatformError(f"{output} already exists; enable overwrite to replace it.")

    csv_lines = []
    for item_date, open_price, high, low, close, volume in normalized:
        csv_lines.append(
            f"{item_date:%Y%m%d} 00:00,{lean_price(open_price)},{lean_price(high)},"
            f"{lean_price(low)},{lean_price(close)},{volume}"
        )

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{ticker}.csv", "\n".join(csv_lines) + "\n")

    return {
        "symbol": ticker.upper(),
        "market": market,
        "source": source,
        "rows": len(csv_lines),
        "first_date": normalized[0][0].isoformat(),
        "last_date": normalized[-1][0].isoformat(),
        "lean_file": str(output.relative_to(REPO_ROOT)),
        "notes": [
            "Imported as raw daily TradeBar data.",
            "Factor and map files are minimal placeholders.",
            "Corporate actions are not reconstructed unless the source data already reflects them.",
        ],
    }


def write_lean_crypto_daily_zip(
    symbol: str,
    rows: list[dict[str, str]],
    source: str,
    overwrite: bool = False,
    venue: str = "coinbase",
    data_type: str = "trade",
) -> dict[str, Any]:
    request = asset_request(symbol, "crypto", venue=venue, resolution="daily", data_type=data_type)
    normalized = normalize_rows(rows)
    ensure_crypto_dirs(request.venue)
    output = crypto_daily_zip_path(request.symbol, request.venue, request.data_type)
    if output.exists() and not overwrite:
        raise LeanPlatformError(f"{output} already exists; enable overwrite to replace it.")

    csv_lines = []
    for item_date, open_price, high, low, close, volume in normalized:
        csv_lines.append(
            f"{item_date:%Y%m%d} 00:00,{open_price:g},{high:g},{low:g},{close:g},{volume}"
        )

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{request.symbol.lower()}.csv", "\n".join(csv_lines) + "\n")

    return {
        "symbol": request.symbol,
        "market": request.venue,
        "venue": request.venue,
        "asset_class": "crypto",
        "resolution": "daily",
        "data_type": request.data_type,
        "source": source,
        "rows": len(csv_lines),
        "first_date": normalized[0][0].isoformat(),
        "last_date": normalized[-1][0].isoformat(),
        "lean_file": str(output.relative_to(REPO_ROOT)),
        "notes": [
            "Imported as crypto daily TradeBar data.",
            "Crypto market hours are handled by LEAN's crypto market model.",
        ],
    }


def write_lean_future_daily_zip(
    symbol: str,
    rows: list[dict[str, str]],
    source: str,
    overwrite: bool = False,
    venue: str = "comex",
    data_type: str = "trade",
) -> dict[str, Any]:
    request = asset_request(symbol, "future", venue=venue, resolution="daily", data_type=data_type)
    normalized = normalize_rows(rows)
    ensure_future_dirs(request.venue)
    output = future_daily_zip_path(request.symbol, request.venue, request.data_type)
    if output.exists() and not overwrite:
        raise LeanPlatformError(f"{output} already exists; enable overwrite to replace it.")

    csv_lines = []
    for item_date, open_price, high, low, close, volume in normalized:
        csv_lines.append(
            f"{item_date:%Y%m%d} 00:00,{open_price:g},{high:g},{low:g},{close:g},{volume}"
        )

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{request.symbol.lower()}_{request.lean_data_type}.csv", "\n".join(csv_lines) + "\n")

    return {
        "symbol": request.symbol,
        "market": request.venue,
        "venue": request.venue,
        "asset_class": "future",
        "resolution": "daily",
        "data_type": request.data_type,
        "source": source,
        "rows": len(csv_lines),
        "first_date": normalized[0][0].isoformat(),
        "last_date": normalized[-1][0].isoformat(),
        "lean_file": str(output.relative_to(REPO_ROOT)),
        "notes": [
            "Imported as futures daily TradeBar data.",
            "Contract metadata, mapping, factors, and margins should be validated before production futures research.",
        ],
    }


def rows_from_csv(
    file_path: Path,
    date_col: str = "timestamp",
    open_col: str = "open",
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
    volume_col: str = "volume",
    encoding: str = "utf-8-sig",
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with file_path.open(newline="", encoding=encoding) as file:
        reader = csv.DictReader(file)
        for row in reader:
            if not row:
                continue
            try:
                rows.append(
                    {
                        "date": row[date_col],
                        "open": row[open_col],
                        "high": row[high_col],
                        "low": row[low_col],
                        "close": row[close_col],
                        "volume": row[volume_col],
                    }
                )
            except KeyError as exc:
                raise LeanPlatformError(f"Missing CSV column: {exc.args[0]!r}") from exc
    return rows
