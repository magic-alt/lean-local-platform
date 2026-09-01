from __future__ import annotations

from collections import defaultdict
from datetime import date
import gzip
import hashlib
import json
import uuid
from typing import Any

from ..core.errors import LeanWebError
from ..db import bulk_db, json_dump, utc_now
from .ashare_repository import infer_exchange
from .csi300_pit import previous_trade_date
from .db_object_store import put_bytes
from .market_repository import instrument_id
from .universe_coverage import universe_spec


def build_snapshot_intervals(
    universe_code: str,
    rows: list[dict[str, Any]],
    *,
    source: str = "tushare:index_weight",
    batch_id: str | None = None,
) -> dict[str, Any]:
    spec = universe_spec(universe_code)
    if not spec or not spec.get("indexSymbol"):
        raise LeanWebError(f"{universe_code} is not a supported index universe.")
    expected = int(spec["expectedMembers"])
    grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        snapshot_date = str(row.get("trade_date") or "")[:10]
        symbol = str(row.get("symbol") or "").strip().upper()
        if snapshot_date and symbol:
            grouped[snapshot_date][symbol] = row
    snapshot_dates = sorted(grouped)
    counts = [{"date": snapshot, "count": len(grouped[snapshot])} for snapshot in snapshot_dates]
    invalid = [item for item in counts if item["count"] != expected]
    if not snapshot_dates:
        raise LeanWebError(f"No index_weight snapshots were returned for {universe_code}.")
    if invalid:
        sample = ", ".join(f"{item['date']}={item['count']}" for item in invalid[:10])
        raise LeanWebError(f"{universe_code} snapshot membership counts are incomplete: {sample}.")

    batch = batch_id or str(uuid.uuid4())
    intervals: list[dict[str, Any]] = []
    for index, snapshot in enumerate(snapshot_dates):
        next_snapshot = snapshot_dates[index + 1] if index + 1 < len(snapshot_dates) else None
        end_date = previous_trade_date(next_snapshot) if next_snapshot else None
        for symbol, row in sorted(grouped[snapshot].items()):
            intervals.append(
                {
                    "universe_code": str(universe_code).upper(),
                    "symbol": symbol,
                    "name": row.get("name") or symbol,
                    "start_date": snapshot,
                    "end_date": end_date,
                    # TuShare exposes effective snapshots, not announcement
                    # timestamps. Using the effective date as knowledge time is
                    # conservative and prevents pre-effective membership use.
                    "announce_date": snapshot,
                    "effective_date": snapshot,
                    "weight": row.get("weight"),
                    "source": source,
                    "batch_id": batch,
                    "listed_date": snapshot,
                    "delisted_date": None,
                }
            )
    return {
        "universeCode": str(universe_code).upper(),
        "batchId": batch,
        "intervals": intervals,
        "snapshotCounts": counts,
        "coverageStart": snapshot_dates[0],
        "coverageEnd": date.today().isoformat(),
        "expectedMembers": expected,
    }


