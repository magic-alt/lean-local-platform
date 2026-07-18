#!/usr/bin/env python3
"""Run an evidence-backed Data -> Project -> Backtest -> Paper -> Research verification.

The command is intentionally inert unless --execute is supplied. It persists every
case in verification_runs/verification_cases and writes a JSON artifact under the
runtime verification directory so failures remain traceable after the run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
sys.path.insert(0, str(BACKEND))

from app.db import db, json_dump, utc_now  # noqa: E402


A_SHARE_SYMBOLS = ["600519", "600036", "601318", "600900", "601166", "000001", "000333", "000858", "300750", "600460"]
HK_SYMBOLS = ["00700", "00941", "09988", "03690", "00005", "01299", "02318", "01810", "00388", "00883"]
MARKETS = {
    "china": {"symbols": A_SHARE_SYMBOLS, "benchmark": "000300", "cash": 500000, "provider": "tushare"},
    # The current 5000-point TuShare entitlement limits hk_daily to one call
    # per hour. Use the production public fallback for the multi-symbol QA run;
    # TuShare availability and its retryable rate-limit evidence are verified
    # independently by the Data/provider diagnostics.
    "hongkong": {"symbols": HK_SYMBOLS, "benchmark": "02800", "cash": 500000, "provider": "akshare"},
}
TERMINAL = {"success", "failed", "cancelled", "stopped"}


class ApiFailure(RuntimeError):
    def __init__(self, status: int, payload: Any, trace_id: str | None = None, workflow_id: str | None = None):
        super().__init__(f"HTTP {status}: {payload}")
        self.status = status
        self.payload = payload
        self.trace_id = trace_id
        self.workflow_id = workflow_id


def api(base_url: str, method: str, path: str, payload: dict[str, Any] | None, *, workflow_id: str) -> tuple[Any, dict[str, str]]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Workflow-ID": workflow_id},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            body = response.read().decode("utf-8")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return (json.loads(body) if body else {}), headers
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body)
        except json.JSONDecodeError:
            detail = body
        raise ApiFailure(exc.code, detail, exc.headers.get("X-Trace-ID"), exc.headers.get("X-Workflow-ID")) from exc


def git_commit() -> str | None:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=False, capture_output=True, text=True)
    return result.stdout.strip() or None


def create_run(run_id: str, name: str, manifest: dict[str, Any]) -> None:
    with db() as connection:
        connection.execute(
            """
            insert into verification_runs
                (id, name, status, git_commit, environment_json, manifest_json, created_at, started_at)
            values (?, ?, 'running', ?, ?, ?, ?, ?)
            """,
            (run_id, name, git_commit(), json_dump({"python": sys.version, "baseUrl": manifest["baseUrl"]}), json_dump(manifest), utc_now(), utc_now()),
        )


def record_case(
    run_id: str,
    case_key: str,
    market: str,
    symbol: str,
    stage: str,
    status: str,
    *,
    details: Any,
    trace_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    error_code: str | None = None,
) -> None:
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into verification_cases
                (id, verification_run_id, case_key, market, symbol, stage, status, trace_id,
                 resource_type, resource_id, error_code, details_json, started_at, finished_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(verification_run_id, case_key) do update set
                status=excluded.status, trace_id=excluded.trace_id, resource_type=excluded.resource_type,
                resource_id=excluded.resource_id, error_code=excluded.error_code,
                details_json=excluded.details_json, finished_at=excluded.finished_at
            """,
            (
                str(uuid.uuid4()), run_id, case_key, market, symbol, stage, status, trace_id,
                resource_type, resource_id, error_code, json_dump(details), now, now,
            ),
        )


def finish_run(run_id: str, status: str, summary: dict[str, Any], artifact_path: Path) -> None:
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    with db() as connection:
        connection.execute(
            "update verification_runs set status=?, summary_json=?, artifact_path=?, finished_at=? where id=?",
            (status, json_dump(summary), str(artifact_path), utc_now(), run_id),
        )


