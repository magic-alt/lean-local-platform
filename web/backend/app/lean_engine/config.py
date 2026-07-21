from __future__ import annotations

from typing import Any

from ..domain.assets import (
    AssetRequest,
    asset_class_key,
    canonical_symbol,
    data_type_key,
    has_lean_data,
    resolution_key,
    venue_key,
)
from .errors import LeanPlatformError
from .symbols import market_key, normalize_symbol, parse_date

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
    *,
    algorithm_class: str,
    algorithm_location: str,
    language: str,
) -> dict[str, Any]:
    python_paths = ["/Lean/Run"] if parameters.get("ashareRules") or parameters.get("hkRules") else []
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
    repairable_equity_market = requested_asset_class == "equity" and market in {"china", "hongkong"}
    if not repairable_equity_market and not has_lean_data(data_request):
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
