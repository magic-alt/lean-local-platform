from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable
import uuid

from ..core.config import PLATFORM_DIR


CONTRACT_PATH = PLATFORM_DIR / "config" / "tushare_contracts.v1.json"
SAFE_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


@lru_cache(maxsize=1)
def contract_snapshot() -> dict[str, Any]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if int(payload.get("schemaVersion") or 0) != 1:
        raise RuntimeError("unsupported_tushare_contract_schema")
    contracts = payload.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        raise RuntimeError("empty_tushare_contract_snapshot")
    dataset_keys: set[str] = set()
    source_tables: set[str] = set()
    for item in contracts:
        dataset_key = str(item.get("datasetKey") or "")
        source_table = str(item.get("sourceTable") or "")
        if not SAFE_IDENTIFIER.fullmatch(dataset_key):
            raise RuntimeError(f"invalid_tushare_dataset_key:{dataset_key}")
        if not SAFE_IDENTIFIER.fullmatch(source_table):
            raise RuntimeError(f"invalid_tushare_source_table:{source_table}")
        if dataset_key in dataset_keys or source_table in source_tables:
            raise RuntimeError(f"duplicate_tushare_contract:{dataset_key}")
        dataset_keys.add(dataset_key)
        source_tables.add(source_table)
        fields = item.get("fields") or []
        field_names = [str(field.get("name") or "") for field in fields]
        if len(field_names) != len(set(field_names)):
            raise RuntimeError(f"duplicate_tushare_contract_field:{dataset_key}")
        if item.get("status") == "active" and not item.get("contractComplete"):
            raise RuntimeError(f"incomplete_active_tushare_contract:{dataset_key}")
    return payload


def all_contracts() -> list[dict[str, Any]]:
    return [dict(item) for item in contract_snapshot()["contracts"]]


@lru_cache(maxsize=1)
def _contract_index() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for contract in contract_snapshot()["contracts"]:
        result[str(contract["datasetKey"])] = contract
        api_name = str(contract["apiName"])
        result.setdefault(api_name, contract)
    return result


def contract_for(dataset_or_api: str) -> dict[str, Any] | None:
    item = _contract_index().get(str(dataset_or_api).strip().lower())
    return dict(item) if item else None


def contract_public_item(contract: dict[str, Any], *, include_fields: bool = False) -> dict[str, Any]:
    item = {
        "datasetKey": contract["datasetKey"],
        "apiName": contract["apiName"],
        "assetClass": contract["assetClass"],
        "title": contract["title"],
        "status": contract["status"],
        "documentationUrl": contract["documentationUrl"],
        "contractVersion": contract_snapshot()["contractVersion"],
        "storageTier": contract["storageTier"],
        "sourceTable": contract["sourceTable"],
        "deliveryMethod": contract.get("deliveryMethod") or "pro_api",
        "naturalKey": list(contract.get("naturalKey") or []),
        "fieldCoverage": {
            "documented": len(contract.get("fields") or []),
            "typed": len(contract.get("fields") or []),
            "complete": bool(contract.get("contractComplete")),
        },
    }
    if include_fields:
        item["fields"] = list(contract.get("fields") or [])
    return item


def coverage_report(registered_specs: Iterable[Any] = ()) -> dict[str, Any]:
    registered_keys = {str(getattr(item, "key", "")) for item in registered_specs}
    registered_apis = {str(getattr(item, "api_name", "")) for item in registered_specs}
    contracts = contract_snapshot()["contracts"]
    active = [item for item in contracts if item["status"] == "active"]
    retired = [item for item in contracts if item["status"] == "retired"]
    wired = [
        item for item in active
        if item["datasetKey"] in registered_keys or item["apiName"] in registered_apis
    ]
    by_asset: dict[str, dict[str, int]] = {}
    for item in contracts:
        summary = by_asset.setdefault(
            str(item["assetClass"]),
            {"documented": 0, "active": 0, "retired": 0, "contractComplete": 0, "runtimeWired": 0},
        )
        summary["documented"] += 1
        summary[str(item["status"])] += 1
        summary["contractComplete"] += int(bool(item.get("contractComplete")))
        summary["runtimeWired"] += int(item in wired)
    storage_tiers: dict[str, int] = {}
    for item in active:
        tier = str(item["storageTier"])
        storage_tiers[tier] = storage_tiers.get(tier, 0) + 1
    return {
        "provider": "tushare",
        "contractVersion": contract_snapshot()["contractVersion"],
        "asOfDate": contract_snapshot()["asOfDate"],
        "documented": len(contracts),
        "active": len(active),
        "retired": len(retired),
        "contractComplete": sum(bool(item.get("contractComplete")) for item in contracts),
        "runtimeWired": len(wired),
        "runtimeCoveragePercent": round((len(wired) / len(active) * 100), 2) if active else 100.0,
        "byAssetClass": by_asset,
        "storageTiers": storage_tiers,
        "documentationUrl": contract_snapshot()["documentationUrl"],
    }


