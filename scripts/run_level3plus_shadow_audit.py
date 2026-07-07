#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, init_db, rows_to_dicts  # noqa: E402
from app.services.alerts import emit_alert  # noqa: E402
from app.services.ashare_multisource import compare_ashare_daily_sources_batch  # noqa: E402
from app.services.data_coverage import benchmark_coverage  # noqa: E402
from app.services.instrument_identity import identifier_coverage  # noqa: E402
from app.services.parquet_lake import parquet_consistency_report  # noqa: E402
from app.services.provider_certification import provider_availability_report, warning_allowlist_status  # noqa: E402
from app.services.source_gate import resolve_effective_data_source, source_priority_for_window  # noqa: E402
from app.services.universe_certification import certified_symbols, get_certified_universe  # noqa: E402

from scripts.cleanup_report_artifacts import _load_policy, _policy_cleanup  # noqa: E402


def _lookback_window(days: int) -> tuple[str, str]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=max(1, days) * 2)
    return start.isoformat(), end.isoformat()


def _latest_pipeline_artifact(universe_code: str | None) -> dict[str, Any] | None:
    clauses = ["artifact_object_id is not null"]
    params: list[Any] = []
    if universe_code:
        clauses.append("universe_code = ?")
        params.append(universe_code.upper())
    with db() as connection:
        row = connection.execute(
            f"""
            select *
            from pipeline_runs
            where {" and ".join(clauses)}
            order by started_at desc
            limit 1
            """,
            params,
        ).fetchone()
    return dict(row) if row else None


