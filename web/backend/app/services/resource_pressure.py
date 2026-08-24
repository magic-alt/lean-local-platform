from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
from typing import Any

from ..core.config import DATA_DIR, RUNS_DIR
from .alerts import emit_alert, resolve_open_alert


RESOURCE_KINDS = ("disk", "memory", "cpu", "queue")


def _env_float(name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return max(minimum, default)


def _read_int(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not value or value == "max":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _read_memory_stat(path: Path) -> dict[str, int]:
    try:
        return {
            parts[0]: int(parts[1])
            for line in path.read_text(encoding="utf-8").splitlines()
            if len(parts := line.split()) == 2
        }
    except (OSError, ValueError):
        return {}


def _process_rss_bytes() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _memory_metrics() -> dict[str, Any]:
    candidates = (
        (
            Path("/sys/fs/cgroup/memory.current"),
            Path("/sys/fs/cgroup/memory.max"),
            "cgroup_v2",
        ),
        (
            Path("/sys/fs/cgroup/memory/memory.usage_in_bytes"),
            Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
            "cgroup_v1",
        ),
    )
    current: int | None = None
    limit: int | None = None
    source = ""
    memory_stat: dict[str, int] = {}
    for current_path, limit_path, candidate_source in candidates:
        current = _read_int(current_path)
        limit = _read_int(limit_path)
        if (
            current is not None
            and limit is not None
            and 0 < limit < (1 << 60)
        ):
            source = candidate_source
            memory_stat = _read_memory_stat(current_path.parent / "memory.stat")
            break
    if current is None or limit is None or limit <= 0:
        try:
            values: dict[str, int] = {}
            for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
                name, raw = line.split(":", 1)
                values[name] = int(raw.strip().split()[0]) * 1024
            limit = values["MemTotal"]
            current = limit - values["MemAvailable"]
            source = "proc_meminfo"
        except (OSError, KeyError, ValueError):
            return {}
    headroom = max(0, limit - current)
    rss = memory_stat.get("anon") if source == "cgroup_v2" else memory_stat.get("rss")
    cache = memory_stat.get("file") if source == "cgroup_v2" else memory_stat.get("cache")
    return {
        "usedBytes": current,
        "limitBytes": limit,
        "usedPercent": round(current * 100 / limit, 2),
        "headroomBytes": headroom,
        "headroomPercent": round(headroom * 100 / limit, 2),
        "rssBytes": rss,
        "cacheBytes": cache,
        "processRssBytes": _process_rss_bytes(),
        "limitConfigured": source.startswith("cgroup"),
        "source": source,
    }


def _disk_metrics() -> dict[str, Any]:
    configured = [
        Path(item).expanduser()
        for item in os.environ.get("LEAN_RESOURCE_MONITOR_PATHS", "").split(":")
        if item.strip()
    ]
    paths = configured or [RUNS_DIR, DATA_DIR]
    items: list[dict[str, Any]] = []
    seen_devices: set[int] = set()
    for path in paths:
        target = path if path.exists() else path.parent
        try:
            stat = target.stat()
            if stat.st_dev in seen_devices:
                continue
            seen_devices.add(stat.st_dev)
            usage = shutil.disk_usage(target)
        except OSError:
            continue
        items.append(
            {
                "path": str(target),
                "usedBytes": usage.used,
                "totalBytes": usage.total,
                "usedPercent": round(usage.used * 100 / max(usage.total, 1), 2),
            }
        )
    return {
        "mounts": items,
        "usedPercent": max(
            (float(item["usedPercent"]) for item in items),
            default=0.0,
        ),
    }


def _cpu_metrics() -> dict[str, Any]:
    try:
        one, five, fifteen = os.getloadavg()
    except (AttributeError, OSError):
        return {}
    cpus = max(1, int(os.cpu_count() or 1))
    return {
        "load1": one,
        "load5": five,
        "load15": fifteen,
        "cpuCount": cpus,
        "usedPercent": round(one * 100 / cpus, 2),
    }


def _queue_metrics() -> dict[str, Any]:
    try:
        from .broker import queue_depths

        depths = queue_depths()
        return {
            "depths": depths,
            "maxDepth": max(depths.values(), default=0),
            "totalDepth": sum(depths.values()),
            "brokerReachable": True,
            "brokerEngine": "rabbitmq",
        }
    except Exception as exc:
        return {
            "depths": {},
            "maxDepth": None,
            "totalDepth": None,
            "brokerReachable": False,
            "brokerEngine": "rabbitmq",
            "error": exc.__class__.__name__,
        }


def collect_resource_snapshot() -> dict[str, Any]:
    return {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "container": {
            "role": str(os.environ.get("LEAN_RELEASE_ROLE", "unknown")),
            "hostname": str(os.environ.get("HOSTNAME", "unknown")),
        },
        "disk": _disk_metrics(),
        "memory": _memory_metrics(),
        "cpu": _cpu_metrics(),
        "queue": _queue_metrics(),
    }


def _thresholds(kind: str) -> tuple[float, float]:
    defaults = {
        "disk": (75.0, 85.0),
        "memory": (80.0, 90.0),
        "cpu": (85.0, 95.0),
        "queue": (20.0, 50.0),
    }
    warning_default, critical_default = defaults[kind]
    prefix = f"LEAN_RESOURCE_{kind.upper()}"
    warning = _env_float(f"{prefix}_WARNING", warning_default)
    critical = _env_float(f"{prefix}_CRITICAL", critical_default)
    return warning, max(warning, critical)


def _value(kind: str, metrics: dict[str, Any]) -> float | None:
    field = "maxDepth" if kind == "queue" else "usedPercent"
    raw = metrics.get(field)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def evaluate_resource_snapshot(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for kind in RESOURCE_KINDS:
        metrics = snapshot.get(kind) if isinstance(snapshot.get(kind), dict) else {}
        value = _value(kind, metrics)
        warning, critical = _thresholds(kind)
        severity: str | None = None
        if value is not None and value >= critical:
            severity = "critical"
        elif value is not None and value >= warning:
            severity = "warning"
        results.append(
            {
                "kind": kind,
                "value": value,
                "warning": warning,
                "critical": critical,
                "severity": severity,
                "metrics": metrics,
            }
        )
    return results


def summarize_resource_capacity(
    snapshot: dict[str, Any],
    evaluations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evaluated = evaluations or evaluate_resource_snapshot(snapshot)
    severities = {str(item["severity"]) for item in evaluated if item["severity"]}
    status = "critical" if "critical" in severities else "degraded" if severities else "ok"
    memory = snapshot.get("memory") if isinstance(snapshot.get("memory"), dict) else {}
    memory_warning, memory_critical = _thresholds("memory")
    return {
        "status": status,
        "snapshot": snapshot,
        "evaluations": evaluated,
        "capacitySlo": {
            "memoryWarningPercent": memory_warning,
            "memoryCriticalPercent": memory_critical,
            "memoryHeadroomPercent": memory.get("headroomPercent"),
            "memoryLimitConfigured": bool(memory.get("limitConfigured")),
        },
    }


def monitor_operational_resources(
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    captured = snapshot or collect_resource_snapshot()
    evaluations = evaluate_resource_snapshot(captured)
    changes: list[dict[str, Any]] = []
    for item in evaluations:
        kind = str(item["kind"])
        dedupe_key = f"resource_pressure:{kind}"
        if item["severity"]:
            alert = emit_alert(
                f"resource_{kind}_pressure",
                severity=str(item["severity"]),
                title=f"{kind.capitalize()} resource pressure",
                message=(
                    f"{kind} utilization {item['value']} reached "
                    f"{item['severity']} threshold"
                ),
                source="resource_monitor",
                related_id=kind,
                details={
                    "value": item["value"],
                    "warning": item["warning"],
                    "critical": item["critical"],
                    "metrics": item["metrics"],
                },
                dedupe_key=dedupe_key,
            )
            changes.append(
                {
                    "kind": kind,
                    "action": "alerted",
                    "alertId": alert.get("id"),
                    "severity": alert.get("severity"),
                }
            )
        else:
            resolved = resolve_open_alert(dedupe_key)
            if resolved:
                changes.append(
                    {
                        "kind": kind,
                        "action": "resolved",
                        "alertId": resolved.get("id"),
                    }
                )
    return {
        **summarize_resource_capacity(captured, evaluations),
        "changes": changes,
    }
