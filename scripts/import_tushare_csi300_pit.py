#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db import database_descriptor, init_db  # noqa: E402
from app.services.tushare_csi300_pit import import_tushare_csi300_snapshots  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import governed TuShare CSI300 index_weight snapshots into the CSI300_TUSHARE shadow PIT universe."
    )
    parser.add_argument("--start-date", default="2005-01-01")
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--quarantine-incomplete",
        action="store_true",
        help="Archive and canonicalize provider rows but exclude incomplete snapshots from the shadow PIT universe.",
    )
    parser.add_argument("--report-out")
    args = parser.parse_args()

    init_db()
    report = import_tushare_csi300_snapshots(
        start_date=args.start_date,
        end_date=args.end_date,
        dry_run=args.dry_run,
        quarantine_incomplete=args.quarantine_incomplete,
    )
    payload = {"database": database_descriptor(), **report}
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.report_out:
        output = Path(args.report_out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
