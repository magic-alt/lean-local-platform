from __future__ import annotations

import os
import uuid
from typing import Any

from ..db import database_backend, db, json_dump, rows_to_dicts, utc_now
from . import market_lake


CAPABILITY_SCOPES = (
    ("equity", "china", "china", "daily", "trade"),
    ("index", "china", "china", "daily", "trade"),
    ("etf", "china", "china", "daily", "trade"),
    ("future", "china", "china", "daily", "trade"),
    ("option", "china", "china", "daily", "trade"),
    ("convertible_bond", "china", "china", "daily", "trade"),
    ("equity", "china", "china", "minute", "trade"),
    ("equity", "china", "china", "tick", "trade"),
)


def _counts(connection: Any, asset_class: str, resolution: str) -> tuple[int, int]:
    if asset_class == "future":
        metadata = connection.execute("select count(*) as count from futures_contracts").fetchone()["count"]
        rows = connection.execute("select count(*) as count from futures_daily_bars").fetchone()["count"]
        return int(metadata or 0), int(rows or 0)
    if asset_class == "convertible_bond":
        metadata = connection.execute("select count(*) as count from cbond_securities").fetchone()["count"]
        rows = connection.execute("select count(*) as count from cbond_daily_bars").fetchone()["count"]
        return int(metadata or 0), int(rows or 0)
    if asset_class == "option":
        metadata = connection.execute(
            "select count(*) as count from provider_raw_records where dataset_key='opt_basic'"
        ).fetchone()["count"]
        return int(metadata or 0), 0
    lake_class = "equity" if asset_class == "etf" else asset_class
    rows = sum(
        int(market_lake.aggregate(**scope, columns="count(*) as count").get("count") or 0)
        for scope in market_lake.matching_scopes(
            kind="bars", asset_class=lake_class, resolution=resolution,
        )
    )
    metadata_class = "equity" if asset_class == "etf" else asset_class
    metadata = connection.execute(
        "select count(*) as count from instruments where asset_class=?",
        (metadata_class,),
    ).fetchone()["count"]
    return int(metadata or 0), int(rows or 0)


def _local_lake_capabilities() -> list[dict[str, Any]]:
    """Compute executable data scopes straight from the mounted Parquet lake."""
    now = utc_now()
    items: list[dict[str, Any]] = []
    for asset_class, market, venue, resolution, data_type in CAPABILITY_SCOPES:
        lake_class = "equity" if asset_class == "etf" else asset_class
        scopes = market_lake.matching_scopes(
            kind="bars", asset_class=lake_class, market=market,
            venue=venue, resolution=resolution, data_type=data_type,
        )
        available = bool(scopes)
        state = (
            "executable" if available and asset_class in {"equity", "index"}
            else "data_ready" if available
            else "unavailable"
        )
        reason = None if state == "executable" else (
            "execution_adapter_not_certified" if available else "local_parquet_scope_missing"
        )
        items.append(
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"local-lake:{asset_class}:{market}:{venue}:{resolution}:{data_type}")),
                "asset_class": asset_class,
                "market": market,
                "venue": venue,
                "resolution": resolution,
                "data_type": data_type,
                "state": state,
                "metadata_count": 0,
                "canonical_row_count": 0,
                "executable_reason": reason,
                "evidence": {
                    "schemaVersion": 1,
                    "derivedFromParquetLake": True,
                    "localOnly": True,
                    "scopeAvailable": available,
                    "rowCountExact": False,
                },
                "refreshed_at": now,
            }
        )
    return items


def refresh_capabilities() -> list[dict[str, Any]]:
    if (
        database_backend() == "mysql"
        and os.environ.get("LEAN_CAPABILITY_BACKEND", "local_parquet").strip().lower() != "database"
    ):
        return _local_lake_capabilities()
    now = utc_now()
    with db() as connection:
        for asset_class, market, venue, resolution, data_type in CAPABILITY_SCOPES:
            metadata_count, row_count = _counts(connection, asset_class, resolution)
            state = (
                "executable" if row_count > 0 and asset_class in {"equity", "index"}
                else "data_ready" if row_count > 0
                else "metadata_only" if metadata_count > 0
                else "unavailable"
            )
            reason = None if state == "executable" else (
                "execution_adapter_not_certified" if row_count > 0
                else
                "canonical_rows_missing" if metadata_count > 0 else "metadata_and_canonical_rows_missing"
            )
            key = f"{asset_class}:{market}:{venue}:{resolution}:{data_type}"
            evidence = {
                "schemaVersion": 1,
                "metadataCount": metadata_count,
                "canonicalRowCount": row_count,
                "derivedFromParquetLake": True,
            }
            connection.execute(
                """
                insert into asset_capabilities
                    (id,asset_class,market,venue,resolution,data_type,state,metadata_count,
                     canonical_row_count,executable_reason,evidence_json,refreshed_at)
                values (?,?,?,?,?,?,?,?,?,?,?,?)
                on conflict(asset_class,market,venue,resolution,data_type) do update set
                    state=excluded.state,metadata_count=excluded.metadata_count,
                    canonical_row_count=excluded.canonical_row_count,
                    executable_reason=excluded.executable_reason,evidence_json=excluded.evidence_json,
                    refreshed_at=excluded.refreshed_at
                """,
                (
                    str(uuid.uuid5(uuid.NAMESPACE_URL, key)), asset_class, market, venue,
                    resolution, data_type, state, metadata_count, row_count, reason,
                    json_dump(evidence), now,
                ),
            )
        rows = connection.execute(
            "select * from asset_capabilities order by asset_class,resolution,market,venue"
        ).fetchall()
    return rows_to_dicts(rows)


def capability_for_scope(
    *,
    asset_class: str,
    market: str,
    venue: str | None,
    resolution: str,
    data_type: str,
) -> dict[str, Any]:
    normalized = "convertible_bond" if asset_class.lower() in {"cbond", "convertible-bond"} else asset_class.lower()
    items = refresh_capabilities()
    match = next(
        (
            item for item in items
            if item["asset_class"] == normalized
            and item["market"] == market.lower()
            and item["venue"] == (venue or market).lower()
            and item["resolution"] == resolution.lower()
            and item["data_type"] == data_type.lower()
        ),
        None,
    )
    return match or {
        "asset_class": normalized,
        "market": market.lower(),
        "venue": (venue or market).lower(),
        "resolution": resolution.lower(),
        "data_type": data_type.lower(),
        "state": "unavailable",
        "metadata_count": 0,
        "canonical_row_count": 0,
        "executable_reason": "capability_scope_not_registered",
    }


def capability_payload() -> dict[str, Any]:
    items = refresh_capabilities()
    return {"items": items, "count": len(items), "states": ["unavailable", "metadata_only", "data_ready", "executable"]}


def require_executable_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    capability = capability_for_scope(
        asset_class=str(parameters.get("assetClass") or "equity"),
        market=str(parameters.get("market") or parameters.get("venue") or "china"),
        venue=str(parameters.get("venue") or parameters.get("market") or "china"),
        resolution=str(parameters.get("resolution") or "daily"),
        data_type=str(parameters.get("dataType") or "trade"),
    )
    if capability["state"] != "executable":
        raise ValueError(
            "asset_capability_not_executable:"
            f"{capability['asset_class']}:{capability['resolution']}:{capability['state']}:"
            f"{capability.get('executable_reason') or 'not_ready'}"
        )
    return capability
