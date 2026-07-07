#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, rows_to_dicts, utc_now  # noqa: E402
from app.parsers.lean_result_parser import parse_result_payload  # noqa: E402
from app.repositories.backtest_repository import get_result, save_result  # noqa: E402


def _resolve_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute() and path.parts[:2] == ("/", "workspace"):
        return ROOT.joinpath(*path.parts[2:])
    return path if path.is_absolute() else ROOT / path


def _run_rows(run_ids: list[str], symbol: str | None, limit: int) -> list[dict[str, Any]]:
    clauses = ["result_json_path is not null"]
    values: list[Any] = []
    if run_ids:
        placeholders = ", ".join("?" for _ in run_ids)
        clauses.append(f"id in ({placeholders})")
        values.extend(run_ids)
    if symbol:
        clauses.append("upper(symbol) = ?")
        values.append(symbol.upper())
    values.append(max(1, min(int(limit), 1000)))
    with db() as connection:
        rows = connection.execute(
            f"""
            select *
            from backtest_runs
            where {" and ".join(clauses)}
            order by created_at desc, id desc
            limit ?
            """,
            values,
        ).fetchall()
    return rows_to_dicts(rows)


def _parse_one(run: dict[str, Any], apply: bool) -> dict[str, Any]:
    result_json = _resolve_path(run.get("result_json_path"))
    summary_json = _resolve_path(run.get("summary_json_path"))
    if result_json is None or not result_json.exists():
        return {"runId": run.get("id"), "status": "failed", "error": f"result_json_missing:{run.get('result_json_path')}"}
    if summary_json is not None and not summary_json.exists():
        summary_json = None
    existing = get_result(run["id"]) or {}
    payload = parse_result_payload(result_json, summary_json, run)
    if existing.get("id"):
        payload["id"] = existing["id"]
    if existing.get("raw_result_object_id"):
        payload["raw_result_object_id"] = existing["raw_result_object_id"]
    if existing.get("summary_object_id"):
        payload["summary_object_id"] = existing["summary_object_id"]
    if apply:
        saved = save_result(run["id"], payload, existing.get("created_at") or utc_now())
    else:
        saved = payload
    performance = saved.get("performance") or {}
    summary = saved.get("summary_metrics") or {}
    return {
        "runId": run["id"],
        "status": "updated" if apply else "planned",
        "resultJson": str(result_json),
        "summaryJson": str(summary_json) if summary_json else None,
        "leanSharpe": (saved.get("statistics") or {}).get("Sharpe Ratio"),
        "recomputedSharpe": performance.get("sharpe_recomputed_from_equity") or summary.get("Recomputed Sharpe"),
        "sharpeSampleCount": performance.get("sharpe_recomputed_sample_count") or summary.get("Sharpe Sample Count"),
        "sharpeMetricStatus": performance.get("sharpe_recompute_status") or summary.get("Sharpe Metric Status"),
        "shortWindowUnstable": performance.get("short_window_unstable") or summary.get("Short Window Unstable"),
        "warnings": performance.get("sharpe_metric_warnings") or [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reparse stored LEAN backtest result JSON into backtest_results.")
    parser.add_argument("--run-id", action="append", default=[])
    parser.add_argument("--symbol")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.dry_run == args.apply:
        parser.error("Specify exactly one of --dry-run or --apply.")

    runs = _run_rows(args.run_id, args.symbol, args.limit)
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for run in runs:
        try:
            item = _parse_one(run, args.apply)
        except Exception as exc:  # pragma: no cover - surfaced in CLI output.
            item = {"runId": run.get("id"), "status": "failed", "error": str(exc)}
        if item.get("status") == "failed":
            errors.append(f"{item.get('runId')}:{item.get('error')}")
        items.append(item)
    payload = {
        "status": "failed" if errors else ("updated" if args.apply else "planned"),
        "dryRun": args.dry_run,
        "apply": args.apply,
        "requestedRunIds": args.run_id,
        "symbol": args.symbol,
        "count": len(items),
        "updated": len([item for item in items if item.get("status") == "updated"]),
        "errors": errors,
        "items": items,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"{payload['status']} count={payload['count']} updated={payload['updated']} errors={len(errors)}")
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
