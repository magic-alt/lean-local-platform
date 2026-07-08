from __future__ import annotations

from typing import Any

from ..db import utc_now
from .ashare_multisource import quality_gate_range
from .ashare_repository import data_coverage, latest_batch_for_symbol


P1_RULE_VERSION = 1


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _is_china_equity(parameters: dict[str, Any]) -> bool:
    asset_class = str(parameters.get("assetClass") or "equity").lower()
    market = str(parameters.get("market") or parameters.get("venue") or "").lower()
    venue = str(parameters.get("venue") or parameters.get("market") or "").lower()
    return asset_class == "equity" and (market == "china" or venue == "china")


def _gate(name: str, passed: bool, *, severity: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "passed": bool(passed),
        "severity": severity or ("ok" if passed else "critical"),
        "details": details or {},
    }


def _ashare_market_rules(parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": P1_RULE_VERSION,
        "enabled": True,
        "market": "china",
        "assetClass": "equity",
        "tPlusOne": True,
        "suspendedBlocked": True,
        "limitUpBuyBlocked": True,
        "limitDownSellBlocked": True,
        "benchmarkRequired": True,
        "feeModel": {
            "commissionRate": parameters.get("commissionRate"),
            "minCommission": parameters.get("minCommission"),
            "stampTaxSell": parameters.get("stampTaxSell"),
            "transferFeeRate": parameters.get("transferFeeRate"),
            "currency": "CNY",
        },
        "slippageModel": {
            "type": "constant_bps",
            "slippageBps": parameters.get("slippageBps"),
        },
        "lotSize": parameters.get("lotSize"),
        "executionPolicy": parameters.get("executionPolicy"),
        "cashBuffer": parameters.get("cashBuffer"),
        "minCash": parameters.get("minCash"),
        "allowStBuy": parameters.get("allowStBuy"),
        "constraintVersion": parameters.get("constraintVersion"),
    }


def _benchmark_snapshot(parameters: dict[str, Any], fingerprint: dict[str, Any] | None) -> dict[str, Any]:
    benchmark_symbol = str(parameters.get("benchmarkSymbol") or "").upper()
    benchmark = ((fingerprint or {}).get("data") or {}).get("benchmark") or {}
    return {
        "symbol": benchmark_symbol,
        "rows": _int_value(benchmark.get("row_count")),
        "firstDate": benchmark.get("first_date"),
        "lastDate": benchmark.get("last_date"),
        "required": True,
        "passed": bool(benchmark_symbol) and _int_value(benchmark.get("row_count")) > 0,
    }


