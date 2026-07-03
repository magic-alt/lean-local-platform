import csv
import json
import math
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .core.errors import LeanWebError
from .core.config import (
    ALGORITHM_PATH,
    DATA_DIR,
    DEFAULT_DOCKER_IMAGE,
    DEFAULT_RESEARCH_IMAGE,
    OBJECT_STORE_DIR,
    PLOT_SCRIPT,
    REPO_ROOT,
)


class LeanPlatformError(LeanWebError, ValueError):
    pass


def symbol_key(symbol: str) -> str:
    cleaned = symbol.strip().lower()
    if not cleaned or not all(ch.isalnum() or ch in ".-" for ch in cleaned):
        raise LeanPlatformError(f"Invalid symbol: {symbol!r}")
    return cleaned


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise LeanPlatformError(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc


def lean_price(value: str | float) -> str:
    return str(int(round(float(value) * 10000)))


def daily_zip_path(symbol: str) -> Path:
    return DATA_DIR / "equity" / "usa" / "daily" / f"{symbol_key(symbol)}.zip"


def list_local_symbols() -> list[str]:
    daily_dir = DATA_DIR / "equity" / "usa" / "daily"
    if not daily_dir.exists():
        return []
    return sorted(path.stem.upper() for path in daily_dir.glob("*.zip"))


def ensure_equity_dirs() -> None:
    for relative in ("equity/usa/daily", "equity/usa/map_files", "equity/usa/factor_files"):
        (DATA_DIR / relative).mkdir(parents=True, exist_ok=True)


def write_auxiliary_files(symbol: str, first_date: date) -> None:
    ticker = symbol_key(symbol)
    ensure_equity_dirs()
    start = first_date.strftime("%Y%m%d")

    map_file = DATA_DIR / "equity" / "usa" / "map_files" / f"{ticker}.csv"
    if not map_file.exists():
        map_file.write_text(f"{start},{ticker},P\n20501231,{ticker},P\n", encoding="utf-8")

    factor_file = DATA_DIR / "equity" / "usa" / "factor_files" / f"{ticker}.csv"
    if not factor_file.exists():
        factor_file.write_text(f"{start},1,1,0\n20501231,1,1,0\n", encoding="utf-8")


def normalize_rows(rows: list[dict[str, str]]) -> list[tuple[date, float, float, float, float, int]]:
    normalized: list[tuple[date, float, float, float, float, int]] = []
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
        if min(open_price, high, low, close) <= 0 or volume < 0:
            continue
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
) -> dict[str, Any]:
    ticker = symbol_key(symbol)
    normalized = normalize_rows(rows)
    ensure_equity_dirs()
    write_auxiliary_files(ticker, normalized[0][0])

    output = daily_zip_path(ticker)
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
    request = urllib.request.Request(url, headers={"User-Agent": "lean-local-platform/1.0"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read().decode("utf-8-sig")


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
    return {
        "environment": "backtesting",
        "algorithm-id": algorithm_id,
        "backtest-name": f"Local {parameters['ticker']} EMA Backtest",
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
        "python-additional-paths": [],
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
    ticker = symbol_key(str(parameters["ticker"])).upper()
    start = parse_date(str(parameters["start"]))
    end = parse_date(str(parameters["end"]))
    if end <= start:
        raise LeanPlatformError("End date must be after start date.")
    fast = int(parameters.get("fast", 10))
    slow = int(parameters.get("slow", 30))
    if fast <= 0 or slow <= 0:
        raise LeanPlatformError("EMA periods must be positive.")
    cash = float(parameters.get("cash", 100000))
    if cash <= 0:
        raise LeanPlatformError("Cash must be positive.")
    if not daily_zip_path(ticker).exists():
        raise LeanPlatformError(f"Missing LEAN daily data for {ticker}.")
    return {
        "ticker": ticker,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "fast": fast,
        "slow": slow,
        "cash": cash,
    }


def docker_command(
    config_path: Path,
    results_dir: Path,
    image: str = DEFAULT_DOCKER_IMAGE,
    algorithm_path: Path = ALGORITHM_PATH,
    algorithm_container_path: str = "/Lean/DockerDemoAlgorithm.py",
    project_dir: Path | None = None,
) -> list[str]:
    docker = shutil.which("docker")
    if not docker:
        raise LeanPlatformError("docker command not found.")
    command = [
        docker,
        "run",
        "--rm",
        "--name",
        f"lean-{config_path.parent.name}"[:60],
        "-v",
        f"{config_path}:/Lean/Launcher/bin/Debug/config.json:ro",
        "-v",
        f"{DATA_DIR}:/Lean/Data:ro",
        "-v",
        f"{results_dir}:/Lean/Results",
        "-v",
        f"{OBJECT_STORE_DIR}:/Lean/Launcher/bin/Debug/storage",
        image,
    ]
    if project_dir is not None:
        command[-1:-1] = ["-v", f"{project_dir}:/Lean/Project:ro"]
    else:
        command[-1:-1] = ["-v", f"{algorithm_path}:{algorithm_container_path}:ro"]
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
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    path = daily_zip_path(symbol)
    if not path.exists():
        return []
    start_date = parse_date(start) if start else None
    end_date = parse_date(end) if end else None
    ticker = symbol_key(symbol)
    points: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as archive:
        name = f"{ticker}.csv"
        members = archive.namelist()
        if name not in members and members:
            name = members[0]
        with archive.open(name) as file:
            for raw_line in file:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                fields = line.split(",")
                if len(fields) < 5:
                    continue
                item_date = datetime.strptime(fields[0].split()[0], "%Y%m%d").date()
                if start_date and item_date < start_date:
                    continue
                if end_date and item_date > end_date:
                    continue
                timestamp = datetime(item_date.year, item_date.month, item_date.day, 21, tzinfo=timezone.utc)
                close = float(fields[4]) / 10000
                points.append({"time": timestamp.isoformat(), "value": close})
    return points


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
    start: str | None = None,
    end: str | None = None,
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
    price = read_lean_daily_price_series(inferred_symbol, start, end) if inferred_symbol else []
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
