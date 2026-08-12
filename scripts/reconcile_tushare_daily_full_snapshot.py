#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, init_db, row_to_dict  # noqa: E402
from app.services.data import _reconcile_market_daily_snapshot  # noqa: E402
from app.services.data_sync import _reconcile_daily_manifest_scope  # noqa: E402
from app.services.db_object_store import read_bytes  # noqa: E402


def _symbol(row: dict[str, Any]) -> str:
    return str(row.get("ts_code") or row.get("symbol") or "").split(".", 1)[0].strip().upper()


def _date(row: dict[str, Any]) -> str:
    value = str(row.get("trade_date") or row.get("date") or "").strip()
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value[:10]


def _load_run(run_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute(
            "select * from data_sync_runs where id=?",
            (run_id,),
        ).fetchone()
    run = row_to_dict(row)
    if not run:
        raise ValueError(f"data_sync_run_not_found:{run_id}")
    summary = run.get("summary") or {}
    full_mode = run.get("mode") in {"initial_full", "full_rebuild"} or summary.get("resumeBaseMode") in {
        "initial_full",
        "full_rebuild",
    }
    daily_evidence = next(
        (
            item
            for item in (summary.get("completionEvidence") or {}).get("items", [])
            if item.get("datasetKey") == "daily"
        ),
        {},
    )
    if (
        run.get("status") != "success"
        or run.get("canonical_status") != "ready"
        or not full_mode
        or not daily_evidence.get("passed")
    ):
        raise ValueError("run_is_not_a_completed_governed_full_snapshot")
    return {"run": run, "dailyEvidence": daily_evidence}


def _inventory(run_id: str) -> dict[str, Any]:
    with db() as connection:
        manifest_rows = connection.execute(
            """
            select scope_key,response_rows,request_json
            from provider_ingestion_manifests
            where run_id=? and provider='tushare' and dataset_key='daily' and status='success'
            order by scope_key
            """,
            (run_id,),
        ).fetchall()
        mismatches = connection.execute(
            """
            select p.scope_key,p.response_rows,count(a.trade_date) as canonical_rows,
                   count(a.trade_date)-p.response_rows as delta
            from provider_ingestion_manifests p
            left join market_daily_bars a
              on a.symbol=p.scope_key and a.source='tushare' and a.adjust='raw'
             and a.asset_class='equity' and a.market='china' and a.venue='china'
             and a.resolution='daily' and a.data_type='trade'
            where p.run_id=? and p.provider='tushare' and p.dataset_key='daily' and p.status='success'
            group by p.scope_key,p.response_rows
            having count(a.trade_date)<>p.response_rows
            order by abs(count(a.trade_date)-p.response_rows) desc,p.scope_key
            """,
            (run_id,),
        ).fetchall()
        orphan_symbols = connection.execute(
            """
            select m.symbol,count(*) as canonical_rows,min(m.trade_date) as first_date,
                   max(m.trade_date) as last_date
            from market_daily_bars m
            where m.source='tushare' and m.adjust='raw' and m.asset_class='equity'
              and m.market='china' and m.venue='china' and m.resolution='daily'
              and m.data_type='trade'
              and not exists (
                  select 1 from provider_ingestion_manifests p
                  where p.run_id=? and p.provider='tushare' and p.dataset_key='daily'
                    and p.status='success' and p.scope_key=m.symbol
              )
            group by m.symbol
            order by canonical_rows desc,m.symbol
            """,
            (run_id,),
        ).fetchall()
        canonical = connection.execute(
            """
            select
              (select count(*) from market_daily_bars where source='tushare' and adjust='raw'
                 and asset_class='equity' and market='china' and venue='china'
                 and resolution='daily' and data_type='trade') as market_rows
            """
        ).fetchone()
    manifests = [dict(row) for row in manifest_rows]
    expected_rows = sum(int(row["response_rows"] or 0) for row in manifests)
    return {
        "expectedRows": expected_rows,
        "manifestCount": len(manifests),
        "manifests": manifests,
        "mismatches": [dict(row) for row in mismatches],
        "orphanSymbols": [dict(row) for row in orphan_symbols],
        "canonicalRows": dict(canonical or {}),
    }


def reconcile(run_id: str, *, apply: bool) -> dict[str, Any]:
    baseline = _load_run(run_id)
    before = _inventory(run_id)
    payload: dict[str, Any] = {
        "runId": run_id,
        "mode": "apply" if apply else "dry_run",
        "dailyEvidence": baseline["dailyEvidence"],
        "before": {key: value for key, value in before.items() if key != "manifests"},
    }
    if not apply:
        return payload

    targets = {str(item["scope_key"]) for item in before["mismatches"]}
    manifests = {str(item["scope_key"]): item for item in before["manifests"]}
    authoritative_dates: dict[str, set[str]] = {symbol: set() for symbol in targets}
    with db() as connection:
        archives = connection.execute(
            """
            select a.object_id,a.archive_sha256
            from provider_raw_archives a
            where a.run_id=? and a.provider='tushare' and a.dataset_key='daily'
            order by a.created_at,a.id
            """,
            (run_id,),
        ).fetchall()
    for archive in archives:
        compressed = read_bytes(str(archive["object_id"]))
        rows = json.loads(gzip.decompress(compressed))
        for row in rows:
            symbol = _symbol(row)
            if symbol in authoritative_dates:
                trade_date = _date(row)
                if trade_date:
                    authoritative_dates[symbol].add(trade_date)

    count_mismatches = {
        symbol: {
            "expected": int(manifests[symbol]["response_rows"] or 0),
            "archiveKeys": len(dates),
        }
        for symbol, dates in authoritative_dates.items()
        if len(dates) != int(manifests[symbol]["response_rows"] or 0)
    }
    if count_mismatches:
        raise ValueError(f"raw_archive_key_count_mismatch:{json.dumps(count_mismatches, sort_keys=True)}")

    entries = []
    normalized = {}
    for symbol in sorted(targets):
        request = json.loads(manifests[symbol]["request_json"] or "{}")
        entries.append(
            {
                "symbol": symbol,
                "snapshot_start": request.get("startDate") or "1990-01-01",
                "snapshot_end": request.get("endDate") or "9999-12-31",
            }
        )
        normalized[symbol] = [{"trade_date": trade_date} for trade_date in sorted(authoritative_dates[symbol])]

    removed_snapshot_rows = _reconcile_market_daily_snapshot(entries, normalized)
    removed_orphan_rows = _reconcile_daily_manifest_scope(run_id)
    after = _inventory(run_id)
    if after["mismatches"] or after["orphanSymbols"]:
        raise RuntimeError("post_reconciliation_canonical_mismatch")
    if any(int(value or 0) != after["expectedRows"] for value in after["canonicalRows"].values()):
        raise RuntimeError("post_reconciliation_row_count_mismatch")
    payload.update(
        {
            "removedSnapshotRows": removed_snapshot_rows,
            "removedOrphanRows": removed_orphan_rows,
            "after": {key: value for key, value in after.items() if key != "manifests"},
        }
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile TuShare daily canonical rows against a completed governed full snapshot."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--apply", action="store_true", help="Apply verified removals; default is dry-run.")
    args = parser.parse_args()
    init_db()
    print(json.dumps(reconcile(args.run_id, apply=args.apply), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
