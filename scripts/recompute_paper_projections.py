#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import database_backend, db  # noqa: E402
from app.services.paper_accounts import (  # noqa: E402
    CanonicalStateDivergence,
    mark_projection_history_trusted,
    rebuild_projection_history,
    verify_projection_history,
)


def _account_ids(requested: list[str]) -> list[str]:
    if requested:
        return list(dict.fromkeys(str(item).strip() for item in requested if str(item).strip()))
    with db() as connection:
        rows = connection.execute(
            "select id from paper_accounts where status<>'archived' order by created_at,id"
        ).fetchall()
    return [str(row["id"]) for row in rows]


def run(*, apply: bool, account_ids: list[str]) -> dict[str, Any]:
    if database_backend() != "mysql":
        raise RuntimeError("mysql_required")
    selected = _account_ids(account_ids)
    if not selected:
        raise RuntimeError("no_paper_accounts_selected")
    before = [verify_projection_history(account_id) for account_id in selected]
    checkpoint_failures = [
        f"{item['accountId']}:{failure}"
        for item in before
        for failure in item["failures"]
        if str(failure).startswith("checkpoint_digest_mismatch:")
    ]
    if apply and checkpoint_failures:
        raise CanonicalStateDivergence(
            "historical_checkpoint_integrity_failed:" + ",".join(checkpoint_failures)
        )
    rebuilt = (
        [rebuild_projection_history(account_id) for account_id in selected]
        if apply
        else []
    )
    after = [verify_projection_history(account_id) for account_id in selected]
    passed = bool(after) and all(item["passed"] for item in after)
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "mode": "apply" if apply else "verify",
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "accountIds": selected,
        "before": before,
        "rebuilt": rebuilt,
        "after": after,
        "passed": passed,
    }
    if apply and passed:
        payload["dataTrust"] = mark_projection_history_trusted(
            {
                "passed": True,
                "accountCount": len(selected),
                "accountIds": selected,
                "verification": after,
            }
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recompute Paper projections, snapshots and reports by their historical as-of dates."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true", help="Rewrite derived Paper history and verify it.")
    mode.add_argument("--verify", action="store_true", help="Read-only verification.")
    parser.add_argument("--account-id", action="append", default=[])
    parser.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / "web" / "runtime" / "audit" / "paper-projection-recompute.json",
    )
    args = parser.parse_args()
    try:
        payload = run(apply=bool(args.apply), account_ids=args.account_id)
        status = "PAPER_PROJECTION_RECOMPUTE_PASS" if payload["passed"] else "PAPER_PROJECTION_RECOMPUTE_FAIL"
        exit_code = 0 if payload["passed"] else 1
    except Exception as exc:
        payload = {
            "schemaVersion": 1,
            "mode": "apply" if args.apply else "verify",
            "passed": False,
            "failure": {"type": type(exc).__name__, "detail": str(exc)},
            "completedAt": datetime.now(timezone.utc).isoformat(),
        }
        status = "PAPER_PROJECTION_RECOMPUTE_FAIL"
        exit_code = 1
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(status)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
