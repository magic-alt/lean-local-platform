#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402


SERVICES = (
    "api",
    "worker",
    "data-worker",
    "data-lineage-worker",
    "data-demand-worker",
    "backtest-worker",
    "ml-worker",
    "lean-runner",
    "beat",
)
REQUIRED_PATHS = {
    "/api/data/releases",
    "/api/data/capabilities",
    "/api/data/qa/{batch_id}",
    "/api/backtests/{run_id}/reproducibility-certificate",
    "/api/backtests/reproducibility/golden-pairs",
    "/api/experiment-batches/{batch_id}/walk-forward-certificate",
}


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _token() -> str:
    configured = os.environ.get("LEAN_API_TOKEN", "").strip()
    if configured:
        return configured
    path = ROOT / "web" / "runtime" / "secrets" / "api_token"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def _get_json(base_url: str, path: str, *, authenticated: bool = False) -> dict[str, Any]:
    headers = {}
    if authenticated and _token():
        headers["Authorization"] = f"Bearer {_token()}"
    request = urllib.request.Request(base_url.rstrip("/") + path, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )


def _service_environment(service: str) -> dict[str, str]:
    located = _run("docker", "compose", "ps", "-q", service)
    container_id = located.stdout.strip()
    if located.returncode or not container_id:
        return {}
    inspected = _run("docker", "inspect", "--format", "{{json .Config.Env}}", container_id)
    if inspected.returncode:
        return {}
    values = json.loads(inspected.stdout.strip() or "[]")
    return dict(item.split("=", 1) for item in values if "=" in item)


def verify(base_url: str) -> dict[str, Any]:
    source_openapi = app.openapi()
    actual_openapi = _get_json(base_url, "/openapi.json", authenticated=True)
    health = _get_json(base_url, "/api/health")
    source_paths = set(source_openapi.get("paths") or {})
    actual_paths = set(actual_openapi.get("paths") or {})
    environments = {service: _service_environment(service) for service in SERVICES}
    release_ids = {
        value.get("LEAN_RELEASE_ID") for value in environments.values() if value.get("LEAN_RELEASE_ID")
    }
    release_shas = {
        value.get("LEAN_RELEASE_SHA") for value in environments.values() if value.get("LEAN_RELEASE_SHA")
    }
    missing_services = [service for service, value in environments.items() if not value]
    ping = _run(
        "docker",
        "compose",
        "exec",
        "-T",
        "worker",
        "celery",
        "-A",
        "app.tasks.celery_app",
        "inspect",
        "ping",
        "--json",
    )
    release = health.get("release") or {}
    checks = {
        "sourceAndActualPathsMatch": source_paths == actual_paths,
        "requiredPathsPresent": REQUIRED_PATHS <= actual_paths,
        "openApiHashMatches": release.get("openApiSha256") == _digest(actual_openapi),
        "schemaAligned": bool((release.get("schema") or {}).get("aligned")),
        "allServicesPresent": not missing_services,
        "singleReleaseId": len(release_ids) == 1 and release.get("releaseId") in release_ids,
        "singleGitSha": len(release_shas) == 1 and release.get("gitSha") in release_shas,
        "workersReachable": ping.returncode == 0 and "pong" in ping.stdout.lower(),
    }
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "passed": all(checks.values()),
        "checks": checks,
        "sourceOpenApiPathCount": len(source_paths),
        "actualOpenApiPathCount": len(actual_paths),
        "missingActualPaths": sorted(source_paths - actual_paths),
        "unexpectedActualPaths": sorted(actual_paths - source_paths),
        "missingRequiredPaths": sorted(REQUIRED_PATHS - actual_paths),
        "health": health,
        "serviceReleaseIdentity": {
            service: {
                "releaseId": value.get("LEAN_RELEASE_ID"),
                "gitSha": value.get("LEAN_RELEASE_SHA"),
                "role": value.get("LEAN_RELEASE_ROLE"),
            }
            for service, value in environments.items()
        },
        "missingServices": missing_services,
        "workerPing": {
            "exitCode": ping.returncode,
            "stdout": ping.stdout.strip(),
            "stderr": ping.stderr.strip(),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify one release identity across the actual LEAN app stack.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / "web" / "runtime" / "audit" / "release-convergence.json",
    )
    args = parser.parse_args()
    try:
        result = verify(args.base_url)
    except Exception as exc:
        result = {
            "schemaVersion": 1,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "passed": False,
            "failure": {"type": type(exc).__name__, "detail": str(exc)},
        }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
