#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import database_backend, db, rows_to_dicts  # noqa: E402
from app.services.db_object_store import delete_object  # noqa: E402


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=max(0, days))).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup stored report/backtest artifacts with a safe dry-run mode.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--namespace", default="backtest-results")
    parser.add_argument("--status", default=None)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--include-success", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    clauses = ["o.namespace = ?", "o.updated_at < ?"]
    params: list[object] = [args.namespace, _cutoff(args.days)]
    join = ""
    if args.status or not args.include_success:
        key_expr = "concat(r.id, '/%%')" if database_backend() == "mysql" else "r.id || '/%'"
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
