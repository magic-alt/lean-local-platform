from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections import defaultdict
from dataclasses import replace
from datetime import date, timedelta
from typing import Any

from ..db import db
from .ashare_repository import upsert_index_weights
from .csi300_pit import upsert_source_artifact
from .data_sync import DATASET_REGISTRY, _raw_row_for_symbol, _save_raw, _validate_dataset_rows
from .tushare_adapter import TushareAdapter


INDEX_CODE = "CSI300"
TUSHARE_INDEX_CODE = "000300.SH"
SHADOW_UNIVERSE_CODE = "CSI300_TUSHARE"
SOURCE = "tushare:index_weight"
SNAPSHOT_SOURCE = "tushare:index_weight:snapshot"
EXPECTED_MEMBERS = 300


def _canonical_payload(rows: list[dict[str, Any]]) -> bytes:
    return json.dumps(
        sorted(rows, key=lambda row: (str(row["trade_date"]), str(row["symbol"]))),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def validate_snapshot_rows(
    rows: list[dict[str, Any]],
    *,
    expected_members: int = EXPECTED_MEMBERS,
    max_snapshot_gap_days: int = 62,
    weight_sum_tolerance: float = 0.5,
) -> dict[str, Any]:
    if not rows:
        raise ValueError("TuShare CSI300 index_weight returned no rows.")
    snapshots: dict[str, dict[str, float]] = defaultdict(dict)
    duplicate_keys: list[str] = []
    for row in rows:
        trade_date = str(row.get("trade_date") or "")[:10]
        symbol = str(row.get("symbol") or "").split(".", 1)[0]
        universe = str(row.get("universe_code") or INDEX_CODE).upper()
        try:
            date.fromisoformat(trade_date)
        except ValueError as exc:
            raise ValueError(f"Invalid CSI300 snapshot date: {trade_date!r}.") from exc
        if universe != INDEX_CODE:
            raise ValueError(f"Unexpected index_weight universe {universe!r}; expected {INDEX_CODE}.")
        if len(symbol) != 6 or not symbol.isdigit():
            raise ValueError(f"Invalid CSI300 constituent symbol: {symbol!r}.")
        try:
            weight = float(row.get("weight"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid CSI300 weight for {symbol} on {trade_date}.") from exc
        if not math.isfinite(weight) or weight <= 0:
            raise ValueError(f"Non-positive CSI300 weight for {symbol} on {trade_date}.")
        if symbol in snapshots[trade_date]:
            duplicate_keys.append(f"{trade_date}:{symbol}")
        snapshots[trade_date][symbol] = weight
    if duplicate_keys:
        raise ValueError(f"Duplicate CSI300 snapshot keys: {', '.join(duplicate_keys[:10])}.")

    dates = sorted(snapshots)
    incomplete = {item_date: len(snapshots[item_date]) for item_date in dates if len(snapshots[item_date]) != expected_members}
    if incomplete:
        sample = ", ".join(f"{key}={value}" for key, value in list(incomplete.items())[:10])
        raise ValueError(f"Incomplete CSI300 snapshots; expected {expected_members} members: {sample}.")
    bad_weight_sums = {
        item_date: round(sum(snapshots[item_date].values()), 6)
        for item_date in dates
        if abs(sum(snapshots[item_date].values()) - 100.0) > weight_sum_tolerance
    }
    if bad_weight_sums:
        sample = ", ".join(f"{key}={value}" for key, value in list(bad_weight_sums.items())[:10])
        raise ValueError(f"CSI300 snapshot weight sums are outside tolerance: {sample}.")
    gaps = []
    for previous, current in zip(dates, dates[1:]):
        days = (date.fromisoformat(current) - date.fromisoformat(previous)).days
        if days > max_snapshot_gap_days:
            gaps.append({"previous": previous, "current": current, "days": days})
    if gaps:
        raise ValueError(f"CSI300 snapshot series contains coverage gaps: {gaps[:10]}.")

    payload_sha256 = hashlib.sha256(_canonical_payload(rows)).hexdigest()
    return {
        "status": "validated",
        "indexCode": INDEX_CODE,
        "source": SOURCE,
        "snapshotCount": len(dates),
        "rowCount": len(rows),
        "memberCount": expected_members,
        "coverageStart": dates[0],
        "coverageEnd": dates[-1],
        "maxSnapshotGapDays": max(
            ((date.fromisoformat(current) - date.fromisoformat(previous)).days for previous, current in zip(dates, dates[1:])),
            default=0,
        ),
        "payloadSha256": payload_sha256,
        "isOfficialSource": False,
    }


def incomplete_snapshot_counts(
    rows: list[dict[str, Any]], *, expected_members: int = EXPECTED_MEMBERS
) -> dict[str, int]:
    counts: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        counts[str(row.get("trade_date") or "")[:10]].add(str(row.get("symbol") or "").split(".", 1)[0])
    return {snapshot_date: len(symbols) for snapshot_date, symbols in sorted(counts.items()) if len(symbols) != expected_members}


def build_snapshot_intervals(
    rows: list[dict[str, Any]],
    *,
    universe_code: str = SHADOW_UNIVERSE_CODE,
    batch_id: str,
) -> list[dict[str, Any]]:
    validate_snapshot_rows(rows)
    snapshots: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        snapshots[str(row["trade_date"])[:10]].append(row)
    dates = sorted(snapshots)
    intervals: list[dict[str, Any]] = []
    for index, snapshot_date in enumerate(dates):
        end_date = None
        if index + 1 < len(dates):
            end_date = (date.fromisoformat(dates[index + 1]) - timedelta(days=1)).isoformat()
        for row in sorted(snapshots[snapshot_date], key=lambda item: str(item["symbol"])):
            intervals.append(
                {
                    "universe_code": universe_code,
                    "symbol": str(row["symbol"]).split(".", 1)[0],
                    "start_date": snapshot_date,
                    "end_date": end_date,
                    # TuShare exposes the snapshot date but no separate announcement
                    # date.  Never back-date availability before that observed date.
                    "announce_date": snapshot_date,
                    "effective_date": snapshot_date,
                    "weight": float(row["weight"]),
                    "source": SNAPSHOT_SOURCE,
                    "batch_id": batch_id,
                }
            )
    return intervals


def replace_shadow_membership(intervals: list[dict[str, Any]], *, universe_code: str = SHADOW_UNIVERSE_CODE) -> int:
    parameters = [
        (
            universe_code,
            row["symbol"],
            row["start_date"],
            row.get("end_date"),
            row["announce_date"],
            row["effective_date"],
            row["weight"],
            row["source"],
            row["batch_id"],
        )
        for row in intervals
    ]
    with db() as connection:
        connection.execute("delete from universe_membership where universe_code=?", (universe_code,))
        for offset in range(0, len(parameters), 5000):
            connection.executemany(
                """
                insert into universe_membership
                    (universe_code,symbol,start_date,end_date,announce_date,effective_date,
                     weight,source,batch_id)
                values (?,?,?,?,?,?,?,?,?)
                """,
                parameters[offset : offset + 5000],
            )
    return len(parameters)


def import_tushare_csi300_snapshots(
    *,
    start_date: str = "2005-01-01",
    end_date: str,
    adapter: TushareAdapter | None = None,
    dry_run: bool = False,
    quarantine_incomplete: bool = False,
) -> dict[str, Any]:
    provider = adapter or TushareAdapter()
    rows = provider.index_weight_rows("000300", start_date, end_date)
    incomplete = incomplete_snapshot_counts(rows)
    if incomplete and not quarantine_incomplete:
        sample = ", ".join(f"{key}={value}" for key, value in list(incomplete.items())[:10])
        raise ValueError(f"Incomplete CSI300 snapshots; expected {EXPECTED_MEMBERS} members: {sample}.")
    usable_rows = [row for row in rows if str(row.get("trade_date") or "")[:10] not in incomplete]
    validation = validate_snapshot_rows(usable_rows)
    batch_id = str(uuid.uuid4())
    intervals = build_snapshot_intervals(usable_rows, batch_id=batch_id)
    result = {
        **validation,
        "batchId": batch_id,
        "requestedStart": start_date,
        "requestedEnd": end_date,
        "shadowUniverse": SHADOW_UNIVERSE_CODE,
        "intervalCount": len(intervals),
        "providerRowCount": len(rows),
        "quarantinedRows": len(rows) - len(usable_rows),
        "quarantinedSnapshots": incomplete,
        "dryRun": dry_run,
        "promotionStatus": "shadow_only",
        "promotionBlocker": "TuShare snapshots must be cross-checked against official CSIndex adjustment notices.",
    }
    if dry_run:
        return result

    spec = next(item for item in DATASET_REGISTRY if item.key == "index_weight")
    governed_spec = replace(spec, retain_raw=True)
    raw_rows = [_raw_row_for_symbol(governed_spec, row, None) for row in rows]
    provider_validation = _validate_dataset_rows(governed_spec, raw_rows)
    if provider_validation["status"] != "passed":
        raise ValueError(f"Provider-shape validation failed: {provider_validation}.")
    inserted, updated = _save_raw(governed_spec, raw_rows, batch_id)
    canonical = upsert_index_weights(rows, source=SOURCE, batch_id=batch_id, bulk=True)
    membership_count = replace_shadow_membership(intervals)
    upsert_source_artifact(
        index_code=SHADOW_UNIVERSE_CODE,
        source_url=f"tushare:index_weight:{TUSHARE_INDEX_CODE}:{start_date}:{end_date}",
        raw_file_hash=validation["payloadSha256"],
        content_type="application/json+gzip",
        parse_status="validated_snapshot_series_with_quarantine" if incomplete else "validated_snapshot_series",
        metadata={**result, "rawInserted": inserted, "rawUpdated": updated, "canonicalRows": canonical["count"]},
    )
    result.update(
        {
            "rawInserted": inserted,
            "rawUpdated": updated,
            "canonicalRows": canonical["count"],
            "membershipRows": membership_count,
        }
    )
    return result
