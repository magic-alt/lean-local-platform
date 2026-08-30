#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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
    "intent_capture",
    "constraint_validation",
    "matching",
    "ledger",
    "snapshot_report",
    "reconciliation",
}
KNOWN_SERVICES = {"worker", "rabbitmq", "postgres", "api"}


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
        f"/api/paper/accounts/candidates?projectId={quote(project_id)}",
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
    stdout = (process.stdout or "").strip()
    stderr = (process.stderr or "").strip()
    combined = "\n".join(part for part in (stdout, stderr) if part)
    if process.returncode != 0:
        return process.returncode, None, combined

    parsed = None
    if stdout:
        try:
            parsed = json.loads(stdout.splitlines()[-1])
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
    session_overrides_json: str,
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
        "--session-overrides-json",
        session_overrides_json,
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


def _daily_job_coverage_passed(
    coverage: Any,
    trade_dates: list[str],
) -> bool:
    if not isinstance(coverage, dict):
        return False
    total_days = len(trade_dates)
    return bool(
        coverage.get("passed") is True
        and int(coverage.get("completedDays") or 0) >= total_days
        and int(coverage.get("totalDays") or 0) == total_days
    )


def _same_replay_evidence(left: dict[str, Any], right: dict[str, Any]) -> bool:
    keys = (
        "projectId",
        "sourceBacktestId",
        "paperMode",
        "sessionId",
        "canonicalStateSha256",
    )
    return bool(
        all(left.get(key) == right.get(key) for key in keys)
        and list(left.get("tradeDates") or []) == list(right.get("tradeDates") or [])
    )


def _requirements_cover(
    result: dict[str, Any],
    *,
    require_fill: bool,
    require_reject: bool,
    require_reject_reason: bool,
    min_fill: int,
    min_reject: int,
) -> bool:
    evidence = result.get("evidence") or {}
    return bool(
        (not require_fill or evidence.get("requireFill") is True)
        and (not require_reject or evidence.get("requireReject") is True)
        and (
            not require_reject_reason
            or evidence.get("requireRejectReason") is True
        )
        and int(evidence.get("minFill") or 0) >= min_fill
        and int(evidence.get("minReject") or 0) >= min_reject
    )