def import_snapshot_history(
    universe_code: str,
    rows: list[dict[str, Any]],
    *,
    replace: bool = True,
    source: str = "tushare:index_weight",
) -> dict[str, Any]:
    built = build_snapshot_intervals(universe_code, rows, source=source)
    spec = universe_spec(universe_code) or {}
    canonical = json.dumps(
        {
            "schemaVersion": 1,
            "universeCode": built["universeCode"],
            "source": source,
            "coverageStart": built["coverageStart"],
            "coverageEnd": built["coverageEnd"],
            "snapshotCounts": built["snapshotCounts"],
            "rows": rows,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    stored = put_bytes(
        "universe-pit",
        f"{built['universeCode']}/{digest}.json.gz",
        gzip.compress(canonical, compresslevel=6, mtime=0),
        content_type="application/gzip",
        metadata={
            "universeCode": built["universeCode"],
            "source": source,
            "coverageStart": built["coverageStart"],
            "coverageEnd": built["coverageEnd"],
            "sha256Uncompressed": digest,
        },
    )
    launch_covered = built["coverageStart"] <= str(spec.get("launchDate") or built["coverageStart"])
    imported = _materialize_snapshot_intervals(
        built["universeCode"],
        built["intervals"],
        source=source,
        batch_id=built["batchId"],
        replace=replace,
    )
    from .universe_coverage import record_universe_coverage

    record_universe_coverage(
        built["universeCode"],
        coverage_start=built["coverageStart"],
        coverage_end=built["coverageEnd"],
        status="complete" if launch_covered else "partial",
        source=source,
        batch_id=built["batchId"],
        bundle_sha256=digest,
        validation={
            "materializedIntervals": imported,
            "snapshotCounts": built["snapshotCounts"],
            "bundleObjectId": stored.get("id"),
        },
    )
    return {
        **{key: value for key, value in built.items() if key != "intervals"},
        "membershipRows": imported,
        "bundleObjectId": stored.get("id"),
        "bundleSha256": digest,
        "launchCovered": launch_covered,
        "status": "complete" if launch_covered else "partial",
    }


def _materialize_snapshot_intervals(
    universe_code: str,
    intervals: list[dict[str, Any]],
    *,
    source: str,
    batch_id: str,
    replace: bool,
) -> int:
    """Bulk-load snapshot intervals without one transaction per membership."""
    now = utc_now()
    first_by_symbol: dict[str, dict[str, Any]] = {}
    for item in intervals:
        current = first_by_symbol.get(item["symbol"])
        if current is None or item["start_date"] < current["start_date"]:
            first_by_symbol[item["symbol"]] = item
    security_parameters = []
    instrument_parameters = []
    for symbol, item in sorted(first_by_symbol.items()):
        exchange = infer_exchange(symbol)
        name = item.get("name") or symbol
        listed_date = item["start_date"]
        security_parameters.append(
            (symbol, name, exchange, "china", listed_date, None, "listed", 0, None, json_dump([]), now, now)
        )
        instrument_parameters.append(
            (
                instrument_id("equity", "china", symbol, "china"),
                symbol,
                symbol,
                name,
                "equity",
                "china",
                exchange,
                "china",
                "CNY",
                listed_date,
                "active",
                100,
                0.01,
                json_dump({"universeSource": source}),
                "securities",
                now,
                now,
            )
        )
    membership_parameters = [
        (
            universe_code,
            item["symbol"],
            item["start_date"],
            item.get("end_date"),
            item.get("announce_date") or item["start_date"],
            item.get("effective_date") or item["start_date"],
            item.get("weight"),
            source,
            batch_id,
        )
        for item in intervals
    ]
    with bulk_db() as connection:
        if replace:
            connection.execute("delete from universe_membership where universe_code=?", (universe_code,))
        for offset in range(0, len(security_parameters), 5_000):
            connection.executemany(
                """
                insert into securities
                    (symbol,name,exchange,market,listed_date,delisted_date,status,is_st,
                     industry,concepts_json,created_at,updated_at)
                values (?,?,?,?,?,?,?,?,?,?,?,?)
                on conflict(symbol) do update set
                    name=case when excluded.name=excluded.symbol and securities.name<>securities.symbol
                              then securities.name else excluded.name end,
                    exchange=excluded.exchange,
                    listed_date=case
                        when securities.listed_date<=excluded.listed_date then securities.listed_date
                        else excluded.listed_date end,
                    updated_at=excluded.updated_at
                """,
                security_parameters[offset : offset + 5_000],
            )
        for offset in range(0, len(instrument_parameters), 5_000):
            connection.executemany(
                """
                insert into instruments
                    (instrument_id,symbol,normalized_symbol,name,asset_class,market,exchange,venue,
                     currency,listed_date,status,lot_size,tick_size,metadata_json,
                     source,created_at,updated_at)
                values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                on conflict(instrument_id) do update set
                    name=case when excluded.name=excluded.symbol and instruments.name<>instruments.symbol
                              then instruments.name else excluded.name end,
                    exchange=excluded.exchange,
                    listed_date=case when instruments.listed_date is null then excluded.listed_date
                                     else min(instruments.listed_date,excluded.listed_date) end,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                instrument_parameters[offset : offset + 5_000],
            )
        for offset in range(0, len(membership_parameters), 5_000):
            connection.executemany(
                """
                insert into universe_membership
                    (universe_code,symbol,start_date,end_date,announce_date,effective_date,
                     weight,source,batch_id)
                values (?,?,?,?,?,?,?,?,?)
                on conflict(universe_code,symbol,start_date) do update set
                    end_date=excluded.end_date,
                    announce_date=excluded.announce_date,
                    effective_date=excluded.effective_date,
                    weight=excluded.weight,
                    source=excluded.source,
                    batch_id=excluded.batch_id
                """,
                membership_parameters[offset : offset + 5_000],
            )
    return len(membership_parameters)
