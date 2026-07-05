import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from urllib.error import URLError
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .core.errors import LeanWebError
from .core.config import (
    ALGORITHM_PATH,
    DATA_DIR,
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_RESEARCH_IMAGE,
    HOST_DATA_DIR,
    HOST_PLATFORM_DIR,
    OBJECT_STORE_DIR,
    PLATFORM_DIR,
    PLOT_SCRIPT,
    REPO_ROOT,
)
from .domain.assets import (
    AssetRequest,
    asset_class_key,
    asset_request,
    canonical_symbol,
    data_type_key,
    has_lean_data,
    parse_lean_zip_price_series,
    resolution_key,
    venue_key,
)


class LeanPlatformError(LeanWebError, ValueError):
    pass


MARKET_CONFIG: dict[str, dict[str, Any]] = {
    "usa": {
        "name": "US Equity",
        "currency": "USD",
        "timezone": "America/New_York",
        "open": "09:30:00",
        "close": "16:00:00",
        "lot_size": "1",
        "tick_size": "0.01",
        "market_id": 1,
    },
    "china": {
        "name": "China A Share",
        "currency": "CNY",
        "timezone": "Asia/Shanghai",
        "open": "09:30:00",
        "close": "15:00:00",
        "lot_size": "100",
        "tick_size": "0.01",
        "market_id": 101,
    },
    "hongkong": {
        "name": "Hong Kong Equity",
        "currency": "HKD",
        "timezone": "Asia/Hong_Kong",
        "open": "09:30:00",
        "close": "16:00:00",
        "lot_size": "100",
        "tick_size": "0.01",
        "market_id": 102,
    },
}


def market_key(market: str | None = None) -> str:
    value = (market or "usa").strip().lower().replace("-", "").replace("_", "")
    aliases = {
        "us": "usa",
        "usa": "usa",
        "america": "usa",
        "cn": "china",
        "a": "china",
        "ashare": "china",
        "china": "china",
        "zh": "china",
        "hk": "hongkong",
        "hkg": "hongkong",
        "hongkong": "hongkong",
    }
    key = aliases.get(value, value)
    if key not in MARKET_CONFIG:
        raise LeanPlatformError(f"Unsupported market: {market!r}")
    return key


def symbol_key(symbol: str) -> str:
    cleaned = symbol.strip().lower()
    if not cleaned or not all(ch.isalnum() or ch in ".-" for ch in cleaned):
        raise LeanPlatformError(f"Invalid symbol: {symbol!r}")
    return cleaned


