from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Any

from ..core.config import DATA_DIR, REPO_ROOT
from ..domain.assets import asset_request
from .errors import LeanPlatformError
from .symbols import MARKET_CONFIG, market_key, normalize_symbol, parse_date, symbol_key

def daily_zip_path(symbol: str, market: str | None = None) -> Path:
    market = market_key(market)
    return DATA_DIR / "equity" / market / "daily" / f"{symbol_key(normalize_symbol(symbol, market))}.zip"


def list_local_symbols(market: str | None = None) -> list[str]:
    daily_dir = DATA_DIR / "equity" / market_key(market) / "daily"
    if not daily_dir.exists():
        return []
    return sorted(path.stem.upper() for path in daily_dir.glob("*.zip"))


def crypto_daily_zip_path(symbol: str, venue: str = "coinbase", data_type: str = "trade") -> Path:
    request = asset_request(symbol, "crypto", venue=venue, resolution="daily", data_type=data_type)
    return DATA_DIR / "crypto" / request.venue / "daily" / f"{request.symbol.lower()}_{request.lean_data_type}.zip"


def future_daily_zip_path(symbol: str, venue: str = "comex", data_type: str = "trade") -> Path:
    request = asset_request(symbol, "future", venue=venue, resolution="daily", data_type=data_type)
    return DATA_DIR / "future" / request.venue / "daily" / f"{request.symbol.lower()}_{request.lean_data_type}.zip"


def ensure_crypto_dirs(venue: str = "coinbase") -> None:
    for resolution in ("daily", "hour", "minute", "second"):
        (DATA_DIR / "crypto" / venue / resolution).mkdir(parents=True, exist_ok=True)


def ensure_future_dirs(venue: str = "comex") -> None:
    for relative in (
        f"future/{venue}/daily",
        f"future/{venue}/hour",
        f"future/{venue}/minute",
        f"future/{venue}/map_files",
        f"future/{venue}/factor_files",
        f"future/{venue}/margins",
    ):
        (DATA_DIR / relative).mkdir(parents=True, exist_ok=True)


def ensure_market_database(market: str) -> None:
    market = market_key(market)
    if market == "usa":
        return
    config = MARKET_CONFIG[market]

    symbol_properties = DATA_DIR / "symbol-properties" / "symbol-properties-database.csv"
    symbol_properties.parent.mkdir(parents=True, exist_ok=True)
    if not symbol_properties.exists():
        symbol_properties.write_text(
            "market,symbol,type,description,quote_currency,contract_multiplier,minimum_price_variation,lot_size,market_ticker,minimum_order_size,price_magnifier,strike_multiplier\n",
            encoding="utf-8",
        )
    text = symbol_properties.read_text(encoding="utf-8", errors="replace")
    entry = f"{market},[*],equity,,{config['currency']},1,{config['tick_size']},{config['lot_size']},,1\n"
    if f"{market},[*],equity" not in text:
        with symbol_properties.open("a", encoding="utf-8") as file:
            file.write(entry)

    market_hours = DATA_DIR / "market-hours" / "market-hours-database.json"
    market_hours.parent.mkdir(parents=True, exist_ok=True)
    data = {"entries": {}} if not market_hours.exists() else json.loads(market_hours.read_text(encoding="utf-8"))
    entries = data.setdefault("entries", {})
    entry_key = f"Equity-{market}-[*]"
    if entry_key not in entries:
        weekday = [{"start": config["open"], "end": config["close"], "state": "market"}]
        entries[entry_key] = {
            "dataTimeZone": config["timezone"],
            "exchangeTimeZone": config["timezone"],
            "sunday": [],
            "monday": weekday,
            "tuesday": weekday,
            "wednesday": weekday,
            "thursday": weekday,
            "friday": weekday,
            "saturday": [],
            "holidays": [],
            "earlyCloses": {},
            "lateOpens": {},
            "regularHolidays": [],
        }
        market_hours.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ensure_equity_dirs(market: str | None = None) -> None:
    market = market_key(market)
    ensure_market_database(market)
    for relative in (f"equity/{market}/daily", f"equity/{market}/map_files", f"equity/{market}/factor_files"):
        (DATA_DIR / relative).mkdir(parents=True, exist_ok=True)


def write_auxiliary_files(symbol: str, first_date: date, market: str | None = None) -> None:
    market = market_key(market)
    ticker = symbol_key(normalize_symbol(symbol, market))
    ensure_equity_dirs(market)
    start = first_date.strftime("%Y%m%d")

    map_file = DATA_DIR / "equity" / market / "map_files" / f"{ticker}.csv"
    if not map_file.exists():
        map_file.write_text(f"{start},{ticker},P\n20501231,{ticker},P\n", encoding="utf-8")

    factor_file = DATA_DIR / "equity" / market / "factor_files" / f"{ticker}.csv"
    if not factor_file.exists():
        factor_file.write_text(f"{start},1,1,0\n20501231,1,1,0\n", encoding="utf-8")


def write_equity_factor_file(
    symbol: str,
    factor_rows: list[dict[str, Any]],
    market: str | None = None,
) -> dict[str, Any]:
    market = market_key(market)
    ticker = symbol_key(normalize_symbol(symbol, market))
    ensure_equity_dirs(market)
    clean_rows = []
    for row in factor_rows:
        raw_date = row.get("trade_date") or row.get("date")
        raw_factor = row.get("adj_factor") or row.get("factor")
        if raw_date in (None, "") or raw_factor in (None, ""):
            continue
        factor = float(raw_factor)
        if factor <= 0 or not math.isfinite(factor):
            raise LeanPlatformError(f"Invalid adjustment factor for {ticker}: {raw_factor!r}")
        clean_rows.append((parse_date(str(raw_date)[:10]), factor))
    clean_rows = sorted(set(clean_rows), key=lambda item: item[0])
    if not clean_rows:
        raise LeanPlatformError(f"No adjustment factors found for {ticker}.")

    latest_factor = clean_rows[-1][1]
    if latest_factor <= 0:
        raise LeanPlatformError(f"Invalid latest adjustment factor for {ticker}.")
    lines = []
    for item_date, factor in clean_rows:
        price_factor = factor / latest_factor
        lines.append(f"{item_date:%Y%m%d},{price_factor:.10f},1,0")
    if clean_rows[-1][0] != date(2050, 12, 31):
        lines.append("20501231,1.0000000000,1,0")

    factor_file = DATA_DIR / "equity" / market / "factor_files" / f"{ticker}.csv"
    factor_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "symbol": ticker.upper(),
        "market": market,
        "factor_file": str(factor_file.relative_to(REPO_ROOT)),
        "rows": len(lines),
        "first_date": clean_rows[0][0].isoformat(),
        "last_date": clean_rows[-1][0].isoformat(),
        "latest_factor": latest_factor,
    }
