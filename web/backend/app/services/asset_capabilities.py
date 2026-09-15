from __future__ import annotations

import json
import os
import uuid
from typing import Any

from ..db import database_backend, db, json_dump, rows_to_dicts, utc_now
from . import market_lake
from .instrument_kernel import asset_kernel_descriptor


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

# Explicit product-support boundary. Presence of market data is never
# sufficient to grant execution admission to another instrument subtype.
EXECUTION_ENABLED_SCOPES = frozenset(
    {
        ("equity", "china", "china", "daily", "trade"),
    }
)


def _scope_key(
    asset_class: str,
    market: str,
    venue: str,
    resolution: str,
    data_type: str,
) -> tuple[str, str, str, str, str]:
    return (
        asset_class.lower(),
        market.lower(),
        venue.lower(),
        resolution.lower(),
        data_type.lower(),
    )


def _available_scope_state(
    *,
    asset_class: str,
    market: str,
    venue: str,
    resolution: str,
    data_type: str,
) -> tuple[str, str | None]:
    key = _scope_key(asset_class, market, venue, resolution, data_type)
    if key in EXECUTION_ENABLED_SCOPES:
        return "executable", None
    return "data_ready", "execution_adapter_not_certified"


def _kernel(asset_class: str, venue: str) -> dict[str, Any]:
    return asset_kernel_descriptor(asset_class, venue=venue)


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
    if asset_class == "etf":
        # ETF metadata must come from ETF/fund endpoints. The equity Security
        # Master and equity Parquet carrier are not subtype evidence.
        metadata = connection.execute(
            "select count(*) as count from provider_raw_records "
            "where dataset_key in ('etf_basic','fund_basic')"
        ).fetchone()["count"]
        return int(metadata or 0), 0

    rows = sum(
        int(market_lake.aggregate(**scope, columns="count(*) as count").get("count") or 0)
        for scope in market_lake.matching_scopes(
            kind="bars", asset_class=asset_class, resolution=resolution,
        )
    )
    metadata = connection.execute(
        "select count(*) as count from instruments where asset_class=?",
        (asset_class,),
    ).fetchone()["count"]
    return int(metadata or 0), int(rows or 0)


def _decorate(item: dict[str, Any]) -> dict[str, Any]:
    result = dict(item)
    descriptor = _kernel(str(result["asset_class"]), str(result["venue"]))
    result["instrument_contract"] = descriptor
    raw_evidence = result.get("evidence") or result.get("evidence_json") or {}
    if isinstance(raw_evidence, str):
        try:
            raw_evidence = json.loads(raw_evidence)
        except (TypeError, ValueError):
            raw_evidence = {}
    evidence = dict(raw_evidence) if isinstance(raw_evidence, dict) else {}
    evidence.update(
        {
            "instrumentSchemaVersion": 1,
            "instrumentAssetClass": descriptor["instrumentAssetClass"],
            "instrumentSubtype": descriptor["instrumentSubtype"],
            "storageAssetClass": descriptor["storageAssetClass"],
            "certificationScopeKey": descriptor["certificationScopeKey"],
            "executionCertified": descriptor["executionCertified"],
        }
    )
    if descriptor["storageAssetClass"] != result["asset_class"]:
        evidence["sharedStorageCarrierOnly"] = True
        evidence["subtypeEvidenceRequired"] = True
    result["evidence"] = evidence
    return result


