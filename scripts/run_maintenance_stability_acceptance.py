#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
import sys
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, rows_to_dicts  # noqa: E402

ACTIVE_STATUSES = {"queued", "running", "retry_wait"}
SUCCESS_STATUSES = {"success"}
FAILED_STATUSES = {"failed"}
CHECKPOINT_KEYS = {"completedUnits", "attempt", "currentUnit"}
KNOWN_RECOVERY_ERRORS = (
    "2013",
    "mysql",
    "oom",
    "out of memory",
    "orphaned_after_worker_restart",
)


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_id(value: Any) -> str:
    value = str(value or "").strip()
    return value


def _parse_checkpoint(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else None
    except json.JSONDecodeError:
        return None


def _failure_signature(error: Any) -> str:
    text = str(error or "").lower()
    if not text:
        return ""
    if "orphaned_after_worker_restart" in text:
        return "orphaned_after_worker_restart"
    if "2013" in text or "mysql" in text:
        return "mysql" if "2013" not in text else "mysql_2013"
    if "oom" in text or "out of memory" in text:
        return "oom"
    return "other"


def _within_window(run: dict[str, Any], start: datetime) -> bool:
    created = _parse_time(run.get("created_at"))
    finished = _parse_time(run.get("finished_at"))
    heartbeat = _parse_time(run.get("heartbeat_at"))
    for item in (finished, heartbeat, created):
        if item and item >= start:
            return True
    if created is None:
        return False
    return created >= start


def _query_runs(start_iso: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from derived_maintenance_runs order by created_at asc"
        ).fetchall()
    all_rows = rows_to_dicts(rows)
    return [dict(item) for item in all_rows]


def _run_summary(run: dict[str, Any], *, window_start: datetime | None = None) -> dict[str, Any]:
    checkpoint = _parse_checkpoint(run.get("checkpoint_json"))
    completed_units = checkpoint.get("completedUnits") if checkpoint else []
    if completed_units is None:
        completed_units = []
    status = str(run.get("status") or "").strip().lower()
    attempt_count = int(run.get("attempt_count") or 0)
    error = run.get("error")
    signature = _failure_signature(error)
    is_active = status in ACTIVE_STATUSES
    return {
        "runId": _normalize_id(run.get("id")),
        "status": status,
        "createdAt": run.get("created_at"),
        "startedAt": run.get("started_at"),
        "finishedAt": run.get("finished_at"),
        "heartbeatAt": run.get("heartbeat_at"),
        "nextRetryAt": run.get("next_retry_at"),
        "attemptCount": attempt_count,
        "maxAttempts": int(run.get("max_attempts") or 0),
        "leaseOwner": run.get("lease_owner"),
        "error": error,
        "failureSignature": signature,
        "isActive": is_active,
        "checkpoint": {
            "attempt": checkpoint.get("attempt") if isinstance(checkpoint, dict) else None,
            "completedUnits": completed_units,
            "currentUnit": checkpoint.get("currentUnit") if isinstance(checkpoint, dict) else None,
            "present": bool(checkpoint and any(
                isinstance(checkpoint.get(key), (list, dict, str, int, float, bool))
                for key in CHECKPOINT_KEYS
            )),
        },
        "inWindow": _within_window(run, window_start) if window_start else True,
        "summary": run.get("summary_json") or {},
    }


def _run_window_summary(runs: list[dict[str, Any]], window_hours: float) -> dict[str, Any]:
    start = datetime.now(timezone.utc) - timedelta(hours=max(0.0, float(window_hours)))
    start_iso = start.isoformat()
    window_items = [run for run in runs if _within_window(run, start)]
    if not window_items:
        return {
            "start": start_iso,
            "runCount": 0,
            "passed": False,
            "criticalFailures": ["no_runs_in_window"],
            "multipleActive": True,
            "checkpointResumePassed": False,
            "activeRunCount": 0,
            "failureTraces": [],
            "runTimeline": [],
        }

    run_timeline = [_run_summary(item, window_start=start) for item in window_items]
    run_timeline.sort(key=lambda item: str(item.get("createdAt") or ""))

    active_runs = [item for item in run_timeline if item["isActive"]]
    multiple_active = len(active_runs) > 1

    failure_traces: list[dict[str, Any]] = []
    for item in run_timeline:
        status = str(item.get("status") or "")
        signature = str(item.get("failureSignature") or "")
        if status in FAILED_STATUSES and signature in {"mysql", "mysql_2013", "oom", "orphaned_after_worker_restart"}:
            failure_traces.append(
                {
                    "runId": item["runId"],
                    "status": status,
                    "signature": signature,
                    "error": item.get("error"),
                    "attemptCount": item.get("attemptCount"),
                }
            )

    active_overlap_ok = not multiple_active

    resumed_candidates = [
        item
        for item in run_timeline
        if int(item["attemptCount"] or 0) > 1
    ]
    checkpoint_resume_passed = all(
        item["checkpoint"].get("present") and item.get("status") == "success"
        for item in resumed_candidates
    ) if resumed_candidates else True

    critical_no_recent_mysql_failures = len(failure_traces) == 0

    passed = bool(
        active_overlap_ok
        and critical_no_recent_mysql_failures
        and checkpoint_resume_passed
    )

    return {
        "start": start_iso,
        "runCount": len(run_timeline),
        "activeRunCount": len(active_runs),
        "multipleActive": multiple_active,
        "activeOverlapOk": active_overlap_ok,
        "criticalNoMysqlOrOrphanFailure": critical_no_recent_mysql_failures,
        "checkpointResumePassed": checkpoint_resume_passed,
        "failureTraces": failure_traces,
        "runTimeline": run_timeline,
        "passed": passed,
    }


def run(*, window_hours: float = 168.0, require_checkpoint_resume: bool = True) -> dict[str, Any]:
    window_hours = max(0.0, float(window_hours))
    runs = _query_runs("")
    summary = _run_window_summary(runs, window_hours=window_hours)
    if not require_checkpoint_resume:
        summary["checkpointResumePassed"] = bool(summary.get("checkpointResumePassed"))
    passed = bool(summary.get("passed"))
    if not require_checkpoint_resume:
        passed = bool(
            summary.get("activeOverlapOk")
            and summary.get("criticalNoMysqlOrOrphanFailure")
        )
        summary["passed"] = passed
    return {
        "status": "MAINTENANCE_STABILITY_PASS" if passed else "MAINTENANCE_STABILITY_FAIL",
        "passed": passed,
        "testedAt": datetime.now(timezone.utc).isoformat(),
        "windowHours": window_hours,
        "runWindow": summary,
        "runCount": summary.get("runCount", 0),
        "activeRunCount": summary.get("activeRunCount", 0),
        "failureTraces": summary.get("failureTraces", []),
        "runTimeline": summary.get("runTimeline", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 7-day maintenance stability observation.")
    parser.add_argument("--window-hours", type=float, default=168, help="Observation window in hours.")
    parser.add_argument(
        "--skip-checkpoint-resume",
        action="store_true",
        help="Skip checkpoint-resume evidence check (default: enabled).",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / "web" / "runtime" / "audit" / "maintenance-stability-acceptance.json",
    )
    args = parser.parse_args()

    exit_code = 0
    try:
        evidence = run(
            window_hours=args.window_hours,
            require_checkpoint_resume=not args.skip_checkpoint_resume,
        )
        if not evidence.get("passed"):
            exit_code = 2
    except Exception as exc:
        evidence = {
            "status": "MAINTENANCE_STABILITY_FAIL",
            "passed": False,
            "testedAt": datetime.now(timezone.utc).isoformat(),
            "failure": {
                "type": type(exc).__name__,
                "detail": str(exc),
            },
        }
        exit_code = 2

    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
