#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import os
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote


KNOWN_PHASES = {
    "before_queue",
    "before_wait",
    "during_wait",
    "after_wait",
    "after_run",
    "post_run",
    "default",
}
KNOWN_SERVICES = {"worker", "redis", "mysql", "api"}


def _api_token() -> str:
    configured = os.environ.get("LEAN_API_TOKEN", "").strip()
    if configured:
        return configured
    token_path = os.environ.get(
        "LEAN_API_TOKEN_FILE",
        str(Path(__file__).resolve().parents[1] / "web" / "runtime" / "secrets" / "api_token"),
    )
    try:
        return Path(token_path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _api(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 60,
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    token = _api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        return exc.code, payload


def _normalize_and_validate_faults(value: str) -> list[dict[str, Any]]:
    if not value.strip():
        return []

    scenarios: list[dict[str, Any]] = []
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_-]+)@(\d+)(?::([A-Za-z0-9_-]+))?", raw)
        if not match:
            raise ValueError(f"invalid_fault_scenario:{raw}")
        service = match.group(1).lower()
        if service not in KNOWN_SERVICES:
            raise ValueError(f"unsupported_fault_service:{service}")
        day = int(match.group(2))
        phase = (match.group(3) or "before_queue").lower()
        if phase not in KNOWN_PHASES:
            raise ValueError(f"unsupported_fault_phase:{phase}:{raw}")
        if day <= 0:
            raise ValueError(f"fault_day_must_be_positive:{day}:{raw}")
        scenarios.append({
            "service": service,
            "day": day,
            "phase": phase,
        })
    return scenarios


def _safe_candidate_id(candidate: dict[str, Any]) -> str:
    candidate_id = candidate.get("id")
    if isinstance(candidate_id, str):
        trimmed = candidate_id.strip()
        if trimmed:
            return trimmed
    return ""


def _resolve_source_backtest_id(*, base_url: str, project_id: str, timeout: int) -> str:
    status, payload = _api(
        base_url,
        "GET",
        f"/api/paper/candidates?projectId={quote(project_id)}",
        timeout=timeout,
    )
    if status >= 400:
        raise RuntimeError(f"paper_candidates_unavailable:{status}:{payload}")
    if not isinstance(payload, list):
        raise RuntimeError(f"paper_candidates_invalid_payload:{payload}")
    if not payload:
        raise RuntimeError(f"paper_candidate_empty:{project_id}")

    for item in payload:
        if not isinstance(item, dict):
            continue
        candidate_id = _safe_candidate_id(item)
        if candidate_id:
            return candidate_id
    raise RuntimeError(f"paper_candidate_missing_id:{payload}")


def _to_end_date(start_date: str, min_days: int, extra_days: int = 7) -> str:
    try:
        start = date.fromisoformat(start_date[:10])
    except ValueError:
        return start_date
    days = max(int(min_days), 7) + max(int(extra_days), 0)
    return (start + timedelta(days=days)).isoformat()


def _run_command(argv: list[str], *, timeout: int) -> tuple[int, Any, str]:
    process = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    combined = (process.stdout or "").strip()
    if process.returncode != 0:
        return process.returncode, None, combined or (process.stderr or "")

    parsed = None
    if combined:
        try:
            parsed = json.loads(combined.splitlines()[-1])
        except json.JSONDecodeError:
            parsed = None
    return process.returncode, parsed, combined


def _scenario_to_args(scenario: dict[str, Any]) -> list[str]:
    token = f"{scenario['service']}@{scenario['day']}:{scenario['phase']}"
    return ["--fault-scenario", token]


