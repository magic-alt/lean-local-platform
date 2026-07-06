#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, init_db  # noqa: E402
from app.services.ashare_multisource import compare_ashare_daily_sources_batch  # noqa: E402
from app.services.parquet_lake import rebuild_all_market_parquet  # noqa: E402
from app.services.paper import run_replay  # noqa: E402


def _csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _step(name: str, status: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"step": name, "status": status, "details": details or {}}


def _reference_import(args: argparse.Namespace) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "import_ashare_reference_public.py"),
        "--symbols",
        args.symbols,
        "--as-of-date",
        args.date,
    ]
    if args.start_date:
        command.extend(["--start-date", args.start_date])
    if args.end_date:
        command.extend(["--end-date", args.end_date])
    completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True, timeout=args.step_timeout)
    payload: dict[str, Any] = {}
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        payload = {"stdout": completed.stdout[-2000:]}
    payload["returnCode"] = completed.returncode
    if completed.stderr:
        payload["stderr"] = completed.stderr[-2000:]
    return payload


def _benchmark_coverage(symbol: str, start_date: str | None, end_date: str | None) -> dict[str, Any]:
    predicates = ["symbol = ?", "asset_class = 'equity'", "market = 'china'", "venue = 'china'", "resolution = 'daily'", "data_type = 'trade'"]
    params: list[Any] = [symbol]
    if start_date:
        predicates.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        predicates.append("trade_date <= ?")
        params.append(end_date)
    with db() as connection:
        row = connection.execute(
            f"""
            select count(distinct trade_date) as rows, min(trade_date) as start_date, max(trade_date) as end_date
            from market_daily_bars
            where {" and ".join(predicates)}
            """,
            params,
        ).fetchone()
    return {"symbol": symbol, "rows": int(row["rows"] or 0), "startDate": row["start_date"], "endDate": row["end_date"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the A-share daily Paper pipeline: reference data, QA, Parquet, benchmark check, Paper Replay, report summary.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--symbols", default="600519,000001")
    parser.add_argument("--qa-sources", default="akshare,adata,baostock")
    parser.add_argument("--benchmark", default="000300")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--paper-session-id")
    parser.add_argument("--paper-start-date")
    parser.add_argument("--paper-end-date")
    parser.add_argument("--skip-reference", action="store_true")
    parser.add_argument("--skip-qa", action="store_true")
    parser.add_argument("--skip-parquet", action="store_true")
    parser.add_argument("--skip-paper", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-on-warning", action="store_true")
    parser.add_argument("--step-timeout", type=int, default=600)
    args = parser.parse_args()

    if args.dry_run:
        steps: list[dict[str, Any]] = []
        for name in ("reference", "multi_source_qa", "parquet", "benchmark_coverage", "paper_replay", "report_summary"):
            steps.append(_step(name, "planned"))
        print(json.dumps({"date": args.date, "dryRun": True, "steps": steps}, ensure_ascii=False, indent=2))
        return 0

    init_db()
    steps = []
    errors: list[str] = []
    warnings: list[str] = []

    if args.skip_reference:
        steps.append(_step("reference", "skipped"))
    else:
        result = _reference_import(args)
        severity = result.get("severity") or ("warning" if result.get("warnings") else "ok")
        steps.append(_step("reference", "warning" if severity == "warning" else "ok", result))
        warnings.extend(result.get("warnings") or [])
        if result.get("returnCode") not in (0, None) and not result.get("warnings"):
            errors.append("reference_import_failed")

    if args.skip_qa:
        steps.append(_step("multi_source_qa", "skipped"))
    else:
        result = compare_ashare_daily_sources_batch(
            symbols=_csv(args.symbols),
            sources=_csv(args.qa_sources),
            start_date=args.start_date,
            end_date=args.end_date,
            persist=True,
            persist_symbol_reports=True,
        )
        steps.append(_step("multi_source_qa", result["severity"], result))
        if result["severity"] == "critical":
            errors.append("multi_source_qa_critical")
        elif result["severity"] == "warning":
            warnings.append("multi_source_qa_warning")

    if args.skip_parquet:
        steps.append(_step("parquet", "skipped"))
    else:
        result = rebuild_all_market_parquet(
            asset_class="equity",
            market="china",
            venue="china",
            resolution="daily",
            data_type="trade",
            adjust="raw",
            start_date=args.start_date,
            end_date=args.end_date,
            continue_on_error=True,
            persist_report=True,
        )
        severity = result["consistencyReport"]["severity"]
        steps.append(_step("parquet", severity, {"rebuiltCount": result["rebuiltCount"], "errorCount": result["errorCount"], "consistencyReport": result["consistencyReport"]}))
        if severity == "critical" or result["errorCount"]:
            errors.append("parquet_rebuild_failed")
        elif severity == "warning":
            warnings.append("parquet_consistency_warning")

    benchmark = _benchmark_coverage(args.benchmark, args.start_date, args.end_date)
    benchmark_status = "ok" if benchmark["rows"] > 0 else "critical"
    steps.append(_step("benchmark_coverage", benchmark_status, benchmark))
    if benchmark_status == "critical":
        errors.append("benchmark_coverage_missing")

    if args.skip_paper or not args.paper_session_id:
        steps.append(_step("paper_replay", "skipped", {"reason": "paper_session_id_missing" if not args.paper_session_id else "skip_paper"}))
    else:
        result = run_replay(
            args.paper_session_id,
            args.paper_start_date or args.start_date or args.date,
            args.paper_end_date or args.end_date or args.date,
            auto_signal=True,
        )
        reports = result.get("reports") or []
        steps.append(_step("paper_replay", "ok" if reports else "warning", {"tradingDays": result["tradingDays"], "reports": len(reports)}))
        if not reports:
            warnings.append("paper_reports_missing")

    status = "failed" if errors or (args.fail_on_warning and warnings) else ("warning" if warnings else "ok")
    steps.append(_step("report_summary", status, {"warnings": sorted(set(warnings)), "errors": errors}))
    summary = {
        "date": args.date,
        "status": status,
        "steps": steps,
        "warnings": sorted(set(warnings)),
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
