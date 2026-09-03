#!/usr/bin/env python3
"""Unified operational CLI for local market-data synchronization and validation."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _resolve_data_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _apply_data_dir_override(value: str | None) -> Path | None:
    if not value:
        return None
    root = _resolve_data_dir(value)
    parquet = root / "output" / "parquet"
    for name, path in {
        "LEAN_DATA_DIR": root,
        "LEAN_HOST_DATA_DIR": root,
        "LEAN_MARKET_DATA_DIR": root,
        "LEAN_PARQUET_DIR": parquet,
        "LEAN_HOST_PARQUET_DIR": parquet,
        "LEAN_DATA_SYNC_SPOOL_DIR": root / ".sync-spool",
    }.items():
        os.environ[name] = str(path)
    return root


def _bootstrap_backend(data_dir: str | None) -> Path:
    _apply_data_dir_override(data_dir)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from app.core.config import DATA_DIR

    return DATA_DIR.expanduser().resolve()


def _status_rank(severity: str) -> int:
    return {"ok": 0, "warning": 1, "critical": 2}.get(str(severity).lower(), 2)


def _step(name: str, runner: Callable[[], tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    try:
        severity, details = runner()
        return {"step": name, "severity": severity, "details": details}
    except Exception as exc:
        return {
            "step": name,
            "severity": "critical",
            "details": {"errorType": type(exc).__name__},
        }


def _benchmark_coverage(symbol: str, start_date: str | None, end_date: str | None) -> dict[str, Any]:
    from app.services import market_lake

    predicates = ["symbol = ?"]
    parameters: list[Any] = [symbol]
    if start_date:
        predicates.append("trade_date >= ?")
        parameters.append(start_date)
    if end_date:
        predicates.append("trade_date <= ?")
        parameters.append(end_date)
    row = market_lake.aggregate(
        kind="bars",
        asset_class="equity",
        market="china",
        venue="china",
        source="tushare",
        columns=(
            "count(distinct trade_date) as rows,"
            "min(trade_date) as start_date,max(trade_date) as end_date"
        ),
        predicates=predicates,
        parameters=parameters,
    )
    return {
        "symbol": symbol,
        "rows": int(row["rows"] or 0),
        "startDate": row["start_date"],
        "endDate": row["end_date"],
    }


def command_status(args: argparse.Namespace) -> int:
    data_root = _bootstrap_backend(args.data_dir)
    from app.services import data_sync

    catalog = data_sync.catalog_payload()
    if args.full:
        payload = {"status": "ok", "dataRoot": str(data_root), "catalog": catalog}
    else:
        items = list(catalog.get("items") or [])
        managed = [
            str(item.get("dataset_key"))
            for item in items
            if str(item.get("sync_policy")) != "on_demand"
        ]
        payload = {
            "status": "ok",
            "dataRoot": str(data_root),
            "marketDataAuthority": catalog.get("marketDataAuthority", "parquet"),
            "provider": catalog.get("provider"),
            "managedDatasets": managed,
            "managedDatasetCount": len(managed),
            "hasCompletedInitialSync": bool(catalog.get("hasCompletedInitialSync")),
            "recommendedMode": catalog.get("recommendedMode"),
            "activeRun": catalog.get("activeRun"),
            "latestRun": catalog.get("latestRun"),
            "automaticUpdate": catalog.get("automaticUpdate"),
            "storage": catalog.get("storage"),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def command_update(args: argparse.Namespace) -> int:
    data_root = _bootstrap_backend(args.data_dir)
    from app.db import init_db
    from app.services import data_sync

    datasets = _csv(args.datasets) or None
    init_db()
    run = data_sync.create_sync_run(requested=datasets, mode=args.mode, request_scope={})
    result = data_sync.run_sync(run["id"])
    status = str(result.get("status") or "unknown")
    payload = {
        "status": status,
        "runId": run["id"],
        "mode": args.mode,
        "dataRoot": str(data_root),
        "requestedDatasets": datasets,
        "datasets": result.get("datasets"),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if status == "success" else 2


def command_repair_current(args: argparse.Namespace) -> int:
    data_root = _bootstrap_backend(args.data_dir)
    os.environ["LEAN_TUSHARE_LINEAGE_ASYNC"] = "0"
    from app.services import data_sync
    from scripts.update_tushare_current import complete_special_datasets

    spool = Path(os.environ.get("LEAN_DATA_SYNC_SPOOL_DIR", data_root / ".sync-spool"))
    if not spool.is_absolute():
        spool = (REPO_ROOT / spool).resolve()
    os.environ["LEAN_DATA_SYNC_SPOOL_DIR"] = str(spool)
    spool.mkdir(parents=True, exist_ok=True)
    result = complete_special_datasets(
        data_sync,
        symbol_batch_size=args.symbol_batch_size,
        max_extended_cycles=args.max_extended_cycles,
        max_dividend_retries=args.max_dividend_retries,
    )
    print(json.dumps({**result, "dataRoot": str(data_root)}, ensure_ascii=False, indent=2))
    return 0


def command_validate(args: argparse.Namespace) -> int:
    data_root = _bootstrap_backend(args.data_dir)
    from app.services.parquet_lake import parquet_consistency_report
    from app.services.tushare_adapter import TushareAdapter
    from scripts.reconcile_provider_archives import reconcile
    from scripts.validate_tushare_contracts import validate_live_samples, validate_offline

    steps: list[dict[str, Any]] = []

    def parquet_step() -> tuple[str, dict[str, Any]]:
        report = parquet_consistency_report(
            asset_class="equity",
            market="china",
            venue="china",
            resolution="daily",
            data_type="trade",
            adjust="raw",
            sources=["tushare"],
            include_research_sources=False,
            persist=not args.no_persist,
        )
        return str(report.get("severity") or "critical"), report

    steps.append(_step("parquet_consistency", parquet_step))

    def benchmark_step() -> tuple[str, dict[str, Any]]:
        coverage = _benchmark_coverage(args.benchmark, args.start_date, args.end_date)
        return ("ok" if coverage["rows"] > 0 else "critical"), coverage

    steps.append(_step("benchmark_coverage", benchmark_step))

    if not args.skip_archives:
        def archive_step() -> tuple[str, dict[str, Any]]:
            report = reconcile(apply=False, run_id=args.run_id)
            return ("ok" if report.get("passed") else "critical"), report

        steps.append(_step("provider_archive_reconcile", archive_step))

    if not args.skip_contracts:
        def offline_contract_step() -> tuple[str, dict[str, Any]]:
            report = validate_offline()
            return ("ok" if report.get("valid") else "critical"), report

        steps.append(_step("tushare_contract_offline", offline_contract_step))

    if args.deep:
        from app.services.ashare_multisource import compare_ashare_daily_sources_batch
        from app.services.source_gate import DATA_SOURCE_PRIORITY

        sources = _csv(args.qa_sources) or list(DATA_SOURCE_PRIORITY)
        symbols = _csv(args.symbols)

        def qa_step() -> tuple[str, dict[str, Any]]:
            report = compare_ashare_daily_sources_batch(
                symbols=symbols,
                sources=sources,
                start_date=args.start_date,
                end_date=args.end_date,
                persist=not args.no_persist,
                persist_symbol_reports=not args.no_persist,
            )
            return str(report.get("severity") or "critical"), report

        steps.append(_step("multi_source_qa", qa_step))

    if args.live_provider:
        def live_contract_step() -> tuple[str, dict[str, Any]]:
            report = validate_live_samples(TushareAdapter().pro)
            return ("ok" if report.get("valid") else "critical"), report

        steps.append(_step("tushare_live_sample", live_contract_step))

    worst = max((_status_rank(item["severity"]) for item in steps), default=2)
    warnings = [item["step"] for item in steps if item["severity"] == "warning"]
    critical = [item["step"] for item in steps if item["severity"] == "critical"]
    failed = bool(critical or (args.fail_on_warning and warnings))
    status = "failed" if failed else ("warning" if worst == 1 else "ok")
    payload = {
        "schemaVersion": 1,
        "command": "validate",
        "status": status,
        "dataRoot": str(data_root),
        "scope": {
            "deep": bool(args.deep),
            "liveProvider": bool(args.live_provider),
            "benchmark": args.benchmark,
            "startDate": args.start_date,
            "endDate": args.end_date,
        },
        "steps": steps,
        "warnings": warnings,
        "critical": critical,
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if args.output:
        path = Path(args.output).expanduser()
        if not path.is_absolute():
            path = REPO_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 2 if failed else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Operate the local governed market-data lake. By default the backend uses "
            "LEAN_DATA_DIR from the process/.env and otherwise <repo>/data."
        )
    )
    parser.add_argument(
        "--data-dir",
        help="Override the data root; relative paths are resolved from the repository root.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show local data-lake and sync status.")
    status_parser.add_argument("--full", action="store_true", help="Print the complete catalog payload.")
    status_parser.set_defaults(func=command_status)

    update_parser = subparsers.add_parser("update", help="Run one managed TuShare sync synchronously.")
    update_parser.add_argument(
        "--mode",
        choices=("auto", "initial_full", "incremental", "full_rebuild"),
        default="auto",
    )
    update_parser.add_argument(
        "--datasets",
        help="Optional comma-separated managed datasets. Omit to use the full bulk set.",
    )
    update_parser.set_defaults(func=command_update)

    repair_parser = subparsers.add_parser(
        "repair-current",
        help="Finish bounded extended_daily/dividend recovery runs.",
    )
    repair_parser.add_argument("--symbol-batch-size", type=int, default=1000)
    repair_parser.add_argument("--max-extended-cycles", type=int, default=12)
    repair_parser.add_argument("--max-dividend-retries", type=int, default=3)
    repair_parser.set_defaults(func=command_repair_current)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Fail-closed local data validation; network QA is opt-in.",
    )
    validate_parser.add_argument("--deep", action="store_true", help="Also run multi-source A-share QA.")
    validate_parser.add_argument(
        "--live-provider",
        action="store_true",
        help="Also call four bounded TuShare live contract probes.",
    )
    validate_parser.add_argument("--fail-on-warning", action="store_true")
    validate_parser.add_argument("--symbols", default="600519,000001")
    validate_parser.add_argument("--qa-sources", default="")
    validate_parser.add_argument("--benchmark", default="000300")
    validate_parser.add_argument("--start-date")
    validate_parser.add_argument("--end-date")
    validate_parser.add_argument("--run-id", help="Audit one successful sync run during archive reconciliation.")
    validate_parser.add_argument("--skip-archives", action="store_true")
    validate_parser.add_argument("--skip-contracts", action="store_true")
    validate_parser.add_argument("--no-persist", action="store_true")
    validate_parser.add_argument("--output")
    validate_parser.set_defaults(func=command_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "command": getattr(args, "command", None),
                    "errorType": type(exc).__name__,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
