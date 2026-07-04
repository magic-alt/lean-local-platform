from __future__ import annotations

import subprocess
import time
from typing import Any, Callable

from redis import Redis

from ..core.config import DATA_DIR, GRAFANA_URL, PROMETHEUS_URL, REDIS_URL
from ..observability.metrics import set_dependency_status
from . import market_data


def _timed(service: str, check: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        result = check()
    except Exception as exc:
        result = {"service": service, "ok": False, "detail": str(exc)}
    result.setdefault("service", service)
    result["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
    set_dependency_status(service, bool(result.get("ok")))
    return result


def check_redis() -> dict[str, Any]:
    ok = bool(Redis.from_url(REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5).ping())
    return {"service": "redis", "ok": ok, "detail": REDIS_URL}


def check_docker() -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "info", "--format", "{{.ServerVersion}}"],
        capture_output=True,
        text=True,
        timeout=2,
        check=False,
    )
    ok = result.returncode == 0
    detail = result.stdout.strip() if ok else (result.stderr.strip() or "docker info failed")
    return {"service": "docker", "ok": ok, "detail": detail}


def check_data_dir() -> dict[str, Any]:
    ok = DATA_DIR.exists() and DATA_DIR.is_dir()
    return {"service": "lean_data_dir", "ok": ok, "detail": str(DATA_DIR)}


def dependency_health() -> dict[str, Any]:
    checks = [
        _timed("redis", check_redis),
        _timed("clickhouse", market_data.ping),
        _timed("docker", check_docker),
        _timed("lean_data_dir", check_data_dir),
    ]
    critical = [item for item in checks if item["service"] in {"redis", "docker", "lean_data_dir"}]
    status = "ok" if all(item["ok"] for item in critical) else "degraded"
    return {
        "status": status,
        "dependencies": checks,
        "urls": {
            "prometheus": PROMETHEUS_URL,
            "grafana": GRAFANA_URL,
        },
    }
