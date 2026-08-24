#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import database_backend, db, rows_to_dicts  # noqa: E402
from app.services.db_object_store import delete_object  # noqa: E402


DEFAULT_POLICY = {
    "protect_recent_days": 7,
    "classes": [
        {"name": "critical_audit", "namespaces": ["level3-audit", "level3plus-audit"], "retain_days": None, "permanent": True},
        {"name": "successful_daily_pipeline", "namespaces": ["pipeline-artifacts"], "statuses": ["success", "passed", "ok"], "retain_days": 365},
        {"name": "failed_run_artifacts", "namespaces": ["pipeline-artifacts", "backtest-results"], "statuses": ["failed", "critical"], "retain_days": 180},
        {"name": "debug_logs", "namespaces": ["debug-logs", "logs"], "retain_days": 30},
        {"name": "reports", "namespaces": ["reports"], "retain_days": 365},
    ],
}


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=max(0, days))).isoformat()


def _load_policy(path: str | None) -> dict[str, Any]:
    if not path:
        return DEFAULT_POLICY
    policy_path = Path(path)
    if not policy_path.exists():
        raise FileNotFoundError(str(policy_path))
    text = policy_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text) or {}
        return {**DEFAULT_POLICY, **loaded}
    except Exception:
        # Minimal parser for this repository's retention_policy.yaml shape.
        result: dict[str, Any] = {"classes": []}
        current: dict[str, Any] | None = None
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            stripped = line.strip()
            if stripped.startswith("- name:"):
                current = {"name": stripped.split(":", 1)[1].strip()}
                result.setdefault("classes", []).append(current)
                continue
            if ":" not in stripped:
                continue
            key, value = [part.strip() for part in stripped.split(":", 1)]
            target = current if current is not None and raw.startswith("  ") else result
            if value.startswith("[") and value.endswith("]"):
                target[key] = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
            elif value.lower() in {"true", "false"}:
                target[key] = value.lower() == "true"
            elif value.lower() in {"null", "none"}:
                target[key] = None
            else:
                try:
                    target[key] = int(value)
                except ValueError:
                    target[key] = value.strip("'\"")
        return {**DEFAULT_POLICY, **result}


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("metadata") or item.get("metadata_json") or {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def _matches(rule: dict[str, Any], item: dict[str, Any], metadata: dict[str, Any]) -> bool:
    namespaces = set(rule.get("namespaces") or [])
    statuses = set(rule.get("statuses") or [])
    if namespaces and item.get("namespace") not in namespaces:
        return False
    if statuses and str(metadata.get("status") or metadata.get("runStatus") or "").lower() not in statuses:
        return False
    return True


def _policy_cleanup(policy: dict[str, Any], *, dry_run: bool, verify: bool, limit: int) -> dict[str, Any]:
    protect_days = int(policy.get("protect_recent_days") or 0)
    protected_after = _cutoff(protect_days)
    with db() as connection:
        rows = connection.execute(
            """
            select *
            from stored_objects
            order by updated_at asc
            limit ?
            """,
            (max(1, min(int(limit), 5000)),),
        ).fetchall()
    items = rows_to_dicts(rows)
    candidates: list[dict[str, Any]] = []
    skipped_pinned = 0
    skipped_recent = 0
    skipped_audit = 0
    errors: list[str] = []
    for item in items:
        metadata = _metadata(item)
        namespace = str(item.get("namespace") or "")
        object_key = str(item.get("object_key") or item.get("objectKey") or "")
        if metadata.get("pinned") or metadata.get("manualPinned"):
            skipped_pinned += 1
            continue
        if item.get("updated_at") and str(item["updated_at"]) >= protected_after:
            skipped_recent += 1
            continue
        if "level3" in namespace.lower() or "level3" in object_key.lower():
            skipped_audit += 1
            continue
        for rule in policy.get("classes") or []:
            if not _matches(rule, item, metadata):
                continue
            if rule.get("permanent") or rule.get("retain_days") is None:
                skipped_audit += 1
                break
            cutoff = _cutoff(int(rule.get("retain_days") or 0))
            if str(item.get("updated_at") or "") < cutoff:
                candidates.append({**item, "retentionClass": rule.get("name")})
            break
    deleted = 0
    if not dry_run and not verify:
        for item in candidates:
            try:
                delete_object(item["id"])
                deleted += 1
            except Exception as exc:
                errors.append(f"{item.get('id')}:{exc}")
    return {
        "status": "verified" if verify else ("planned" if dry_run else ("ok" if not errors else "warning")),
        "dryRun": dry_run,
        "verify": verify,
        "wouldDelete": len(candidates),
        "deleted": deleted,
        "freedBytes": sum(int(item.get("size") or 0) for item in candidates),
        "skippedPinned": skipped_pinned,
        "skippedRecent": skipped_recent,
        "skippedAudit": skipped_audit,
        "errors": errors,
        "items": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup stored report/backtest artifacts with a safe dry-run mode.")
    parser.add_argument("--policy")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--namespace", default="backtest-results")
    parser.add_argument("--status", default=None)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--include-success", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.policy:
        policy = _load_policy(args.policy)
        payload = _policy_cleanup(policy, dry_run=args.dry_run or not args.execute, verify=args.verify, limit=args.limit)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"{payload['status']} wouldDelete={payload['wouldDelete']} deleted={payload['deleted']} freedBytes={payload['freedBytes']}")
        return 0 if not payload["errors"] else 1

    clauses = ["o.namespace = ?", "o.updated_at < ?"]
    params: list[object] = [args.namespace, _cutoff(args.days)]
    join = ""
    if args.status or not args.include_success:
        key_expr = "r.id || '/%'"
        join = f"left join backtest_runs r on o.object_key like {key_expr}"
        if args.status:
            clauses.append("r.status = ?")
            params.append(args.status)
        if not args.include_success:
            clauses.append("(r.status is null or r.status not in ('success', 'completed'))")
    limit = max(1, min(int(args.limit), 1000))
    params.append(limit)
    with db() as connection:
        rows = connection.execute(
            f"""
            select o.*
            from stored_objects o
            {join}
            where {" and ".join(clauses)}
            order by o.updated_at asc
            limit ?
            """,
            params,
        ).fetchall()
    items = rows_to_dicts(rows)
    if not args.dry_run:
        for item in items:
            delete_object(item["id"])
    payload = {
        "status": "planned" if args.dry_run else "ok",
        "dryRun": args.dry_run,
        "wouldDelete": len(items),
        "deleted": 0 if args.dry_run else len(items),
        "freedBytes": sum(int(item.get("size") or 0) for item in items),
        "skippedPinned": 0,
        "skippedRecent": 0,
        "errors": [],
        "protectedSuccessRuns": not args.include_success,
        "items": items,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"{payload['status']} wouldDelete={payload['wouldDelete']} deleted={payload['deleted']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
