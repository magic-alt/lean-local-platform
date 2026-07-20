from __future__ import annotations

from collections.abc import Callable
import gzip
import hashlib
import json
from typing import Any

from ..db import bulk_db, db
from .data_sync import DATASET_REGISTRY, _archive_raw_batch
from .db_object_store import read_bytes


ProgressCallback = Callable[[dict[str, Any]], None]


def _emit(callback: ProgressCallback | None, **payload: Any) -> None:
    if callback is not None:
        callback(payload)


def _active_sync() -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            """
            select id,status from data_sync_runs
            where status in ('queued','running','cancelling')
            order by created_at desc limit 1
            """
        ).fetchone()
    return dict(row) if row else None


def legacy_json_inventory() -> dict[str, Any]:
    with db() as connection:
        rows = connection.execute(
            """
            select dataset_key,count(*) as rows,
                   coalesce(sum(length(payload_json)),0) as json_bytes
            from provider_raw_records
            where provider='tushare' and payload_json<>''
            group by dataset_key order by dataset_key
            """
        ).fetchall()
    datasets = [
        {
            "dataset": str(row["dataset_key"]),
            "rows": int(row["rows"] or 0),
            "jsonBytes": int(row["json_bytes"] or 0),
        }
        for row in rows
    ]
    return {
        "rows": sum(item["rows"] for item in datasets),
        "jsonBytes": sum(item["jsonBytes"] for item in datasets),
        "datasets": datasets,
    }


def _next_payload_batch(dataset: str, after_key: str, limit: int) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select record_key,payload_json from provider_raw_records
            where provider='tushare' and dataset_key=? and payload_json<>'' and record_key>?
            order by record_key limit ?
            """,
            (dataset, after_key, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def _clear_key_range(dataset: str, first_key: str, last_key: str, expected: int) -> int:
    with bulk_db() as connection:
        cursor = connection.execute(
            """
            update provider_raw_records set payload_json=''
            where provider='tushare' and dataset_key=? and payload_json<>''
              and record_key>=? and record_key<=?
            """,
            (dataset, first_key, last_key),
        )
        changed = int(cursor.rowcount or 0)
    if changed != expected:
        raise RuntimeError(
            f"Legacy JSON cleanup range changed {changed} rows; expected {expected} for {dataset}."
        )
    return changed


def _archive_and_clear_dataset(
    dataset: str,
    *,
    batch_size: int,
    callback: ProgressCallback | None,
) -> tuple[int, int]:
    spec_by_key = {item.key: item for item in DATASET_REGISTRY}
    spec = spec_by_key[dataset]
    # Legacy stock_basic includes one invalid historical symbol that was
    # deliberately rejected by the canonical table. Preserve the whole small
    # dataset before removing its row JSON.
    if dataset == "stock_basic" and not spec.retain_raw:
        from dataclasses import replace

        spec = replace(spec, retain_raw=True)
    cleared = 0
    archived = 0
    after_key = ""
    while True:
        records = _next_payload_batch(dataset, after_key, batch_size)
        if not records:
            break
        first_key = str(records[0]["record_key"])
        last_key = str(records[-1]["record_key"])
        payloads: list[dict[str, Any]] = []
        for record in records:
            try:
                payload = json.loads(str(record["payload_json"]))
            except (TypeError, ValueError) as exc:
                raise RuntimeError(f"Invalid legacy JSON in {dataset}:{record['record_key']}") from exc
            if not isinstance(payload, dict):
                raise RuntimeError(f"Legacy JSON is not an object in {dataset}:{record['record_key']}")
            payloads.append(payload)
        range_id = hashlib.sha256(f"{dataset}:{first_key}:{last_key}".encode("utf-8")).hexdigest()[:32]
        run_id = f"legacy:{dataset}:{range_id}"
        if len(run_id) > 64:
            raise RuntimeError(f"Legacy archive run id exceeds MySQL limit: {run_id}")
        archive = _archive_raw_batch(spec, payloads, run_id)
        if not archive or int(archive.get("rowCount") or 0) != len(records):
            raise RuntimeError(f"Legacy archive was not persisted for {dataset}:{first_key}-{last_key}")
        stored = read_bytes(str(archive["objectId"]))
        restored = json.loads(gzip.decompress(stored))
        if not isinstance(restored, list) or len(restored) != len(records):
            raise RuntimeError(f"Legacy archive verification failed for {dataset}:{first_key}-{last_key}")
        _clear_key_range(dataset, first_key, last_key, len(records))
        archived += len(records)
        cleared += len(records)
        after_key = last_key
        _emit(callback, phase="archive", dataset=dataset, archived=archived, cleared=cleared)
    return archived, cleared


def _clear_lossless_dataset(
    dataset: str,
    *,
    batch_size: int,
    callback: ProgressCallback | None,
) -> int:
    cleared = 0
    after_key = ""
    while True:
        records = _next_payload_batch(dataset, after_key, batch_size)
        if not records:
            break
        first_key = str(records[0]["record_key"])
        last_key = str(records[-1]["record_key"])
        _clear_key_range(dataset, first_key, last_key, len(records))
        cleared += len(records)
        after_key = last_key
        _emit(callback, phase="clear", dataset=dataset, cleared=cleared)
    return cleared


def cleanup_legacy_provider_json(
    *,
    archive_batch_size: int = 20_000,
    clear_batch_size: int = 250_000,
    callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    active = _active_sync()
    if active:
        raise RuntimeError(f"Data sync {active['id']} is {active['status']}; cleanup refused.")
    before = legacy_json_inventory()
    spec_by_key = {item.key: item for item in DATASET_REGISTRY}
    unknown = sorted({item["dataset"] for item in before["datasets"]} - set(spec_by_key))
    if unknown:
        raise RuntimeError(f"Unknown provider raw datasets cannot be cleaned safely: {', '.join(unknown)}")

    results: dict[str, Any] = {}
    for item in before["datasets"]:
        dataset = str(item["dataset"])
        spec = spec_by_key[dataset]
        # stk_limit is declared lossless and has a complete canonical status
        # table. All other current legacy datasets are archived first. The
        # stock_basic exception preserves a rejected historical anomaly.
        if dataset == "stk_limit" and not spec.retain_raw:
            cleared = _clear_lossless_dataset(
                dataset,
                batch_size=max(1, clear_batch_size),
                callback=callback,
            )
            results[dataset] = {"archived": 0, "cleared": cleared}
        else:
            archived, cleared = _archive_and_clear_dataset(
                dataset,
                batch_size=max(1, archive_batch_size),
                callback=callback,
            )
            results[dataset] = {"archived": archived, "cleared": cleared}

    after = legacy_json_inventory()
    if after["rows"] != 0 or after["jsonBytes"] != 0:
        raise RuntimeError(f"Legacy JSON cleanup incomplete: {after}")
    return {"before": before, "after": after, "datasets": results}
