from __future__ import annotations

import subprocess
import time
from typing import Any, Callable

from redis import Redis

from ..core.config import DATA_DIR, GRAFANA_URL, PROMETHEUS_URL, REDIS_URL
from ..db import database_backend, database_descriptor, db
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


def _database_objects(connection) -> set[str]:
    if database_backend() == "mysql":
        rows = connection.execute(
            """
            select table_name as name
            from information_schema.tables
            where table_schema = database()
            """
        ).fetchall()
        return {row["name"] for row in rows}
    rows = connection.execute(
        """
        select name
        from sqlite_master
        where type = 'table'
        """
    ).fetchall()
    return {row["name"] for row in rows}


def check_database() -> dict[str, Any]:
    expected_tables = ["instruments", "market_daily_bars", "ashare_daily_bars", "universe_membership", "index_membership_pit", "stored_objects"]
    fallback = {
        "missingTables": expected_tables,
        "counts": {},
        "csi300MembershipRows": 0,
    }
    try:
        descriptor = database_descriptor()
    except Exception as exc:
        return {
            "service": "database",
            "ok": False,
            "detail": {
                **fallback,
                "engine": "unknown",
                "error": str(exc),
            },
        }

    try:
        with db() as connection:
            tables = _database_objects(connection)
            missing = [table for table in expected_tables if table not in tables]
            counts: dict[str, int] = {}
            for table in expected_tables:
                if table in tables:
                    counts[table] = int(connection.execute(f"select count(*) as count from {table}").fetchone()["count"])
            csi300_count = 0
            if "universe_membership" in tables:
                csi300_count = int(
                    connection.execute(
                        """
                        select count(*) as count
                        from universe_membership
                        where universe_code = 'CSI300'
                        """
                    ).fetchone()["count"]
                )
        core_ok = not missing and counts.get("instruments", 0) >= 0 and counts.get("market_daily_bars", 0) >= 0
        ok = bool(core_ok)
        detail = {
            **descriptor,
            "missingTables": missing,
            "counts": counts,
            "csi300MembershipRows": csi300_count,
        }
        return {"service": "database", "ok": ok, "detail": detail}
    except Exception as exc:
        return {
            "service": "database",
            "ok": False,
            "detail": {
                **fallback,
                **descriptor,
                "error": str(exc),
            },
        }


def dependency_health() -> dict[str, Any]:
    checks = [
        _timed("database", check_database),
        _timed("redis", check_redis),
        _timed("clickhouse", market_data.ping),
        _timed("docker", check_docker),
        _timed("lean_data_dir", check_data_dir),
    ]
    critical = [item for item in checks if item["service"] in {"database", "redis", "docker", "lean_data_dir"}]
    status = "ok" if all(item["ok"] for item in critical) else "degraded"
    return {
        "status": status,
        "dependencies": checks,
        "urls": {
            "prometheus": PROMETHEUS_URL,
            "grafana": GRAFANA_URL,
        },
    }
