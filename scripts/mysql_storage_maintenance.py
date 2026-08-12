#!/usr/bin/env python3
"""Run explicit, confirmation-protected MySQL storage maintenance actions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services import storage_maintenance  # noqa: E402


MUTATING_ACTIONS = {"hide-indexes", "restore-indexes", "drop-indexes", "optimize", "delete-equivalent-eav", "migrate-objects", "prune-artifacts", "prune-raw-records", "prepare-ashare", "cutover-ashare", "drop-ashare-legacy", "direct-market-reset", "purge-backtests"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("report", "index-status", "eav-audit", "ashare-coverage", "market-reset-plan", "backtest-purge-plan", "schema-report", *sorted(MUTATING_ACTIONS)))
    parser.add_argument("--confirm", action="store_true", help="Required for every mutating action.")
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--max-batches", type=int)
    parser.add_argument("--limit", type=int, default=1_000)
    parser.add_argument("--namespace")
    parser.add_argument("--retention-days", type=int, default=180)
    parser.add_argument("--tables", default="", help="Comma-separated OPTIMIZE TABLE allowlist.")
    parser.add_argument("--output", default="docs/operations/mysql-schema-current.md", help="Markdown path for schema-report.")
    parser.add_argument("--no-backup", action="store_true", help="Required acknowledgement: this reset does not create a backup.")
    parser.add_argument("--direct-reset", action="store_true", help="Required acknowledgement: clear live regenerable market data, not a shadow copy.")
    args = parser.parse_args()
    if args.action in MUTATING_ACTIONS and not args.confirm:
        parser.error(f"{args.action} is mutating; repeat with --confirm after reviewing the dry-run report.")
    if args.action == "direct-market-reset" and (not args.no_backup or not args.direct_reset):
        parser.error("direct-market-reset requires --confirm --no-backup --direct-reset after reviewing market-reset-plan.")

    if args.action == "report":
        result = storage_maintenance.storage_report()
    elif args.action == "index-status":
        result = storage_maintenance.redundant_index_status()
    elif args.action == "eav-audit":
        result = storage_maintenance.daily_basic_eav_audit()
    elif args.action == "ashare-coverage":
        result = storage_maintenance.ashare_canonical_coverage()
    elif args.action == "market-reset-plan":
        result = storage_maintenance.market_reset_plan()
    elif args.action == "backtest-purge-plan":
        result = storage_maintenance.backtest_purge_plan()
    elif args.action == "schema-report":
        result = storage_maintenance.write_mysql_schema_report((ROOT / args.output).resolve())
    elif args.action == "hide-indexes":
        result = storage_maintenance.set_redundant_indexes_visible(visible=False)
    elif args.action == "restore-indexes":
        result = storage_maintenance.set_redundant_indexes_visible(visible=True)
    elif args.action == "drop-indexes":
        result = storage_maintenance.drop_redundant_indexes()
    elif args.action == "optimize":
        result = storage_maintenance.optimize_tables([item for item in args.tables.split(",") if item])
    elif args.action == "delete-equivalent-eav":
        result = storage_maintenance.delete_equivalent_daily_basic_eav(batch_size=args.batch_size, max_batches=args.max_batches)
    elif args.action == "migrate-objects":
        result = storage_maintenance.migrate_objects(limit=args.limit, namespace=args.namespace)
    elif args.action == "prepare-ashare":
        result = storage_maintenance.prepare_ashare_canonical_storage()
    elif args.action == "cutover-ashare":
        storage_maintenance.cutover_ashare_compatibility_views()
        result = {"cutover": "complete"}
    elif args.action == "drop-ashare-legacy":
        storage_maintenance.drop_ashare_legacy_tables()
        result = {"legacyTables": "dropped"}
    elif args.action == "direct-market-reset":
        result = storage_maintenance.direct_market_reset()
    elif args.action == "purge-backtests":
        result = storage_maintenance.purge_backtests()
    elif args.action == "prune-raw-records":
        result = storage_maintenance.prune_expired_provider_raw_records(retention_days=args.retention_days, limit=args.limit)
    else:
        result = storage_maintenance.prune_expired_objects(retention_days=args.retention_days, limit=args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
