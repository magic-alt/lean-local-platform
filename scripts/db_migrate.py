#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, init_db  # noqa: E402
from app.migrations.runner import migration_status, verify_migrations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage local platform database migrations.")
    parser.add_argument("command", nargs="?", choices=("status", "apply", "verify"))
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--status", action="store_true")
    group.add_argument("--apply", action="store_true")
    group.add_argument("--verify", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    selected = [name for name in ("status", "apply", "verify") if getattr(args, name)]
    if args.command and selected:
        parser.error("Use either a positional command or a --flag, not both.")
    if not args.command and not selected:
        parser.error("one of status/apply/verify is required")
    if args.command:
        setattr(args, args.command, True)

    try:
        if args.apply:
            init_db()
        with db() as connection:
            if args.verify:
                items = verify_migrations(connection)
            else:
                items = migration_status(connection)
        payload = {
            "status": "ok" if all(item["status"] != "checksum_mismatch" for item in items) else "failed",
            "applied": sum(1 for item in items if item["status"] == "applied"),
            "pending": sum(1 for item in items if item["status"] == "pending"),
            "mismatches": [item["revision"] for item in items if item["status"] == "checksum_mismatch"],
            "items": items,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        else:
            for item in items:
                print(f"{item['revision']} {item['status']} {item['description']}")
        return 0 if payload["status"] == "ok" and (not args.verify or payload["pending"] == 0) else 2
    except Exception as exc:
        payload = {"status": "failed", "error": str(exc)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
