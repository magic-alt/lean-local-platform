#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
from app.services.instrument_identity import identifier_coverage  # noqa: E402
from app.services.source_gate import resolve_source_context  # noqa: E402


def _csv(value: str) -> list[str]:
    return [item.strip().zfill(6)[-6:] for item in value.split(",") if item.strip()]


def _run(command: list[str], timeout: int = 900) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout)
    payload: Any = None
    try:
        payload = json.loads(completed.stdout or "{}")
    except Exception:
        payload = None
    return {"command": command, "returnCode": completed.returncode, "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:], "json": payload}


def _api_json(base_url: str, path: str) -> tuple[int, Any]:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8") or "{}")
    except Exception as exc:
        return 0, {"error": str(exc)}


def _table_counts() -> dict[str, int]:
    tables = [
        "instruments",
        "instrument_identifiers",
        "market_daily_bars",
        "market_trade_status",
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
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a one-command Level 3 shadow audit.")
    parser.add_argument("--symbols", required=True)
    parser.add_argument("--benchmark", default="000300")
    parser.add_argument("--source", default="jqdata")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--min-trading-days", type=int, default=10)
    parser.add_argument("--api-url", default="http://127.0.0.1:8003")
    parser.add_argument("--with-frontend", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = _csv(args.symbols)
    if args.dry_run:
        payload = {"status": "planned", "decision": "LEVEL3_CANDIDATE", "symbols": symbols}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    errors: list[str] = []

    compose = _run(["docker", "compose", "--profile", "app", "config"], timeout=60)
    checks.append({"name": "docker_compose_config", "status": "ok" if compose["returnCode"] == 0 else "critical", "evidence": compose})
    if compose["returnCode"] != 0:
        errors.append("docker_compose_config_failed")

    init_db()
    migrations = _run([str(BACKEND / ".venv/bin/python"), str(ROOT / "scripts/db_migrate.py"), "--verify", "--json"], timeout=120)
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
            str(BACKEND / ".venv/bin/python"),
            str(ROOT / "scripts/run_daily_shadow_pipeline.py"),
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
            str(BACKEND / ".venv/bin/python"),
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
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if decision == "LEVEL3_PASS" else (1 if decision == "LEVEL3_CANDIDATE" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
