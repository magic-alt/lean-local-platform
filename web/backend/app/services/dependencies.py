from __future__ import annotations

import subprocess
import time
import uuid
from typing import Any, Callable

from redis import Redis

from ..core.config import (
    BACKTEST_EXECUTION_DELEGATED,
    DATA_DIR,
    DEFAULT_DOCKER_IMAGE,
    GRAFANA_URL,
    PAPER_ORDER_PIPELINE_V2_ENABLED,
    PROMETHEUS_URL,
    REDIS_URL,
    RUNS_DIR,
    SCHEDULED_AUTOMATION_ENABLED,
)
from ..db import database_backend, database_descriptor, db
from ..observability.metrics import set_dependency_status
from . import market_data
from .alerts import external_alert_channel_configured
from .source_gate import source_certification


EXECUTION_CRITICAL_SERVICES = frozenset(
    {
        "database",
        "redis",
        "docker",
        "backtest_worker",
        "lean_data_dir",
        "results_dir_writable",
        "lean_runner",
        "paper_order_pipeline_v2",
        "source_certification",
    }
)
OPERATIONAL_CRITICAL_SERVICES = EXECUTION_CRITICAL_SERVICES | {
    "external_alert_channel",
}


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


def check_lean_image() -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "image", "inspect", DEFAULT_DOCKER_IMAGE, "--format", "{{.Id}}"],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )
    ok = result.returncode == 0
    detail = {
        "image": DEFAULT_DOCKER_IMAGE,
        "id": result.stdout.strip() if ok else None,
        "error": None if ok else (result.stderr.strip() or "docker image inspect failed"),
    }
    return {"service": "lean_image", "ok": ok, "detail": detail}


def check_results_dir() -> dict[str, Any]:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    probe = RUNS_DIR / f".healthcheck-{uuid.uuid4().hex}"
    try:
        probe.write_text("ok", encoding="utf-8")
        ok = probe.read_text(encoding="utf-8") == "ok"
    finally:
        try:
            probe.unlink(missing_ok=True)
        except Exception:
            pass
    return {"service": "results_dir_writable", "ok": ok, "detail": str(RUNS_DIR)}


def check_alert_channel() -> dict[str, Any]:
    configured = external_alert_channel_configured()
    ok = bool(configured or not SCHEDULED_AUTOMATION_ENABLED)
    return {
        "service": "external_alert_channel",
        "ok": ok,
        "detail": {
            "configured": configured,
            "scheduledAutomationEnabled": SCHEDULED_AUTOMATION_ENABLED,
            "severity": None if ok else "critical",
            "reason": None if ok else "scheduled_automation_requires_external_alert_channel",
        },
    }


def check_paper_order_pipeline() -> dict[str, Any]:
    return {
        "service": "paper_order_pipeline_v2",
        "ok": bool(PAPER_ORDER_PIPELINE_V2_ENABLED),
        "detail": {
            "enabled": bool(PAPER_ORDER_PIPELINE_V2_ENABLED),
            "mode": "immutable_v2" if PAPER_ORDER_PIPELINE_V2_ENABLED else "legacy_degraded",
        },
    }


def check_source_certifications() -> dict[str, Any]:
    scopes = [
        source_certification("tushare", asset_class="equity", market="china", venue="china"),
        source_certification("tushare", asset_class="index", market="china", venue="china"),
    ]
    ready = [
        bool(
            item.get("isProduction")
            and item.get("isCertified")
            and item.get("environment") == "production"
            and str(item.get("qaStatus") or "").lower() == "ok"
        )
        for item in scopes
    ]
    return {
        "service": "source_certification",
        "ok": all(ready),
        "detail": {
            "executable": all(ready),
            "scopes": [
                {
                    "assetClass": scope,
                    "datasetId": item.get("datasetId"),
                    "datasetVersion": item.get("datasetVersion"),
                    "certifiedAt": item.get("certifiedAt"),
                    "certificationError": item.get("certificationError"),
                }
                for item, scope in zip(scopes, ("equity", "index"), strict=True)
            ],
        },
    }