def _run_walkforward_case(
    *,
    api_url: str,
    project_id: str,
    source_backtest_id: str,
    start_date: str,
    days: int,
    evidence_path: Path,
    scenarios: list[dict[str, Any]],
    execute_timeout: int,
    require_fill: bool,
    require_reject: bool,
    require_reject_reason: bool,
    min_fill: int,
    min_reject: int,
    docker_project: str,
    api_timeout: int,
    timeout_per_day: int,
    paper_mode: str,
) -> dict[str, Any]:
    cmd: list[str] = [
        sys.executable,
        str(Path(__file__).resolve().parent / "run_lean_paper_walkforward_acceptance.py"),
        "--project-id",
        project_id,
        "--start-date",
        start_date,
        "--days",
        str(days),
        "--evidence-out",
        str(evidence_path),
        "--api-url",
        api_url,
        "--require-fill",
        str(require_fill).lower(),
        "--require-reject",
        str(require_reject).lower(),
        "--require-reject-reason",
        str(require_reject_reason).lower(),
        "--min-fill",
        str(min_fill),
        "--min-reject",
        str(min_reject),
        "--docker-project",
        docker_project,
        "--timeout-per-day",
        str(timeout_per_day),
        "--paper-mode",
        paper_mode,
        "--api-timeout",
        str(api_timeout),
    ]
    if source_backtest_id:
        cmd.extend(["--source-backtest-id", source_backtest_id])

    for scenario in scenarios:
        cmd.extend(_scenario_to_args(scenario))

    rc, parsed, raw = _run_command(cmd, timeout=execute_timeout)
    if not isinstance(parsed, dict) and evidence_path.is_file():
        try:
            parsed = json.loads(evidence_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            parsed = None
    if rc != 0:
        raise RuntimeError(raw or "walk-forward acceptance failed")
    if not isinstance(parsed, dict):
        raise RuntimeError("walk-forward script output is not json")
    return parsed


def _require_int_arg(name: str, value: int, minimum: int) -> int:
    if value < minimum:
        raise ValueError(f"--{name} requires >= {minimum}: {value}")
    return value


def _case_status(case_result: dict[str, Any]) -> str:
    if case_result.get("status") == "passed":
        return "passed"
    if case_result.get("walkforwardPassed"):
        return "partial"
    return "failed"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Level 5 replay acceptance bundle")
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--source-backtest-id",
        default="",
        help="Trusted source backtest id; omit to auto-discover candidate backtest for project.",
    )
    parser.add_argument("--start-date", default="2026-06-01")
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--evidence-dir", default="web/runtime/audit")
    parser.add_argument("--compose-project", default="lean-platform")
    parser.add_argument(
        "--paper-mode",
        choices=("lean_walkforward_v2",),
        default="lean_walkforward_v2",
        help="Level 5 certification is restricted to the unified v2 Paper pipeline.",
    )

    parser.add_argument(
        "--with-fault",
        action="store_true",
        help="Run configured fault matrix in addition to no-fault case.",
    )
    parser.add_argument(
        "--fault-scenarios",
        default="",
        help=(
            "Comma-separated scenarios like worker@7:before_queue,redis@14:before_wait,mysql@20:after_wait "
            "(default phase before_queue)."
        ),
    )
    parser.add_argument(
        "--timeout-per-day",
        type=int,
        default=900,
        help="Per-day timeout when running LEAN walk-forward day.",
    )
    parser.add_argument(
        "--constraints",
        action="store_true",
        help="Run paper constraint acceptance in addition to walk-forward cases.",
    )
    parser.add_argument(
        "--constraints-symbols",
        default="600519,000001,300750",
        help="Comma-separated symbols for constraint acceptance.",
    )
    parser.add_argument(
        "--constraints-benchmark",
        default="000300",
        help="Benchmark for constraint acceptance runs.",
    )
    parser.add_argument(
        "--constraints-source",
        default="tushare",
        help="Source for constraint acceptance runs.",
    )
    parser.add_argument(
        "--min-fill",
        type=int,
        default=1,
        help="Minimum fills required by walk-forward evidence.",
    )
    parser.add_argument(
        "--min-reject",
        type=int,
        default=1,
        help="Minimum policy rejects required by walk-forward evidence.",
    )
    parser.add_argument(
        "--require-reject-reason",
        action="store_true",
        default=False,
        help="Require at least one rejected order with reason text.",
    )
    parser.add_argument(
        "--require-fill",
        action="store_true",
        default=True,
        help="Require at least min-fill filled orders in successful run.",
    )
    parser.add_argument(
        "--require-reject",
        action="store_true",
        default=True,
        help="Require at least min-reject rejected orders in successful run.",
    )
    parser.add_argument(
        "--max-failure",
        action="store_true",
        help="Continue running cases even when one fails.",
    )
    parser.add_argument(
        "--api-timeout",
        type=int,
        default=90,
        help="Timeout for control/API calls (seconds).",
    )
    args = parser.parse_args()

    args.days = _require_int_arg("days", args.days, 1)
    args.timeout_per_day = _require_int_arg("timeout-per-day", args.timeout_per_day, 60)
    args.min_fill = _require_int_arg("min-fill", args.min_fill, 0)
    args.min_reject = _require_int_arg("min-reject", args.min_reject, 0)
    args.api_timeout = _require_int_arg("api-timeout", args.api_timeout, 1)

    if args.with_fault and not args.fault_scenarios.strip():
        args.fault_scenarios = "worker@7:before_queue,redis@14:before_wait,mysql@20:after_wait"

    fault_cases = _normalize_and_validate_faults(args.fault_scenarios)

    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)

    base_timeout = max(600, args.days * max(120, args.timeout_per_day))

    resolved_source_backtest_id = args.source_backtest_id.strip()
    if not resolved_source_backtest_id:
        resolved_source_backtest_id = _resolve_source_backtest_id(
            base_url=args.api_url,
            project_id=args.project_id,
            timeout=args.api_timeout,
        )

    summary: dict[str, Any] = {
        "projectId": args.project_id,
        "sourceBacktestId": resolved_source_backtest_id,
        "startDate": args.start_date,
        "days": args.days,
        "apiUrl": args.api_url,
        "composeProject": args.compose_project,
        "paperMode": args.paper_mode,
        "cases": {},
        "walkforwardMatrix": [],
    }

    no_fault_out = evidence_dir / "level5-replay-no-fault.json"
    no_fault_result = _run_walkforward_case(
        api_url=args.api_url,
        project_id=args.project_id,
        source_backtest_id=resolved_source_backtest_id,
        docker_project=args.compose_project,
        start_date=args.start_date,
        days=args.days,
        evidence_path=no_fault_out,
        scenarios=[],
        execute_timeout=base_timeout,
        require_fill=args.require_fill,
        require_reject=args.require_reject,
        require_reject_reason=args.require_reject_reason,
        min_fill=args.min_fill,
        min_reject=args.min_reject,
        timeout_per_day=args.timeout_per_day,
        api_timeout=args.api_timeout,
        paper_mode=args.paper_mode,
    )
    summary["cases"]["walkforward_no_fault"] = no_fault_result
    summary["cases"]["walkforward_no_fault"]["matrixTag"] = "no_fault"

    no_fault_passed = bool(
        _case_status(no_fault_result) == "passed"
        and no_fault_result.get("level5ReplayRequirementsPassed") is True
    )
    summary["walkforward_no_fault_passed"] = no_fault_passed

    if args.with_fault and fault_cases:
        for scenario in fault_cases:
            tag = f"{scenario['service']}-{scenario['day']}-{scenario['phase']}"
            print(f"[LEVEL5] running fault scenario: {tag}", flush=True)
            fault_out = evidence_dir / f"level5-replay-{tag}.json"
            case = {
                "scenario": scenario,
                "matrixTag": tag,
            }
            try:
                case["result"] = _run_walkforward_case(
                    api_url=args.api_url,
                    project_id=args.project_id,
                    source_backtest_id=resolved_source_backtest_id,
                    docker_project=args.compose_project,
                    start_date=args.start_date,
                    days=args.days,
                    evidence_path=fault_out,
                    scenarios=[scenario],
                    execute_timeout=base_timeout,
                    require_fill=args.require_fill,
                    require_reject=args.require_reject,
                    require_reject_reason=args.require_reject_reason,
                    min_fill=args.min_fill,
                    min_reject=args.min_reject,
                    timeout_per_day=args.timeout_per_day,
                    api_timeout=args.api_timeout,
                    paper_mode=args.paper_mode,
                )
                case["passed"] = bool(
                    _case_status(case["result"]) == "passed"
                    and case["result"].get("level5ReplayRequirementsPassed") is True
                )
                case["failedReason"] = case["result"].get("failedReason") if not case["passed"] else None
            except Exception as exc:
                case["passed"] = False
                case["failedReason"] = str(exc)
                case["result"] = {"status": "failed"}
                summary["walkforwardMatrix"].append(case)
                if not args.max_failure:
                    summary["walkforward_fault_matrix_passed"] = False
                    summary["walkforward_with_fault_passed"] = False
                    summary["passed"] = False
                    summary["status"] = "failed"
                    evidence = evidence_dir / "level5-audit.json"
                    evidence.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                    print(
                        json.dumps(
                            {"status": summary["status"], "passed": summary["passed"], "evidence": str(evidence)},
                            ensure_ascii=False,
                        )
                    )
                    return 2
            summary["walkforwardMatrix"].append(case)

    with_fault_passed = True
    if args.with_fault and fault_cases:
        with_fault_passed = all(item.get("passed") for item in summary["walkforwardMatrix"])

    constraints_passed = True
    constraints_result: dict[str, Any] = {}
    if args.constraints:
        constraints_end_date = _to_end_date(args.start_date, args.days)
        constraint_cmd = [
            sys.executable,
            str(Path(__file__).resolve().parent / "run_paper_constraints_acceptance.py"),
            "--symbols",
            args.constraints_symbols,
            "--benchmark",
            args.constraints_benchmark,
            "--source",
            args.constraints_source,
            "--start-date",
            args.start_date,
            "--end-date",
            constraints_end_date,
        ]
        rc, parsed, raw = _run_command(constraint_cmd, timeout=1200)
        constraints_result = parsed if isinstance(parsed, dict) else {"raw": raw}
        constraints_passed = bool(
            rc == 0
            and isinstance(constraints_result, dict)
            and int(constraints_result.get("filled") if "filled" in constraints_result else constraints_result.get("fills") or 0)
            >= args.min_fill
            and int(constraints_result.get("rejected") if "rejected" in constraints_result else constraints_result.get("rejects") or 0)
            >= args.min_reject
            and (not args.require_reject_reason or bool((constraints_result.get("rejectReasons") or [])))
        )

    summary["cases"]["constraints"] = constraints_result
    summary["walkforward_fault_matrix_passed"] = with_fault_passed if args.with_fault and fault_cases else True
    summary["walkforward_with_fault_passed"] = with_fault_passed if args.with_fault and fault_cases else no_fault_passed
    summary["constraints_passed"] = constraints_passed
    summary["passed"] = bool(no_fault_passed and with_fault_passed and constraints_passed)
    summary["status"] = "passed" if summary["passed"] else "failed"

    evidence = evidence_dir / "level5-audit.json"
    evidence.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": summary["status"], "passed": summary["passed"], "evidence": str(evidence)}, ensure_ascii=False))
    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
