#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import urllib.parse
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in os.sys.path:
    os.sys.path.insert(0, str(BACKEND))

from app.services.ashare_repository import trade_dates_between  # noqa: E402
from app.tasks.celery_app import celery_app  # noqa: E402


FAULT_PHASES = {
    "before_queue",
    "before_wait",
    "during_wait",
    "after_wait",
    "post_run",
    "intent_capture",
    "constraint_validation",
    "matching",
    "ledger",
    "snapshot_report",
    "reconciliation",
}
CHECKPOINT_PHASES = {
    "intent_capture",
    "constraint_validation",
    "matching",
    "ledger",
    "snapshot_report",
    "reconciliation",
}
PHASE_ALIASES = {
    "before_run": "before_queue",
    "beforepoll": "before_wait",
    "beforepolling": "before_wait",
    "before_wait": "before_wait",
    "during_poll": "during_wait",
    "duringpoll": "during_wait",
    "afterpoll": "after_wait",
    "after_wait": "after_wait",
    "before_next": "post_run",
    "after_run": "post_run",
    "postrun": "post_run",
    "post_run": "post_run",
}
CONTROL_API_TIMEOUT = 60


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


def _api(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int | None = None,
) -> tuple[int, Any]:
    request_timeout = timeout or CONTROL_API_TIMEOUT
    deadline = time.monotonic() + request_timeout
    headers = {"Content-Type": "application/json"}
    token = _api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    while True:
        request = urllib.request.Request(
            base_url.rstrip("/") + path,
            data=(json.dumps(payload).encode("utf-8") if payload is not None else None),
            headers=headers,
            method=method,
        )
        try:
            remaining = max(0.1, deadline - time.monotonic())
            with urllib.request.urlopen(request, timeout=remaining) as response:
                raw = response.read().decode("utf-8")
                return response.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                body: Any = json.loads(raw)
            except json.JSONDecodeError:
                body = {"detail": raw}
            return exc.code, body
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            if time.monotonic() >= deadline:
                raise
            time.sleep(min(0.5, max(0.1, deadline - time.monotonic())))


def _field(item: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in item:
            return item[name]
    return None


def _run_for_date(items: list[dict[str, Any]], trade_date: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in items
            if str(_field(item, "trade_date", "tradeDate") or "") == trade_date
        ),
        None,
    )


