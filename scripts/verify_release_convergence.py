#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
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
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise RuntimeError(result.stderr.strip() or "unable to resolve git HEAD")
    return result.stdout.strip()


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


def _run(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _service_environment(service: str) -> dict[str, str]:
    located = _run("docker", "compose", "ps", "-q", service)
    container_id = located.stdout.strip()
    if located.returncode or not container_id:
        return {}
    inspected = _run(
        "docker", "inspect", "--format", "{{json .Config.Env}}", container_id
    )
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
        value.get("LEAN_RELEASE_ID")
        for value in environments.values()
        if value.get("LEAN_RELEASE_ID")
    }
    release_shas = {
        value.get("LEAN_RELEASE_SHA")
        for value in environments.values()
        if value.get("LEAN_RELEASE_SHA")
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
        "singleReleaseId": len(release_ids) == 1
        and release.get("releaseId") in release_ids,
        "singleGitSha": len(release_shas) == 1
        and release.get("gitSha") in release_shas,
        "workersReachable": ping.returncode == 0 and "pong" in ping.stdout.lower(),
    }
    return {
        "schemaVersion": 2,
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


def _ensure_compose_secret(path: Path) -> bool:
    if path.is_file():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secrets.token_urlsafe(48) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return True


def _managed_environment(data_dir: Path | None) -> tuple[dict[str, str], str]:
    sha = _git_sha()
    resolved_data = (
        data_dir.expanduser().resolve()
        if data_dir is not None
        else (ROOT / "web" / "runtime" / "convergence-data").resolve()
    )
    resolved_data.mkdir(parents=True, exist_ok=True)
    parquet_dir = resolved_data / "output" / "parquet"
    parquet_dir.mkdir(parents=True, exist_ok=True)
    project = f"lean-convergence-{sha[:8]}"
    env = {
        "COMPOSE_PROJECT_NAME": project,
        "LEAN_RELEASE_SHA": sha,
        "LEAN_RELEASE_ID": f"convergence-{sha[:12]}",
        "LEAN_DEPLOYMENT_PROFILE": "full",
        "LEAN_POSTGRES_ADMIN_PASSWORD": "convergence-admin-only",
        "LEAN_POSTGRES_APP_PASSWORD": "convergence-app-only",
        "LEAN_POSTGRES_CELERY_PASSWORD": "convergence-celery-only",
        "LEAN_POSTGRES_MLFLOW_PASSWORD": "convergence-mlflow-only",
        "LEAN_RABBITMQ_PASSWORD": "convergence-rabbit-only",
        "LEAN_API_AUTH_REQUIRED": "0",
        "LEAN_DATA_AUTO_UPDATE": "0",
        "LEAN_SCHEDULED_AUTOMATION_ENABLED": "0",
        "CLICKHOUSE_ENABLED": "0",
        "LEAN_HOST_DATA_DIR": str(resolved_data),
        "LEAN_HOST_PARQUET_DIR": str(parquet_dir),
        "LEAN_API_PORT": "18081",
        "LEAN_POSTGRES_PORT": "15433",
        "LEAN_RABBITMQ_PORT": "15675",
        "LEAN_RABBITMQ_MANAGEMENT_PORT": "15676",
        "LEAN_MLFLOW_PORT": "15001",
        "LEAN_PROMETHEUS_PORT": "19091",
        "LEAN_GRAFANA_PORT": "13001",
    }
    return env, "http://127.0.0.1:18081"


def _compose_failure_diagnostics() -> dict[str, Any]:
    ps = _run("docker", "compose", "--profile", "app", "ps", "-a")
    logs = _run(
        "docker",
        "compose",
        "--profile",
        "app",
        "logs",
        "--no-color",
        "--tail",
        "300",
        "migration",
        "postgres-init",
        "postgres",
        timeout=120,
    )
    return {
        "composePs": ((ps.stdout or "") + ("\n" + ps.stderr if ps.stderr else "")).strip()[-12000:],
        "migrationLogs": ((logs.stdout or "") + ("\n" + logs.stderr if logs.stderr else "")).strip()[-24000:],
    }


def verify_managed_stack(data_dir: Path | None) -> dict[str, Any]:
    managed_env, base_url = _managed_environment(data_dir)
    previous = {key: os.environ.get(key) for key in managed_env}
    created_secrets: list[Path] = []
    secrets_root = ROOT / "web" / "runtime" / "secrets"
    for name in ("api_token", "runner_token"):
        path = secrets_root / name
        if _ensure_compose_secret(path):
            created_secrets.append(path)
    os.environ.update(managed_env)

    start = _run(
        "docker",
        "compose",
        "--profile",
        "app",
        "up",
        "-d",
        "--build",
        "--wait",
        timeout=3600,
    )
    try:
        if start.returncode:
            diagnostics = _compose_failure_diagnostics()
            return {
                "schemaVersion": 2,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "managedStack": True,
                "baseUrl": base_url,
                "composeProject": managed_env["COMPOSE_PROJECT_NAME"],
                "managedDataDir": managed_env["LEAN_HOST_DATA_DIR"],
                "passed": False,
                "failure": {
                    "type": "ComposeStartFailed",
                    "detail": (start.stderr or start.stdout).strip()[-12000:],
                    "exitCode": start.returncode,
                    **diagnostics,
                },
            }
        result = verify(base_url)
        result["managedStack"] = True
        result["baseUrl"] = base_url
        result["composeProject"] = managed_env["COMPOSE_PROJECT_NAME"]
        result["managedDataDir"] = managed_env["LEAN_HOST_DATA_DIR"]
        return result
    finally:
        down = _run(
            "docker",
            "compose",
            "--profile",
            "app",
            "down",
            "--remove-orphans",
            timeout=600,
        )
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for path in created_secrets:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        if start.returncode == 0 and down.returncode:
            print(
                f"warning: managed convergence stack cleanup failed: {down.stderr.strip()}",
                file=sys.stderr,
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify one release identity across the actual LEAN app stack."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--manage-stack",
        action="store_true",
        help="Start the complete Compose app profile, verify it, and tear it down.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        help="Data directory mounted into the managed stack; omit for a scratch convergence lake.",
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / "web" / "runtime" / "audit" / "release-convergence.json",
    )
    args = parser.parse_args()
    try:
        if args.manage_stack:
            result = verify_managed_stack(args.data_dir)
        else:
            result = verify(args.base_url)
            result["managedStack"] = False
            result["baseUrl"] = args.base_url
    except Exception as exc:
        result = {
            "schemaVersion": 2,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "managedStack": bool(args.manage_stack),
            "passed": False,
            "failure": {"type": type(exc).__name__, "detail": str(exc)},
        }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