def _trade_reference_summary(symbols: list[str], start_date: str, end_date: str) -> dict[str, Any]:
    if not symbols:
        return {"coverageRatio": 0.0, "missingSymbols": []}
    placeholders = ", ".join("?" for _ in symbols)
    with db() as connection:
        rows = connection.execute(
            f"""
            select symbol, count(*) as rows,
                   sum(case when is_st = 1 then 1 else 0 end) as st_rows,
                   sum(case when is_suspended = 1 then 1 else 0 end) as suspended_rows,
                   sum(case when is_limit_up = 1 or is_limit_down = 1 then 1 else 0 end) as limit_rows
            from ashare_trade_status
            where symbol in ({placeholders}) and trade_date between ? and ?
            group by symbol
            """,
            (*symbols, start_date, end_date),
        ).fetchall()
    items = rows_to_dicts(rows)
    covered = {item["symbol"] for item in items if int(item.get("rows") or 0) > 0}
    return {
        "coverageRatio": len(covered) / len(symbols),
        "missingSymbols": [symbol for symbol in symbols if symbol not in covered],
        "symbols": items,
        "stRows": sum(int(item.get("st_rows") or 0) for item in items),
        "suspendedRows": sum(int(item.get("suspended_rows") or 0) for item in items),
        "limitRows": sum(int(item.get("limit_rows") or 0) for item in items),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Level3+ A-share shadow paper audit.")
    parser.add_argument("--universe-code", required=True)
    parser.add_argument("--benchmark", default="000300")
    parser.add_argument("--source", default="jqdata")
    parser.add_argument("--lookback-trading-days", type=int, default=60)
    parser.add_argument("--min-symbols", type=int, default=20)
    parser.add_argument("--max-symbols", type=int, default=50)
    parser.add_argument("--min-identifier-coverage", type=float, default=0.95)
    parser.add_argument("--fail-on-expired-warning", action="store_true")
    parser.add_argument("--with-frontend", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    init_db()
    universe_code = args.universe_code.upper()
    universe = get_certified_universe(universe_code)
    certification = universe.get("certification") or {}
    symbols = certified_symbols(universe_code)
    start_date = certification.get("start_date") or certification.get("startDate")
    end_date = certification.get("end_date") or certification.get("endDate")
    if not start_date or not end_date:
        start_date, end_date = _lookback_window(args.lookback_trading_days)
    source_policy = resolve_effective_data_source(args.source, start_date=start_date, end_date=end_date)
    effective_source = source_policy["effectiveSource"]
    qa_sources = source_priority_for_window(source=args.source, start_date=start_date, end_date=end_date)
    checks: list[dict[str, Any]] = []
    p0: list[str] = []
    p1: list[str] = []
    p2: list[str] = []

    def check(name: str, requirement: str, ok: bool, evidence: Any, *, severity: str = "P1") -> None:
        checks.append({"check": name, "requirement": requirement, "actual": evidence, "evidence": evidence, "conclusion": "OK" if ok else severity})
        if ok:
            return
        if severity == "P0":
            p0.append(name)
        elif severity == "P1":
            p1.append(name)
        else:
            p2.append(name)

    full_identifier = identifier_coverage()
    universe_identifier = identifier_coverage(symbols)
    provider = provider_availability_report(["jqdata", "akshare", "tushare", "rqdata", "baostock", "adata"], start_date=start_date, end_date=end_date, persist=True)
    qa = compare_ashare_daily_sources_batch(symbols=symbols or ["000000"], sources=qa_sources, start_date=start_date, end_date=end_date, persist=True, persist_symbol_reports=False) if symbols else {"severity": "critical", "criticalSymbols": [], "warningSymbols": [], "reportId": None}
    warning_codes = ["provider_secondary_missing"] if qa.get("severity") == "warning" else []
    warnings = warning_allowlist_status(warning_codes, affected_symbols=symbols, scope={"universeCode": universe_code, "audit": "level3plus"})
    parquet = parquet_consistency_report(asset_class="equity", market="china", venue="china", resolution="daily", data_type="trade", adjust="raw", sources=[effective_source], persist=True)
    benchmark = benchmark_coverage(args.benchmark, start_date=start_date, end_date=end_date, source=effective_source)
    trade_reference = _trade_reference_summary(symbols, start_date, end_date)
    artifact = _latest_pipeline_artifact(universe_code)
    alert_probe = emit_alert("provider_unavailable", severity="info", source="level3plus_audit", related_id=universe_code, details={"probe": True}, dedupe_key=f"level3plus_audit_probe:{universe_code}")
    retention = _policy_cleanup(_load_policy(str(ROOT / "config" / "retention_policy.yaml")), dry_run=True, verify=False, limit=1000)
    frontend = {"enabled": args.with_frontend, "returnCode": None}
    if args.with_frontend:
        proc = subprocess.run(["npm", "run", "build"], cwd=ROOT / "web" / "frontend", capture_output=True, text=True, check=False, timeout=600)
        frontend = {"enabled": True, "returnCode": proc.returncode, "stdoutTail": proc.stdout[-500:], "stderrTail": proc.stderr[-500:]}

    check("certified_universe_size", f"{args.min_symbols}-{args.max_symbols} certified symbols", args.min_symbols <= len(symbols) <= args.max_symbols, {"symbolCount": len(symbols), "symbols": symbols}, severity="P0")
    check("universe_identifier_coverage", "universe identifier coverage = 1.0", universe_identifier["coverageRatio"] == 1.0 and universe_identifier["missing"] == 0, universe_identifier, severity="P0")
    check("full_identifier_coverage", f"full identifier coverage >= {args.min_identifier_coverage}", full_identifier["coverageRatio"] >= args.min_identifier_coverage, full_identifier, severity="P1")
    check("provider_availability", "provider diagnostics available and effective source not unavailable", not any(item["provider"] == effective_source and item["status"] == "unavailable" for item in provider["providers"]), provider, severity="P1")
    check("multi_source_qa", "multi-source QA critical = 0", len(qa.get("criticalSymbols") or []) == 0 and qa.get("severity") != "critical", qa, severity="P0")
    check("accepted_warnings", "accepted warning not expired", not warnings["expiredWarnings"] and (not args.fail_on_expired_warning or warnings["passed"]), warnings, severity="P1")
    check("parquet_consistency", "Parquet consistency severity=ok", parquet.get("severity") == "ok", parquet, severity="P1")
    check("benchmark_coverage", "benchmark coverage ok and no constant fallback", benchmark["severity"] == "ok", benchmark, severity="P0")
    check("trade_reference_coverage", "trade status/ST/suspend/limit coverage queryable", trade_reference["coverageRatio"] == 1.0, trade_reference, severity="P1")
    check("pipeline_artifact", "latest pipeline artifact traceable", bool(artifact), artifact, severity="P1")
    check("alert_events_writable", "alert_events writable", bool(alert_probe.get("id")), alert_probe, severity="P1")
    check("retention_dry_run", "retention dry-run succeeds", retention.get("status") in {"planned", "ok"} and not retention.get("errors"), retention, severity="P1")
    if args.with_frontend:
        check("frontend_build", "frontend build succeeds", frontend["returnCode"] == 0, frontend, severity="P2")

    decision = "LEVEL3_PLUS_FAIL" if p0 else ("LEVEL3_PLUS_CANDIDATE" if p1 else "LEVEL3_PLUS_PASS")
    payload = {
        "decision": decision,
        "status": "passed" if decision == "LEVEL3_PLUS_PASS" else ("candidate" if decision == "LEVEL3_PLUS_CANDIDATE" else "failed"),
        "universeCode": universe_code,
        "source": effective_source,
        "requestedSource": args.source,
        "sourcePolicy": source_policy,
        "benchmark": args.benchmark,
        "startDate": start_date,
        "endDate": end_date,
        "symbols": symbols,
        "checks": checks,
        "risks": {"P0": p0, "P1": p1, "P2": p2},
        "identifierCoverage": {"full": full_identifier, "universe": universe_identifier},
        "providerDiagnostics": provider,
        "qa": qa,
        "tradeReference": trade_reference,
        "pipelineArtifact": artifact,
        "alertProbe": alert_probe,
        "retention": retention,
        "frontend": frontend,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if decision == "LEVEL3_PLUS_PASS" else (1 if decision == "LEVEL3_PLUS_CANDIDATE" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