def _wait_for_run(
    base_url: str,
    session_id: str,
    trade_date: str,
    *,
    timeout_seconds: int,
    poll_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status, body = _api(base_url, "GET", f"/api/paper/{session_id}/runs")
        if status >= 400:
            raise RuntimeError(f"paper_runs_unavailable:{status}:{body}")
        items = body if isinstance(body, list) else list(body.get("items") or [])
        last = _run_for_date(items, trade_date)
        run_status = str((last or {}).get("status") or "")
        if run_status == "success":
            return last or {}
        if run_status == "failed":
            raise RuntimeError(f"paper_walkforward_failed:{trade_date}:{(last or {}).get('failure')}")
        if run_status in {"cancelled", "stopped"}:
            raise RuntimeError(f"paper_walkforward_stopped:{trade_date}:{run_status}")
        time.sleep(max(0.25, poll_seconds))
    raise TimeoutError(f"paper_walkforward_timeout:{trade_date}:{last}")


def _wait_for_checkpoint(
    base_url: str,
    session_id: str,
    trade_date: str,
    phase: str,
    *,
    timeout_seconds: int,
    poll_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    query = urllib.parse.urlencode({"tradeDate": trade_date, "phase": phase})
    while time.monotonic() < deadline:
        status, body = _api(
            base_url,
            "GET",
            f"/api/paper/{session_id}/checkpoints?{query}",
        )
        if status >= 400:
            time.sleep(max(0.25, poll_seconds))
            continue
        for checkpoint in body if isinstance(body, list) else []:
            checkpoint_date = str(_field(checkpoint, "trade_date", "tradeDate") or "")
            if checkpoint_date == trade_date and checkpoint.get("phase") == phase:
                return {
                    **checkpoint,
                    "observedRunStatus": str(
                        _field(checkpoint, "run_status", "runStatus") or ""
                    ),
                }
        run_status, runs = _api(
            base_url,
            "GET",
            f"/api/paper/{session_id}/runs",
        )
        if run_status < 400:
            run = _run_for_date(
                runs if isinstance(runs, list) else list(runs.get("items") or []),
                trade_date,
            )
            observed = str((run or {}).get("status") or "")
            if observed == "failed":
                raise RuntimeError(
                    f"paper_walkforward_failed_before_checkpoint:"
                    f"{trade_date}:{phase}:{(run or {}).get('failure')}"
                )
            if observed in {"cancelled", "stopped"}:
                raise RuntimeError(
                    f"paper_walkforward_stopped_before_checkpoint:"
                    f"{trade_date}:{phase}:{observed}"
                )
        time.sleep(max(0.1, min(poll_seconds, 0.5)))
    raise TimeoutError(f"paper_checkpoint_timeout:{trade_date}:{phase}")


def _reports(base_url: str, session_id: str) -> list[dict[str, Any]]:
    status, body = _api(
        base_url,
        "GET",
        f"/api/paper/{session_id}/reports?light=true&paged=true&limit=1000",
    )
    if status >= 400:
        raise RuntimeError(f"paper_reports_unavailable:{status}:{body}")
    return body if isinstance(body, list) else list(body.get("items") or [])


def _compose_restart(root: Path, service: str, project: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    base = [
        "docker",
        "compose",
        "--project-directory",
        str(root),
        "-p",
        project,
    ]
    if service == "worker":
        kill_args = [*base, "kill", "-s", "SIGKILL", service]
        killed = subprocess.run(
            kill_args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if killed.returncode != 0:
            return killed
        start_args = [*base, "up", "-d", "--no-deps", service]
        started = subprocess.run(
            start_args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return subprocess.CompletedProcess(
            args=[kill_args, start_args],
            returncode=started.returncode,
            stdout="\n".join(
                part.strip()
                for part in (killed.stdout or "", started.stdout or "")
                if part.strip()
            ),
            stderr="\n".join(
                part.strip()
                for part in (killed.stderr or "", started.stderr or "")
                if part.strip()
            ),
        )
    args = [*base, "restart", service]
    return subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _wait_api_ready(base_url: str, timeout_seconds: int, poll_seconds: float = 1.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base_url.rstrip("/") + "/api/health", timeout=3) as response:
                if response.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(max(0.25, poll_seconds))
    return False


def _normalize_phase(value: str) -> str:
    normalized = (value or "").strip().lower()
    return PHASE_ALIASES.get(normalized, normalized)


def _parse_fault_scenarios(values: list[str] | None) -> list[dict[str, Any]]:
    if not values:
        return []

    raw_items: list[str] = []
    for raw in values:
        if raw:
            raw_items.extend([item.strip() for item in raw.split(",") if item.strip()])

    scenarios: list[dict[str, Any]] = []
    for raw in raw_items:
        match = re.fullmatch(r"([A-Za-z0-9_-]+)@(\d+)(?::([A-Za-z0-9_-]+))?", raw)
        if not match:
            raise ValueError(f"invalid_fault_scenario:{raw}")
        service = match.group(1).strip().lower()
        day = int(match.group(2))
        phase = _normalize_phase(match.group(3) or "before_queue")
        if day <= 0:
            raise ValueError(f"fault_day_must_be_positive:{day}:{raw}")
        if phase not in FAULT_PHASES:
            raise ValueError(f"unsupported_fault_phase:{phase}:{raw}")
        scenarios.append({"service": service, "day": day, "phase": phase})
    return scenarios


def _scenarios_by_day_phase(scenarios: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    buckets: dict[int, list[dict[str, Any]]] = {}
    for item in scenarios:
        buckets.setdefault(int(item["day"]), []).append(item)

    # Keep deterministic order inside the same day.
    for day in buckets:
        buckets[day] = sorted(buckets[day], key=lambda row: (row["phase"], row["service"]))
    return buckets


def _inject_fault(
    *,
    base_url: str,
    day_index: int,
    trade_date: str,
    service: str,
    phase: str,
    project: str,
    root: Path,
    restart_timeout: int,
    recover_timeout: int,
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    result = _compose_restart(root, service, project, timeout=restart_timeout)
    recovered = _wait_api_ready(base_url, timeout_seconds=max(20, recover_timeout), poll_seconds=1.0)
    return {
        "day": day_index,
        "tradeDate": trade_date,
        "service": service,
        "phase": phase,
        "faultAction": "sigkill_restart" if service == "worker" else "compose_restart",
        "startedAt": started_at,
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "recoverySeconds": round(time.monotonic() - started, 3),
        "restartExitCode": result.returncode,
        "restartStdout": (result.stdout or "").strip(),
        "restartStderr": result.stderr.strip() if result.stderr else None,
        "apiRecovered": recovered,
    }


def _dispatch_finalization_recovery(paper_run_id: str) -> str:
    result = celery_app.send_task(
        "lean_web.recover_paper_finalizations",
        kwargs={
            "paper_run_id": paper_run_id,
            "stale_seconds": 0,
        },
    )
    return str(result.id)


def _safe_candidate_id(candidate: dict[str, Any]) -> str:
    candidate_id = candidate.get("id")
    if isinstance(candidate_id, str):
        trimmed = candidate_id.strip()
        if trimmed:
            return trimmed
    return ""


def _resolve_source_backtest_id(*, project_id: str, api_url: str) -> str:
    status, payload = _api(
        api_url,
        "GET",
        f"/api/paper/accounts/candidates?projectId={urllib.parse.quote(project_id)}",
    )
    if status >= 400:
        raise RuntimeError(f"paper_candidates_unavailable:{status}:{payload}")
    if not isinstance(payload, list):
        raise RuntimeError(f"paper_candidates_invalid_payload:{payload}")
    if not payload:
        raise RuntimeError(f"no_trusted_source_backtest_for_project:{project_id}")
    selected = _safe_candidate_id(payload[0])
    if not selected:
        raise RuntimeError(f"paper_candidate_missing_id:{payload[0]}")
    return selected


def _parse_boolish(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "y", "on"}


def _canonical_number(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 8)
    return value


def _canonical_rows(
    rows: list[dict[str, Any]],
    fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    projected = [
        {
            field: _canonical_number(item.get(field))
            for field in fields
        }
        for item in rows
        if isinstance(item, dict)
    ]
    return sorted(
        projected,
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), default=str),
    )


def _canonical_session_state(detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "orders": _canonical_rows(
            list(detail.get("orders") or []),
            (
                "trade_date",
                "symbol",
                "side",
                "quantity",
                "order_price",
                "fill_price",
                "fee",
                "status",
                "reason",
            ),
        ),
        "fills": _canonical_rows(
            list(detail.get("fills") or []),
            (
                "trade_date",
                "quantity",
                "price",
                "fee",
                "tax",
                "slippage",
                "fee_model_version",
                "matching_contract",
            ),
        ),
        "ledger": _canonical_rows(
            list(detail.get("ledger") or []),
            (
                "trade_date",
                "entry_type",
                "asset",
                "symbol",
                "quantity",
                "amount",
                "currency",
                "debit_account",
                "credit_account",
            ),
        ),
        "snapshots": _canonical_rows(
            list(detail.get("snapshots") or []),
            (
                "trade_date",
                "cash",
                "market_value",
                "equity",
                "benchmark_symbol",
            ),
        ),
        "reconciliations": _canonical_rows(
            list(detail.get("reconciliations") or []),
            (
                "trade_date",
                "status",
                "opening_cash",
                "ledger_cash_movement",
                "closing_cash",
                "cash_drift",
                "position_drift",
                "order_fill_ok",
                "fill_ledger_ok",
                "ledger_cash_ok",
                "ledger_positions_ok",
                "snapshot_ok",
                "daily_report_ok",
            ),
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a resumable, real 21-trading-day LEAN Paper walk-forward acceptance."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--source-backtest-id",
        default="",
        help="Explicit trusted source backtest id; omit to auto-select candidate.",
    )
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--session-id")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-timeout", type=int, default=60)
    parser.add_argument(
        "--paper-mode",
        choices=("lean_walkforward", "lean_walkforward_v2"),
        default="lean_walkforward",
        help="Paper pipeline mode. Level 5 certification must use lean_walkforward_v2.",
    )
    parser.add_argument("--timeout-per-day", type=int, default=900)
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument(
        "--fault-scenario",
        action="append",
        default=[],
        help="Inject compose restart like worker@7:before_queue (repeatable).",
    )
    parser.add_argument(
        "--fault-at-day",
        type=int,
        default=0,
        help="Deprecated compatibility alias: one fault at this 1-based day index before queueing.",
    )
    parser.add_argument(
        "--fault-service",
        default="",
        help="Deprecated compatibility alias: one restart service for --fault-at-day (worker, rabbitmq, postgres).",
    )
    parser.add_argument(
        "--fault-phase",
        default="before_queue",
        help="Deprecated compatibility alias for --fault-scenario phase.",
    )
    parser.add_argument("--docker-project", default="lean-platform", help="Docker compose -p project used for fault injection.")
    parser.add_argument("--compose-restart-timeout", type=int, default=180, help="Timeout for compose restart call.")
    parser.add_argument("--compose-recover-timeout", type=int, default=180, help="Timeout waiting for API recovery.")
    parser.add_argument(
        "--require-fill",
        default="true",
        help="Require minimum filled orders (true/false).",
    )
    parser.add_argument(
        "--require-reject",
        default="true",
        help="Require minimum rejected orders (true/false).",
    )
    parser.add_argument(
        "--require-reject-reason",
        nargs="?",
        const="true",
        default="false",
        help="Require at least one reject reason text when rejected orders exist.",
    )
    parser.add_argument("--min-fill", type=int, default=1)
    parser.add_argument("--min-reject", type=int, default=1)
    parser.add_argument("--evidence-out")
    parser.add_argument(
        "--session-overrides-json",
        default="{}",
        help=(
            "JSON object merged into Paper session creation. Use isolated acceptance "
            "constraints such as {\"blacklist\":[\"600519\"]} to prove real LEAN rejects."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    global CONTROL_API_TIMEOUT
    CONTROL_API_TIMEOUT = max(1, int(args.api_timeout))

    if args.days < 1:
        parser.error("--days must be positive")

    require_fill = _parse_boolish(args.require_fill, default=True)
    require_reject = _parse_boolish(args.require_reject, default=True)
    require_reject_reason = _parse_boolish(args.require_reject_reason, default=False)
    try:
        session_overrides = json.loads(args.session_overrides_json)
    except json.JSONDecodeError as exc:
        parser.error(f"--session-overrides-json must be valid JSON: {exc}")
    if not isinstance(session_overrides, dict):
        parser.error("--session-overrides-json must be a JSON object")

    if args.min_fill < 0:
        parser.error("--min-fill must be >= 0")
    if args.min_reject < 0:
        parser.error("--min-reject must be >= 0")

    resolved_source_backtest_id = args.source_backtest_id.strip()
    if not resolved_source_backtest_id:
        resolved_source_backtest_id = _resolve_source_backtest_id(
            project_id=args.project_id,
            api_url=args.api_url,
        )

    fault_phase = _normalize_phase(args.fault_phase)
    if fault_phase not in FAULT_PHASES:
        parser.error(f"unsupported fault phase: {args.fault_phase}")

    if args.fault_at_day and not args.fault_service:
        parser.error("--fault-at-day requires --fault-service")
    if args.fault_service and args.fault_at_day <= 0:
        parser.error("--fault-service requires --fault-at-day > 0")

    legacy = []
    if args.fault_at_day and args.fault_service:
        legacy.append(f"{args.fault_service}@{args.fault_at_day}:{fault_phase}")

    scenarios = _parse_fault_scenarios([*args.fault_scenario, *legacy])
    scenario_by_day = _scenarios_by_day_phase(scenarios)

    calendar = trade_dates_between("china", args.start_date, "2099-12-31")
    trade_dates = [item for item in calendar if item >= args.start_date][: args.days]
    if len(trade_dates) != args.days:
        raise RuntimeError(f"trade_calendar_incomplete:{len(trade_dates)}/{args.days}")

    if args.dry_run:
        print(
            json.dumps(
                {
                    "status": "planned",
                    "projectId": args.project_id,
                    "sourceBacktestId": resolved_source_backtest_id,
                    "tradeDates": trade_dates,
                    "faultScenarios": scenarios,
                    "sessionOverrides": session_overrides,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    session_id = str(args.session_id or "")
    if not session_id:
        create_payload = {
            "name": f"LEAN 21-day acceptance {args.start_date}",
            "mode": args.paper_mode,
            "projectId": args.project_id,
            "sourceBacktestId": resolved_source_backtest_id,
            "startDate": args.start_date,
            "autoAdvance": False,
            **session_overrides,
        }
        status, session = _api(
            args.api_url,
            "POST",
            "/api/paper",
            create_payload,
        )
        if status >= 400:
            raise RuntimeError(f"paper_session_create_failed:{status}:{session}")
        session_id = str(session["id"])

    completed: list[dict[str, Any]] = []
    fault_injections: list[dict[str, Any]] = []
    daily_runs: list[dict[str, Any]] = []
    for index, trade_date in enumerate(trade_dates, start=1):
        for scenario in [item for item in scenario_by_day.get(index, []) if item["phase"] == "before_queue"]:
            injection = _inject_fault(
                base_url=args.api_url,
                day_index=index,
                trade_date=trade_date,
                service=scenario["service"],
                phase=scenario["phase"],
                project=args.docker_project,
                root=ROOT,
                restart_timeout=args.compose_restart_timeout,
                recover_timeout=args.compose_recover_timeout,
            )
            fault_injections.append(injection)
            if injection.get("restartExitCode", 1) != 0 or not injection.get("apiRecovered"):
                raise RuntimeError(f"paper_fault_injection_failed:{index}:{injection}")
            print(f"[{index}/{len(trade_dates)}] fault injection injected on {trade_date}: {json.dumps(injection, ensure_ascii=False)}", flush=True)

        status, runs_body = _api(args.api_url, "GET", f"/api/paper/{session_id}/runs")
        if status >= 400:
            raise RuntimeError(f"paper_runs_unavailable:{status}:{runs_body}")
        runs = runs_body if isinstance(runs_body, list) else list(runs_body.get("items") or [])
        existing = _run_for_date(runs, trade_date)
        if str((existing or {}).get("status") or "") == "success":
            completed.append(existing or {})
            daily_runs.append({"tradeDate": trade_date, "status": "success", "id": (existing or {}).get("id") or (existing or {}).get("runId")})
            print(f"[{index}/{len(trade_dates)}] {trade_date} already success", flush=True)
            continue

        if str((existing or {}).get("status") or "") in {"queued", "running", "pending"}:
            print(f"[{index}/{len(trade_dates)}] {trade_date} in-flight {str((existing or {}).get('status'))}", flush=True)
            item = _wait_for_run(
                args.api_url,
                session_id,
                trade_date,
                timeout_seconds=args.timeout_per_day,
                poll_seconds=args.poll_seconds,
            )
            completed.append(item)
            daily_runs.append({"tradeDate": trade_date, "status": str(item.get("status") or ""), "id": item.get("id")})
            continue
        if str((existing or {}).get("status") or "") in {"failed", "cancelled", "stopped"}:
            raise RuntimeError(f"paper_day_previous_failure:{trade_date}:{existing}")

        print(f"[{index}/{len(trade_dates)}] queue {trade_date}", flush=True)
        for scenario in [item for item in scenario_by_day.get(index, []) if item["phase"] == "before_wait"]:
            injection = _inject_fault(
                base_url=args.api_url,
                day_index=index,
                trade_date=trade_date,
                service=scenario["service"],
                phase=scenario["phase"],
                project=args.docker_project,
                root=ROOT,
                restart_timeout=args.compose_restart_timeout,
                recover_timeout=args.compose_recover_timeout,
            )
            fault_injections.append(injection)
            if injection.get("restartExitCode", 1) != 0 or not injection.get("apiRecovered"):
                raise RuntimeError(f"paper_fault_injection_failed:{index}:{injection}")
            print(f"[{index}/{len(trade_dates)}] fault injection injected on {trade_date}: {json.dumps(injection, ensure_ascii=False)}", flush=True)

        status, response = _api(
            args.api_url,
            "POST",
            f"/api/paper/{session_id}/run-day",
            {"tradeDate": trade_date, "autoSignal": False},
        )
        if status >= 400:
            raise RuntimeError(f"paper_run_day_failed:{trade_date}:{status}:{response}")

        for scenario in [item for item in scenario_by_day.get(index, []) if item["phase"] == "during_wait"]:
            injection = _inject_fault(
                base_url=args.api_url,
                day_index=index,
                trade_date=trade_date,
                service=scenario["service"],
                phase=scenario["phase"],
                project=args.docker_project,
                root=ROOT,
                restart_timeout=args.compose_restart_timeout,
                recover_timeout=args.compose_recover_timeout,
            )
            fault_injections.append(injection)
            if injection.get("restartExitCode", 1) != 0 or not injection.get("apiRecovered"):
                raise RuntimeError(f"paper_fault_injection_failed:{index}:{injection}")
            print(f"[{index}/{len(trade_dates)}] fault injection injected on {trade_date}: {json.dumps(injection, ensure_ascii=False)}", flush=True)

        for scenario in [
            item
            for item in scenario_by_day.get(index, [])
            if item["phase"] in CHECKPOINT_PHASES
        ]:
            checkpoint = _wait_for_checkpoint(
                args.api_url,
                session_id,
                trade_date,
                str(scenario["phase"]),
                timeout_seconds=args.timeout_per_day,
                poll_seconds=args.poll_seconds,
            )
            injection = _inject_fault(
                base_url=args.api_url,
                day_index=index,
                trade_date=trade_date,
                service=scenario["service"],
                phase=scenario["phase"],
                project=args.docker_project,
                root=ROOT,
                restart_timeout=args.compose_restart_timeout,
                recover_timeout=args.compose_recover_timeout,
            )
            injection["checkpointDigest"] = checkpoint.get("digest")
            injection["runStatusAtInjection"] = checkpoint.get("observedRunStatus")
            if scenario["service"] == "worker":
                paper_run_id = str(
                    checkpoint.get("paper_run_id")
                    or checkpoint.get("paperRunId")
                    or ""
                )
                if not paper_run_id:
                    raise RuntimeError(
                        f"paper_checkpoint_missing_run_id:{trade_date}:{scenario['phase']}"
                    )
                injection["finalizationRecoveryTaskId"] = (
                    _dispatch_finalization_recovery(paper_run_id)
                )
            fault_injections.append(injection)
            if injection.get("restartExitCode", 1) != 0 or not injection.get("apiRecovered"):
                raise RuntimeError(f"paper_fault_injection_failed:{index}:{injection}")
            print(
                f"[{index}/{len(trade_dates)}] checkpoint fault injected on "
                f"{trade_date}: {json.dumps(injection, ensure_ascii=False)}",
                flush=True,
            )

        item = _wait_for_run(
            args.api_url,
            session_id,
            trade_date,
            timeout_seconds=args.timeout_per_day,
            poll_seconds=args.poll_seconds,
        )
        completed.append(item)
        daily_runs.append({"tradeDate": trade_date, "status": str(item.get("status") or ""), "id": item.get("id")})

        for scenario in [
            item
            for item in scenario_by_day.get(index, [])
            if item["phase"] in {"after_wait", "post_run"}
        ]:
            injection = _inject_fault(
                base_url=args.api_url,
                day_index=index,
                trade_date=trade_date,
                service=scenario["service"],
                phase=scenario["phase"],
                project=args.docker_project,
                root=ROOT,
                restart_timeout=args.compose_restart_timeout,
                recover_timeout=args.compose_recover_timeout,
            )
            fault_injections.append(injection)
            if injection.get("restartExitCode", 1) != 0 or not injection.get("apiRecovered"):
                raise RuntimeError(f"paper_fault_injection_failed:{index}:{injection}")
            print(f"[{index}/{len(trade_dates)}] fault injection injected on {trade_date}: {json.dumps(injection, ensure_ascii=False)}", flush=True)

        print(
            f"[{index}/{len(trade_dates)}] {trade_date} success backtest="
            f"{_field(item, 'backtest_run_id', 'backtestRunId')}",
            flush=True,
        )

    reports = _reports(args.api_url, session_id)
    status, detail = _api(args.api_url, "GET", f"/api/paper/{session_id}")
    if status >= 400:
        raise RuntimeError(f"paper_detail_unavailable:{status}:{detail}")

    before_counts = {
        "runs": len(detail.get("runs") or []),
        "reports": len(reports),
        "orders": len(detail.get("orders") or []),
        "snapshots": len(detail.get("snapshots") or []),
    }
    orders = [item for item in (detail.get("orders") or []) if isinstance(item, dict)]
    fills = [
        item
        for item in orders
        if str(item.get("status") or "").lower() in {"3", "filled", "success", "completed"}
    ]
    rejects = [
        item
        for item in orders
        if str(item.get("status") or "").lower() == "rejected"
    ]
    reject_reasons = [
        str(
            item.get("reason")
            or item.get("rejectReason")
            or item.get("failure")
            or item.get("message")
            or ""
        )
        for item in rejects
    ]

    duplicate_status, duplicate_body = _api(
        args.api_url,
        "POST",
        f"/api/paper/{session_id}/run-day",
        {"tradeDate": trade_dates[-1], "autoSignal": False},
    )
    reports_after = _reports(args.api_url, session_id)
    _, detail_after = _api(args.api_url, "GET", f"/api/paper/{session_id}")
    after_counts = {
        "runs": len(detail_after.get("runs") or []),
        "reports": len(reports_after),
        "orders": len(detail_after.get("orders") or []),
        "snapshots": len(detail_after.get("snapshots") or []),
    }

    successful_dates = {
        str(_field(item, "trade_date", "tradeDate") or "")
        for item in completed
        if str(item.get("status") or "") == "success"
    }
    reconciliation_failures = [
        str(_field(item, "trade_date", "tradeDate") or "")
        for item in completed
        if (item.get("reconciliation") or {}).get("passed") is not True
    ]
    report_dates = {
        str(_field(item, "trade_date", "tradeDate") or "")
        for item in reports
    }

    duplicate_idempotent_statuses = {200, 400, 409}
    checkpoint_rows = list(detail_after.get("checkpoints") or [])
    completed_job_dates = {
        str(_field(item, "trade_date", "tradeDate") or "")
        for item in detail_after.get("dailyJobs") or []
        if str(item.get("state") or "") == "COMPLETED"
    }
    daily_job_coverage_ok = set(trade_dates) <= completed_job_dates
    checkpoint_phases_by_date = {
        trade_date: {
            str(item.get("phase") or "")
            for item in checkpoint_rows
            if str(_field(item, "trade_date", "tradeDate") or "") == trade_date
        }
        for trade_date in trade_dates
    }
    required_checkpoint_phases = set(CHECKPOINT_PHASES)
    checkpoint_coverage_ok = bool(
        args.paper_mode != "lean_walkforward_v2"
        or all(
            required_checkpoint_phases <= checkpoint_phases_by_date.get(trade_date, set())
            for trade_date in trade_dates
        )
    )
    interruption_recovery_ok = bool(
        len(fault_injections) == len(scenarios)
        and all(
            item.get("restartExitCode") == 0 and item.get("apiRecovered") is True
            for item in fault_injections
        )
        and all(
            item.get("phase") not in CHECKPOINT_PHASES
            or item.get("runStatusAtInjection") in {"queued", "running"}
            for item in fault_injections
        )
        and all(
            item.get("service") != "worker"
            or (
                item.get("faultAction") == "sigkill_restart"
                and bool(item.get("finalizationRecoveryTaskId"))
            )
            for item in fault_injections
        )
    )

    walkforward_passed = bool(
        successful_dates == set(trade_dates)
        and set(trade_dates) <= report_dates
        and not reconciliation_failures
        and duplicate_status in duplicate_idempotent_statuses
        and before_counts["reports"] == after_counts["reports"]
        and before_counts["orders"] == after_counts["orders"]
        and before_counts["snapshots"] == after_counts["snapshots"]
        and checkpoint_coverage_ok
        and daily_job_coverage_ok
        and interruption_recovery_ok
    )

    fill_count = len(fills)
    reject_count = len(rejects)
    fills_ok = (not require_fill) or fill_count >= max(0, args.min_fill)
    rejects_ok = (not require_reject) or reject_count >= max(0, args.min_reject)
    reject_reason_ok = (not require_reject_reason) or any(bool((reason or "").strip()) for reason in reject_reasons)

    remaining_failure = None
    if not fills_ok:
        remaining_failure = "required_fill_not_met"
    elif not rejects_ok:
        remaining_failure = "required_reject_not_met"
    elif not reject_reason_ok:
        remaining_failure = "required_reject_reason_missing"

    passed = bool(
        walkforward_passed
        and fills_ok
        and rejects_ok
        and reject_reason_ok
    )
    canonical_state = _canonical_session_state(detail_after)
    canonical_state_sha256 = hashlib.sha256(
        json.dumps(
            canonical_state,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    result = {
        "status": "passed" if passed else ("partial" if walkforward_passed else "failed"),
        "sessionId": session_id,
        "sourceBacktestId": resolved_source_backtest_id,
        "projectId": args.project_id,
        "paperMode": args.paper_mode,
        "tradeDates": trade_dates,
        "dailyRuns": daily_runs,
        "successfulDays": len(successful_dates),
        "reportDays": len(set(trade_dates) & report_dates),
        "orders": before_counts["orders"],
        "filledOrders": fill_count,
        "rejectedOrders": reject_count,
        "rejectReasons": sorted({reason for reason in reject_reasons if reason}),
        "snapshots": before_counts["snapshots"],
        "reconciliationFailures": reconciliation_failures,
        "duplicateReplay": {
            "httpStatus": duplicate_status,
            "blocked": duplicate_status in {400, 409},
            "detail": duplicate_body.get("detail") if isinstance(duplicate_body, dict) else None,
            "countsStable": before_counts == after_counts,
            "idempotentStatusSet": sorted(duplicate_idempotent_statuses),
        },
        "faultScenarios": scenarios,
        "faultInjections": fault_injections,
        "sessionOverrides": session_overrides,
        "checkpointCoverage": {
            "requiredPhases": sorted(required_checkpoint_phases),
            "completeDays": sum(
                1
                for trade_date in trade_dates
                if required_checkpoint_phases
                <= checkpoint_phases_by_date.get(trade_date, set())
            ),
            "totalDays": len(trade_dates),
            "passed": checkpoint_coverage_ok,
        },
        "dailyJobCoverage": {
            "completedDays": len(set(trade_dates) & completed_job_dates),
            "totalDays": len(trade_dates),
            "passed": daily_job_coverage_ok,
        },
        "interruptionRecoveryPassed": interruption_recovery_ok,
        "canonicalState": canonical_state,
        "canonicalStateSha256": canonical_state_sha256,
        "walkforwardPassed": walkforward_passed,
        "level5ReplayRequirementsPassed": passed,
        "remainingRequirement": remaining_failure,
        "passed": passed,
        "evidence": {
            "requireFill": require_fill,
            "requireReject": require_reject,
            "requireRejectReason": require_reject_reason,
            "minFill": args.min_fill,
            "minReject": args.min_reject,
        },
        "timeoutPerDay": args.timeout_per_day,
    }

    encoded = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.evidence_out:
        evidence_path = Path(args.evidence_out).expanduser().resolve()
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