def _local_lake_capabilities() -> list[dict[str, Any]]:
    """Compute fail-closed readiness from the mounted Parquet lake.

    A physical storage mapping is not an instrument certification. In
    particular, ETF bars may ultimately live in the equity carrier, but the
    generic equity lake cannot prove ETF subtype membership on its own.
    """

    now = utc_now()
    items: list[dict[str, Any]] = []
    for asset_class, market, venue, resolution, data_type in CAPABILITY_SCOPES:
        descriptor = _kernel(asset_class, venue)
        storage_class = str(descriptor["storageAssetClass"])
        scopes = market_lake.matching_scopes(
            kind="bars", asset_class=storage_class, market=market,
            venue=venue, resolution=resolution, data_type=data_type,
        )
        carrier_available = bool(scopes)
        shared_carrier = storage_class != asset_class

        if shared_carrier:
            # Shared carrier presence is visible as evidence but cannot be used
            # as subtype-specific readiness.
            state = "unavailable"
            reason = "instrument_subtype_evidence_missing" if carrier_available else "local_parquet_scope_missing"
        elif carrier_available:
            state, reason = _available_scope_state(
                asset_class=asset_class,
                market=market,
                venue=venue,
                resolution=resolution,
                data_type=data_type,
            )
        else:
            state, reason = "unavailable", "local_parquet_scope_missing"

        items.append(
            _decorate(
                {
                    "id": str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"local-lake:{asset_class}:{market}:{venue}:{resolution}:{data_type}",
                        )
                    ),
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
                        "schemaVersion": 2,
                        "derivedFromParquetLake": True,
                        "localOnly": True,
                        "scopeAvailable": carrier_available and not shared_carrier,
                        "sharedStorageScopeAvailable": carrier_available and shared_carrier,
                        "rowCountExact": False,
                        "executionEnabled": state == "executable",
                    },
                    "refreshed_at": now,
                }
            )
        )
    return items


def refresh_capabilities() -> list[dict[str, Any]]:
    if (
        database_backend() == "postgresql"
        and os.environ.get("LEAN_CAPABILITY_BACKEND", "local_parquet").strip().lower() != "database"
    ):
        return _local_lake_capabilities()

    now = utc_now()
    with db() as connection:
        for asset_class, market, venue, resolution, data_type in CAPABILITY_SCOPES:
            metadata_count, row_count = _counts(connection, asset_class, resolution)
            if row_count > 0:
                state, reason = _available_scope_state(
                    asset_class=asset_class,
                    market=market,
                    venue=venue,
                    resolution=resolution,
                    data_type=data_type,
                )
            elif metadata_count > 0:
                state, reason = "metadata_only", "canonical_rows_missing"
            else:
                state, reason = "unavailable", "metadata_and_canonical_rows_missing"

            key = f"{asset_class}:{market}:{venue}:{resolution}:{data_type}"
            descriptor = _kernel(asset_class, venue)
            evidence = {
                "schemaVersion": 2,
                "metadataCount": metadata_count,
                "canonicalRowCount": row_count,
                "derivedFromParquetLake": True,
                "executionEnabled": state == "executable",
                "instrumentAssetClass": descriptor["instrumentAssetClass"],
                "instrumentSubtype": descriptor["instrumentSubtype"],
                "storageAssetClass": descriptor["storageAssetClass"],
                "certificationScopeKey": descriptor["certificationScopeKey"],
                "sharedStorageCarrierOnly": descriptor["storageAssetClass"] != asset_class,
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
                    str(uuid.uuid5(uuid.NAMESPACE_URL, key)),
                    asset_class,
                    market,
                    venue,
                    resolution,
                    data_type,
                    state,
                    metadata_count,
                    row_count,
                    reason,
                    json_dump(evidence),
                    now,
                ),
            )
        rows = connection.execute(
            "select * from asset_capabilities order by asset_class,resolution,market,venue"
        ).fetchall()

    return [_decorate(item) for item in rows_to_dicts(rows)]


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
            item
            for item in items
            if item["asset_class"] == normalized
            and item["market"] == market.lower()
            and item["venue"] == (venue or market).lower()
            and item["resolution"] == resolution.lower()
            and item["data_type"] == data_type.lower()
        ),
        None,
    )
    if match:
        return match
    result = {
        "asset_class": normalized,
        "market": market.lower(),
        "venue": (venue or market).lower(),
        "resolution": resolution.lower(),
        "data_type": data_type.lower(),
        "state": "unavailable",
        "metadata_count": 0,
        "canonical_row_count": 0,
        "executable_reason": "capability_scope_not_registered",
        "evidence": {"schemaVersion": 2},
    }
    try:
        return _decorate(result)
    except Exception:
        return result


def capability_payload() -> dict[str, Any]:
    items = refresh_capabilities()
    return {
        "schemaVersion": 2,
        "instrumentSchemaVersion": 1,
        "items": items,
        "count": len(items),
        "states": ["unavailable", "metadata_only", "data_ready", "executable"],
    }


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