def build_backtest_validation(
    parameters: dict[str, Any],
    fingerprint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    symbol = str(parameters.get("ticker") or parameters.get("symbol") or "").upper()
    start = str(parameters.get("start") or "")
    end = str(parameters.get("end") or "")
    adjust = str(parameters.get("adjust") or "raw")
    requested_source = parameters.get("source") or parameters.get("providerSource")
    source = str(requested_source) if requested_source else None
    result: dict[str, Any] = {
        "schemaVersion": P1_RULE_VERSION,
        "generatedAt": utc_now(),
        "scope": {
            "symbol": symbol,
            "assetClass": parameters.get("assetClass") or "equity",
            "market": parameters.get("market") or parameters.get("venue"),
            "venue": parameters.get("venue") or parameters.get("market"),
            "resolution": parameters.get("resolution") or "daily",
            "dataType": parameters.get("dataType") or "trade",
            "start": start,
            "end": end,
            "adjust": adjust,
            "source": source or "database",
        },
        "marketRules": {
            "schemaVersion": P1_RULE_VERSION,
            "enabled": False,
            "reason": "market_rule_validation_not_required_for_this_scope",
        },
        "data": {},
        "gates": [],
        "passed": True,
        "severity": "ok",
    }
    if not _is_china_equity(parameters):
        return result

    coverage = data_coverage(symbol, start, end, adjust, source=source)
    batch = latest_batch_for_symbol(symbol, source=source) or {}
    qa_report = batch.get("qa_report") or {}
    benchmark = _benchmark_snapshot(parameters, fingerprint)
    symbols_to_gate = [symbol]
    if benchmark.get("symbol") and benchmark["symbol"] != symbol:
        symbols_to_gate.append(benchmark["symbol"])
    quality_gates = [quality_gate_range(item, start, end) for item in symbols_to_gate if item]
    from .data_coverage import ashare_coverage

    coverage_summary = ashare_coverage(
        symbols=[symbol],
        benchmark=benchmark.get("symbol") or str(parameters.get("benchmarkSymbol") or "000300"),
        start_date=start,
        end_date=end,
        source=source,
    )
    bar_count = max(_int_value(coverage.get("bar_count")), _int_value(coverage.get("market_bar_count")))
    status_count = _int_value(coverage.get("status_count"))
    coverage_passed = bar_count > 0 and status_count >= bar_count
    batch_passed = batch.get("status") == "success" and bool(qa_report.get("passed"))
    gates = [
        _gate("ashare_data_coverage", coverage_passed, details=coverage),
        _gate("ashare_trade_status", status_count >= bar_count > 0, details=coverage),
        _gate(
            "ashare_import_batch_qa",
            batch_passed,
            severity="ok" if batch_passed else "critical",
            details={
                "batchId": batch.get("id"),
                "status": batch.get("status"),
                "qaReport": qa_report,
            },
        ),
        _gate("benchmark_data", bool(benchmark.get("passed")), details=benchmark),
        *[
            _gate(
                "ashare_multisource_quality",
                bool(item.get("passed")),
                severity=str(item.get("severity") or ("ok" if item.get("passed") else "critical")),
                details=item,
            )
            for item in quality_gates
        ],
    ]
    passed = all(item["passed"] for item in gates)
    result.update(
        {
            "marketRules": _ashare_market_rules(parameters),
            "data": {
                "coverage": coverage,
                "latestImportBatch": {
                    "id": batch.get("id"),
                    "status": batch.get("status"),
                    "source": batch.get("source"),
                    "startedAt": batch.get("started_at"),
                    "finishedAt": batch.get("finished_at"),
                    "qaReport": qa_report,
                },
                "benchmark": benchmark,
                "qualityGates": quality_gates,
                "coverageSummary": coverage_summary,
            },
            "gates": gates,
            "passed": passed,
            "severity": "ok" if passed else "critical",
        }
    )
    return result


def build_experiment_record(
    *,
    run_id: str,
    parameters: dict[str, Any],
    fingerprint: dict[str, Any],
    project_id: str | None = None,
    strategy_path: str | None = None,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = fingerprint.get("data") or {}
    market_daily = data.get("marketDailyBars") or {}
    trade_status = data.get("tradeStatus") or {}
    benchmark = data.get("benchmark") or {}
    return {
        "schemaVersion": P1_RULE_VERSION,
        "runId": run_id,
        "createdAt": fingerprint.get("createdAt") or utc_now(),
        "strategy": {
            "projectId": project_id,
            "path": strategy_path,
            "sha256": fingerprint.get("strategy_file_sha256"),
            "gitCommit": fingerprint.get("git_commit"),
            "gitBranch": fingerprint.get("git_branch"),
            "gitDirty": fingerprint.get("git_dirty"),
            "gitStatusHash": fingerprint.get("git_status_hash"),
        },
        "parameters": {
            "sha256": fingerprint.get("parameters_sha256"),
            "start": parameters.get("start"),
            "end": parameters.get("end"),
            "initialCash": parameters.get("initialCash") or parameters.get("cash"),
            "benchmarkSymbol": parameters.get("benchmarkSymbol"),
            "ashareRules": parameters.get("ashareRules"),
        },
        "data": {
            "scope": data.get("scope") or {},
            "batchId": fingerprint.get("data_batch_id"),
            "marketDailyBars": market_daily,
            "tradeStatus": trade_status,
            "benchmark": benchmark,
            "leanZipSha256": fingerprint.get("lean_zip_sha256"),
            "factorFileSha256": fingerprint.get("factor_file_sha256"),
            "parquetDatasetId": fingerprint.get("parquet_dataset_id"),
            "parquetFileSha256": fingerprint.get("parquet_file_sha256"),
        },
        "environment": {
            "dockerImage": fingerprint.get("docker_image"),
            "dockerImageDigest": fingerprint.get("docker_image_digest"),
            "pythonVersion": fingerprint.get("python_version"),
            "requirementsHash": fingerprint.get("requirements_hash"),
            "timezone": fingerprint.get("timezone"),
        },
        "validation": {
            "passed": (validation or {}).get("passed"),
            "severity": (validation or {}).get("severity"),
            "schemaVersion": (validation or {}).get("schemaVersion"),
        },
    }