def check_lean_runner() -> dict[str, Any]:
    docker = check_docker()
    image = check_lean_image() if docker.get("ok") else {"ok": False, "detail": "docker unavailable"}
    data_dir = check_data_dir()
    results_dir = check_results_dir()
    ok = bool(docker.get("ok") and image.get("ok") and data_dir.get("ok") and results_dir.get("ok"))
    return {
        "service": "lean_runner",
        "ok": ok,
        "detail": {
            "docker": docker.get("detail"),
            "image": image.get("detail"),
            "dataDir": data_dir.get("detail"),
            "resultsDir": results_dir.get("detail"),
        },
    }


def check_backtest_worker() -> dict[str, Any]:
    from ..tasks.celery_app import celery_app

    replies = celery_app.control.inspect(timeout=1.5).ping() or {}
    workers = sorted(str(name) for name in replies if str(name).startswith("backtest@"))
    return {
        "service": "backtest_worker",
        "ok": bool(workers),
        "detail": {"mode": "delegated", "workers": workers},
    }


def _delegated_runner_checks(worker: dict[str, Any]) -> list[dict[str, Any]]:
    available = bool(worker.get("ok"))
    detail = {
        "mode": "delegated_to_backtest_worker",
        "localDockerSocket": False,
        "workers": (worker.get("detail") or {}).get("workers") or [],
    }
    return [
        {"service": "docker", "ok": available, "detail": detail},
        {
            "service": "lean_image",
            "ok": available,
            "detail": {**detail, "image": DEFAULT_DOCKER_IMAGE},
        },
        {"service": "lean_runner", "ok": available, "detail": detail},
    ]


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
            orphan_archives = 0
            quarantined_archive_issues = 0
            if "stored_objects" in tables and "provider_raw_archives" in tables:
                orphan_archives = int(
                    connection.execute(
                        """
                        select count(*) as count
                        from provider_raw_archives a
                        left join stored_objects o on o.id = a.object_id
                        where o.id is null
                        """
                    ).fetchone()["count"]
                    or 0
                )
            if "provider_raw_archive_issues" in tables:
                quarantined_archive_issues = int(
                    connection.execute(
                        "select count(*) as count from provider_raw_archive_issues"
                    ).fetchone()["count"]
                    or 0
                )
        core_ok = (
            not missing
            and counts.get("instruments", 0) >= 0
            and counts.get("market_daily_bars", 0) >= 0
            and orphan_archives == 0
        )
        ok = bool(core_ok)
        detail = {
            **descriptor,
            "missingTables": missing,
            "counts": counts,
            "csi300MembershipRows": csi300_count,
            "orphanProviderRawArchives": orphan_archives,
            "quarantinedProviderRawArchiveIssues": quarantined_archive_issues,
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


def _dependency_status(
    checks: list[dict[str, Any]],
    critical_services: frozenset[str],
) -> str:
    critical = [item for item in checks if item["service"] in critical_services]
    return "ok" if all(item["ok"] for item in critical) else "degraded"


def dependency_health() -> dict[str, Any]:
    checks = [
        _timed("database", check_database),
        _timed("redis", check_redis),
        _timed("clickhouse", market_data.ping),
    ]
    if BACKTEST_EXECUTION_DELEGATED:
        worker = _timed("backtest_worker", check_backtest_worker)
        checks.extend([worker, *_delegated_runner_checks(worker)])
    else:
        checks.extend(
            [
                _timed("docker", check_docker),
                _timed("lean_image", check_lean_image),
                _timed("lean_runner", check_lean_runner),
            ]
        )
    checks.extend(
        [
            _timed("lean_data_dir", check_data_dir),
            _timed("results_dir_writable", check_results_dir),
            _timed("external_alert_channel", check_alert_channel),
            _timed("paper_order_pipeline_v2", check_paper_order_pipeline),
            _timed("source_certification", check_source_certifications),
        ]
    )
    return {
        "status": _dependency_status(checks, OPERATIONAL_CRITICAL_SERVICES),
        "executionStatus": _dependency_status(checks, EXECUTION_CRITICAL_SERVICES),
        "dependencies": checks,
        "urls": {
            "prometheus": PROMETHEUS_URL,
            "grafana": GRAFANA_URL,
        },
    }
