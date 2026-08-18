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
    data = {"entries": {}}
    if market_hours.exists():
        try:
            content = market_hours.read_text(encoding="utf-8")
            if content.strip():
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    data = parsed
        except Exception:
            backup = market_hours.with_suffix(".json.bak")
            if market_hours.exists():
                market_hours.replace(backup)
            data = {"entries": {}}
    entries = data.setdefault("entries", {})
    entry_key = f"Equity-{market}-[*]"
    if entry_key not in entries:
        weekday = [
            {"start": start, "end": end, "state": "market"}
            for start, end in config.get("sessions", ((config["open"], config["close"]),))
        ]
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


def write_equity_symbol_properties(
    symbol: str,
    *,
    market: str,
    currency: str,
    lot_size: int,
    tick_size: float = 0.01,
) -> None:
    market = market_key(market)
    ticker = symbol_key(normalize_symbol(symbol, market))
    ensure_market_database(market)
    path = DATA_DIR / "symbol-properties" / "symbol-properties-database.csv"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    prefix = f"{market},{ticker},equity,"
    lines = [line for line in lines if not line.lower().startswith(prefix.lower())]
    lines.append(f"{market},{ticker},equity,,{currency},1,{tick_size},{int(lot_size)},,1")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    *,
    price_rows: list[dict[str, Any]] | None = None,
    require_reference_prices: bool = False,
) -> dict[str, Any]:
    market = market_key(market)
    ticker = symbol_key(normalize_symbol(symbol, market))
    ensure_equity_dirs(market)
    factor_by_date: dict[date, float] = {}
    for row in factor_rows:
        raw_date = row.get("trade_date") or row.get("date")
        raw_factor = row.get("adj_factor") or row.get("factor")
        if raw_date in (None, "") or raw_factor in (None, ""):
            continue
        factor = float(raw_factor)
        if factor <= 0 or not math.isfinite(factor):
            raise LeanPlatformError(f"Invalid adjustment factor for {ticker}: {raw_factor!r}")
        factor_by_date[parse_date(str(raw_date)[:10])] = factor
    clean_rows = sorted(factor_by_date.items(), key=lambda item: item[0])
    if not clean_rows:
        raise LeanPlatformError(f"No adjustment factors found for {ticker}.")

    # A cumulative adjustment factor cannot legitimately change for one session
    # and immediately return to the prior value. TuShare occasionally publishes
    # this transient shape; LEAN interprets it as a dividend and requires a
    # non-zero reference price, so smooth only these isolated reversals.
    normalized_rows = list(clean_rows)
    sanitized_dates: list[str] = []
    for index in range(1, len(normalized_rows) - 1):
        previous_factor = normalized_rows[index - 1][1]
        item_date, current_factor = normalized_rows[index]
        next_factor = normalized_rows[index + 1][1]
        scale = max(abs(previous_factor), abs(current_factor), abs(next_factor), 1.0)
        current_changed = abs(current_factor - previous_factor) > scale * 1e-10
        next_restores_previous = abs(next_factor - previous_factor) <= scale * 1e-10
        if current_changed and next_restores_previous:
            normalized_rows[index] = (item_date, previous_factor)
            sanitized_dates.append(item_date.isoformat())
    clean_rows = normalized_rows

    prices: list[tuple[date, float]] = []
    for row in price_rows or []:
        raw_date = row.get("trade_date") or row.get("date")
        raw_close = row.get("close")
        if raw_date in (None, "") or raw_close in (None, ""):
            continue
        close = float(raw_close)
        if close > 0 and math.isfinite(close):
            prices.append((parse_date(str(raw_date)[:10]), close))
    prices.sort(key=lambda item: item[0])

    def previous_close(event_date: date) -> float | None:
        value = None
        for price_date, close in prices:
            if price_date >= event_date:
                break
            value = close
        return value

    latest_factor = clean_rows[-1][1]
    if latest_factor <= 0:
        raise LeanPlatformError(f"Invalid latest adjustment factor for {ticker}.")
    lines: list[str] = []
    event_dates: list[str] = []
    previous_factor = None
    for item_date, factor in clean_rows:
        if previous_factor is not None and abs(factor - previous_factor) <= max(abs(factor), abs(previous_factor), 1.0) * 1e-10:
            continue
        price_factor = factor / latest_factor
        if previous_factor is None:
            reference_price = 1.0
        else:
            reference_price = previous_close(item_date)
            if reference_price is None and require_reference_prices:
                raise LeanPlatformError(
                    f"Missing previous close for {ticker} factor event on {item_date.isoformat()}."
                )
            reference_price = reference_price or 1.0
            event_dates.append(item_date.isoformat())
        lines.append(f"{item_date:%Y%m%d},{price_factor:.10f},1,{reference_price:.10f}")
        previous_factor = factor
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
        "source_rows": len(clean_rows),
        "event_dates": event_dates,
        "sanitized_transient_dates": sanitized_dates,
    }


def validate_equity_factor_file(path: Path) -> dict[str, Any]:
    errors: list[str] = []
    rows: list[tuple[str, float, float, float]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {"passed": False, "errors": [str(exc)], "rows": 0}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        fields = [item.strip() for item in line.split(",")]
        if len(fields) < 4:
            errors.append(f"line_{line_number}:expected_4_fields")
            continue
        try:
            row = (fields[0], float(fields[1]), float(fields[2]), float(fields[3]))
        except ValueError:
            errors.append(f"line_{line_number}:invalid_numeric_value")
            continue
        if row[1] <= 0 or row[2] <= 0 or not all(math.isfinite(value) for value in row[1:]):
            errors.append(f"line_{line_number}:invalid_factor_value")
        rows.append(row)
    for index in range(1, len(rows)):
        _, previous_price_factor, previous_split_factor, _ = rows[index - 1]
        item_date, price_factor, split_factor, reference_price = rows[index]
        changed = (
            abs(price_factor - previous_price_factor) > max(abs(price_factor), abs(previous_price_factor), 1.0) * 1e-10
            or abs(split_factor - previous_split_factor) > max(abs(split_factor), abs(previous_split_factor), 1.0) * 1e-10
        )
        is_terminal = item_date == "20501231"
        if changed and not is_terminal and reference_price <= 0:
            errors.append(f"{item_date}:zero_reference_price")
    return {"passed": not errors, "errors": errors, "rows": len(rows)}
