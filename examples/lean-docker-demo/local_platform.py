#!/usr/bin/env python3
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.reporting.html_report import render_report_file  # noqa: E402

DATA_DIR = Path(os.environ.get("LEAN_DATA_DIR", REPO_ROOT.parent / "Data")).expanduser()
EXAMPLE_RUNTIME_DIR = REPO_ROOT / "web" / "runtime" / "examples" / "lean-docker-demo"
RUNS_DIR = EXAMPLE_RUNTIME_DIR / "runs"
RESULTS_DIR = EXAMPLE_RUNTIME_DIR / "results"
ALGORITHM_PATH = SCRIPT_DIR / "DockerDemoAlgorithm.py"


def display_path(path):
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def die(message, code=1):
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        die(f"invalid date {value!r}; expected YYYY-MM-DD")


def symbol_key(symbol):
    cleaned = symbol.strip().lower()
    if not cleaned or not all(ch.isalnum() or ch in ".-" for ch in cleaned):
        die(f"invalid symbol {symbol!r}")
    return cleaned


def lean_price(value):
    return str(int(round(float(value) * 10000)))


def daily_zip_path(symbol):
    return DATA_DIR / "equity" / "usa" / "daily" / f"{symbol_key(symbol)}.zip"


def ensure_equity_dirs():
    for relative in [
        "equity/usa/daily",
        "equity/usa/map_files",
        "equity/usa/factor_files",
    ]:
        (DATA_DIR / relative).mkdir(parents=True, exist_ok=True)


def write_auxiliary_files(symbol, first_date):
    ticker = symbol_key(symbol)
    ensure_equity_dirs()
    start = first_date.strftime("%Y%m%d")

    map_file = DATA_DIR / "equity" / "usa" / "map_files" / f"{ticker}.csv"
    if not map_file.exists():
        map_file.write_text(f"{start},{ticker},P\n20501231,{ticker},P\n", encoding="utf-8")

    factor_file = DATA_DIR / "equity" / "usa" / "factor_files" / f"{ticker}.csv"
    if not factor_file.exists():
        factor_file.write_text(f"{start},1,1,0\n20501231,1,1,0\n", encoding="utf-8")


