#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


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


def _api(base_url: str, path: str, *, timeout: int = 20) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json"}
    token = _api_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        method="GET",
        headers=headers,
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


def _required_fields(snapshot: dict[str, Any]) -> list[str]:
    fields: list[str] = ["memory", "cpu", "queue", "disk", "container"]
    missing = []
    for field in fields:
        if field not in snapshot:
            missing.append(field)
    container = snapshot.get("container")
    if isinstance(container, dict):
        if str(container.get("hostname") or "").strip() == "":
            missing.append("container.hostname")
        if str(container.get("role") or "").strip() == "":
            missing.append("container.role")
    else:
        missing.append("container.hostname")
        missing.append("container.role")
    memory = snapshot.get("memory")
    if isinstance(memory, dict):
        if memory.get("usedPercent") is None:
            missing.append("memory.usedPercent")
        if memory.get("headroomPercent") is None:
            missing.append("memory.headroomPercent")
    cpu = snapshot.get("cpu")
    if isinstance(cpu, dict) and cpu.get("usedPercent") is None:
        missing.append("cpu.usedPercent")
    queue = snapshot.get("queue")
    if isinstance(queue, dict) and queue.get("maxDepth") is None:
        missing.append("queue.maxDepth")
    disk = snapshot.get("disk")
    if isinstance(disk, dict) and disk.get("usedPercent") is None:
        missing.append("disk.usedPercent")
    return missing


def _extract_operational_summary(payload: Any) -> tuple[dict[str, Any], str]:
    if not isinstance(payload, dict):
        return {}, ""
    summary = payload
    snapshot = summary.get("snapshot")
    if isinstance(snapshot, dict):
        status = str(summary.get("status") or snapshot.get("status") or "").strip().lower()
        return snapshot, status
    status = str(summary.get("status") or "").strip().lower()
    return summary, status


def _resource_observation_ok(
    snapshot: dict[str, Any],
    *,
    snapshot_status: str | None = None,
    require_non_critical: bool = True,
) -> tuple[bool, list[str]]:
    status = str(snapshot_status or snapshot.get("status") or "").strip().lower()
    missing = _required_fields(snapshot)
    if missing:
        return False, [f"missing_field:{item}" for item in missing]
    violations: list[str] = []
    if require_non_critical:
        if status == "":
            violations.append("missing_field:status")
        elif status in {"warning", "degraded", "critical"}:
            violations.append(f"resource_status:{status}")
    memory = snapshot.get("memory") or {}
    cpu = snapshot.get("cpu") or {}
    queue = snapshot.get("queue") or {}
    disk = snapshot.get("disk") or {}
    used_memory = memory.get("usedPercent")
    headroom = memory.get("headroomPercent")
    used_cpu = cpu.get("usedPercent")
    queue_depth = queue.get("maxDepth")
    disk_used = disk.get("usedPercent")
    for label, value in (
        ("memory.usedPercent", used_memory),
        ("memory.headroomPercent", headroom),
        ("cpu.usedPercent", used_cpu),
        ("queue.maxDepth", queue_depth),
        ("disk.usedPercent", disk_used),
    ):
        if value is None:
            violations.append(f"missing_value:{label}")
            continue
        try:
            float(value)
        except (TypeError, ValueError):
            violations.append(f"invalid_value:{label}")
    if str(snapshot.get("memory", {}).get("source") or "") == "":
        violations.append("missing_field:memory.source")
    if str(snapshot.get("cpu", {}).get("cpuCount") or "") == "":
        violations.append("missing_field:cpu.cpuCount")
    return (len(violations) == 0), violations


def _collect_container_restarts(
    samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deltas: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for sample in samples:
        snapshot = sample.get("snapshot")
        if not isinstance(snapshot, dict):
            continue
        container = snapshot.get("container") or {}
        current = {
            "hostname": str(container.get("hostname") or "").strip(),
            "role": str(container.get("role") or "").strip(),
        }
        if previous and current != previous:
            deltas.append(
                {
                    "at": sample.get("at"),
                    "from": previous,
                    "to": current,
                }
            )
        previous = current
    return deltas


def run(
    *,
    api_url: str = "http://127.0.0.1:8000",
    window_hours: float = 24.0,
    poll_seconds: float = 20.0,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    if window_hours < 0:
        raise ValueError("window_hours_must_be_non_negative")
    start = datetime.now(timezone.utc)
    deadline = time.time() + max(0.0, float(window_hours)) * 3600

    samples: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    resource_violations: list[dict[str, Any]] = []

    while True:
        status, payload = _api(api_url, "/api/operational/resources", timeout=timeout_seconds)
        now_iso = datetime.now(timezone.utc).isoformat()
        snapshot, resource_status = _extract_operational_summary(payload)
        passed, violations = _resource_observation_ok(
            snapshot,
            snapshot_status=resource_status,
        )
        entry = {
            "at": now_iso,
            "status": "ready",
            "snapshot": snapshot,
            "httpStatus": status,
            "snapshotStatus": str(resource_status or snapshot.get("status") or "").strip().lower(),
            "observationPassed": bool(passed and status < 400),
            "violations": violations,
            "summarize": snapshot.get("snapshot") if isinstance(snapshot, dict) else None,
        }
        if status >= 400:
            entry["status"] = "failed_http"
            entry["violations"] = [*violations, f"api_http:{status}"]
            entry["observationPassed"] = False
            passed = False
        if not entry["observationPassed"]:
            entry["status"] = "failed"
        observations.append(entry)
        if isinstance(snapshot, dict):
            sample = {
                "at": now_iso,
                "snapshot": snapshot,
                "snapshotStatus": (
                    str(snapshot.get("status") or "").strip().lower()
                    or str(resource_status or "").strip().lower()
                ),
                "resourceStatus": "pass" if entry["observationPassed"] else "fail",
                "violations": violations,
            }
            samples.append(sample)
            for violation in violations:
                resource_violations.append(
                    {
                        "at": now_iso,
                        "snapshotStatus": sample["snapshotStatus"],
                        "violation": violation,
                    }
                )
        if time.time() >= deadline:
            break
        if window_hours <= 0:
            break
        time.sleep(max(1.0, float(poll_seconds)))

    if not observations:
        raise RuntimeError("operational_resources_unavailable")

    container_restart_deltas = _collect_container_restarts(samples)
    statuses = [str(sample.get("snapshotStatus") or "") for sample in samples]
    passed = bool(
        all(item.get("observationPassed") for item in observations)
        and "" not in statuses
    )
    return {
        "status": "CAPACITY_STABILITY_PASS" if passed else "CAPACITY_STABILITY_FAIL",
        "passed": passed,
        "testedAt": datetime.now(timezone.utc).isoformat(),
        "windowHours": float(window_hours),
        "pollSeconds": float(poll_seconds),
        "apiUrl": api_url,
        "startedAt": start.isoformat(),
        "sampleCount": len(observations),
        "resourceSnapshotCount": len(samples),
        "containerRestartDeltas": container_restart_deltas,
        "resourceViolations": resource_violations,
        "observations": observations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 24h operational resource observation.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--window-hours", type=float, default=24)
    parser.add_argument("--poll-seconds", type=float, default=20)
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / "web" / "runtime" / "audit" / "capacity-stability-acceptance.json",
    )
    args = parser.parse_args()

    exit_code = 0
    try:
        evidence = run(
            api_url=args.api_url,
            window_hours=args.window_hours,
            poll_seconds=args.poll_seconds,
        )
        if not evidence.get("passed"):
            exit_code = 2
    except Exception as exc:
        evidence = {
            "status": "CAPACITY_STABILITY_FAIL",
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
