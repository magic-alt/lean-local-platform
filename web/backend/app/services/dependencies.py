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
    LEAN_EXECUTION_BACKEND,
    PAPER_ORDER_PIPELINE_V2_ENABLED,
    PROMETHEUS_URL,
    REDIS_URL,
    RUNS_DIR,
    SCHEDULED_AUTOMATION_ENABLED,
)
from ..db import database_backend, database_descriptor, db
from ..observability.metrics import set_dependency_status
from . import market_data
from .alerts import external_alert_channel_configured, notification_delivery_health
from .source_gate import source_certification
from ..runners.native_runner import NativeLeanBackend


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
    return {"service": "redis", "ok": ok, "detail": "configured Redis endpoint"}


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
    delivery = notification_delivery_health()
    configuration_ok = bool(configured or not SCHEDULED_AUTOMATION_ENABLED)
    ok = bool(configuration_ok and delivery.get("ok"))
    return {
        "service": "external_alert_channel",
        "ok": ok,
        "detail": {
            "configured": configured,
            "scheduledAutomationEnabled": SCHEDULED_AUTOMATION_ENABLED,
            "delivery": delivery,
            "severity": None if ok else "critical",
            "reason": (
                None
                if ok
                else "scheduled_automation_requires_external_alert_channel"
                if not configuration_ok
                else str(delivery.get("reason") or "notification_delivery_failed")
            ),
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
    if LEAN_EXECUTION_BACKEND == "native":
        status = NativeLeanBackend(3600).health()
        return {
            "service": "lean_runner",
            "ok": status.ready,
            "detail": {
                "backend": "native",
                "sandbox": status.sandbox,
                "runtimeIdentity": (
                    status.runtime_identity.as_dict() if status.runtime_identity is not None else None
                ),
                "status": status.detail,
            },
        }
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
    worker_detail = worker.get("detail")
    workers = worker_detail.get("workers") or [] if isinstance(worker_detail, dict) else []
    detail = {
        "mode": "delegated_to_backtest_worker",
        "localDockerSocket": False,
        "workers": workers,
        **({"workerError": worker_detail} if isinstance(worker_detail, str) and worker_detail else {}),
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


def _database_table_counts(connection, tables: list[str]) -> tuple[dict[str, int], str]:
    """Return cheap readiness counts without scanning large MySQL tables."""
    if not tables:
        return {}, "none"
    if database_backend() != "mysql":
        return {
            table: int(connection.execute(f"select count(*) as count from {table}").fetchone()["count"])
            for table in tables
        }, "exact"
    placeholders = ",".join("?" for _ in tables)
    rows = connection.execute(
        f"""
        select table_name as readiness_table_name,
               coalesce(table_rows,0) as readiness_table_rows
        from information_schema.tables
        where table_schema=database() and table_name in ({placeholders})
        """,
        tables,
    ).fetchall()
    estimates = {
        str(row["readiness_table_name"]): int(row["readiness_table_rows"] or 0)
        for row in rows
    }
    return {table: estimates.get(table, 0) for table in tables}, "information_schema_estimate"


def check_database() -> dict[str, Any]:
    expected_tables = ["instruments", "universe_membership", "index_membership_pit", "parquet_datasets", "stored_objects"]
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
            counts, count_source = _database_table_counts(
                connection,
                [table for table in expected_tables if table in tables],
            )
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
            and counts.get("parquet_datasets", 0) >= 0
            and orphan_archives == 0
        )
        ok = bool(core_ok)
        detail = {
            **descriptor,
            "missingTables": missing,
            "counts": counts,
            "countSource": count_source,
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


def _dependency_blockers(
    checks: list[dict[str, Any]],
    critical_services: frozenset[str],
) -> list[str]:
    return [
        str(item["service"])
        for item in checks
        if item["service"] in critical_services and not item["ok"]
    ]


def dependency_health() -> dict[str, Any]:
    checks = [
        _timed("database", check_database),
        _timed("redis", check_redis),
        _timed("clickhouse", market_data.ping),
    ]
    if BACKTEST_EXECUTION_DELEGATED and LEAN_EXECUTION_BACKEND == "docker":
        worker = _timed("backtest_worker", check_backtest_worker)
        checks.extend([worker, *_delegated_runner_checks(worker)])
    elif LEAN_EXECUTION_BACKEND == "docker":
        checks.extend(
            [
                _timed("docker", check_docker),
                _timed("lean_image", check_lean_image),
                _timed("lean_runner", check_lean_runner),
            ]
        )
    else:
        checks.extend(
            [
                _timed("backtest_worker", check_backtest_worker),
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
    execution_blockers = _dependency_blockers(checks, EXECUTION_CRITICAL_SERVICES)
    operational_blockers = _dependency_blockers(checks, OPERATIONAL_CRITICAL_SERVICES)
    return {
        "status": "ok" if not operational_blockers else "degraded",
        "executionStatus": "ok" if not execution_blockers else "degraded",
        "executionBlockers": execution_blockers,
        "operationalBlockers": operational_blockers,
        "dependencies": checks,
        "urls": {
            "prometheus": PROMETHEUS_URL,
            "grafana": GRAFANA_URL,
        },
    }
