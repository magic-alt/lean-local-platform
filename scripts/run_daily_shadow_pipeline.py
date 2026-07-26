#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.config import DATA_DIR, PARQUET_DIR  # noqa: E402
from app.db import db, init_db  # noqa: E402
from app.migrations.runner import verify_migrations  # noqa: E402
from app.services.alerts import emit_alert  # noqa: E402
from app.services.ashare_multisource import compare_ashare_daily_sources_batch  # noqa: E402
from app.services.data_coverage import ashare_coverage, benchmark_coverage  # noqa: E402
from app.services.db_object_store import put_bytes  # noqa: E402
from app.services.lean_cache import ensure_ashare_lean_cache  # noqa: E402
from app.services.parquet_lake import parquet_consistency_report  # noqa: E402
from app.services.pipeline_tracking import finish_pipeline_run, record_pipeline_step, start_pipeline_run  # noqa: E402
from app.services.provider_certification import provider_availability_report, warning_allowlist_status  # noqa: E402
from app.services.source_gate import DATA_SOURCE_PRIORITY, PRIMARY_DATA_SOURCE, resolve_effective_data_source, resolve_source_context, source_priority_for_window  # noqa: E402
from app.services.universe_certification import certified_symbols, get_certified_universe  # noqa: E402


ACCEPTED_LEVEL3_WARNINGS = {"multi_source_qa_warning"}


def _api_token() -> str:
    configured = os.environ.get("LEAN_API_TOKEN", "").strip()
    if configured:
        return configured
    token_path = Path(
        os.environ.get(
            "LEAN_API_TOKEN_FILE",
            str(ROOT / "web" / "runtime" / "secrets" / "api_token"),
        )
    )
    try:
        return token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _csv(value: str) -> list[str]:
    return [item.strip().zfill(6)[-6:] for item in value.split(",") if item.strip()]


def _api(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None, timeout: int = 300) -> tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    token = _api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers=headers,
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
    return {"name": name, "status": status, "details": details or {}, "warnings": [], "errors": [], "duration": None}


def _step_from_details(name: str, status: str, details: dict[str, Any] | None = None, warnings: list[str] | None = None, errors: list[str] | None = None, duration: float | None = None) -> dict[str, Any]:
    return {"name": name, "status": status, "details": details or {}, "warnings": warnings or [], "errors": errors or [], "duration": duration}


def _artifact_write(path: str | None, run_id: str, payload: dict[str, Any]) -> tuple[str | None, str | None]:
    data = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    local_path = None
    if path:
        artifact_dir = Path(path)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        target = artifact_dir / f"{run_id}.json"
        target.write_bytes(data)
        local_path = str(target)
    stored = put_bytes(
        "pipeline-artifacts",
        f"{run_id}/summary.json",
        data,
        content_type="application/json",
        metadata={"runId": run_id, "status": payload.get("status"), "decision": payload.get("level3Decision") or payload.get("level3PlusDecision")},
    )
    return local_path, stored.get("id")


def _certification_window(universe_code: str | None) -> tuple[str | None, str | None]:
    if not universe_code:
        return None, None
    certification = (get_certified_universe(universe_code).get("certification") or {})
    return certification.get("start_date") or certification.get("startDate"), certification.get("end_date") or certification.get("endDate")


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