def _revalidate_reused_daily_job_coverage(
    *,
    no_fault_result: dict[str, Any],
    reuse_path: Path,
    api_url: str,
    api_timeout: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    trade_dates = [str(item) for item in no_fault_result.get("tradeDates") or []]
    embedded = no_fault_result.get("dailyJobCoverage")
    if _daily_job_coverage_passed(embedded, trade_dates):
        return dict(embedded), {
            "source": "reused_no_fault_evidence",
            "path": str(reuse_path),
            "sha256": hashlib.sha256(reuse_path.read_bytes()).hexdigest(),
        }

    companion_path = reuse_path.with_name("level5-audit.json")
    if companion_path.is_file():
        try:
            companion = json.loads(companion_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            companion = {}
        companion_case = (
            (companion.get("cases") or {}).get("walkforward_no_fault") or {}
            if isinstance(companion, dict)
            else {}
        )
        companion_coverage = companion_case.get("dailyJobCoverage")
        if (
            companion.get("passed") is True
            and companion.get("status") == "passed"
            and _same_replay_evidence(no_fault_result, companion_case)
            and _daily_job_coverage_passed(companion_coverage, trade_dates)
        ):
            return dict(companion_coverage), {
                "source": "companion_level5_audit",
                "path": str(companion_path),
                "sha256": hashlib.sha256(companion_path.read_bytes()).hexdigest(),
            }

    session_id = str(no_fault_result.get("sessionId") or "")
    status, detail = _api(
        api_url,
        "GET",
        f"/api/paper/{session_id}",
        timeout=api_timeout,
    )
    completed_job_dates = (
        {
            str(item.get("trade_date") or item.get("tradeDate") or "")
            for item in (detail.get("dailyJobs") or [])
            if isinstance(item, dict) and item.get("state") == "COMPLETED"
        }
        if status < 400 and isinstance(detail, dict)
        else set()
    )
    coverage = {
        "completedDays": len(set(trade_dates) & completed_job_dates),
        "totalDays": len(trade_dates),
        "passed": set(trade_dates) <= completed_job_dates,
    }
    if not _daily_job_coverage_passed(coverage, trade_dates):
        raise RuntimeError(
            "no_fault_daily_job_coverage_unverifiable:"
            f"session_http_status={status}:"
            "provide evidence with dailyJobCoverage or its passed companion level5-audit.json"
        )
    return coverage, {
        "source": "live_session",
        "sessionId": session_id,
        "httpStatus": status,
    }


def _apply_certification_mode(summary: dict[str, Any]) -> None:
    """Prevent reused evidence from being represented as fresh certification."""
    if summary.get("certificationMode") == "evidence_revalidation":
        summary["status"] = "revalidated_from_prior_evidence"
        summary["passed"] = False


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
            "Comma-separated scenarios like worker@7:before_queue,rabbitmq@14:before_wait,postgres@20:after_wait "
            "(default phase before_queue)."
        ),
    )
    parser.add_argument(
        "--fault-mode",
        choices=("combined", "isolated"),
        default="combined",
        help=(
            "combined injects every scenario into one 21-day chain and compares it "
            "with the clean baseline; isolated runs one full chain per scenario."
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
    parser.add_argument(
        "--session-overrides-json",
        default="{}",
        help=(
            "Paper session constraints applied to clean and fault runs, for example "
            "{\"blacklist\":[\"600519\"]}."
        ),
    )
    parser.add_argument(
        "--reuse-no-fault-evidence",
        default="",
        help=(
            "Reuse a previously passed clean-chain JSON after validating project, "
            "source, dates, mode, and session overrides. This lets fault-only "
            "workers enable checkpoint pauses without slowing the clean baseline."
        ),
    )
    parser.add_argument(
        "--reuse-combined-fault-evidence",
        default="",
        help=(
            "Reuse a previously passed combined six-phase fault-chain JSON after "
            "validating scope, coverage, fault actions, and canonical equivalence. "
            "Use with --with-fault --fault-mode combined."
        ),
    )
    args = parser.parse_args()

    args.days = _require_int_arg("days", args.days, 1)
    args.timeout_per_day = _require_int_arg("timeout-per-day", args.timeout_per_day, 60)
    args.min_fill = _require_int_arg("min-fill", args.min_fill, 0)
    args.min_reject = _require_int_arg("min-reject", args.min_reject, 0)
    args.api_timeout = _require_int_arg("api-timeout", args.api_timeout, 1)
    if args.reuse_combined_fault_evidence and not (
        args.with_fault and args.fault_mode == "combined"
    ):
        parser.error(
            "--reuse-combined-fault-evidence requires --with-fault --fault-mode combined"
        )

    if args.with_fault and not args.fault_scenarios.strip():
        args.fault_scenarios = (
            "worker@3:intent_capture,"
            "rabbitmq@6:constraint_validation,"
            "postgres@9:matching,"
            "worker@12:ledger,"
            "rabbitmq@15:snapshot_report,"
            "postgres@18:reconciliation"
        )

    try:
        session_overrides = json.loads(args.session_overrides_json)
    except json.JSONDecodeError as exc:
        parser.error(f"--session-overrides-json must be valid JSON: {exc}")
    if not isinstance(session_overrides, dict):
        parser.error("--session-overrides-json must be a JSON object")
    normalized_session_overrides = json.dumps(
        session_overrides,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

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
        "sessionOverrides": session_overrides,
        "faultMode": args.fault_mode,
        "certificationMode": (
            "evidence_revalidation"
            if args.reuse_no_fault_evidence or args.reuse_combined_fault_evidence
            else "fresh_execution"
        ),
    }

    no_fault_out = evidence_dir / "level5-replay-no-fault.json"
    if args.reuse_no_fault_evidence:
        reuse_path = Path(args.reuse_no_fault_evidence).expanduser().resolve()
        try:
            no_fault_result = json.loads(reuse_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"no_fault_evidence_unavailable:{reuse_path}:{exc}") from exc
        expected = {
            "projectId": args.project_id,
            "sourceBacktestId": resolved_source_backtest_id,
            "paperMode": args.paper_mode,
            "tradeDatesCount": args.days,
            "sessionOverrides": session_overrides,
        }
        actual = {
            "projectId": no_fault_result.get("projectId"),
            "sourceBacktestId": no_fault_result.get("sourceBacktestId"),
            "paperMode": no_fault_result.get("paperMode"),
            "tradeDatesCount": len(no_fault_result.get("tradeDates") or []),
            "sessionOverrides": no_fault_result.get("sessionOverrides") or {},
        }
        if expected != actual or list(no_fault_result.get("tradeDates") or [])[:1] != [
            args.start_date
        ]:
            raise RuntimeError(
                f"no_fault_evidence_scope_mismatch:expected={expected}:actual={actual}"
            )
        if (
            no_fault_result.get("status") != "passed"
            or no_fault_result.get("level5ReplayRequirementsPassed") is not True
            or not _requirements_cover(
                no_fault_result,
                require_fill=args.require_fill,
                require_reject=args.require_reject,
                require_reject_reason=args.require_reject_reason,
                min_fill=args.min_fill,
                min_reject=args.min_reject,
            )
        ):
            raise RuntimeError("no_fault_evidence_not_passed")
        coverage, coverage_revalidation = _revalidate_reused_daily_job_coverage(
            no_fault_result=no_fault_result,
            reuse_path=reuse_path,
            api_url=args.api_url,
            api_timeout=args.api_timeout,
        )
        no_fault_result["dailyJobCoverage"] = coverage
        no_fault_result["dailyJobCoverageRevalidation"] = coverage_revalidation
        summary["reusedNoFaultEvidence"] = str(reuse_path)
    else:
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
            session_overrides_json=normalized_session_overrides,
        )
    summary["cases"]["walkforward_no_fault"] = no_fault_result
    summary["cases"]["walkforward_no_fault"]["matrixTag"] = "no_fault"

    no_fault_passed = bool(
        _case_status(no_fault_result) == "passed"
        and no_fault_result.get("level5ReplayRequirementsPassed") is True
    )
    summary["walkforward_no_fault_passed"] = no_fault_passed

    if args.with_fault and fault_cases and args.fault_mode == "combined":
        tag = "combined-six-phase"
        action = "revalidating" if args.reuse_combined_fault_evidence else "running"
        print(f"[LEVEL5] {action} combined fault scenario: {tag}", flush=True)
        fault_out = evidence_dir / f"level5-replay-{tag}.json"
        case: dict[str, Any] = {
            "scenarios": fault_cases,
            "matrixTag": tag,
        }
        try:
            if args.reuse_combined_fault_evidence:
                reuse_fault_path = (
                    Path(args.reuse_combined_fault_evidence).expanduser().resolve()
                )
                try:
                    case["result"] = json.loads(
                        reuse_fault_path.read_text(encoding="utf-8")
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    raise RuntimeError(
                        f"combined_fault_evidence_unavailable:{reuse_fault_path}:{exc}"
                    ) from exc
                expected_fault_scope = {
                    "projectId": args.project_id,
                    "sourceBacktestId": resolved_source_backtest_id,
                    "paperMode": args.paper_mode,
                    "tradeDatesCount": args.days,
                    "sessionOverrides": session_overrides,
                }
                actual_fault_scope = {
                    "projectId": case["result"].get("projectId"),
                    "sourceBacktestId": case["result"].get("sourceBacktestId"),
                    "paperMode": case["result"].get("paperMode"),
                    "tradeDatesCount": len(case["result"].get("tradeDates") or []),
                    "sessionOverrides": case["result"].get("sessionOverrides") or {},
                }
                if (
                    expected_fault_scope != actual_fault_scope
                    or list(case["result"].get("tradeDates") or [])[:1]
                    != [args.start_date]
                ):
                    raise RuntimeError(
                        "combined_fault_evidence_scope_mismatch:"
                        f"expected={expected_fault_scope}:actual={actual_fault_scope}"
                    )
                case["evidenceRevalidation"] = {
                    "source": "combined_fault_evidence",
                    "path": str(reuse_fault_path),
                    "sha256": hashlib.sha256(
                        reuse_fault_path.read_bytes()
                    ).hexdigest(),
                }
                summary["reusedCombinedFaultEvidence"] = str(reuse_fault_path)
            else:
                case["result"] = _run_walkforward_case(
                    api_url=args.api_url,
                    project_id=args.project_id,
                    source_backtest_id=resolved_source_backtest_id,
                    docker_project=args.compose_project,
                    start_date=args.start_date,
                    days=args.days,
                    evidence_path=fault_out,
                    scenarios=fault_cases,
                    execute_timeout=base_timeout,
                    require_fill=args.require_fill,
                    require_reject=args.require_reject,
                    require_reject_reason=args.require_reject_reason,
                    min_fill=args.min_fill,
                    min_reject=args.min_reject,
                    timeout_per_day=args.timeout_per_day,
                    api_timeout=args.api_timeout,
                    paper_mode=args.paper_mode,
                    session_overrides_json=normalized_session_overrides,
                )
            case["canonicalEquivalent"] = bool(
                case["result"].get("canonicalStateSha256")
                and case["result"].get("canonicalStateSha256")
                == no_fault_result.get("canonicalStateSha256")
            )
            observed_phases = {
                str(item.get("phase") or "")
                for item in case["result"].get("faultInjections") or []
            }
            observed_scenarios = [
                {
                    "service": str(item.get("service") or ""),
                    "day": int(item.get("day") or 0),
                    "phase": str(item.get("phase") or ""),
                }
                for item in case["result"].get("faultInjections") or []
            ]
            scenario_scope_matches = observed_scenarios == fault_cases
            six_phase_covered = {
                "intent_capture",
                "constraint_validation",
                "matching",
                "ledger",
                "snapshot_report",
                "reconciliation",
            } <= observed_phases
            worker_loss_injected = all(
                item.get("faultAction") == "sigkill_restart"
                for item in case["result"].get("faultInjections") or []
                if item.get("service") == "worker"
            ) and any(
                item.get("service") == "worker"
                for item in case["result"].get("faultInjections") or []
            )
            case["sixPhaseCovered"] = six_phase_covered
            case["workerLossInjected"] = worker_loss_injected
            case["passed"] = bool(
                _case_status(case["result"]) == "passed"
                and case["result"].get("level5ReplayRequirementsPassed") is True
                and _requirements_cover(
                    case["result"],
                    require_fill=args.require_fill,
                    require_reject=args.require_reject,
                    require_reject_reason=args.require_reject_reason,
                    min_fill=args.min_fill,
                    min_reject=args.min_reject,
                )
                and _daily_job_coverage_passed(
                    case["result"].get("dailyJobCoverage"),
                    list(case["result"].get("tradeDates") or []),
                )
                and (case["result"].get("checkpointCoverage") or {}).get("passed")
                is True
                and case["result"].get("interruptionRecoveryPassed") is True
                and scenario_scope_matches
                and case["canonicalEquivalent"]
                and six_phase_covered
                and worker_loss_injected
            )
            case["scenarioScopeMatches"] = scenario_scope_matches
            case["failedReason"] = (
                None
                if case["passed"]
                else case["result"].get("failedReason")
                or (
                    "fault_state_digest_differs_from_clean_baseline"
                    if not case["canonicalEquivalent"]
                    else (
                        "six_phase_checkpoint_coverage_missing"
                        if not six_phase_covered
                        else "worker_sigkill_evidence_missing"
                    )
                )
            )
        except Exception as exc:
            case["passed"] = False
            case["failedReason"] = str(exc)
            case["result"] = {"status": "failed"}
        summary["walkforwardMatrix"].append(case)

    if args.with_fault and fault_cases and args.fault_mode == "isolated":
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
                    session_overrides_json=normalized_session_overrides,
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
    _apply_certification_mode(summary)

    evidence = evidence_dir / "level5-audit.json"
    evidence.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": summary["status"], "passed": summary["passed"], "evidence": str(evidence)}, ensure_ascii=False))
    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
