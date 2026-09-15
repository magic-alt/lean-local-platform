#!/usr/bin/env python3
"""Exercise bounded service restarts and prove state invariants on a local stack."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db  # noqa: E402


ACTIVE_QUERIES = {
    "dataSync": "select count(*) as count from data_sync_runs where status in ('queued','running','cancelling')",
    "backtests": "select count(*) as count from backtest_runs where status in ('queued','running','cancelling')",
    "paper": "select count(*) as count from paper_walkforward_runs where status in ('queued','running')",
}
INVARIANT_QUERIES = {
    "projects": "select count(*) as count from projects",
    "backtests": "select count(*) as count from backtest_runs",
    "paperSessions": "select count(*) as count from paper_sessions",
    "paperReports": "select count(*) as count from paper_daily_reports",
    "datasetVersions": "select count(*) as count from dataset_versions",
}
SCENARIO_BY_SERVICE = {
    "postgres": "database_short_disconnect",
    "rabbitmq": "rabbitmq_outage",
    "worker": "worker_crash",
}


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode or not completed.stdout.strip():
        return "unknown"
    return completed.stdout.strip()


def _query_counts(queries: dict[str, str]) -> dict[str, int]:
    with db() as connection:
        return {
            name: int(connection.execute(statement).fetchone()["count"])
            for name, statement in queries.items()
        }


def _compose(project: str, *arguments: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "compose",
            "--project-directory",
            str(ROOT),
            "-p",
            project,
            *arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _service_state(project: str, service: str) -> dict[str, Any]:
    result = _compose(project, "ps", "--format", "json", service)
    if result.returncode != 0:
        return {"service": service, "status": "unknown", "error": result.stderr.strip()}
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return {"service": service, "status": "unknown", "error": "invalid_compose_ps_json"}
    item = payload if isinstance(payload, list) else [payload]
    row = item[0] if item else {}
    return {
        "service": service,
        "status": str(row.get("State") or row.get("Status") or "").lower(),
        "health": str(row.get("Health") or "").lower(),
        "container": row.get("Name"),
    }


def _api_health(api_url: str) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(api_url.rstrip("/") + "/api/health", timeout=3) as response:
            body = json.loads(response.read().decode("utf-8"))
            return {"ok": response.status == 200, "httpStatus": response.status, "body": body}
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": type(exc).__name__}


def _wait_recovered(project: str, service: str, api_url: str, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    last_state: dict[str, Any] = {}
    last_api: dict[str, Any] = {}
    samples: list[dict[str, Any]] = []
    while time.monotonic() - started < timeout:
        last_state = _service_state(project, service)
        last_api = _api_health(api_url)
        samples.append(
            {
                "atSeconds": round(time.monotonic() - started, 3),
                "serviceState": last_state,
                "apiOk": bool(last_api.get("ok")),
            }
        )
        service_ready = last_state.get("status") == "running"
        health = last_state.get("health")
        if health:
            service_ready = service_ready and health == "healthy"
        if service_ready and last_api.get("ok"):
            return {
                "recovered": True,
                "seconds": round(time.monotonic() - started, 3),
                "serviceState": last_state,
                "apiHealth": last_api,
                "samples": samples,
            }
        time.sleep(2)
    return {
        "recovered": False,
        "seconds": round(time.monotonic() - started, 3),
        "serviceState": last_state,
        "apiHealth": last_api,
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="lean-platform")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--services", default="worker,rabbitmq,postgres")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.confirm != "RESTART_LOCAL_SERVICES":
        parser.error("--confirm must be RESTART_LOCAL_SERVICES")

    baseline_health = _api_health(args.api_url)
    baseline_release = ((baseline_health.get("body") or {}).get("release") or {})
    active = _query_counts(ACTIVE_QUERIES)
    if any(active.values()):
        raise RuntimeError(f"active_work_refuses_fault_injection:{active}")
    before = _query_counts(INVARIANT_QUERIES)
    results: list[dict[str, Any]] = []
    scenarios: dict[str, dict[str, Any]] = {}
    for service in [item.strip() for item in args.services.split(",") if item.strip()]:
        started_at = datetime.now(timezone.utc).isoformat()
        restart = _compose(args.project, "restart", service)
        recovery = _wait_recovered(args.project, service, args.api_url, args.timeout)
        worker_ping: dict[str, Any] | None = None
        if service.endswith("worker"):
            ping = _compose(
                args.project,
                "exec",
                "-T",
                service,
                "celery",
                "-A",
                "app.tasks.celery_app",
                "inspect",
                "ping",
                "--timeout",
                "10",
                timeout=30,
            )
            worker_ping = {
                "ok": ping.returncode == 0 and "pong" in ping.stdout.lower(),
                "exitCode": ping.returncode,
            }
            recovery["workerPing"] = worker_ping
            recovery["recovered"] = bool(recovery.get("recovered") and worker_ping["ok"])
        scenario_after = _query_counts(INVARIANT_QUERIES) if recovery.get("recovered") else {}
        result = {
            "service": service,
            "startedAt": started_at,
            "restartExitCode": restart.returncode,
            "restartError": restart.stderr.strip() if restart.returncode else None,
            **recovery,
        }
        results.append(result)
        scenario = SCENARIO_BY_SERVICE.get(service)
        if scenario:
            invariant_stable = bool(scenario_after) and before == scenario_after
            scenario_passed = bool(
                restart.returncode == 0 and recovery.get("recovered") and invariant_stable
            )
            scenarios[scenario] = {
                "passed": scenario_passed,
                "evidenceMode": "production_shape_service_fault",
                "trace": {
                    "service": service,
                    "startedAt": started_at,
                    "restartExitCode": restart.returncode,
                    "recoverySeconds": recovery.get("seconds"),
                    "samples": recovery.get("samples") or [],
                    "workerPing": worker_ping,
                },
                "invariants": {
                    "before": before,
                    "after": scenario_after,
                    "stable": invariant_stable,
                },
            }
    after = _query_counts(INVARIANT_QUERIES)
    passed = (
        all(item.get("restartExitCode") == 0 and item.get("recovered") for item in results)
        and before == after
    )
    payload = {
        "schemaVersion": 2,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "gitSha": _git_sha(),
        "releaseId": baseline_release.get("releaseId"),
        "releaseGitSha": baseline_release.get("gitSha"),
        "project": args.project,
        "activeWorkBefore": active,
        "invariantsBefore": before,
        "invariantsAfter": after,
        "invariantsStable": before == after,
        "results": results,
        "scenarios": scenarios,
        "notCovered": [
            "duplicate_delivery",
            "runner_timeout_cancel",
            "disk_full",
            "object_corruption",
            "lease_expiry_stale_worker",
            "missing_pit_benchmark",
            "notification_failure",
            "oom_kill",
            "network_partition",
            "in_flight_order_or_fill_boundary",
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
