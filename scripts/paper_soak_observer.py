#!/usr/bin/env python3
"""Collect real-time production-shape Paper observation evidence.

The observer cannot backdate samples. Start/sample timestamps are generated from
the current clock, and finalization requires both elapsed calendar time and
distinct observed local dates. Accelerated historical replay belongs to Paper
functional acceptance and is intentionally not accepted here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any
import urllib.request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import database_backend, db  # noqa: E402
from app.services.paper_accounts import verify_projection_history  # noqa: E402

DEFAULT_STATE = ROOT / "web" / "runtime" / "audit" / "paper-soak-state.json"
DEFAULT_EVIDENCE = ROOT / "web" / "runtime" / "audit" / "paper-soak-evidence.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")
HEX_64 = set("0123456789abcdef")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token() -> str:
    configured = os.environ.get("LEAN_API_TOKEN", "").strip()
    if configured:
        return configured
    path = ROOT / "web" / "runtime" / "secrets" / "api_token"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def _health(base_url: str) -> dict[str, Any]:
    headers: dict[str, str] = {}
    if _token():
        headers["Authorization"] = f"Bearer {_token()}"
    request = urllib.request.Request(base_url.rstrip("/") + "/api/health", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("health_payload_invalid")
    return payload


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("paper_soak_state_invalid")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in HEX_64 for char in value)


def _canonical_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _active_cycle_counts(account_ids: list[str]) -> dict[str, int]:
    placeholders = ",".join("?" for _ in account_ids)
    with db() as connection:
        row = connection.execute(
            f"""
            select
              count(*) as total,
              sum(case when status in ('queued','running','waiting_data') then 1 else 0 end) as active,
              sum(case when status='completed' then 1 else 0 end) as completed,
              sum(case when status in ('failed','cancelled') then 1 else 0 end) as failed
            from paper_execution_cycles
            where paper_account_id in ({placeholders})
            """,
            tuple(account_ids),
        ).fetchone()
    return {
        "total": int(row["total"] or 0),
        "active": int(row["active"] or 0),
        "completed": int(row["completed"] or 0),
        "failed": int(row["failed"] or 0),
    }


def _release_identity(health: dict[str, Any]) -> tuple[str, str]:
    release = health.get("release") or {}
    release_id = str(release.get("releaseId") or "")
    git_sha = str(release.get("gitSha") or "")
    if release_id in {"", "local-unversioned", "unknown"}:
        raise RuntimeError("versioned_release_id_required")
    if git_sha in {"", "unknown"}:
        raise RuntimeError("versioned_release_git_sha_required")
    return release_id, git_sha


def start(args: argparse.Namespace) -> dict[str, Any]:
    if database_backend() != "postgresql":
        raise RuntimeError("postgresql_required")
    if args.state.exists() and not args.replace:
        raise RuntimeError("paper_soak_state_already_exists")
    account_ids = list(dict.fromkeys(item.strip() for item in args.account_id if item.strip()))
    if not account_ids:
        raise RuntimeError("at_least_one_paper_account_required")
    if not args.data_release_id.strip():
        raise RuntimeError("data_release_id_required")
    manifest_sha = args.data_release_manifest_sha256.strip().lower()
    if not _valid_sha256(manifest_sha):
        raise RuntimeError("data_release_manifest_sha256_invalid")
    health = _health(args.base_url)
    release_id, git_sha = _release_identity(health)
    now = _now()
    state = {
        "schemaVersion": 1,
        "evidenceMode": "production_shape_observation",
        "startedAt": now.isoformat(),
        "startedLocalDate": now.astimezone(SHANGHAI).date().isoformat(),
        "releaseId": release_id,
        "gitSha": git_sha,
        "dataReleaseId": args.data_release_id.strip(),
        "dataReleaseManifestSha256": manifest_sha,
        "accountIds": account_ids,
        "samples": [],
    }
    _write(args.state, state)
    return state


def sample(args: argparse.Namespace) -> dict[str, Any]:
    if database_backend() != "postgresql":
        raise RuntimeError("postgresql_required")
    state = _load(args.state)
    account_ids = [str(item) for item in state.get("accountIds") or []]
    if not account_ids:
        raise RuntimeError("paper_soak_accounts_missing")
    health = _health(args.base_url)
    release_id, git_sha = _release_identity(health)
    if release_id != state.get("releaseId") or git_sha != state.get("gitSha"):
        raise RuntimeError("paper_soak_release_identity_changed")
    projection = [verify_projection_history(account_id) for account_id in account_ids]
    now = _now()
    previous_digest = None
    samples = state.get("samples") or []
    if samples:
        previous_digest = samples[-1].get("sampleSha256")
    sample_payload: dict[str, Any] = {
        "observedAt": now.isoformat(),
        "localDate": now.astimezone(SHANGHAI).date().isoformat(),
        "releaseId": release_id,
        "gitSha": git_sha,
        "healthStatus": health.get("status"),
        "database": health.get("database"),
        "broker": health.get("broker"),
        "cycleCounts": _active_cycle_counts(account_ids),
        "projectionVerification": projection,
        "projectionPassed": bool(projection) and all(item.get("passed") for item in projection),
        "previousSampleSha256": previous_digest,
    }
    sample_payload["sampleSha256"] = _canonical_digest(sample_payload)
    samples.append(sample_payload)
    state["samples"] = samples
    state["lastObservedAt"] = now.isoformat()
    _write(args.state, state)
    return sample_payload


def _fault_recovery(path: Path) -> dict[str, Any]:
    payload = _load(path)
    scenarios = payload.get("scenarios") or {}
    required = (
        "database_short_disconnect",
        "rabbitmq_outage",
        "worker_crash",
    )
    passed = bool(payload.get("passed")) and all(
        isinstance(scenarios.get(name), dict) and scenarios[name].get("passed")
        for name in required
    )
    return {
        "passed": passed,
        "requiredScenarios": list(required),
        "faultMatrix": str(path),
    }


def finalize(args: argparse.Namespace) -> dict[str, Any]:
    state = _load(args.state)
    samples = list(state.get("samples") or [])
    if not samples:
        raise RuntimeError("paper_soak_samples_missing")
    started = datetime.fromisoformat(str(state["startedAt"]).replace("Z", "+00:00"))
    completed = datetime.fromisoformat(str(samples[-1]["observedAt"]).replace("Z", "+00:00"))
    elapsed_days = max(0.0, (completed - started).total_seconds() / 86400.0)
    observed_dates = sorted({str(item.get("localDate")) for item in samples if item.get("localDate")})
    projection_passed = all(bool(item.get("projectionPassed")) for item in samples)
    hash_chain_valid = True
    previous: str | None = None
    for item in samples:
        recorded = str(item.get("sampleSha256") or "")
        body = {key: value for key, value in item.items() if key != "sampleSha256"}
        if body.get("previousSampleSha256") != previous or _canonical_digest(body) != recorded:
            hash_chain_valid = False
            break
        previous = recorded
    recovery = _fault_recovery(args.fault_matrix)
    minimum_days = int(args.minimum_days)
    passed = bool(
        elapsed_days >= minimum_days
        and len(observed_dates) >= minimum_days
        and projection_passed
        and hash_chain_valid
        and recovery["passed"]
    )
    evidence = {
        "schemaVersion": 1,
        "status": "PAPER_SOAK_PASS" if passed else "PAPER_SOAK_INCOMPLETE",
        "passed": passed,
        "evidenceMode": "production_shape_observation",
        "startedAt": state["startedAt"],
        "completedAt": samples[-1]["observedAt"],
        "observedElapsedDays": round(elapsed_days, 6),
        "observedLocalDates": observed_dates,
        "observedCalendarDays": len(observed_dates),
        "minimumCalendarDays": minimum_days,
        "gitSha": state["gitSha"],
        "releaseId": state["releaseId"],
        "dataReleaseId": state["dataReleaseId"],
        "dataReleaseManifestSha256": state["dataReleaseManifestSha256"],
        "accountIds": state["accountIds"],
        "sampleCount": len(samples),
        "hashChainValid": hash_chain_valid,
        "ledgerProjection": {"passed": projection_passed},
        "interruptionRecovery": recovery,
        "samples": samples,
    }
    _write(args.evidence, evidence)
    return evidence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    sub = parser.add_subparsers(dest="command", required=True)

    start_parser = sub.add_parser("start")
    start_parser.add_argument("--account-id", action="append", default=[], required=True)
    start_parser.add_argument("--data-release-id", required=True)
    start_parser.add_argument("--data-release-manifest-sha256", required=True)
    start_parser.add_argument("--replace", action="store_true")

    sub.add_parser("sample")

    finalize_parser = sub.add_parser("finalize")
    finalize_parser.add_argument("--minimum-days", type=int, default=21)
    finalize_parser.add_argument("--fault-matrix", type=Path, required=True)
    finalize_parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.state = args.state.expanduser().resolve()
    try:
        if args.command == "start":
            payload = start(args)
            exit_code = 0
        elif args.command == "sample":
            payload = sample(args)
            exit_code = 0 if payload.get("projectionPassed") else 1
        else:
            args.fault_matrix = args.fault_matrix.expanduser().resolve()
            args.evidence = args.evidence.expanduser().resolve()
            payload = finalize(args)
            exit_code = 0 if payload.get("passed") else 1
    except Exception as exc:
        payload = {
            "status": "PAPER_SOAK_ERROR",
            "passed": False,
            "failure": {"type": type(exc).__name__, "detail": str(exc)},
        }
        exit_code = 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
