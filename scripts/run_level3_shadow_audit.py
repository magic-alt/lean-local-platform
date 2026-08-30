#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, init_db  # noqa: E402
from app.services import market_lake  # noqa: E402
from app.services.instrument_identity import identifier_coverage  # noqa: E402
from app.services.source_gate import PRIMARY_DATA_SOURCE, resolve_source_context  # noqa: E402


_PYTHON_IMPORT_CHECKS = ("psycopg", "fastapi")


def _pick_python() -> list[str]:
    candidates = [
        BACKEND / ".venv/bin/python3.14",
        BACKEND / ".venv/bin/python3",
        BACKEND / ".venv/bin/python",
        Path("/usr/local/bin/python3"),
        Path("/usr/bin/python3"),
        Path("/opt/homebrew/bin/python3"),
        Path(sys.executable),
    ]

    def _usable(candidate: Path) -> bool:
        if not candidate.exists():
            return False
        try:
            check = subprocess.run(
                [str(candidate), "-c", "import psycopg,fastapi; print('ok')"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            return check.returncode == 0
        except Exception:
            return False

    for candidate in candidates:
        if _usable(candidate):
            return [str(candidate)]

    # fallback to previous default for compatibility, caller will surface errors
    return [str(BACKEND / ".venv/bin/python")]


def _backend_python() -> list[str]:
    return _pick_python()


def _csv(value: str) -> list[str]:
    return [item.strip().zfill(6)[-6:] for item in value.split(",") if item.strip()]


_SENSITIVE_CONFIG_LINE = re.compile(
    r"(?im)^(\s*[A-Z0-9_]*(?:TOKEN|API_KEY|PASSWORD|DATABASE_URL|BROKER_URL)[A-Z0-9_]*:\s*).*$"
)


def _redact_text(value: str) -> str:
    return _SENSITIVE_CONFIG_LINE.sub(r"\1<redacted>", value)


def _run(command: list[str], timeout: int = 900) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout)
    payload: Any = None
    try:
        payload = json.loads(completed.stdout or "{}")
    except Exception:
        payload = None
    return {
        "command": command,
        "returnCode": completed.returncode,
        "stdout": _redact_text(completed.stdout[-4000:]),
        "stderr": _redact_text(completed.stderr[-4000:]),
        "json": payload,
    }


def _compose_cmd() -> tuple[list[str] | None, dict[str, Any] | None]:
    primary = ["docker", "compose", "--profile", "app", "config", "--quiet"]
    result = _run(primary, timeout=60)
    if result["returnCode"] == 0:
        return primary, result
    stderr_text = (result.get("stderr") or "")
    if "unknown flag: --quiet" in stderr_text or "unknown shorthand flag" in stderr_text:
        return ["docker", "compose", "--profile", "app", "config"], _run(
            ["docker", "compose", "--profile", "app", "config"], timeout=60
        )
    if "Usage:  docker [OPTIONS] COMMAND" in stderr_text and ("compose" in stderr_text or "docker-compose" in stderr_text):
        legacy = ["docker-compose", "config", "--services"]
        legacy_result = _run(legacy, timeout=60)
        if legacy_result["returnCode"] == 0:
            return legacy, legacy_result
        return primary, result
    if "unknown command" in stderr_text and "compose" in stderr_text:
        legacy = ["docker-compose", "config"]
        legacy_result = _run(legacy, timeout=60)
        if legacy_result["returnCode"] == 0:
            return legacy, legacy_result
        return primary, result
    return primary, result


def _is_docker_daemon_unreachable(payload: dict[str, Any]) -> bool:
    stderr_text = (payload.get("stderr") or "").lower()
    stdout_text = (payload.get("stdout") or "").lower()
    return (
        "cannot connect to the docker daemon" in stderr_text
        or "is docker running" in stderr_text
        or "connection refused" in stderr_text
        or "denied: permission denied" in stderr_text
        or "permission denied" in stderr_text
        or "dial unix" in stderr_text
        or "no such file or directory" in stderr_text
        or "cannot connect to docker daemon" in stdout_text
    )


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


def _api_json(base_url: str, path: str) -> tuple[int, Any]:
    try:
        headers: dict[str, str] = {}
        token = _api_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(base_url.rstrip("/") + path, headers=headers)
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except Exception as exc:
        return 0, {"error": str(exc)}


def _table_counts() -> dict[str, int]:
    tables = [
        "instruments",
        "instrument_identifiers",
        "data_quality_reports",
        "parquet_datasets",
        "stored_objects",
        "backtest_runs",
        "paper_daily_reports",
    ]
    counts: dict[str, int] = {}
    with db() as connection:
        for table in tables:
            try:
                counts[table] = int(connection.execute(f"select count(*) as count from {table}").fetchone()["count"] or 0)
            except Exception:
                counts[table] = -1
    counts["market_daily_bars"] = sum(
        int(row.get("rows") or 0)
        for row in market_lake.query_matching(kind="bars", columns="count(*) as rows")
    )
    counts["market_trade_status"] = sum(
        int(row.get("rows") or 0)
        for row in market_lake.query_matching(kind="trade_status", columns="count(*) as rows")
    )
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a one-command Level 3 shadow audit.")
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--project-id", help="Existing governed project used for the real LEAN smoke run.")
    parser.add_argument("--benchmark", default="000300")
    parser.add_argument("--source", default=PRIMARY_DATA_SOURCE)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--min-trading-days", type=int, default=10)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--with-frontend", action="store_true")
    parser.add_argument(
        "--evidence-out",
        help="Optional path for the complete machine-readable Level 3 aggregate.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = _csv(args.symbols)
    if args.dry_run:
        payload = {"status": "planned", "decision": "LEVEL3_CANDIDATE", "symbols": symbols}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if not args.project_id:
        parser.error("--project-id is required unless --dry-run is used")

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    _, compose = _compose_cmd()
    compose_status = "ok"
    if compose["returnCode"] != 0:
        compose_status = "warning"
        stderr_text = str(compose.get("stderr", ""))
        if _is_docker_daemon_unreachable(compose) or "command 'compose'" in stderr_text:
            compose_status = "critical"
    checks.append({"name": "docker_compose_config", "status": compose_status, "evidence": compose})
    if compose["returnCode"] != 0 and compose_status == "critical":
        errors.append("docker_compose_config_failed")

    init_db()
    py = _backend_python()
    migrations = _run([*py, str(ROOT / "scripts/db_migrate.py"), "--verify", "--json"], timeout=120)
    checks.append({"name": "migrations", "status": "ok" if migrations["returnCode"] == 0 else "critical", "evidence": migrations.get("json") or migrations})
    if migrations["returnCode"] != 0:
        errors.append("migrations_failed")

    for path in ("/api/health", "/api/health/database"):
        status, body = _api_json(args.api_url, path)
        ok = status == 200 and (body.get("ok", True) is not False)
        checks.append({"name": path, "status": "ok" if ok else "critical", "evidence": {"status": status, "body": body}})
        if not ok:
            errors.append(f"api_health_failed:{path}")

    counts = _table_counts()
    checks.append({"name": "key_table_counts", "status": "ok" if all(value >= 0 for value in counts.values()) else "critical", "evidence": counts})
    if counts.get("instrument_identifiers", 0) <= 0:
        errors.append("instrument_identifiers_empty")

    try:
        source_context = resolve_source_context({"source": args.source})
        checks.append({"name": "source_gate", "status": "ok", "evidence": source_context})
    except Exception as exc:
        checks.append({"name": "source_gate", "status": "critical", "evidence": {"error": str(exc)}})
        errors.append("source_gate_failed")

    identifiers = identifier_coverage([*symbols, args.benchmark])
    checks.append({"name": "instrument_identifier_coverage", "status": "ok" if identifiers["missing"] == 0 else "critical", "evidence": identifiers})
    if identifiers["missing"]:
        errors.append("instrument_identifier_coverage_failed")

    daily = _run(
        [
            *_backend_python(),
            str(ROOT / "scripts/run_daily_shadow_pipeline.py"),
            "--symbols",
            ",".join(symbols),
            "--project-id",
            args.project_id,
            "--benchmark",
            args.benchmark,
            "--source",
            args.source,
            "--start-date",
            args.start_date,
            "--end-date",
            args.end_date,
            "--min-trading-days",
            str(args.min_trading_days),
            "--api-url",
            args.api_url,
            "--json",
        ],
        timeout=1800,
    )
    daily_json = daily.get("json") or {}
    checks.append({"name": "daily_shadow_pipeline", "status": "ok" if daily["returnCode"] == 0 else ("warning" if daily["returnCode"] == 1 else "critical"), "evidence": daily_json or daily})
    if daily["returnCode"] == 1:
        warnings.append("daily_shadow_pipeline_warning")
    elif daily["returnCode"] != 0:
        errors.append("daily_shadow_pipeline_failed")

    constraints = _run(
        [
            *_backend_python(),
            str(ROOT / "scripts/run_paper_constraints_acceptance.py"),
            "--symbols",
            ",".join(symbols),
            "--benchmark",
            args.benchmark,
            "--source",
            args.source,
            "--start-date",
            args.start_date,
            "--end-date",
            args.end_date,
            "--json",
        ],
        timeout=900,
    )
    checks.append({"name": "paper_constraints_acceptance", "status": "ok" if constraints["returnCode"] == 0 else "critical", "evidence": constraints.get("json") or constraints})
    if constraints["returnCode"] != 0:
        errors.append("paper_constraints_acceptance_failed")

    if args.with_frontend:
        frontend = _run(["npm", "run", "build"], timeout=600)
        checks.append({"name": "frontend_build", "status": "ok" if frontend["returnCode"] == 0 else "critical", "evidence": frontend})
        if frontend["returnCode"] != 0:
            errors.append("frontend_build_failed")

    if errors:
        decision = "LEVEL3_FAIL"
    elif warnings or daily_json.get("level3Decision") == "LEVEL3_CANDIDATE":
        decision = "LEVEL3_CANDIDATE"
    else:
        decision = "LEVEL3_PASS"
    payload = {
        "decision": decision,
        "status": "passed" if decision == "LEVEL3_PASS" else ("warning" if decision == "LEVEL3_CANDIDATE" else "failed"),
        "symbols": symbols,
        "benchmark": args.benchmark,
        "source": args.source,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if args.evidence_out:
        evidence_path = Path(args.evidence_out).expanduser().resolve()
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if decision == "LEVEL3_PASS" else (1 if decision == "LEVEL3_CANDIDATE" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