def poll_backtest(base_url: str, run_id: str, workflow_id: str, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        item, _ = api(base_url, "GET", f"/api/backtests/{run_id}", None, workflow_id=workflow_id)
        if str(item.get("status")) in TERMINAL:
            return item
        time.sleep(2)
    raise TimeoutError(f"Backtest {run_id} did not finish within {timeout}s")


def execute(args: argparse.Namespace) -> int:
    run_id = str(uuid.uuid4())
    qa_tag = f"qa:{run_id}"
    manifest = {
        "baseUrl": args.base_url,
        "qaRunId": run_id,
        "start": args.start,
        "end": args.end,
        "markets": MARKETS,
        "providers": {market: spec["provider"] for market, spec in MARKETS.items()},
    }
    create_run(run_id, "20-stock web full-flow verification", manifest)
    results: dict[str, Any] = {"runId": run_id, "qaRunId": qa_tag, "manifest": manifest, "projects": {}, "symbols": {}}
    failures = 0
    projects: dict[str, dict[str, Any]] = {}
    try:
        for market in MARKETS:
            workflow = f"{run_id}:project:{market}"
            project, headers = api(
                args.base_url,
                "POST",
                "/api/projects",
                {
                    "name": f"QA {run_id[:8]} {market}",
                    "language": "Python",
                    "templateKey": "macd",
                    "assetClass": "equity",
                    "market": market,
                    "venue": market,
                    "resolution": "daily",
                    "dataType": "trade",
                    "parameters": {"qaRunId": run_id},
                },
                workflow_id=workflow,
            )
            projects[market] = project
            results["projects"][market] = project.get("id")
            record_case(run_id, f"project:{market}", market, "", "project", "success", details=project, trace_id=headers.get("x-trace-id"), resource_type="project", resource_id=project.get("id"))

        for market, spec in MARKETS.items():
            for symbol in [spec["benchmark"], *spec["symbols"]]:
                case_prefix = f"{market}:{symbol}"
                workflow = f"{run_id}:{case_prefix}"
                symbol_result: dict[str, Any] = results["symbols"].setdefault(case_prefix, {})
                try:
                    if market == "china" and symbol == spec["benchmark"]:
                        fetched, headers = api(
                            args.base_url,
                            "POST",
                            "/api/backtests/preflight",
                            {
                                "symbol": spec["symbols"][0],
                                "assetClass": "equity",
                                "market": market,
                                "venue": market,
                                "resolution": "daily",
                                "dataType": "trade",
                                "start": args.start,
                                "end": args.end,
                                "cash": spec["cash"],
                                "projectId": projects[market]["id"],
                                "parameters": {"benchmarkSymbol": symbol, "source": "tushare", "qaRunId": run_id},
                            },
                            workflow_id=workflow,
                        )
                    else:
                        fetched, headers = api(
                            args.base_url,
                            "POST",
                            "/api/data/fetch",
                            {
                                "symbol": symbol,
                                "assetClass": "equity",
                                "market": market,
                                "venue": market,
                                "resolution": "daily",
                                "dataType": "trade",
                                "provider": spec["provider"],
                                "outputsize": "full",
                                "startDate": args.start,
                                "endDate": args.end,
                                "adjust": "raw",
                                # Verification is repeatable even when a prior
                                # run already populated the managed LEAN cache.
                                "overwrite": True,
                            },
                            workflow_id=workflow,
                        )
                    symbol_result["data"] = fetched
                    record_case(run_id, f"{case_prefix}:data", market, symbol, "data", "success", details=fetched, trace_id=headers.get("x-trace-id"), resource_type="data_asset", resource_id=fetched.get("id") or fetched.get("batch_id"))
                except Exception as exc:
                    failures += 1
                    details = exc.payload if isinstance(exc, ApiFailure) else {"message": str(exc)}
                    record_case(run_id, f"{case_prefix}:data", market, symbol, "data", "failed", details=details, trace_id=getattr(exc, "trace_id", None), error_code="data_fetch_failed")
                    continue
                if symbol == spec["benchmark"]:
                    continue
                try:
                    current_stage = "backtest"
                    request_payload = {
                        "symbol": symbol,
                        "name": f"QA {run_id[:8]} {market} {symbol}",
                        "assetClass": "equity",
                        "market": market,
                        "venue": market,
                        "resolution": "daily",
                        "dataType": "trade",
                        "start": args.start,
                        "end": args.end,
                        "cash": spec["cash"],
                        "projectId": projects[market]["id"],
                        "parameters": {"benchmarkSymbol": spec["benchmark"], "source": spec["provider"], "qaRunId": run_id},
                    }
                    run, headers = api(args.base_url, "POST", "/api/backtests", request_payload, workflow_id=workflow)
                    run = poll_backtest(args.base_url, str(run["id"]), workflow, args.wait_timeout)
                    passed = run.get("status") == "success" and (run.get("validation") or {}).get("passed") is True
                    status = "success" if passed else "failed"
                    if not passed:
                        failures += 1
                    symbol_result["backtest"] = run.get("id")
                    record_case(run_id, f"{case_prefix}:backtest", market, symbol, "backtest", status, details=run, trace_id=headers.get("x-trace-id"), resource_type="backtest", resource_id=run.get("id"), error_code=None if passed else "backtest_validation_failed")
                    if not passed:
                        continue
                    current_stage = "paper"
                    paper, headers = api(
                        args.base_url,
                        "POST",
                        "/api/paper",
                        {
                            "mode": "lean_walkforward",
                            "name": f"QA {run_id[:8]} {market} {symbol}",
                            "projectId": projects[market]["id"],
                            "sourceBacktestId": run["id"],
                            "symbol": symbol,
                            "autoAdvance": False,
                            "parameters": {"qaRunId": run_id},
                        },
                        workflow_id=workflow,
                    )
                    symbol_result["paper"] = paper.get("id")
                    record_case(run_id, f"{case_prefix}:paper", market, symbol, "paper", "success", details=paper, trace_id=headers.get("x-trace-id"), resource_type="paper_session", resource_id=paper.get("id"))
                except Exception as exc:
                    failures += 1
                    details = exc.payload if isinstance(exc, ApiFailure) else {"message": str(exc)}
                    stage = locals().get("current_stage", "backtest")
                    record_case(
                        run_id,
                        f"{case_prefix}:{stage}",
                        market,
                        symbol,
                        stage,
                        "failed",
                        details=details,
                        trace_id=getattr(exc, "trace_id", None),
                        error_code=f"{stage}_failed",
                    )

        if args.include_research:
            for market, project in projects.items():
                workflow = f"{run_id}:research:{market}"
                try:
                    session, headers = api(args.base_url, "POST", "/api/research", {"projectId": project["id"]}, workflow_id=workflow)
                    check, _ = api(args.base_url, "POST", f"/api/research/{session['id']}/checks", {}, workflow_id=workflow)
                    api(args.base_url, "POST", f"/api/research/{session['id']}/stop", {}, workflow_id=workflow)
                    passed = bool(check.get("passed"))
                    failures += 0 if passed else 1
                    record_case(run_id, f"research:{market}", market, "", "research", "success" if passed else "failed", details=check, trace_id=headers.get("x-trace-id"), resource_type="research_session", resource_id=session.get("id"), error_code=None if passed else "research_check_failed")
                except Exception as exc:
                    failures += 1
                    record_case(run_id, f"research:{market}", market, "", "research", "failed", details={"message": str(exc)}, trace_id=getattr(exc, "trace_id", None), error_code="research_start_failed")
    except Exception as exc:
        failures += 1
        results["fatalError"] = str(exc)
    results["failures"] = failures
    results["status"] = "success" if failures == 0 else "failed"
    artifact = ROOT / "web" / "runtime" / "verification" / f"{run_id}.json"
    finish_run(run_id, results["status"], results, artifact)
    print(json.dumps({"runId": run_id, "status": results["status"], "failures": failures, "artifact": str(artifact)}, ensure_ascii=False))
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end", default="2026-07-13")
    parser.add_argument("--wait-timeout", type=int, default=600)
    parser.add_argument("--include-research", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Perform writes and launch the full verification.")
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"execute": False, "markets": MARKETS, "message": "Pass --execute to run the full verification."}, ensure_ascii=False, indent=2))
        return 0
    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