def write_lean_daily_zip(symbol, rows, source, overwrite=False):
    ticker = symbol_key(symbol)
    normalized = []
    for row in rows:
        date = parse_date(row["date"])
        open_price = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        volume = int(float(row["volume"]))
        if min(open_price, high, low, close) <= 0 or volume < 0:
            continue
        normalized.append((date, open_price, high, low, close, volume))

    normalized.sort(key=lambda item: item[0])
    if not normalized:
        die("no valid OHLCV rows to write")

    ensure_equity_dirs()
    write_auxiliary_files(ticker, normalized[0][0])

    csv_lines = []
    for date, open_price, high, low, close, volume in normalized:
        csv_lines.append(
            f"{date:%Y%m%d} 00:00,{lean_price(open_price)},{lean_price(high)},"
            f"{lean_price(low)},{lean_price(close)},{volume}"
        )

    output = daily_zip_path(ticker)
    if output.exists() and not overwrite:
        die(f"{output} already exists; pass --overwrite if you really want to replace it")

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{ticker}.csv", "\n".join(csv_lines) + "\n")

    metadata_dir = EXAMPLE_RUNTIME_DIR / "data-metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "symbol": ticker.upper(),
        "source": source,
        "rows": len(csv_lines),
        "first_date": normalized[0][0].isoformat(),
        "last_date": normalized[-1][0].isoformat(),
        "lean_file": display_path(output),
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
        "notes": [
            "Imported as raw daily TradeBar data.",
            "Factor and map files are minimal placeholders.",
            "Corporate actions are not reconstructed unless your source data already reflects them.",
        ],
    }
    (metadata_dir / f"{ticker}.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"wrote {output} ({len(csv_lines)} rows, {normalized[0][0]} to {normalized[-1][0]})")


def read_generic_csv(path, args):
    rows = []
    with Path(path).open(newline="", encoding=args.encoding) as file:
        reader = csv.DictReader(file)
        for row in reader:
            if not row:
                continue
            try:
                rows.append({
                    "date": row[args.date_col][:10],
                    "open": row[args.open_col],
                    "high": row[args.high_col],
                    "low": row[args.low_col],
                    "close": row[args.close_col],
                    "volume": row[args.volume_col],
                })
            except KeyError as err:
                die(f"missing column {err.args[0]!r} in {path}")
    return rows


def download_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "lean-local-platform/1.0"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read().decode("utf-8-sig")


def fetch_alpha_vantage(args):
    api_key = args.api_key or os.environ.get("ALPHAVANTAGE_API_KEY")
    if not api_key:
        die("Alpha Vantage requires --api-key or ALPHAVANTAGE_API_KEY")

    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": args.symbol.upper(),
        "outputsize": args.outputsize,
        "datatype": "csv",
        "apikey": api_key,
    }
    url = "https://www.alphavantage.co/query?" + urllib.parse.urlencode(params)
    print(f"downloading Alpha Vantage daily data for {args.symbol.upper()}...")
    text = download_text(url)
    if "timestamp,open,high,low,close,volume" not in text.splitlines()[0]:
        print(text[:800], file=sys.stderr)
        die("Alpha Vantage did not return a daily CSV; check API key, rate limits, and entitlement")

    reader = csv.DictReader(text.splitlines())
    rows = [
        {
            "date": row["timestamp"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        }
        for row in reader
    ]
    write_lean_daily_zip(args.symbol, rows, f"alpha_vantage:{args.outputsize}", overwrite=args.overwrite)


def import_csv(args):
    rows = read_generic_csv(args.csv_file, args)
    write_lean_daily_zip(args.symbol, rows, f"csv:{Path(args.csv_file).name}", overwrite=args.overwrite)


def list_symbols(_args):
    daily_dir = DATA_DIR / "equity" / "usa" / "daily"
    if not daily_dir.exists():
        print("no local daily data directory")
        return

    symbols = sorted(path.stem.upper() for path in daily_dir.glob("*.zip"))
    for symbol in symbols:
        print(symbol)
    print(f"\n{len(symbols)} symbols in {daily_dir}")


def show_sources(_args):
    print(
        """Suitable data sources for this local LEAN platform:

1. Existing QuantConnect/Lean sample data
   - Already in Data/.
   - Good for smoke tests and framework development.

2. Alpha Vantage
   - API key required.
   - Daily CSV is easy to convert to LEAN daily equity format.
   - Free/premium entitlements and rate limits apply.
   - Command: fetch-alpha-vantage SYMBOL --api-key KEY

3. Generic CSV export from any provider
   - Recommended durable path for serious local work.
   - Export columns date/open/high/low/close/volume, then import-csv.
   - Works with broker exports, paid vendors, manually downloaded Yahoo/Stooq CSV, etc.

4. Tiingo / Polygon / Nasdaq Data Link / Databento
   - Better production candidates, but API keys and licenses vary.
   - Add a small adapter that returns date/open/high/low/close/volume rows.

5. Yahoo Finance / Stooq
   - Useful for exploration, but direct scripted downloads can be rate-limited or blocked.
   - Prefer manual CSV export plus import-csv when reliability matters.

Data-quality warning:
Daily OHLCV alone is not enough for institutional-grade equity backtests. Splits,
dividends, delistings, survivorship bias, symbol mapping, market hours, and fees
can materially change results. This platform imports simple raw daily bars and
uses minimal factor/map files unless your source data is richer.
"""
    )


def base_config(algorithm_id, parameters):
    return {
        "environment": "backtesting",
        "algorithm-id": algorithm_id,
        "backtest-name": f"Local {parameters['ticker']} EMA Backtest",
        "algorithm-type-name": "DockerDemoAlgorithm",
        "algorithm-language": "Python",
        "algorithm-location": "/Lean/DockerDemoAlgorithm.py",
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
        "parameters": parameters,
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


def run_backtest(args):
    ticker = symbol_key(args.symbol).upper()
    if not daily_zip_path(ticker).exists():
        die(f"missing LEAN daily data for {ticker}: {daily_zip_path(ticker)}")

    start = parse_date(args.start)
    end = parse_date(args.end)
    if end <= start:
        die("--end must be after --start")
    if args.fast <= 0 or args.slow <= 0:
        die("--fast and --slow must be positive")

    run_id = args.run_id or f"{ticker.lower()}-{start:%Y%m%d}-{end:%Y%m%d}-{time.strftime('%Y%m%d%H%M%S')}"
    run_dir = RUNS_DIR / run_id
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    parameters = {
        "ticker": ticker,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "cash": args.cash,
        "fast": args.fast,
        "slow": args.slow,
    }
    config = base_config(run_id, parameters)
    config_path = run_dir / "config.json"
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    docker = shutil.which("docker")
    if not docker:
        die("docker command not found")

    command = [
        docker,
        "run",
        "--rm",
        "--name",
        f"lean-{run_id}"[:60],
        "-v",
        f"{config_path}:/Lean/Launcher/bin/Debug/config.json:ro",
        "-v",
        f"{ALGORITHM_PATH}:/Lean/DockerDemoAlgorithm.py:ro",
        "-v",
        f"{DATA_DIR}:/Lean/Data:ro",
        "-v",
        f"{results_dir}:/Lean/Results",
        args.image,
    ]
    print("running:", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    if completed.returncode != 0:
        die(f"docker backtest failed with exit code {completed.returncode}")

    result_json = results_dir / f"{run_id}.json"
    if not result_json.exists():
        die(f"expected result file not found: {result_json}")

    report = results_dir / "report.html"
    render_report_file(result_json, report)

    print(f"run dir: {run_dir}")
    print(f"results: {result_json}")
    print(f"report:  {report}")
    if args.open:
        subprocess.run(["open", str(report)], check=False)


def generate_report(args):
    input_path = Path(args.input)
    if not input_path.exists():
        die(f"input result JSON does not exist: {input_path}")
    output = Path(args.output) if args.output else input_path.with_name("report.html")
    render_report_file(input_path, output)
    print(output)
    if args.open:
        subprocess.run(["open", str(output)], check=False)


def build_parser():
    parser = argparse.ArgumentParser(description="Local QuantConnect LEAN Docker backtesting platform.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sources = subparsers.add_parser("sources", help="show supported data-source guidance")
    sources.set_defaults(func=show_sources)

    symbols = subparsers.add_parser("symbols", help="list local daily US equity symbols")
    symbols.set_defaults(func=list_symbols)

    alpha = subparsers.add_parser("fetch-alpha-vantage", help="download Alpha Vantage daily data and convert to LEAN format")
    alpha.add_argument("symbol")
    alpha.add_argument("--api-key", default=None)
    alpha.add_argument("--outputsize", choices=["compact", "full"], default="compact")
    alpha.add_argument("--overwrite", action="store_true")
    alpha.set_defaults(func=fetch_alpha_vantage)

    importer = subparsers.add_parser("import-csv", help="import OHLCV CSV into LEAN daily US equity format")
    importer.add_argument("symbol")
    importer.add_argument("csv_file")
    importer.add_argument("--date-col", default="timestamp")
    importer.add_argument("--open-col", default="open")
    importer.add_argument("--high-col", default="high")
    importer.add_argument("--low-col", default="low")
    importer.add_argument("--close-col", default="close")
    importer.add_argument("--volume-col", default="volume")
    importer.add_argument("--encoding", default="utf-8-sig")
    importer.add_argument("--overwrite", action="store_true")
    importer.set_defaults(func=import_csv)

    backtest = subparsers.add_parser("backtest", help="run a parameterized Docker LEAN backtest")
    backtest.add_argument("--symbol", required=True)
    backtest.add_argument("--start", required=True)
    backtest.add_argument("--end", required=True)
    backtest.add_argument("--fast", type=int, default=10)
    backtest.add_argument("--slow", type=int, default=30)
    backtest.add_argument("--cash", type=float, default=100000)
    backtest.add_argument(
        "--image",
        default="quantconnect/lean@sha256:19e3633d2da1e8b378dd6af4b999b0ca6cf0660a1bf557a0518a2e43fc270823",
    )
    backtest.add_argument("--run-id", default=None)
    backtest.add_argument("--open", action="store_true")
    backtest.set_defaults(func=run_backtest)

    report = subparsers.add_parser("report", help="render a LEAN result JSON as HTML")
    report.add_argument("input")
    report.add_argument("--output", default=None)
    report.add_argument("--open", action="store_true")
    report.set_defaults(func=generate_report)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