def _backtest_smoke(
    api_url: str,
    project_id: str,
    symbol: str,
    benchmark: str,
    source: str,
    start: str,
    end: str,
    execution_policy: str,
) -> dict[str, Any]:
    project_status, project = _api(
        api_url,
        "GET",
        f"/api/projects/{urllib.parse.quote(project_id)}",
        timeout=30,
    )
    project_config = (
        project.get("config") or {}
        if project_status == 200 and isinstance(project, dict)
        else {}
    )
    project_defaults = (
        project_config.get("exampleDefaults") or {}
        if isinstance(project_config, dict)
        else {}
    )
    template_key = str(project_config.get("templateKey") or "")
    universe_code = str(
        project_config.get("universeCode")
        or project_defaults.get("universeCode")
        or ""
    ).strip().upper()
    dynamic_universe = bool(
        template_key == "dynamic_universe"
        or project_config.get("dynamicUniverse") is True
        or project_defaults.get("dynamicUniverse") is True
    )
    strategy_parameters = dict(project_config.get("parameters") or {})
    universe_schedule: list[dict[str, Any]] = []
    if dynamic_universe:
        if not universe_code:
            return {
                "status": "critical",
                "error": "dynamic_universe_code_missing",
                "httpStatus": project_status,
            }
        with db() as connection:
            rows = connection.execute(
                """
                select symbol,start_date,end_date,effective_date,weight
                from universe_membership
                where universe_code=? and start_date<=? and (end_date is null or end_date>=?)
                  and (announce_date is null or announce_date<=coalesce(effective_date,start_date))
                order by start_date,symbol
                """,
                (universe_code, end, start),
            ).fetchall()
        universe_schedule = [
            {
                "symbol": str(row["symbol"]).upper(),
                "startDate": max(str(row["effective_date"] or row["start_date"]), start),
                "endDate": min(str(row["end_date"]), end) if row["end_date"] else None,
                "weight": row["weight"],
            }
            for row in rows
            if str(row["effective_date"] or row["start_date"]) <= end
        ]
        if not universe_schedule:
            return {
                "status": "critical",
                "error": f"dynamic_universe_schedule_missing:{universe_code}:{start}:{end}",
                "httpStatus": project_status,
            }
        strategy_parameters.update(
            {
                "universeCode": universe_code,
                "dynamicUniverse": True,
                "universeSchedule": json.dumps(
                    universe_schedule,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "universeSymbols": sorted(
                    {item["symbol"] for item in universe_schedule}
                ),
            }
        )
    payload = {
        "projectId": project_id,
        "symbol": symbol,
        "assetClass": "equity",
        "market": "china",
        "start": start,
        "end": end,
        "cash": 1000000,
        "source": source,
        "benchmarkSymbol": benchmark,
        "executionPolicy": execution_policy,
        "parameters": strategy_parameters,
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
        "smokeMode": "dynamic_universe" if dynamic_universe else "single_symbol",
        "universeCode": universe_code or None,
        "universeScheduleRows": len(universe_schedule),
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
    parser.add_argument("--symbols")
    parser.add_argument("--project-id", help="Existing governed project used for the real LEAN smoke run.")
    parser.add_argument("--universe-code")
    parser.add_argument("--benchmark", default="000300")
    parser.add_argument("--source", default=PRIMARY_DATA_SOURCE)
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--since-last-run", action="store_true")
    parser.add_argument("--save-artifact-dir")
    parser.add_argument("--alert-webhook")
    parser.add_argument("--alert-email")
    parser.add_argument("--alert-file")
    parser.add_argument("--fail-on-expired-warning", action="store_true")
    parser.add_argument("--max-reject-rate", type=float, default=1.0)
    parser.add_argument("--max-drawdown-warning", type=float, default=1.0)
    parser.add_argument("--paper-session-mode", choices=["reuse", "create"], default="create")
    parser.add_argument("--pipeline-run-id")
    parser.add_argument("--execution-policy", default="next_open")
    parser.add_argument("--min-trading-days", type=int, default=10)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.alert_webhook:
        os.environ["LEAN_ALERT_WEBHOOK_URL"] = str(args.alert_webhook)
    if args.alert_email:
        parser.error("--alert-email is not implemented; configure --alert-webhook instead")

    symbols = _csv(args.symbols) if args.symbols else []
    if args.universe_code:
        symbols = certified_symbols(args.universe_code)
    window_start, window_end = _certification_window(args.universe_code)
    start_date = args.start_date or window_start
    end_date = args.end_date or window_end
    source_policy = resolve_effective_data_source(args.source, start_date=start_date, end_date=end_date)
    effective_source = source_policy["effectiveSource"]
    qa_sources = source_priority_for_window(source=args.source, start_date=start_date, end_date=end_date)
    if args.dry_run:
        payload = {"status": "planned", "symbols": symbols, "universeCode": args.universe_code, "benchmark": args.benchmark, "source": effective_source, "requestedSource": args.source, "sourcePolicy": source_policy, "startDate": start_date, "endDate": end_date}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if not args.project_id:
        parser.error("--project-id is required unless --dry-run is used")
    if not symbols:
        payload = {"status": "failed", "severity": "critical", "errors": ["symbols_missing"], "level3Decision": "LEVEL3_FAIL"}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    if not start_date or not end_date:
        payload = {"status": "failed", "severity": "critical", "errors": ["date_window_missing"], "level3Decision": "LEVEL3_FAIL"}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2

    steps: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []
    alerts: list[dict[str, Any]] = []
    init_db()
    run = start_pipeline_run(universe_code=args.universe_code, source=effective_source, benchmark_symbol=args.benchmark, artifact_dir=args.save_artifact_dir, run_id=args.pipeline_run_id)
    run_id = run["id"]
    run_perf = run["perfStart"]

    def add_step(name: str, status: str, details: dict[str, Any] | None = None, *, step_warnings: list[str] | None = None, step_errors: list[str] | None = None, started: float | None = None) -> None:
        duration = (time.perf_counter() - started) if started else None
        item = _step_from_details(name, status, details, step_warnings, step_errors, duration)
        steps.append(item)
        record_pipeline_step(run_id, name, status=status, details=details or {}, warnings=step_warnings or [], errors=step_errors or [], duration_seconds=duration)

    env_steps, env_warnings, env_errors = _environment(args.api_url)
    env_status = "critical" if env_errors else "ok"
    add_step("environment_check", env_status, {"checks": env_steps}, step_warnings=env_warnings, step_errors=env_errors)
    warnings.extend(env_warnings)
    errors.extend(env_errors)
    if env_errors:
        for error in env_errors:
            event_type = "mysql_down" if "mysql" in error else ("api_down" if "api" in error else "worker_down")
            alerts.append(emit_alert(event_type, severity="critical", source="daily_shadow_pipeline", related_id=run_id, details={"error": error}, alert_file=args.alert_file))
        payload = {"status": "failed", "severity": "critical", "pipelineRunId": run_id, "steps": steps, "warnings": warnings, "errors": errors, "alerts": {"count": len(alerts), "items": alerts}, "level3Decision": "LEVEL3_FAIL"}
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        finish_pipeline_run(run_id, status="failed", severity="critical", decision="LEVEL3_FAIL", summary=payload, warnings=warnings, errors=errors, perf_start=run_perf)
        return 3

    started = time.perf_counter()
    try:
        with db() as connection:
            verify_migrations(connection)
        add_step("migration_check", "ok", {"status": "ok"}, started=started)
    except Exception as exc:
        errors.append("migration_mismatch")
        add_step("migration_check", "critical", {"error": str(exc)}, step_errors=["migration_mismatch"], started=started)

    started = time.perf_counter()
    providers = provider_availability_report(
        list(DATA_SOURCE_PRIORITY),
        start_date=start_date,
        end_date=end_date,
        persist=True,
    )
    provider_errors = ["provider_unavailable"] if any(item["provider"] == effective_source and item["status"] == "unavailable" for item in providers["providers"]) else []
    add_step("provider_availability", "critical" if provider_errors else providers["severity"], providers, step_errors=provider_errors, started=started)
    errors.extend(provider_errors)

    if args.universe_code:
        started = time.perf_counter()
        universe = get_certified_universe(args.universe_code)
        certification = universe.get("certification") or {}
        universe_errors = []
        if not certification:
            universe_errors.append("universe_not_certified")
        elif certification.get("certification_status") != "certified" and certification.get("certificationStatus") != "certified":
            universe_errors.append("universe_not_certified")
        if len(symbols) < 1:
            universe_errors.append("universe_empty")
        add_step("universe_certification", "critical" if universe_errors else "ok", {"certification": certification, "symbolCount": len(symbols)}, step_errors=universe_errors, started=started)
        errors.extend(universe_errors)

    try:
        source_context = resolve_source_context({"source": effective_source}, asset_class="equity", market="china", venue="china")
        add_step("source_gate", "ok", {**source_context, "sourcePolicy": source_policy})
    except Exception as exc:
        errors.append(str(exc))
        add_step("source_gate", "critical", {"error": str(exc)}, step_errors=[str(exc)])

    started = time.perf_counter()
    coverage = ashare_coverage(symbols=symbols, benchmark=args.benchmark, source=effective_source, start_date=start_date, end_date=end_date)
    add_step("data_coverage", coverage["severity"], coverage, step_warnings=coverage.get("warnings") or [], step_errors=coverage.get("issues") or [], started=started)
    if coverage["severity"] == "critical":
        errors.extend(coverage.get("issues") or ["coverage_critical"])
    elif coverage["severity"] == "warning":
        warnings.extend(coverage.get("warnings") or ["coverage_warning"])

    started = time.perf_counter()
    bench = benchmark_coverage(args.benchmark, start_date=start_date, end_date=end_date, source=effective_source)
    add_step("benchmark_check", bench["severity"], bench, step_errors=bench.get("issues") or [], started=started)
    if bench["severity"] == "critical":
        errors.append("benchmark_missing")

    started = time.perf_counter()
    qa = compare_ashare_daily_sources_batch(symbols=symbols, sources=qa_sources, start_date=start_date, end_date=end_date, persist=True, persist_symbol_reports=True)
    qa_warnings = ["provider_secondary_missing"] if qa["severity"] == "warning" else []
    acceptance = warning_allowlist_status(qa_warnings, affected_symbols=symbols, scope={"universeCode": args.universe_code, "step": "multisource_qa"})
    qa_errors = []
    if qa["severity"] == "critical":
        qa_errors.append("multi_source_qa_critical")
    if args.fail_on_expired_warning and acceptance["expiredWarnings"]:
        qa_errors.append("warning_expired")
    add_step("multisource_qa", "critical" if qa_errors else qa["severity"], {"reportId": qa.get("reportId"), "warningSymbols": qa.get("warningSymbols"), "criticalSymbols": qa.get("criticalSymbols"), "acceptedWarnings": acceptance["acceptedWarnings"], "expiredWarnings": acceptance["expiredWarnings"]}, step_warnings=qa_warnings, step_errors=qa_errors, started=started)
    if qa["severity"] == "critical":
        errors.append("multi_source_qa_critical")
    elif qa["severity"] == "warning":
        warnings.append("multi_source_qa_warning")
    errors.extend(error for error in qa_errors if error not in errors)

    started = time.perf_counter()
    parquet = parquet_consistency_report(
        asset_class="equity",
        market="china",
        venue="china",
        resolution="daily",
        data_type="trade",
        adjust="raw",
        sources=[effective_source],
        persist=True,
    )
    parquet_status = parquet["severity"]
    add_step(
        "parquet_consistency",
        parquet_status,
        {
            "datasetCount": parquet["datasetCount"],
            "criticalCount": parquet["criticalCount"],
            "warningCount": parquet["warningCount"],
            "reportId": parquet.get("reportId"),
            "issues": parquet.get("issues") or [],
        },
        step_errors=["parquet_consistency_failed"] if parquet_status != "ok" else [],
        started=started,
    )
    if parquet_status != "ok":
        errors.append("parquet_consistency_failed")

    started = time.perf_counter()
    cache_items = {}
    for symbol in [*symbols, args.benchmark]:
        try:
            cache_items[symbol] = ensure_ashare_lean_cache(symbol, source=effective_source)
        except Exception as exc:
            errors.append(f"lean_cache:{symbol}:{exc}")
    cache_errors = [error for error in errors if error.startswith("lean_cache:")]
    add_step("lean_cache_check", "ok" if not cache_errors else "critical", cache_items, step_errors=cache_errors, started=started)

    started = time.perf_counter()
    backtest = _backtest_smoke(
        args.api_url,
        args.project_id,
        symbols[0],
        args.benchmark,
        effective_source,
        start_date,
        end_date,
        args.execution_policy,
    )
    backtest_details = {
        "runId": backtest.get("runId"),
        "httpStatus": backtest.get("httpStatus"),
        "error": backtest.get("error"),
        "final": backtest.get("final"),
        "fingerprintPresent": bool((backtest.get("fingerprint") or {}).get("parametersHash")),
        "smokeMode": backtest.get("smokeMode"),
        "universeCode": backtest.get("universeCode"),
        "universeScheduleRows": backtest.get("universeScheduleRows"),
    }
    add_step("backtest_smoke", backtest["status"], backtest_details, step_errors=["backtest_smoke_failed"] if backtest["status"] != "ok" else [], started=started)
    if backtest["status"] != "ok":
        errors.append("backtest_smoke_failed")

    started = time.perf_counter()
    paper = _paper_replay(args.api_url, symbols, args.benchmark, effective_source, start_date, end_date, args.execution_policy)
    reject_rate = (float(paper.get("rejects") or 0) / max(1.0, float((paper.get("fills") or 0) + (paper.get("rejects") or 0))))
    paper_errors = []
    paper_warnings = []
    if paper["status"] != "ok" or int(paper.get("tradingDays") or 0) < args.min_trading_days:
        paper_errors.append("paper_replay_failed")
    if reject_rate > args.max_reject_rate:
        paper_warnings.append("paper_reject_spike")
    add_step("paper_replay", "critical" if paper_errors else ("warning" if paper_warnings else paper["status"]), {**paper, "rejectRate": reject_rate, "paperSessionMode": args.paper_session_mode}, step_warnings=paper_warnings, step_errors=paper_errors, started=started)
    if paper["status"] != "ok" or int(paper.get("tradingDays") or 0) < args.min_trading_days:
        errors.append("paper_replay_failed")
    warnings.extend(paper_warnings)

    started = time.perf_counter()
    status, report_list = _api(args.api_url, "GET", "/api/reports?paged=true&limit=3&offset=0", timeout=30)
    report_ok = status == 200 and isinstance(report_list, dict) and "items" in report_list
    add_step("report_generation", "ok" if report_ok else "critical", {"status": status, "body": report_list if not report_ok else {"count": report_list.get("count")}}, step_errors=[] if report_ok else ["reports_api_failed"], started=started)
    if not report_ok:
        errors.append("reports_api_failed")

    for error in sorted(set(errors)):
        if "benchmark_missing" in error:
            alerts.append(emit_alert("benchmark_missing", severity="critical", source="daily_shadow_pipeline", related_id=run_id, details={"benchmark": args.benchmark}, alert_file=args.alert_file))
        elif "migration_mismatch" in error:
            alerts.append(emit_alert("migration_mismatch", severity="critical", source="daily_shadow_pipeline", related_id=run_id, details={"steps": steps}, alert_file=args.alert_file))
        elif "coverage_critical" in error or "parquet_consistency_failed" in error:
            alerts.append(emit_alert("qa_critical", severity="critical", title=error, source="daily_shadow_pipeline", related_id=run_id, details={"error": error}, alert_file=args.alert_file))
        elif "qa_critical" in error or "multi_source_qa_critical" in error:
            alerts.append(emit_alert("qa_critical", severity="critical", source="daily_shadow_pipeline", related_id=run_id, details={"qaReportId": qa.get("reportId")}, alert_file=args.alert_file))
        elif "warning_expired" in error:
            alerts.append(emit_alert("warning_expired", severity="critical", source="daily_shadow_pipeline", related_id=run_id, details={"expiredWarnings": acceptance.get("expiredWarnings")}, alert_file=args.alert_file))
        elif "provider_unavailable" in error:
            alerts.append(emit_alert("provider_unavailable", severity="critical", source="daily_shadow_pipeline", related_id=run_id, details=providers, alert_file=args.alert_file))
        elif "lean_cache:" in error:
            alerts.append(emit_alert("cache_restore_failed", severity="critical", source="daily_shadow_pipeline", related_id=run_id, details={"error": error}, alert_file=args.alert_file))
        elif "reports_api_failed" in error:
            alerts.append(emit_alert("report_write_failed", severity="critical", source="daily_shadow_pipeline", related_id=run_id, details={"status": status}, alert_file=args.alert_file))
        elif "backtest_smoke_failed" in error:
            backtest_text = json.dumps(backtest, ensure_ascii=False, default=str)
            alert_type = "qa_critical" if "qa" in backtest_text.lower() or "critical" in backtest_text.lower() else "worker_down"
            alerts.append(emit_alert(alert_type, severity="critical", title="backtest_smoke_failed", message="backtest_smoke_failed", source="daily_shadow_pipeline", related_id=run_id, details=backtest, alert_file=args.alert_file))
        elif "paper_replay_failed" in error:
            alerts.append(emit_alert("worker_down", severity="critical", title="paper_replay_failed", message="paper_replay_failed", source="daily_shadow_pipeline", related_id=run_id, details=paper, alert_file=args.alert_file))
    if "paper_reject_spike" in warnings:
        alerts.append(emit_alert("paper_reject_spike", severity="warning", source="daily_shadow_pipeline", related_id=run_id, details={"rejectRate": reject_rate}, alert_file=args.alert_file))
    add_step("alert_dispatch", "ok" if not alerts else "warning", {"alerts": len(alerts), "alertFile": args.alert_file})

    accepted_warnings = sorted({warning for warning in warnings if warning in ACCEPTED_LEVEL3_WARNINGS})
    accepted_warnings.extend(["provider_secondary_missing"] if acceptance.get("acceptedWarnings") else [])
    blocking_warnings = sorted({warning for warning in warnings if warning not in ACCEPTED_LEVEL3_WARNINGS and warning != "provider_secondary_missing"})
    severity = "critical" if errors else ("warning" if warnings else "ok")
    decision = "LEVEL3_FAIL" if errors else ("LEVEL3_CANDIDATE" if blocking_warnings else "LEVEL3_PASS")
    level3_plus_decision = "LEVEL3_PLUS_FAIL" if errors else ("LEVEL3_PLUS_CANDIDATE" if blocking_warnings else "LEVEL3_PLUS_PASS")
    payload = {
        "status": "passed" if decision == "LEVEL3_PASS" else ("warning" if decision == "LEVEL3_CANDIDATE" else "failed"),
        "severity": severity,
        "pipelineRunId": run_id,
        "universeCode": args.universe_code,
        "tradingDays": paper.get("tradingDays"),
        "symbols": symbols,
        "benchmark": args.benchmark,
        "source": effective_source,
        "requestedSource": args.source,
        "sourcePolicy": source_policy,
        "qaReports": {"batch": qa.get("reportId")},
        "parquetReports": {"consistency": parquet.get("reportId")},
        "backtestRunId": backtest.get("runId"),
        "paperSessionId": paper.get("sessionId"),
        "paperReportCount": paper.get("reports"),
        "fills": paper.get("fills"),
        "rejects": paper.get("rejects"),
        "rejectRate": reject_rate,
        "rejectReasons": paper.get("rejectReasons"),
        "fingerprints": {"backtest": bool((backtest.get("fingerprint") or {}).get("parametersHash"))},
        "warnings": sorted(set(warnings)),
        "acceptedWarnings": accepted_warnings,
        "blockingWarnings": blocking_warnings,
        "errors": errors,
        "alerts": {"count": len(alerts), "items": alerts},
        "level3Decision": decision,
        "level3PlusDecision": level3_plus_decision,
        "steps": steps,
    }
    artifact_path, artifact_object_id = _artifact_write(args.save_artifact_dir, run_id, payload)
    payload["artifacts"] = {"localPath": artifact_path, "objectId": artifact_object_id}
    status_value = "passed" if decision == "LEVEL3_PASS" else ("warning" if decision == "LEVEL3_CANDIDATE" else "failed")
    finish_pipeline_run(run_id, status=status_value, severity=severity, decision=decision, summary=payload, warnings=sorted(set(warnings)), errors=errors, artifact_object_id=artifact_object_id, perf_start=run_perf)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if decision == "LEVEL3_PASS" else (1 if decision == "LEVEL3_CANDIDATE" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
