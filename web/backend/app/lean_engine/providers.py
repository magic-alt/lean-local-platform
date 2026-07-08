from __future__ import annotations

import csv
import json
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.error import URLError

from ..domain.assets import canonical_symbol
from .errors import LeanPlatformError
from .symbols import market_key, normalize_symbol, parse_date, symbol_key

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
    interval_ms = {"1m": 60_000, "1h": 3_600_000, "1d": 86_400_000}[interval]
    start_dt = parse_date(start) if start else None
    end_dt = parse_date(end) if end else None
    start_ms = int(datetime.combine(start_dt, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000) if start_dt else None
    end_ms = (
        int(datetime.combine(end_dt + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000) - 1
        if end_dt
        else None
    )
    cursor_ms: int | None = start_ms
    rows: list[dict[str, str]] = []
    while True:
        params: dict[str, str | int] = {"symbol": ticker, "interval": interval, "limit": 1000}
        if cursor_ms is not None:
            params["startTime"] = cursor_ms
        if end_ms is not None:
            params["endTime"] = end_ms
        url = "https://api.binance.com/api/v3/klines?" + urllib.parse.urlencode(params)
        text = download_text(url)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LeanPlatformError("Binance did not return JSON kline data.") from exc
        if isinstance(payload, dict) and payload.get("code"):
            raise LeanPlatformError(f"Binance error for {ticker}: {payload.get('msg') or payload}")
        if not isinstance(payload, list):
            raise LeanPlatformError(f"Binance returned malformed kline payload for {ticker}.")
        batch: list[dict[str, str]] = []
        for item in payload:
            if not isinstance(item, list) or len(item) < 6:
                continue
            batch.append(
                {
                    "date": datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc).date().isoformat(),
                    "open": str(item[1]),
                    "high": str(item[2]),
                    "low": str(item[3]),
                    "close": str(item[4]),
                    "volume": str(item[5]),
                }
            )
        rows.extend(batch)
        if len(payload) < 1000:
            break
        if end_ms is not None and cursor_ms is not None and cursor_ms > end_ms:
            break
        last_open = int(payload[-1][0])
        cursor_ms = last_open + interval_ms
    rows.sort(key=lambda item: item["date"])
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