def list_public_contracts(
    *,
    asset_class: str | None = None,
    status: str | None = None,
    include_fields: bool = False,
) -> dict[str, Any]:
    items = all_contracts()
    if asset_class:
        items = [item for item in items if item["assetClass"] == asset_class]
    if status:
        items = [item for item in items if item["status"] == status]
    return {
        **coverage_report(),
        "items": [contract_public_item(item, include_fields=include_fields) for item in items],
        "count": len(items),
    }


def sync_contract_catalog() -> dict[str, int]:
    """Materialize the checked-in provider contract into the v2 governance tables."""
    from ..db import db, json_dump, utc_now

    provider_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "lean:data-provider:tushare"))
    snapshot = contract_snapshot()
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into data_providers_v2
                (id,provider_key,display_name,priority,status,metadata_json,created_at,updated_at)
            values (?,'tushare','TuShare Pro',100,'active',?,?,?)
            on conflict(provider_key) do update set
                display_name=excluded.display_name,status=excluded.status,
                metadata_json=excluded.metadata_json,updated_at=excluded.updated_at
            """,
            (
                provider_id,
                json_dump({"documentationUrl": snapshot["documentationUrl"], "contractVersion": snapshot["contractVersion"]}),
                now,
                now,
            ),
        )
        existing_datasets = connection.execute(
            """
            select count(*) as count from provider_datasets_v2
            where provider_id=? and contract_version=?
            """,
            (provider_id, snapshot["contractVersion"]),
        ).fetchone()
        existing_contracts = connection.execute(
            """
            select count(*) as count
            from dataset_contract_versions_v2 contract
            join provider_datasets_v2 dataset on dataset.id=contract.provider_dataset_id
            where dataset.provider_id=? and contract.contract_version=?
            """,
            (provider_id, snapshot["contractVersion"]),
        ).fetchone()
        if (
            existing_datasets
            and existing_contracts
            and int(existing_datasets["count"] or 0) == len(snapshot["contracts"])
            and int(existing_contracts["count"] or 0) == len(snapshot["contracts"])
        ):
            return {"providers": 1, "datasets": len(snapshot["contracts"]), "contracts": len(snapshot["contracts"])}
        for contract in snapshot["contracts"]:
            dataset_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"lean:data-provider:tushare:{contract['datasetKey']}:{snapshot['contractVersion']}",
                )
            )
            contract_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{dataset_id}:contract"))
            contract_document = {
                "naturalKey": contract.get("naturalKey") or [],
                "fields": contract.get("fields") or [],
                "storageTier": contract["storageTier"],
                "sourceTable": contract["sourceTable"],
                "deliveryMethod": contract.get("deliveryMethod") or "pro_api",
            }
            digest = hashlib.sha256(
                json.dumps(contract_document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            connection.execute(
                """
                insert into provider_datasets_v2
                    (id,provider_id,dataset_key,api_name,asset_class,contract_version,
                     storage_tier,status,permission_status,documentation_url,created_at,updated_at)
                values (?,?,?,?,?,?,?,?, 'unknown',?,?,?)
                on conflict(provider_id,dataset_key,contract_version) do update set
                    api_name=excluded.api_name,asset_class=excluded.asset_class,
                    storage_tier=excluded.storage_tier,status=excluded.status,
                    documentation_url=excluded.documentation_url,updated_at=excluded.updated_at
                """,
                (
                    dataset_id,
                    provider_id,
                    contract["datasetKey"],
                    contract["apiName"],
                    contract["assetClass"],
                    snapshot["contractVersion"],
                    contract["storageTier"],
                    contract["status"],
                    contract["documentationUrl"],
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                insert into dataset_contract_versions_v2
                    (id,provider_dataset_id,contract_version,effective_from,effective_to,
                     natural_key_json,fields_json,contract_sha256,created_at)
                values (?,?,?,?,null,?,?,?,?)
                on conflict(provider_dataset_id,contract_version) do update set
                    natural_key_json=excluded.natural_key_json,
                    fields_json=excluded.fields_json,
                    contract_sha256=excluded.contract_sha256
                """,
                (
                    contract_id,
                    dataset_id,
                    snapshot["contractVersion"],
                    snapshot["asOfDate"],
                    json_dump(contract_document["naturalKey"]),
                    json_dump(contract_document["fields"]),
                    digest,
                    now,
                ),
            )
    return {"providers": 1, "datasets": len(snapshot["contracts"]), "contracts": len(snapshot["contracts"])}
