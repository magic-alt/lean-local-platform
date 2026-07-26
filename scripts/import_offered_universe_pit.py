#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import init_db  # noqa: E402
from app.services.tushare_adapter import TushareAdapter  # noqa: E402
from app.services.tushare_index_pit import import_snapshot_history  # noqa: E402
from app.services.universe_coverage import OFFERED_UNIVERSES, universe_coverage_overview  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import licensed point-in-time history for every offered index universe."
    )
    parser.add_argument(
        "--universes",
        default="CSI500,CSI1000,SSE50,STAR50",
        help="Comma-separated offered index universes. CSI300 remains on its official CSIndex chain.",
    )
    parser.add_argument("--end-date", default=date.today().isoformat())
    parser.add_argument("--no-replace", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Return zero when imports succeed but launch-to-current certification remains partial.",
    )
    parser.add_argument("--evidence-out")
    args = parser.parse_args()

    init_db()
    adapter = TushareAdapter()
    selected = [item.strip().upper() for item in args.universes.split(",") if item.strip()]
    results = []
    failures = []
    for code in selected:
        spec = OFFERED_UNIVERSES.get(code)
        if not spec or not spec.get("indexSymbol"):
            failures.append({"universeCode": code, "error": "unsupported_or_non_index_universe"})
            continue
        try:
            rows = adapter.index_weight_rows(spec["indexSymbol"], spec["launchDate"], args.end_date)
            if args.dry_run:
                snapshots = {}
                for row in rows:
                    snapshots.setdefault(row["trade_date"], 0)
                    snapshots[row["trade_date"]] += 1
                result = {
                    "universeCode": code,
                    "rowCount": len(rows),
                    "coverageStart": min(snapshots) if snapshots else None,
                    "coverageEnd": max(snapshots) if snapshots else None,
                    "snapshotCounts": [{"date": key, "count": value} for key, value in sorted(snapshots.items())],
                    "dryRun": True,
                }
            else:
                result = import_snapshot_history(code, rows, replace=not args.no_replace)
            results.append(result)
            print(
                json.dumps(
                    {key: value for key, value in result.items() if key != "snapshotCounts"},
                    ensure_ascii=False,
                )
            )
        except Exception as exc:  # noqa: BLE001 - retain all universe diagnostics
            failures.append({"universeCode": code, "error": str(exc)})
            print(f"{code}: {exc}", file=sys.stderr)
    incomplete = [
        {
            "universeCode": item.get("universeCode"),
            "coverageStart": item.get("coverageStart"),
            "coverageEnd": item.get("coverageEnd"),
            "status": item.get("status") or "unverified",
        }
        for item in results
        if not args.dry_run and item.get("status") != "complete"
    ]
    status = "fail" if failures or len(results) != len(selected) else "partial" if incomplete else "pass"
    evidence = {
        "schemaVersion": 1,
        "source": "tushare:index_weight",
        "results": results,
        "failures": failures,
        "incomplete": incomplete,
        "coverage": universe_coverage_overview(),
        "status": status,
    }
    if args.evidence_out:
        path = Path(args.evidence_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    if evidence["status"] == "pass" or (args.allow_partial and evidence["status"] == "partial"):
        return 0
    return 2 if evidence["status"] == "partial" else 1


if __name__ == "__main__":
    raise SystemExit(main())
