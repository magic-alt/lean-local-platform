#!/usr/bin/env python3
"""Exercise failed-child retry and cancelled-batch restart on the real local stack."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Any, Callable
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"success", "failed", "partial", "cancelled"}


def _api_token() -> str:
    configured = os.environ.get("LEAN_API_TOKEN", "").strip()
    if configured:
        return configured
    token_file = Path(
        os.environ.get(
            "LEAN_API_TOKEN_FILE",
            str(ROOT / "web" / "runtime" / "secrets" / "api_token"),
        )
    )
    try:
        return token_file.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _api(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    token = _api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read()
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"detail": body.decode("utf-8", errors="replace")}
        return exc.code, parsed


def _require_api(base_url: str, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    status, body = _api(base_url, method, path, payload)
    if status >= 400:
        raise RuntimeError(f"api_failed:{method}:{path}:{status}:{body}")
    return body


def _compose(project: str, *arguments: str, timeout: int = 600) -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-directory",
            str(ROOT),
            "-p",
            project,
            *arguments,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"compose_failed:{' '.join(arguments)}:{result.stderr.strip()}")


def _batch_payload(project_id: str, *, name: str, candidates: list[int]) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "backtest",
        "mode": "single_symbol_grid",
        "projectIds": [project_id],
        "symbol": "600519",
        "assetClass": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "dataType": "trade",
        "cash": 300000,
        "start": "2023-01-03",
        "end": "2023-03-31",
        "source": "tushare",
        "maxCandidates": len(candidates),
        "parameterGrid": {"fast": candidates, "slow": [40]},
    }


def _wait_batch(
    base_url: str,
    batch_id: str,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout: int,
    poll_seconds: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout
    timeline: list[dict[str, Any]] = []
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = _require_api(base_url, "GET", f"/api/experiment-batches/{batch_id}")
        sample = {
            "at": datetime.now(timezone.utc).isoformat(),
            "status": latest.get("status"),
            "queued": latest.get("queued"),
            "running": latest.get("running"),
            "succeeded": latest.get("succeeded"),
            "failed": latest.get("failed"),
            "cancelled": latest.get("cancelled"),
        }
        if not timeline or sample != {**timeline[-1], "at": sample["at"]}:
            timeline.append(sample)
        if predicate(latest):
            return latest, timeline
        time.sleep(max(0.1, poll_seconds))
    raise TimeoutError(f"batch_wait_timeout:{batch_id}:{latest}")


def _attempts(batch: dict[str, Any]) -> dict[str, int]:
    return {str(item["id"]): int(item.get("attempt") or 0) for item in batch.get("items") or []}


def _failed_retry(
    *,
    base_url: str,
    project_id: str,
    compose_project: str,
    timeout: int,
    poll_seconds: float,
) -> dict[str, Any]:
    runner_recovered = False
    try:
        _compose(compose_project, "stop", "lean-runner")
        created = _require_api(
            base_url,
            "POST",
            "/api/experiment-batches",
            _batch_payload(project_id, name="Level 4 failed-child retry", candidates=[5, 10, 15]),
        )
        failed, failure_timeline = _wait_batch(
            base_url,
            str(created["id"]),
            lambda item: str(item.get("status")) in TERMINAL,
            timeout=timeout,
            poll_seconds=poll_seconds,
        )
        failed_ids = [str(item["id"]) for item in failed.get("items") or [] if item.get("status") == "failed"]
        if not failed_ids:
            raise RuntimeError(f"runner_outage_did_not_fail_children:{failed.get('status')}")
        first_attempts = _attempts(failed)
        _compose(compose_project, "up", "-d", "--wait", "lean-runner")
        runner_recovered = True
        retried = _require_api(
            base_url,
            "POST",
            f"/api/experiment-batches/{created['id']}/retry-failed",
            {},
        )
        completed, retry_timeline = _wait_batch(
            base_url,
            str(created["id"]),
            lambda item: str(item.get("status")) in TERMINAL,
            timeout=timeout,
            poll_seconds=poll_seconds,
        )
        final_attempts = _attempts(completed)
        passed = bool(
            completed.get("status") == "success"
            and all(final_attempts[item_id] == first_attempts[item_id] + 1 for item_id in failed_ids)
        )
        return {
            "batchId": created["id"],
            "initialStatus": failed.get("status"),
            "initialFailedIds": failed_ids,
            "initialAttempts": first_attempts,
            "retryDispatchStatus": retried.get("status"),
            "finalStatus": completed.get("status"),
            "finalAttempts": final_attempts,
            "failureTimeline": failure_timeline,
            "retryTimeline": retry_timeline,
            "passed": passed,
        }
    finally:
        if not runner_recovered:
            _compose(compose_project, "up", "-d", "--wait", "lean-runner")


def _cancel_restart(
    *,
    base_url: str,
    project_id: str,
    timeout: int,
    poll_seconds: float,
) -> dict[str, Any]:
    created = _require_api(
        base_url,
        "POST",
        "/api/experiment-batches",
        _batch_payload(project_id, name="Level 4 cancel/restart", candidates=[5, 10, 15, 20, 25]),
    )
    active, active_timeline = _wait_batch(
        base_url,
        str(created["id"]),
        lambda item: int(item.get("succeeded") or 0) >= 1
        and int(item.get("queued") or 0) + int(item.get("running") or 0) > 0,
        timeout=timeout,
        poll_seconds=poll_seconds,
    )
    successful_before = {
        str(item["id"]): int(item.get("attempt") or 0)
        for item in active.get("items") or []
        if item.get("status") == "success"
    }
    _require_api(base_url, "POST", f"/api/experiment-batches/{created['id']}/cancel", {})
    cancelled, cancel_timeline = _wait_batch(
        base_url,
        str(created["id"]),
        lambda item: str(item.get("status")) in TERMINAL,
        timeout=timeout,
        poll_seconds=poll_seconds,
    )
    cancelled_ids = [str(item["id"]) for item in cancelled.get("items") or [] if item.get("status") == "cancelled"]
    if not cancelled_ids:
        raise RuntimeError("cancel_did_not_leave_restartable_children")
    restarted = _require_api(
        base_url,
        "POST",
        f"/api/experiment-batches/{created['id']}/restart",
        {},
    )
    completed, restart_timeline = _wait_batch(
        base_url,
        str(created["id"]),
        lambda item: str(item.get("status")) in TERMINAL,
        timeout=timeout,
        poll_seconds=poll_seconds,
    )
    final_attempts = _attempts(completed)
    passed = bool(
        successful_before
        and completed.get("status") == "success"
        and all(final_attempts[item_id] == attempt for item_id, attempt in successful_before.items())
        and all(final_attempts[item_id] >= 1 for item_id in cancelled_ids)
    )
    return {
        "batchId": created["id"],
        "activeTimeline": active_timeline,
        "successfulAttemptsBeforeCancel": successful_before,
        "cancelledStatus": cancelled.get("status"),
        "cancelledIds": cancelled_ids,
        "cancelTimeline": cancel_timeline,
        "restartDispatchStatus": restarted.get("status"),
        "finalStatus": completed.get("status"),
        "finalAttempts": final_attempts,
        "restartTimeline": restart_timeline,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--compose-project", default="lean-platform")
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=float, default=0.5)
    parser.add_argument("--evidence-out", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != "RUN_LEVEL4_RECOVERY_AUDIT":
        parser.error("--confirm must be RUN_LEVEL4_RECOVERY_AUDIT")

    result: dict[str, Any] = {
        "schemaVersion": 1,
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "projectId": args.project_id,
        "environment": {
            "baseUrl": args.base_url,
            "composeProject": args.compose_project,
            "runtime": "real-mysql-celery-docker-lean",
        },
    }
    try:
        result["failedChildRetry"] = _failed_retry(
            base_url=args.base_url,
            project_id=args.project_id,
            compose_project=args.compose_project,
            timeout=args.timeout,
            poll_seconds=args.poll_seconds,
        )
        result["cancelRestart"] = _cancel_restart(
            base_url=args.base_url,
            project_id=args.project_id,
            timeout=args.timeout,
            poll_seconds=args.poll_seconds,
        )
        result["passed"] = bool(result["failedChildRetry"]["passed"] and result["cancelRestart"]["passed"])
        result["status"] = "passed" if result["passed"] else "failed"
    except Exception as exc:  # noqa: BLE001 - persist operational evidence
        result["passed"] = False
        result["status"] = "failed"
        result["error"] = str(exc)
    result["finishedAt"] = datetime.now(timezone.utc).isoformat()
    path = Path(args.evidence_out).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": result["status"], "evidence": str(path)}, ensure_ascii=False))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
