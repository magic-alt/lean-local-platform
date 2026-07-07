#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import DATA_DIR, PARQUET_DIR  # noqa: E402
from app.db import db, init_db  # noqa: E402
from app.services.ashare_multisource import compare_ashare_daily_sources_batch  # noqa: E402
from app.services.data_coverage import ashare_coverage  # noqa: E402
from app.services.lean_cache import ensure_ashare_lean_cache  # noqa: E402
from app.services.parquet_lake import parquet_consistency_report, rebuild_all_market_parquet  # noqa: E402
from app.services.source_gate import resolve_source_context  # noqa: E402


ACCEPTED_LEVEL3_WARNINGS = {"multi_source_qa_warning"}


def _csv(value: str) -> list[str]:
    return [item.strip().zfill(6)[-6:] for item in value.split(",") if item.strip()]


def _api(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 300) -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json.loads(raw.decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"detail": raw}
        return exc.code, body


def _step(name: str, status: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "details": details or {}}


def _environment(api_url: str) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    steps: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    try:
        init_db()
        with db() as connection:
            row = connection.execute("select 1 as ok").fetchone()
        steps.append(_step("mysql", "ok", {"ok": bool(row)}))
    except Exception as exc:
        errors.append(f"mysql_unavailable:{exc}")
        steps.append(_step("mysql", "critical", {"error": str(exc)}))
    for path_name, path in (("lean_data", DATA_DIR), ("parquet", PARQUET_DIR)):
        exists = Path(path).exists()
        steps.append(_step(path_name, "ok" if exists else "critical", {"path": str(path), "exists": exists}))
        if not exists:
            errors.append(f"{path_name}_missing")
    docker = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], cwd=ROOT, capture_output=True, text=True, check=False, timeout=10)
    steps.append(_step("docker", "ok" if docker.returncode == 0 else "critical", {"stdout": docker.stdout.strip(), "stderr": docker.stderr.strip()}))
    if docker.returncode != 0:
        errors.append("docker_unavailable")
    for path in ("/api/health", "/api/health/database"):
        status, body = _api(api_url, "GET", path, timeout=10)
        ok = status == 200 and (body.get("ok", True) is not False)
        steps.append(_step(path, "ok" if ok else "critical", {"status": status, "body": body}))
        if not ok:
            errors.append(f"api_unavailable:{path}")
    return steps, warnings, errors


def _backtest_smoke(api_url: str, symbol: str, benchmark: str, source: str, start: str, end: str, execution_policy: str) -> dict[str, Any]:
    payload = {
        "symbol": symbol,
        "assetClass": "equity",
        "market": "china",
        "start": start,
        "end": end,
        "cash": 1000000,
        "source": source,
        "benchmarkSymbol": benchmark,
        "executionPolicy": execution_policy,
    }
    status, body = _api(api_url, "POST", "/api/backtests", payload, timeout=60)
    if status >= 400:
        return {"status": "critical", "error": body, "httpStatus": status}
    run_id = body["id"]
    final = body
    for _ in range(90):
        status, final = _api(api_url, "GET", f"/api/backtests/{run_id}", timeout=30)
        if final.get("status") in {"success", "failed", "cancelled"}:
            break
        time.sleep(2)
    if final.get("status") != "success":
        return {"status": "critical", "runId": run_id, "final": final}
    status, result = _api(api_url, "GET", f"/api/backtests/{run_id}/result", timeout=30)
    fingerprint = (result.get("job") or {}).get("fingerprint") or {}
    return {
        "status": "ok" if status == 200 and fingerprint else "critical",
        "runId": run_id,
        "httpStatus": status,
        "fingerprint": fingerprint,
        "result": result.get("result") if status == 200 else result,
    }