def normalize_symbol(symbol: str, market: str | None = None) -> str:
    key = market_key(market)
    value = symbol_key(symbol).upper().replace("_", ".")
    if key == "usa":
        return value.replace("-", ".")
    if key == "china":
        value = value.replace("SH", "").replace("SZ", "").replace("BJ", "").replace(".", "")
        if not value.isdigit() or len(value) != 6:
            raise LeanPlatformError("A-share symbols must be 6 digits, e.g. 600519 or 000001.")
        return value
    if key == "hongkong":
        value = value.replace("HK", "").replace(".", "")
        if not value.isdigit():
            raise LeanPlatformError("Hong Kong symbols must be numeric, e.g. 00700.")
        return value.zfill(5)
    return value


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise LeanPlatformError(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc


def lean_price(value: str | float) -> str:
    return str(int(round(float(value) * 10000)))


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


def download_text(url: str) -> str:
    last_error: Exception | None = None
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) lean-local-platform/1.0",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    for attempt in range(3):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.read().decode("utf-8-sig")
        except (OSError, URLError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))

    curl = shutil.which("curl")
    if curl:
        try:
            result = subprocess.run(
                [
                    curl,
                    "--silent",
                    "--show-error",
                    "--location",
                    "--max-time",
                    "40",
                    "-H",
                    f"User-Agent: {headers['User-Agent']}",
                    "-H",
                    "Accept: application/json,text/plain,*/*",
                    url,
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            if result.stdout.strip():
                return result.stdout
        except (OSError, subprocess.CalledProcessError) as exc:
            last_error = exc
    raise LeanPlatformError(f"Data provider request failed: {last_error}") from last_error


def fetch_alpha_vantage_rows(symbol: str, api_key: str, outputsize: str) -> list[dict[str, str]]:
    if outputsize not in {"compact", "full"}:
        raise LeanPlatformError("Alpha Vantage outputsize must be compact or full.")
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol.upper(),
        "outputsize": outputsize,
        "datatype": "csv",
        "apikey": api_key,
    }
    url = "https://www.alphavantage.co/query?" + urllib.parse.urlencode(params)
    text = download_text(url)
    first_line = text.splitlines()[0] if text.splitlines() else ""
    if "timestamp,open,high,low,close,volume" not in first_line:
        raise LeanPlatformError(
            "Alpha Vantage did not return daily CSV data. Check API key, rate limits, and entitlement."
        )
    return [
        {
            "date": row["timestamp"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        }
        for row in csv.DictReader(text.splitlines())
    ]


def fetch_stooq_rows(symbol: str) -> list[dict[str, str]]:
    ticker = symbol_key(symbol).replace(".", "-")
    url = f"https://stooq.com/q/d/l/?s={urllib.parse.quote(ticker)}.us&i=d"
    text = download_text(url)
    lines = text.splitlines()
    if text.lstrip().startswith("<!DOCTYPE") or "__verify" in text:
        raise LeanPlatformError("Stooq is requiring browser verification from this network; choose another provider.")
    if not lines or not lines[0].lower().startswith("date,open,high,low,close,volume"):
        raise LeanPlatformError(f"Stooq did not return daily CSV data for {symbol}.")
    rows = []
    for row in csv.DictReader(lines):
        if not row or (row.get("Close") or "").lower() == "null":
            continue
        rows.append(
            {
                "date": row["Date"],
                "open": row["Open"],
                "high": row["High"],
                "low": row["Low"],
                "close": row["Close"],
                "volume": row["Volume"],
            }
        )
    if not rows:
        raise LeanPlatformError(f"No Stooq rows found for {symbol}.")
    return rows


def fetch_yahoo_rows(symbol: str, start: str = "2000-01-01", end: str | None = None) -> list[dict[str, str]]:
    start_ts = int(datetime.combine(parse_date(start), datetime.min.time(), tzinfo=timezone.utc).timestamp())
    end_date = parse_date(end) if end else date.today()
    end_ts = int(datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    ticker = symbol_key(symbol).upper().replace(".", "-")
    params = urllib.parse.urlencode(
        {
            "period1": start_ts,
            "period2": end_ts,
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    text = download_text(f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{params}")
    if "Too Many Requests" in text:
        raise LeanPlatformError("Yahoo Finance is rate-limiting this network; choose another provider.")
    data = json.loads(text)
    result = ((data.get("chart") or {}).get("result") or [None])[0]
    if not result:
        error = (data.get("chart") or {}).get("error") or {}
        raise LeanPlatformError(f"Yahoo Finance did not return chart data for {symbol}: {error}")
    timestamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [{}])[0])
    rows = []
    for index, timestamp in enumerate(timestamps):
        try:
            open_price = quote["open"][index]
            high = quote["high"][index]
            low = quote["low"][index]
            close = quote["close"][index]
            volume = quote["volume"][index] or 0
        except (KeyError, IndexError):
            continue
        if None in (open_price, high, low, close):
            continue
        rows.append(
            {
                "date": datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat(),
                "open": str(open_price),
                "high": str(high),
                "low": str(low),
                "close": str(close),
                "volume": str(volume),
            }
        )
    if not rows:
        raise LeanPlatformError(f"No Yahoo Finance rows found for {symbol}.")
    return rows


def fetch_binance_crypto_rows(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    interval: str = "1d",
) -> list[dict[str, str]]:
    if interval not in {"1d", "1h", "1m"}:
        raise LeanPlatformError("Binance crypto interval must be 1d, 1h, or 1m.")
    ticker = canonical_symbol(symbol, "crypto")
    params: dict[str, str | int] = {"symbol": ticker, "interval": interval, "limit": 1000}
    if start:
        params["startTime"] = int(datetime.combine(parse_date(start), datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    if end:
        params["endTime"] = int(datetime.combine(parse_date(end), datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    url = "https://api.binance.com/api/v3/klines?" + urllib.parse.urlencode(params)
    text = download_text(url)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LeanPlatformError("Binance did not return JSON kline data.") from exc
    if isinstance(payload, dict) and payload.get("code"):
        raise LeanPlatformError(f"Binance error for {ticker}: {payload.get('msg') or payload}")
    rows = []
    for item in payload:
        if not isinstance(item, list) or len(item) < 6:
            continue
        rows.append(
            {
                "date": datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc).date().isoformat(),
                "open": str(item[1]),
                "high": str(item[2]),
                "low": str(item[3]),
                "close": str(item[4]),
                "volume": str(item[5]),
            }
        )
    if not rows:
        raise LeanPlatformError(f"No Binance rows found for {ticker}.")
    return rows


def _date_param(value: str | None, fallback: str) -> str:
    return parse_date(value).strftime("%Y%m%d") if value else fallback


def _adjust_param(adjust: str | None) -> str:
    value = (adjust or "").strip().lower()
    if value in {"none", "raw", "normal"}:
        return ""
    if value not in {"", "qfq", "hfq"}:
        raise LeanPlatformError("adjust must be one of raw, qfq, or hfq.")
    return value


def _china_prefixed_symbol(symbol: str) -> str:
    ticker = normalize_symbol(symbol, "china")
    if ticker.startswith(("6", "9")):
        return f"sh{ticker}"
    if ticker.startswith(("0", "2", "3")):
        return f"sz{ticker}"
    if ticker.startswith(("4", "8")):
        return f"bj{ticker}"
    return ticker


def _eastmoney_secid(symbol: str, market: str) -> str:
    ticker = normalize_symbol(symbol, market)
    if market == "china":
        exchange = "1" if ticker.startswith(("6", "9")) else "0"
        return f"{exchange}.{ticker}"
    if market == "hongkong":
        return f"116.{ticker}"
    if market == "usa":
        return ticker
    raise LeanPlatformError(f"EastMoney does not support market {market}.")


def _records_to_rows(records: list[dict[str, Any]], columns: dict[str, str]) -> list[dict[str, str]]:
    rows = []
    for record in records:
        try:
            rows.append(
                {
                    "date": str(record[columns["date"]])[:10],
                    "open": str(record[columns["open"]]),
                    "high": str(record[columns["high"]]),
                    "low": str(record[columns["low"]]),
                    "close": str(record[columns["close"]]),
                    "volume": str(record[columns["volume"]]),
                }
            )
        except KeyError as exc:
            raise LeanPlatformError(f"Provider response is missing column {exc.args[0]!r}.") from exc
    if not rows:
        raise LeanPlatformError("Provider returned no OHLCV rows.")
    return rows


def _akshare_module():
    try:
        import akshare as ak  # type: ignore
    except ImportError as exc:
        raise LeanPlatformError("AKShare is not installed. Run: pip install -r web/backend/requirements.txt") from exc
    return ak


def _ak_dataframe_rows(frame, columns: dict[str, str]) -> list[dict[str, str]]:
    if frame is None or getattr(frame, "empty", True):
        raise LeanPlatformError("Provider returned an empty data frame.")
    return _records_to_rows(frame.to_dict("records"), columns)


def _filter_rows_by_date(rows: list[dict[str, str]], start: str | None, end: str | None, provider_name: str, symbol: str) -> list[dict[str, str]]:
    start_date = parse_date(start) if start else None
    end_date = parse_date(end) if end else None
    filtered = [
        row
        for row in rows
        if (start_date is None or parse_date(row["date"]) >= start_date)
        and (end_date is None or parse_date(row["date"]) <= end_date)
    ]
    if not filtered:
        raise LeanPlatformError(f"{provider_name} returned no daily rows for {symbol}.")
    return filtered


def fetch_eastmoney_rows(
    symbol: str,
    market: str,
    start: str | None = None,
    end: str | None = None,
    adjust: str | None = None,
) -> list[dict[str, str]]:
    market = market_key(market)
    if market not in {"china", "hongkong"}:
        raise LeanPlatformError("EastMoney provider supports China A-share and Hong Kong daily data in this platform.")
    fqt = {"": "0", "qfq": "1", "hfq": "2"}[_adjust_param(adjust)]
    params = urllib.parse.urlencode(
        {
            "secid": _eastmoney_secid(symbol, market),
            "klt": "101",
            "fqt": fqt,
            "beg": _date_param(start, "19900101"),
            "end": _date_param(end, "20500101"),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        }
    )
    text = download_text("https://push2his.eastmoney.com/api/qt/stock/kline/get?" + params)
    data = json.loads(text)
    klines = ((data.get("data") or {}).get("klines") or [])
    rows = []
    for line in klines:
        fields = str(line).split(",")
        if len(fields) < 6:
            continue
        rows.append(
            {
                "date": fields[0],
                "open": fields[1],
                "close": fields[2],
                "high": fields[3],
                "low": fields[4],
                "volume": fields[5],
            }
        )
    if not rows:
        raise LeanPlatformError(f"EastMoney returned no daily rows for {symbol}.")
    return rows


def fetch_akshare_rows(
    symbol: str,
    market: str,
    start: str | None = None,
    end: str | None = None,
    adjust: str | None = None,
) -> list[dict[str, str]]:
    market = market_key(market)
    ak = _akshare_module()
    adjust_value = _adjust_param(adjust)
    start_value = _date_param(start, "19900101")
    end_value = _date_param(end, date.today().strftime("%Y%m%d"))
    if market == "china":
        try:
            frame = ak.stock_zh_a_hist(
                symbol=normalize_symbol(symbol, market),
                period="daily",
                start_date=start_value,
                end_date=end_value,
                adjust=adjust_value,
            )
            return _ak_dataframe_rows(
                frame,
                {"date": "日期", "open": "开盘", "high": "最高", "low": "最低", "close": "收盘", "volume": "成交量"},
            )
        except Exception as primary_exc:
            try:
                frame = ak.stock_zh_a_daily(
                    symbol=_china_prefixed_symbol(symbol),
                    start_date=start_value,
                    end_date=end_value,
                    adjust=adjust_value,
                )
                return _ak_dataframe_rows(
                    frame,
                    {"date": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"},
                )
            except Exception as fallback_exc:
                raise LeanPlatformError(
                    f"AKShare request failed for {symbol}: {fallback_exc}; primary endpoint failed with {primary_exc}"
                ) from fallback_exc
    if market == "hongkong":
        try:
            frame = ak.stock_hk_daily(symbol=normalize_symbol(symbol, market), adjust=adjust_value)
            rows = _ak_dataframe_rows(
                frame,
                {"date": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"},
            )
            return _filter_rows_by_date(rows, start, end, "AKShare", symbol)
        except LeanPlatformError:
            raise
        except Exception as exc:
            raise LeanPlatformError(f"AKShare request failed for {symbol}: {exc}") from exc
    if market == "usa":
        try:
            frame = ak.stock_us_daily(symbol=normalize_symbol(symbol, market), adjust=adjust_value)
            return _ak_dataframe_rows(
                frame,
                {"date": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"},
            )
        except LeanPlatformError:
            raise
        except Exception as exc:
            raise LeanPlatformError(f"AKShare request failed for {symbol}: {exc}") from exc
    raise LeanPlatformError(f"AKShare does not support market {market}.")


def fetch_sina_rows(
    symbol: str,
    market: str,
    start: str | None = None,
    end: str | None = None,
    adjust: str | None = None,
) -> list[dict[str, str]]:
    market = market_key(market)
    ak = _akshare_module()
    adjust_value = _adjust_param(adjust)
    if market == "china":
        frame = ak.stock_zh_a_daily(
            symbol=_china_prefixed_symbol(symbol),
            start_date=_date_param(start, "19900101"),
            end_date=_date_param(end, date.today().strftime("%Y%m%d")),
            adjust=adjust_value,
        )
        return _ak_dataframe_rows(
            frame,
            {"date": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"},
        )
    if market == "hongkong":
        frame = ak.stock_hk_daily(symbol=normalize_symbol(symbol, market), adjust=adjust_value)
        rows = _ak_dataframe_rows(
            frame,
            {"date": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"},
        )
        return _filter_rows_by_date(rows, start, end, "Sina", symbol)
    if market == "usa":
        frame = ak.stock_us_daily(symbol=normalize_symbol(symbol, market), adjust=adjust_value)
        return _ak_dataframe_rows(
            frame,
            {"date": "date", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"},
        )
    raise LeanPlatformError(f"Sina provider does not support market {market}.")


def fetch_tonghuashun_rows(
    symbol: str,
    market: str,
    start: str | None = None,
    end: str | None = None,
    adjust: str | None = None,
) -> list[dict[str, str]]:
    market = market_key(market)
    if market != "china":
        raise LeanPlatformError("TongHuaShun provider is enabled for A-share daily data only.")
    # AKShare does not expose a stable TongHuaShun individual daily endpoint. Use
    # its A-share history adapter for the same normalized OHLCV contract.
    return fetch_akshare_rows(symbol, market, start=start, end=end, adjust=adjust)


def lean_job_parameters(parameters: dict[str, Any]) -> dict[str, str]:
    excluded = {"dockerImage", "fastValues", "slowValues"}
    clean: dict[str, str] = {}
    for key, value in parameters.items():
        if key in excluded or value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[key] = str(value)
    return clean


def base_config(
    algorithm_id: str,
    parameters: dict[str, Any],
    algorithm_class: str = "DockerDemoAlgorithm",
    algorithm_location: str = "/Lean/DockerDemoAlgorithm.py",
    language: str = "Python",
) -> dict[str, Any]:
    python_paths = ["/Lean/Run"] if parameters.get("ashareRules") else []
    return {
        "environment": "backtesting",
        "algorithm-id": algorithm_id,
        "backtest-name": f"Local {parameters.get('assetClass', 'equity')} {parameters['ticker']} Backtest",
        "algorithm-type-name": algorithm_class,
        "algorithm-language": language,
        "algorithm-location": algorithm_location,
        "data-folder": "/Lean/Data",
        "results-destination-folder": "/Lean/Results",
        "close-automatically": True,
        "debugging": False,
        "debugging-method": "LocalCmdline",
        "log-handler": "QuantConnect.Logging.CompositeLogHandler",
        "messaging-handler": "QuantConnect.Messaging.Messaging",
        "job-queue-handler": "QuantConnect.Queues.JobQueue",
        "api-handler": "QuantConnect.Api.Api",
        "map-file-provider": "QuantConnect.Data.Auxiliary.LocalDiskMapFileProvider",
        "factor-file-provider": "QuantConnect.Data.Auxiliary.LocalDiskFactorFileProvider",
        "data-provider": "QuantConnect.Lean.Engine.DataFeeds.DefaultDataProvider",
        "data-channel-provider": "DataChannelProvider",
        "object-store": "QuantConnect.Lean.Engine.Storage.LocalObjectStore",
        "data-aggregator": "QuantConnect.Lean.Engine.DataFeeds.AggregationManager",
        "symbol-minute-limit": 10000,
        "symbol-second-limit": 10000,
        "symbol-tick-limit": 10000,
        "seed-lookback-period": 5,
        "seed-retry-minute-lookback-period": 1440,
        "seed-retry-hour-lookback-period": 24,
        "seed-retry-daily-lookback-period": 10,
        "ignore-unknown-asset-holdings": True,
        "show-missing-data-logs": True,
        "maximum-warmup-history-days-look-back": 5,
        "maximum-data-points-per-chart-series": 1000000,
        "maximum-chart-series": 30,
        "force-exchange-always-open": False,
        "transaction-log": "",
        "reserved-words-prefix": "@",
        "job-user-id": "0",
        "project-id": "0",
        "api-access-token": "",
        "job-organization-id": "",
        "parameters": lean_job_parameters(parameters),
        "python-additional-paths": python_paths,
        "environments": {
            "backtesting": {
                "live-mode": False,
                "setup-handler": "QuantConnect.Lean.Engine.Setup.BacktestingSetupHandler",
                "result-handler": "QuantConnect.Lean.Engine.Results.BacktestingResultHandler",
                "data-feed-handler": "QuantConnect.Lean.Engine.DataFeeds.FileSystemDataFeed",
                "real-time-handler": "QuantConnect.Lean.Engine.RealTime.BacktestingRealTimeHandler",
                "history-provider": [
                    "QuantConnect.Lean.Engine.HistoricalData.SubscriptionDataReaderHistoryProvider"
                ],
                "transaction-handler": "QuantConnect.Lean.Engine.TransactionHandlers.BacktestingTransactionHandler",
            }
        },
    }


def validate_backtest_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    requested_asset_class = asset_class_key(str(parameters.get("assetClass") or parameters.get("asset_class") or "equity"))
    requested_resolution = resolution_key(str(parameters.get("resolution") or "daily"))
    requested_data_type = data_type_key(str(parameters.get("dataType") or parameters.get("data_type") or "trade"))
    if requested_asset_class == "equity":
        market = market_key(str(parameters.get("market", parameters.get("venue", "usa"))))
        ticker = normalize_symbol(str(parameters["ticker"]), market).upper()
        venue = market
    else:
        venue = venue_key(requested_asset_class, str(parameters.get("venue") or parameters.get("market") or ""), None)
        market = venue
        ticker = canonical_symbol(str(parameters["ticker"]), requested_asset_class)
    start = parse_date(str(parameters["start"]))
    end = parse_date(str(parameters["end"]))
    if end <= start:
        raise LeanPlatformError("End date must be after start date.")
    cash = float(parameters.get("cash", 100000))
    if cash <= 0:
        raise LeanPlatformError("Cash must be positive.")
    data_request = AssetRequest(
        requested_asset_class,
        ticker,
        venue,
        requested_resolution,
        requested_data_type,
    )
    if not (requested_asset_class == "equity" and market == "china") and not has_lean_data(data_request):
        raise LeanPlatformError(
            f"Missing LEAN {requested_resolution} {requested_data_type} data for "
            f"{ticker} ({requested_asset_class}/{venue})."
        )

    clean: dict[str, Any] = {
        "ticker": ticker,
        "assetClass": requested_asset_class,
        "market": market,
        "venue": venue,
        "resolution": requested_resolution,
        "dataType": requested_data_type,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "cash": cash,
    }
    for key, value in parameters.items():
        if key in {
            "ticker",
            "symbol",
            "assetClass",
            "asset_class",
            "market",
            "venue",
            "resolution",
            "dataType",
            "data_type",
            "start",
            "end",
            "cash",
            "dockerImage",
            "projectId",
            "parameters",
        }:
            continue
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
    return clean


def docker_command(
    config_path: Path,
    results_dir: Path,
    image: str = DEFAULT_DOCKER_IMAGE,
    algorithm_path: Path = ALGORITHM_PATH,
    algorithm_container_path: str = "/Lean/DockerDemoAlgorithm.py",
    project_dir: Path | None = None,
    support_dir: Path | None = None,
) -> list[str]:
    docker = shutil.which("docker")
    if not docker:
        raise LeanPlatformError("docker command not found.")
    def mount_source(path: Path) -> str:
        resolved = Path(path)
        data_mount_root = HOST_DATA_DIR if os.environ.get("LEAN_HOST_DATA_DIR") else DATA_DIR
        platform_mount_root = HOST_PLATFORM_DIR if os.environ.get("LEAN_HOST_PLATFORM_DIR") else PLATFORM_DIR
        try:
            relative = resolved.relative_to(DATA_DIR)
            return str(data_mount_root / relative)
        except ValueError:
            pass
        try:
            relative = resolved.relative_to(PLATFORM_DIR)
            return str(platform_mount_root / relative)
        except ValueError:
            return str(resolved)

    command = [
        docker,
        "run",
        "--rm",
        "--name",
        f"lean-{config_path.parent.name}"[:60],
        "-v",
        f"{mount_source(config_path)}:/Lean/Launcher/bin/Debug/config.json:ro",
        "-v",
        f"{mount_source(DATA_DIR)}:/Lean/Data:ro",
        "-v",
        f"{mount_source(results_dir)}:/Lean/Results",
        "-v",
        f"{mount_source(OBJECT_STORE_DIR)}:/Lean/Launcher/bin/Debug/storage",
        image,
    ]
    if project_dir is not None:
        command[-1:-1] = ["-v", f"{mount_source(project_dir)}:/Lean/Project:ro"]
    else:
        command[-1:-1] = ["-v", f"{mount_source(algorithm_path)}:{algorithm_container_path}:ro"]
    if support_dir is not None:
        command[-1:-1] = ["-v", f"{mount_source(support_dir)}:/Lean/Run:ro"]
    return command


def render_report(result_json: Path, report_html: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(PLOT_SCRIPT),
            "--input",
            str(result_json),
            "--output",
            str(report_html),
        ],
        check=True,
        cwd=REPO_ROOT,
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def extract_statistics(result_json: Path, summary_json: Path | None = None) -> dict[str, Any]:
    source = summary_json if summary_json and summary_json.exists() else result_json
    if not source.exists():
        return {}
    data = load_json(source)
    return data.get("statistics") or data.get("Statistics") or {}


def point_series(chart: dict[str, Any], name: str) -> list[dict[str, Any]]:
    series = (chart.get("series") or {}).get(name) or {}
    points = []
    for row in series.get("values", []):
        if len(row) < 2:
            continue
        timestamp = float(row[0])
        value = float(row[-1])
        if math.isfinite(timestamp) and math.isfinite(value):
            points.append(
                {
                    "time": datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(),
                    "value": value,
                }
            )
    return points


def read_lean_daily_price_series(
    symbol: str,
    market: str | None = None,
    start: str | None = None,
    end: str | None = None,
    asset_class: str | None = None,
    venue: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
) -> list[dict[str, Any]]:
    start_date = parse_date(start) if start else None
    end_date = parse_date(end) if end else None
    try:
        if asset_class_key(asset_class or "equity") == "equity":
            market_value = market_key(market or venue)
            request = AssetRequest("equity", normalize_symbol(symbol, market_value).upper(), market_value, resolution_key(resolution), data_type_key(data_type))
        else:
            request = asset_request(symbol, asset_class, venue=venue or market, resolution=resolution, data_type=data_type)
    except LeanWebError:
        return []
    return parse_lean_zip_price_series(request, start_date, end_date)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _nearest_value(points: list[dict[str, Any]], time_value: str | None) -> float | None:
    target = _parse_time(time_value)
    if target is None or not points:
        return None
    nearest = min(
        points,
        key=lambda point: abs((_parse_time(point.get("time")) or target) - target),
    )
    return float(nearest["value"])


def extract_chart_data(
    result_json: Path,
    symbol: str | None = None,
    market: str | None = None,
    start: str | None = None,
    end: str | None = None,
    asset_class: str | None = None,
    venue: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
) -> dict[str, Any]:
    data = load_json(result_json)
    charts = data.get("charts") or {}
    equity = charts.get("Strategy Equity") or {}
    drawdown = charts.get("Drawdown") or {}
    ema = charts.get("EMA") or {}
    benchmark = charts.get("Benchmark") or {}

    orders = []
    for order in (data.get("orders") or {}).values():
        quantity = float(order.get("quantity", 0))
        time_value = order.get("lastFillTime") or order.get("time")
        orders.append(
            {
                "time": time_value,
                "side": "BUY" if quantity > 0 else "SELL",
                "symbol": ((order.get("symbol") or {}).get("value") or ""),
                "quantity": quantity,
                "price": float(order.get("price") or 0),
                "tag": order.get("tag") or "",
            }
        )

    inferred_symbol = symbol or next((order["symbol"] for order in orders if order["symbol"]), None)
    price = (
        read_lean_daily_price_series(
            inferred_symbol,
            market,
            start,
            end,
            asset_class=asset_class,
            venue=venue,
            resolution=resolution,
            data_type=data_type,
        )
        if inferred_symbol
        else []
    )
    equity_series = point_series(equity, "Equity")
    order_markers = [
        {
            **order,
            "fillPrice": order["price"],
            "priceValue": _nearest_value(price, order["time"]) or order["price"],
            "equityValue": _nearest_value(equity_series, order["time"]),
        }
        for order in orders
    ]

    return {
        "statistics": data.get("statistics") or {},
        "series": {
            "equity": equity_series,
            "return": point_series(equity, "Return"),
            "drawdown": point_series(drawdown, "Equity Drawdown"),
            "emaFast": point_series(ema, "Fast"),
            "emaSlow": point_series(ema, "Slow"),
            "benchmark": point_series(benchmark, "Benchmark"),
            "price": price,
        },
        "orders": orders,
        "orderMarkers": order_markers,
    }


def run_command_stream(command: list[str], output_callback, cwd: Path = REPO_ROOT) -> int:
    output_callback("running: " + " ".join(command))
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        output_callback(line.rstrip())
    return process.wait()


def run_docker_backtest(
    run_id: str,
    parameters: dict[str, Any],
    docker_image: str,
    run_dir: Path,
    output_callback,
    algorithm_path: Path = ALGORITHM_PATH,
    algorithm_class: str = "DockerDemoAlgorithm",
    language: str = "Python",
    project_dir: Path | None = None,
) -> dict[str, Any]:
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    if parameters.get("ashareRules"):
        from .services.ashare_execution import write_ashare_execution_artifacts

        write_ashare_execution_artifacts(run_dir, parameters)
    config_path = run_dir / "config.json"
    algorithm_container_path = "/Lean/Project/main.py" if project_dir is not None else "/Lean/DockerDemoAlgorithm.py"
    config_path.write_text(
        json.dumps(
            base_config(
                run_id,
                parameters,
                algorithm_class=algorithm_class,
                algorithm_location=algorithm_container_path,
                language=language,
            ),
            indent=2,
        ),
        encoding="utf-8",
    )

    command = docker_command(
        config_path,
        results_dir,
        docker_image,
        algorithm_path=algorithm_path,
        algorithm_container_path=algorithm_container_path,
        project_dir=project_dir,
        support_dir=run_dir if parameters.get("ashareRules") else None,
    )
    exit_code = run_command_stream(command, output_callback)

    result_json = results_dir / f"{run_id}.json"
    summary_json = results_dir / f"{run_id}-summary.json"
    report_html = results_dir / "report.html"
    if exit_code == 0 and result_json.exists():
        render_report(result_json, report_html)

    return {
        "exit_code": exit_code,
        "result_json_path": str(result_json) if result_json.exists() else None,
        "summary_json_path": str(summary_json) if summary_json.exists() else None,
        "report_html_path": str(report_html) if report_html.exists() else None,
        "statistics": extract_statistics(result_json, summary_json if summary_json.exists() else None)
        if result_json.exists()
        else {},
    }


def run_detached_research(
    session_id: str,
    project_dir: Path,
    port: int,
    output_callback,
    image: str = DEFAULT_RESEARCH_IMAGE,
) -> dict[str, Any]:
    docker = shutil.which("docker")
    if not docker:
        raise LeanPlatformError("docker command not found.")
    command = [
        docker,
        "run",
        "-d",
        "--name",
        f"lean-research-{session_id}"[:60],
        "-p",
        f"{port}:8888",
        "-v",
        f"{DATA_DIR}:/Lean/Data:ro",
        "-v",
        f"{project_dir}:/Lean/Project",
        "-v",
        f"{OBJECT_STORE_DIR}:/Lean/Launcher/bin/Debug/storage",
        image,
    ]
    output_callback("running: " + " ".join(command))
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if completed.stdout:
        output_callback(completed.stdout.strip())
    if completed.stderr:
        output_callback(completed.stderr.strip())
    if completed.returncode != 0:
        raise LeanPlatformError(f"Research container failed to start: {completed.stderr or completed.stdout}")
    return {"container_id": completed.stdout.strip(), "url": f"http://127.0.0.1:{port}"}


def stop_container(container_id: str) -> None:
    docker = shutil.which("docker")
    if not docker:
        raise LeanPlatformError("docker command not found.")
    subprocess.run([docker, "stop", container_id], cwd=REPO_ROOT, check=False)


def new_run_id(symbol: str, start: str, end: str) -> str:
    return f"{symbol_key(symbol)}-{start.replace('-', '')}-{end.replace('-', '')}-{time.strftime('%Y%m%d%H%M%S')}"
