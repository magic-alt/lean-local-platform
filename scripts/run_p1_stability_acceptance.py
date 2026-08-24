#!/usr/bin/env python3
"""Run five real LEAN jobs, queued/running cancellation, and service restarts."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"success", "failed", "cancelled"}


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


def _api(
    base_url: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 90,
) -> tuple[int, Any]:
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"detail": raw}
        return exc.code, body


def _compose(
    project: str,
    *arguments: str,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
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


def _worker_replicas(project: str) -> int:
    result = _compose(project, "ps", "-q", "backtest-worker")
    if result.returncode != 0:
        raise RuntimeError(f"compose_ps_failed:{result.stderr.strip()}")
    return len([line for line in result.stdout.splitlines() if line.strip()])


def _scale_workers(project: str, replicas: int) -> None:
    result = _compose(
        project,
        "up",
        "-d",
        "--no-build",
        "--scale",
        f"backtest-worker={replicas}",
        "backtest-worker",
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"backtest_worker_scale_failed:{result.stderr.strip()}")


def _run_payload(
    *,
    project_id: str,
    symbol: str,
    start: str,
    end: str,
    source: str,
    benchmark: str,
    name: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "projectId": project_id,
        "symbol": symbol,
        "assetClass": "equity",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "dataType": "trade",
        "start": start,
        "end": end,
        "cash": 300000,
        "parameters": {
            "source": source,
            "benchmarkSymbol": benchmark,
        },
    }


def _create_run(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    status, body = _api(base_url, "POST", "/api/backtests", payload)
    if status >= 400 or not isinstance(body, dict) or not body.get("id"):
        raise RuntimeError(f"backtest_create_failed:{status}:{body}")
    return body


def _create_runs_parallel(
    base_url: str,
    payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    with ThreadPoolExecutor(
        max_workers=len(payloads),
        thread_name_prefix="p1-create",
    ) as executor:
        futures = [
            executor.submit(_create_run, base_url, payload)
            for payload in payloads
        ]
        return [future.result() for future in futures]


def _run_status(base_url: str, run_id: str) -> dict[str, Any]:
    status, body = _api(base_url, "GET", f"/api/backtests/{run_id}/status")
    if status >= 400 or not isinstance(body, dict):
        raise RuntimeError(f"backtest_status_failed:{run_id}:{status}:{body}")
    return body


def _wait_runs(
    base_url: str,
    run_ids: list[str],
    *,
    timeout_seconds: int,
    poll_seconds: float,
    stop_when: Any | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout_seconds
    timeline: list[dict[str, Any]] = []
    latest: dict[str, dict[str, Any]] = {}
    while time.monotonic() < deadline:
        latest = {run_id: _run_status(base_url, run_id) for run_id in run_ids}
        counts: dict[str, int] = {}
        for item in latest.values():
            state = str(item.get("status") or "")
            counts[state] = counts.get(state, 0) + 1
        sample = {
            "at": datetime.now(timezone.utc).isoformat(),
            "counts": counts,
            "states": {
                run_id: str(item.get("status") or "")
                for run_id, item in latest.items()
            },
        }
        if not timeline or timeline[-1]["states"] != sample["states"]:
            timeline.append(sample)
        if stop_when and stop_when(latest):
            return latest, timeline
        if not stop_when and all(
            str(item.get("status") or "") in TERMINAL for item in latest.values()
        ):
            return latest, timeline
        time.sleep(max(0.1, poll_seconds))
    raise TimeoutError(f"backtest_wait_timeout:{latest}")


def _cancel(base_url: str, run_id: str) -> dict[str, Any]:
    status, body = _api(base_url, "POST", f"/api/backtests/{run_id}/cancel", {})
    if status >= 400:
        raise RuntimeError(f"backtest_cancel_failed:{run_id}:{status}:{body}")
    return body


def _max_count(timeline: list[dict[str, Any]], status: str) -> int:
    return max(
        (int(item.get("counts", {}).get(status, 0)) for item in timeline),
        default=0,
    )


def _run_service_fault_matrix(
    *,
    project: str,
    api_url: str,
    timeout: int,
    evidence_path: Path,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_service_restart_fault_acceptance.py"),
        "--project",
        project,
        "--api-url",
        api_url,
        "--services",
        "worker,rabbitmq,postgres",
        "--timeout",
        str(timeout),
        "--confirm",
        "RESTART_LOCAL_SERVICES",
        "--output",
        str(evidence_path),
    ]
    process = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=max(600, timeout * 4),
        cwd=ROOT / "web" / "backend",
    )
    if evidence_path.is_file():
        result = json.loads(evidence_path.read_text(encoding="utf-8"))
    else:
        result = {"status": "failed", "stderr": process.stderr.strip()}
    result["exitCode"] = process.returncode
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--symbol", default="600519")
    parser.add_argument("--start", default="2024-01-02")
    parser.add_argument("--end", default="2024-03-29")
    parser.add_argument("--source", default="tushare")
    parser.add_argument("--benchmark", default="000300")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--compose-project", default="lean-platform")
    parser.add_argument("--jobs", type=int, default=5)
    parser.add_argument("--worker-replicas", type=int, default=1)
    parser.add_argument(
        "--execution-limit",
        type=int,
        default=2,
        help="Bounded LEAN execution slots used while five jobs are submitted concurrently.",
    )
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=float, default=0.25)
    parser.add_argument("--evidence-out", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != "RUN_P1_STABILITY_ACCEPTANCE":
        parser.error("--confirm must be RUN_P1_STABILITY_ACCEPTANCE")
    if args.jobs != 5:
        parser.error("--jobs must be exactly 5 for this acceptance")
    if args.execution_limit < 2 or args.execution_limit > args.jobs:
        parser.error("--execution-limit must be between 2 and --jobs")

    evidence_path = Path(args.evidence_out).expanduser().resolve()
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    fault_path = evidence_path.with_name(f"{evidence_path.stem}-service-faults.json")
    original_replicas = _worker_replicas(args.compose_project)
    settings_status, original_settings = _api(args.api_url, "GET", "/api/settings")
    if settings_status >= 400:
        raise RuntimeError(f"settings_unavailable:{settings_status}:{original_settings}")
    original_limit = int(original_settings.get("maxConcurrentJobs") or 1)
    result: dict[str, Any] = {
        "schemaVersion": 1,
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "projectId": args.project_id,
        "fiveJobConcurrency": {},
        "phaseCancellation": {},
        "serviceFaults": {},
        "environment": {
            "composeProject": args.compose_project,
            "originalBacktestWorkerReplicas": original_replicas,
            "acceptanceBacktestWorkerReplicas": args.worker_replicas,
            "originalMaxConcurrentJobs": original_limit,
            "acceptanceMaxConcurrentJobs": args.execution_limit,
        },
    }
    try:
        if original_replicas != args.worker_replicas:
            _scale_workers(args.compose_project, args.worker_replicas)
        status, _ = _api(
            args.api_url,
            "PUT",
            "/api/settings",
            {"maxConcurrentJobs": args.execution_limit},
        )
        if status >= 400:
            raise RuntimeError(f"settings_update_failed:{status}")

        base_end = date.fromisoformat(args.end)
        concurrency_runs = _create_runs_parallel(
            args.api_url,
            [
                _run_payload(
                    project_id=args.project_id,
                    symbol=args.symbol,
                    start=args.start,
                    end=(base_end - timedelta(days=index)).isoformat(),
                    source=args.source,
                    benchmark=args.benchmark,
                    name=f"P1 five-job concurrency {index + 1}",
                )
                for index in range(args.jobs)
            ],
        )
        concurrency_ids = [str(item["id"]) for item in concurrency_runs]
        final, timeline = _wait_runs(
            args.api_url,
            concurrency_ids,
            timeout_seconds=args.timeout,
            poll_seconds=args.poll_seconds,
        )
        max_running = _max_count(timeline, "running")
        max_queued = _max_count(timeline, "queued")
        five_passed = bool(
            max_running == args.execution_limit
            and max_queued >= args.jobs - args.execution_limit
            and all(str(item.get("status") or "") == "success" for item in final.values())
        )
        result["fiveJobConcurrency"] = {
            "runIds": concurrency_ids,
            "timeline": timeline,
            "maxRunning": max_running,
            "maxQueued": max_queued,
            "executionLimit": args.execution_limit,
            "backpressureObserved": max_queued >= args.jobs - args.execution_limit,
            "terminalStatuses": {
                run_id: str(item.get("status") or "") for run_id, item in final.items()
            },
            "passed": five_passed,
        }

        status, _ = _api(
            args.api_url,
            "PUT",
            "/api/settings",
            {"maxConcurrentJobs": 1},
        )
        if status >= 400:
            raise RuntimeError(f"settings_update_failed:{status}")
        queued_candidates = _create_runs_parallel(
            args.api_url,
            [
                _run_payload(
                    project_id=args.project_id,
                    symbol=args.symbol,
                    start=args.start,
                    end=(base_end - timedelta(days=10 + index)).isoformat(),
                    source=args.source,
                    benchmark=args.benchmark,
                    name=f"P1 queued cancellation {index + 1}",
                )
                for index in range(2)
            ],
        )
        queued_ids = [str(item["id"]) for item in queued_candidates]
        queued_state, queued_timeline = _wait_runs(
            args.api_url,
            queued_ids,
            timeout_seconds=args.timeout,
            poll_seconds=args.poll_seconds,
            stop_when=lambda states: (
                sum(str(item.get("status") or "") == "running" for item in states.values()) == 1
                and sum(str(item.get("status") or "") == "queued" for item in states.values()) == 1
            ),
        )
        queued_id = next(
            run_id
            for run_id, item in queued_state.items()
            if str(item.get("status") or "") == "queued"
        )
        blocker_id = next(run_id for run_id in queued_ids if run_id != queued_id)
        _cancel(args.api_url, queued_id)
        queued_final, queued_after = _wait_runs(
            args.api_url,
            [queued_id, blocker_id],
            timeout_seconds=args.timeout,
            poll_seconds=args.poll_seconds,
        )

        running_run = _create_run(
            args.api_url,
            _run_payload(
                project_id=args.project_id,
                symbol=args.symbol,
                start="2023-01-03",
                end="2024-12-31",
                source=args.source,
                benchmark=args.benchmark,
                name="P1 running cancellation",
            ),
        )
        running_id = str(running_run["id"])
        _, running_timeline = _wait_runs(
            args.api_url,
            [running_id],
            timeout_seconds=args.timeout,
            poll_seconds=args.poll_seconds,
            stop_when=lambda states: str(states[running_id].get("status") or "")
            == "running",
        )
        _cancel(args.api_url, running_id)
        running_final, running_after = _wait_runs(
            args.api_url,
            [running_id],
            timeout_seconds=args.timeout,
            poll_seconds=args.poll_seconds,
        )
        cancellation_passed = bool(
            str(queued_final[queued_id].get("status") or "") == "cancelled"
            and str(queued_final[blocker_id].get("status") or "") == "success"
            and str(running_final[running_id].get("status") or "") == "cancelled"
        )
        result["phaseCancellation"] = {
            "queued": {
                "runId": queued_id,
                "status": queued_final[queued_id].get("status"),
                "timeline": [*queued_timeline, *queued_after],
            },
            "running": {
                "runId": running_id,
                "status": running_final[running_id].get("status"),
                "timeline": [*running_timeline, *running_after],
            },
            "successfulBlockerPreserved": (
                str(queued_final[blocker_id].get("status") or "") == "success"
            ),
            "passed": cancellation_passed,
        }
    finally:
        _api(
            args.api_url,
            "PUT",
            "/api/settings",
            {"maxConcurrentJobs": original_limit},
        )
        if _worker_replicas(args.compose_project) != max(1, original_replicas):
            _scale_workers(args.compose_project, max(1, original_replicas))

    result["serviceFaults"] = _run_service_fault_matrix(
        project=args.compose_project,
        api_url=args.api_url,
        timeout=min(args.timeout, 300),
        evidence_path=fault_path,
    )
    result["passed"] = bool(
        result.get("fiveJobConcurrency", {}).get("passed")
        and result.get("phaseCancellation", {}).get("passed")
        and result.get("serviceFaults", {}).get("status") == "passed"
    )
    result["status"] = "passed" if result["passed"] else "failed"
    result["finishedAt"] = datetime.now(timezone.utc).isoformat()
    evidence_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "passed": result["passed"],
                "evidence": str(evidence_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