def _paper_replay(api_url: str, symbols: list[str], benchmark: str, source: str, start: str, end: str, execution_policy: str) -> dict[str, Any]:
    status, session = _api(
        api_url,
        "POST",
        "/api/paper",
        {
            "name": "Daily Shadow Pipeline Paper Replay",
            "symbol": symbols[0],
            "symbols": symbols,
            "assetClass": "equity",
            "market": "china",
            "cash": 5000000,
            "benchmarkSymbol": benchmark,
            "executionPolicy": execution_policy,
            "source": source,
            "maxPositions": max(1, len(symbols)),
            "maxPositionWeight": min(0.4, 1 / max(1, len(symbols))),
            "signalTargetPercent": min(0.4, 1 / max(1, len(symbols))),
            "watchlist": ",".join(symbols),
            "fast": 3,
            "slow": 5,
        },
        timeout=30,
    )
    if status >= 400:
        return {"status": "critical", "error": session, "httpStatus": status}
    session_id = session["id"]
    status, result = _api(api_url, "POST", f"/api/paper/{session_id}/replay", {"startDate": start, "endDate": end, "autoSignal": True}, timeout=600)
    if status >= 400:
        return {"status": "critical", "sessionId": session_id, "error": result, "httpStatus": status}
    _, orders = _api(api_url, "GET", f"/api/paper/{session_id}/orders", timeout=30)
    _, reports = _api(api_url, "GET", f"/api/paper/{session_id}/reports?light=true&limit=1000", timeout=30)
    report_items = reports.get("items") if isinstance(reports, dict) else reports
    rejects = [order for order in orders if order.get("status") == "rejected"]
    return {
        "status": "ok" if report_items else "critical",
        "sessionId": session_id,
        "tradingDays": result.get("tradingDays"),
        "reports": len(report_items or []),
        "fills": sum(1 for order in orders if order.get("status") == "filled"),
        "rejects": len(rejects),
        "rejectReasons": sorted({order.get("reason") for order in rejects if order.get("reason")}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Level 3 A-share daily shadow pipeline.")
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--benchmark", default="000300")
    parser.add_argument("--source", default="akshare")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--execution-policy", default="next_open")
    parser.add_argument("--min-trading-days", type=int, default=10)
    parser.add_argument("--api-url", default="http://127.0.0.1:8003")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = _csv(args.symbols)
    if args.dry_run:
        payload = {"status": "planned", "symbols": symbols, "benchmark": args.benchmark, "source": args.source}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    steps: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    env_steps, env_warnings, env_errors = _environment(args.api_url)
    steps.extend(env_steps)
    warnings.extend(env_warnings)
    errors.extend(env_errors)
    if env_errors:
        payload = {"status": "failed", "severity": "critical", "steps": steps, "warnings": warnings, "errors": errors, "level3Decision": "LEVEL3_FAIL"}
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 3

    try:
        source_context = resolve_source_context({"source": args.source}, asset_class="equity", market="china", venue="china")
        steps.append(_step("source_gate", "ok", source_context))
    except Exception as exc:
        errors.append(str(exc))
        steps.append(_step("source_gate", "critical", {"error": str(exc)}))

    coverage = ashare_coverage(symbols=symbols, benchmark=args.benchmark, source=args.source, start_date=args.start_date, end_date=args.end_date)
    steps.append(_step("coverage", coverage["severity"], coverage))
    if coverage["severity"] == "critical":
        errors.extend(coverage.get("issues") or ["coverage_critical"])
    elif coverage["severity"] == "warning":
        warnings.extend(coverage.get("warnings") or ["coverage_warning"])

    qa = compare_ashare_daily_sources_batch(symbols=symbols, sources=["akshare", "adata", "baostock"], start_date=args.start_date, end_date=args.end_date, persist=True, persist_symbol_reports=True)
    steps.append(_step("multi_source_qa", qa["severity"], {"reportId": qa.get("reportId"), "warningSymbols": qa.get("warningSymbols"), "criticalSymbols": qa.get("criticalSymbols")}))
    if qa["severity"] == "critical":
        errors.append("multi_source_qa_critical")
    elif qa["severity"] == "warning":
        warnings.append("multi_source_qa_warning")

    parquet = rebuild_all_market_parquet(asset_class="equity", market="china", venue="china", resolution="daily", data_type="trade", adjust="raw", sources=[args.source], continue_on_error=True, persist_report=True)
    parquet_status = parquet["consistencyReport"]["severity"]
    steps.append(_step("parquet", parquet_status, {"rebuiltCount": parquet["rebuiltCount"], "errorCount": parquet["errorCount"], "reportId": parquet["consistencyReport"].get("reportId")}))
    if parquet_status != "ok" or parquet["errorCount"]:
        errors.append("parquet_consistency_failed")

    cache_items = {}
    for symbol in [*symbols, args.benchmark]:
        try:
            cache_items[symbol] = ensure_ashare_lean_cache(symbol, source=args.source)
        except Exception as exc:
            errors.append(f"lean_cache:{symbol}:{exc}")
    steps.append(_step("lean_cache", "ok" if not any(error.startswith("lean_cache:") for error in errors) else "critical", cache_items))

    backtest = _backtest_smoke(args.api_url, symbols[0], args.benchmark, args.source, args.start_date, args.end_date, args.execution_policy)
    steps.append(_step("backtest_smoke", backtest["status"], {"runId": backtest.get("runId"), "httpStatus": backtest.get("httpStatus")}))
    if backtest["status"] != "ok":
        errors.append("backtest_smoke_failed")

    paper = _paper_replay(args.api_url, symbols, args.benchmark, args.source, args.start_date, args.end_date, args.execution_policy)
    steps.append(_step("paper_replay", paper["status"], paper))
    if paper["status"] != "ok" or int(paper.get("tradingDays") or 0) < args.min_trading_days:
        errors.append("paper_replay_failed")

    status, report_list = _api(args.api_url, "GET", "/api/reports?paged=true&limit=3&offset=0", timeout=30)
    report_ok = status == 200 and isinstance(report_list, dict) and "items" in report_list
    steps.append(_step("reports_api", "ok" if report_ok else "critical", {"status": status, "body": report_list if not report_ok else {"count": report_list.get("count")}}))
    if not report_ok:
        errors.append("reports_api_failed")

    accepted_warnings = sorted({warning for warning in warnings if warning in ACCEPTED_LEVEL3_WARNINGS})
    blocking_warnings = sorted({warning for warning in warnings if warning not in ACCEPTED_LEVEL3_WARNINGS})
    severity = "critical" if errors else ("warning" if warnings else "ok")
    decision = "LEVEL3_FAIL" if errors else ("LEVEL3_CANDIDATE" if blocking_warnings else "LEVEL3_PASS")
    payload = {
        "status": "passed" if decision == "LEVEL3_PASS" else ("warning" if decision == "LEVEL3_CANDIDATE" else "failed"),
        "severity": severity,
        "tradingDays": paper.get("tradingDays"),
        "symbols": symbols,
        "benchmark": args.benchmark,
        "source": args.source,
        "qaReports": {"batch": qa.get("reportId")},
        "parquetReports": {"consistency": parquet["consistencyReport"].get("reportId")},
        "backtestRunId": backtest.get("runId"),
        "paperSessionId": paper.get("sessionId"),
        "paperReportCount": paper.get("reports"),
        "fills": paper.get("fills"),
        "rejects": paper.get("rejects"),
        "rejectReasons": paper.get("rejectReasons"),
        "fingerprints": {"backtest": bool((backtest.get("fingerprint") or {}).get("parametersHash"))},
        "warnings": sorted(set(warnings)),
        "acceptedWarnings": accepted_warnings,
        "blockingWarnings": blocking_warnings,
        "errors": errors,
        "level3Decision": decision,
        "steps": steps,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if decision == "LEVEL3_PASS" else (1 if decision == "LEVEL3_CANDIDATE" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
