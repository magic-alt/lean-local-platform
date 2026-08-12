from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from typing import Any
import uuid

from ..db import bulk_db, json_dump, utc_now
from .tushare_contracts import SAFE_IDENTIFIER, contract_for


LOOKUP_CHUNK_SIZE = 500


def _chunks(values: list[str], size: int = LOOKUP_CHUNK_SIZE) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _date_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


def _datetime_value(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return f"{value.isoformat()} 00:00:00"
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]} 00:00:00"
    return text.replace("T", " ", 1)


def _decimal_value(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None


def _integer_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) else None


def _boolean_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return 1
        if lowered in {"0", "false", "no", "n", "off"}:
            return 0
    return int(bool(value))


def _typed_value(value: Any, field_type: str) -> Any:
    if field_type == "date":
        return _date_value(value)
    if field_type == "datetime":
        return _datetime_value(value)
    if field_type == "decimal":
        return _decimal_value(value)
    if field_type == "integer":
        return _integer_value(value)
    if field_type == "boolean":
        return _boolean_value(value)
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    return str(value)


def _payload(row: dict[str, Any]) -> tuple[str, str]:
    serialized = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return serialized, hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _natural_key_hash(contract: dict[str, Any], row: dict[str, Any]) -> str:
    values = []
    for name in contract.get("naturalKey") or []:
        field = next((item for item in contract.get("fields") or [] if item["name"] == name), None)
        provider_name = str(field.get("providerName") or name) if field else name
        values.append(row.get(provider_name, row.get(name)))
    if not values or all(value in (None, "") for value in values):
        _, digest = _payload(row)
        return digest
    serialized = json.dumps(values, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def persist_typed_source_rows(
    dataset_key: str,
    rows: list[dict[str, Any]],
    batch_id: str,
) -> dict[str, int]:
    if not rows or os.environ.get("LEAN_TUSHARE_TYPED_SOURCE_WRITES", "1").lower() in {"0", "false", "no", "off"}:
        return {"scanned": len(rows), "inserted": 0, "revised": 0, "unchanged": len(rows)}
    contract = contract_for(dataset_key)
    if not contract or contract["storageTier"] == "columnar":
        return {"scanned": len(rows), "inserted": 0, "revised": 0, "unchanged": len(rows)}
    table = str(contract["sourceTable"])
    if not SAFE_IDENTIFIER.fullmatch(table):
        raise RuntimeError(f"unsafe_tushare_source_table:{table}")
    fields = list(contract.get("fields") or [])
    field_names = [str(field["name"]) for field in fields]
    if any(not SAFE_IDENTIFIER.fullmatch(name) for name in field_names):
        raise RuntimeError(f"unsafe_tushare_source_field:{table}")

    prepared: dict[str, dict[str, Any]] = {}
    for row in rows:
        clean_row = {str(key): (value.item() if hasattr(value, "item") else value) for key, value in row.items()}
        natural_hash = _natural_key_hash(contract, clean_row)
        _, payload_hash = _payload(clean_row)
        prepared[natural_hash] = {
            "row": clean_row,
            "payloadHash": payload_hash,
        }
    existing: dict[str, dict[str, Any]] = {}
    inserted = revised = 0
    unchanged = len(rows) - len(prepared)
    now = utc_now()
    with bulk_db() as connection:
        for natural_hashes in _chunks(list(prepared)):
            placeholders = ",".join("?" for _ in natural_hashes)
            result_rows = connection.execute(
                f"""
                select `_natural_key_hash`,`_revision_no`,`_payload_hash`
                from `{table}`
                where `_is_current`=1 and `_natural_key_hash` in ({placeholders})
                """,
                tuple(natural_hashes),
            ).fetchall()
            existing.update({str(item["_natural_key_hash"]): dict(item) for item in result_rows})
        metadata_columns = [
            "_observation_id", "_batch_id", "_natural_key_hash", "_revision_no", "_is_current",
            "_published_at", "_source_updated_at", "_observed_at", "_valid_from", "_valid_to",
            "_payload_hash",
        ]
        columns = metadata_columns + field_names
        quoted_columns = ",".join(f"`{name}`" for name in columns)
        value_placeholders = ",".join("?" for _ in columns)
        parameters: list[tuple[Any, ...]] = []
        changed_hashes: list[str] = []
        for natural_hash, item in prepared.items():
            previous = existing.get(natural_hash)
            if previous and str(previous["_payload_hash"]) == item["payloadHash"]:
                unchanged += 1
                continue
            revision = int(previous["_revision_no"] or 0) + 1 if previous else 1
            revised += int(previous is not None)
            inserted += int(previous is None)
            if previous:
                changed_hashes.append(natural_hash)
            row = item["row"]
            published = row.get("ann_date") or row.get("pub_date") or row.get("update_time")
            source_updated = row.get("update_time") or row.get("ann_date") or row.get("pub_date")
            observation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"tushare:{table}:{natural_hash}:{item['payloadHash']}"))
            values: list[Any] = [
                observation_id,
                batch_id,
                natural_hash,
                revision,
                1,
                _datetime_value(published),
                _datetime_value(source_updated),
                now,
                None,
                None,
                item["payloadHash"],
            ]
            for field in fields:
                provider_name = str(field.get("providerName") or field["name"])
                value = row.get(provider_name, row.get(str(field["name"])))
                values.append(_typed_value(value, str(field.get("type") or "string")))
            parameters.append(tuple(values))
        for natural_hashes in _chunks(changed_hashes):
            update_placeholders = ",".join("?" for _ in natural_hashes)
            connection.execute(
                f"update `{table}` set `_is_current`=0,`_valid_to`=? where `_is_current`=1 and `_natural_key_hash` in ({update_placeholders})",
                (now, *natural_hashes),
            )
        if parameters:
            connection.executemany(
                f"insert into `{table}` ({quoted_columns}) values ({value_placeholders})",
                parameters,
            )
    return {"scanned": len(rows), "inserted": inserted, "revised": revised, "unchanged": unchanged}
