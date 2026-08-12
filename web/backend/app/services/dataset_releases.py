from __future__ import annotations

import hashlib
from contextlib import nullcontext
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


def _release_id(dataset_version: str, manifest_sha256: str) -> str:
    digest = hashlib.sha256(f"{dataset_version}:{manifest_sha256}".encode("utf-8")).hexdigest()
    return f"release:{digest}"


def certify_parquet_dataset(
    dataset_id: str,
    *,
    dataset_version: str,
    manifest_sha256: str,
    qa_report_id: str,
    certified_at: str | None = None,
    connection: Any | None = None,
) -> dict[str, Any]:
    """Create the immutable authority record for a certified Parquet dataset."""
    with (db() if connection is None else nullcontext(connection)) as conn:
        row = conn.execute(
            "select * from parquet_datasets where id=?",
            (dataset_id,),
        ).fetchone()
        if not row:
            raise ValueError(f"parquet_dataset_missing:{dataset_id}")
        item = dict(row)
        now = certified_at or utc_now()
        release_id = _release_id(dataset_version, manifest_sha256)
        metadata = {
            "schemaVersion": 1,
            "authority": "dataset_releases",
            "parquetDatasetId": dataset_id,
            "datasetVersion": dataset_version,
            "fileManifestSha256": manifest_sha256,
            "qaReportId": qa_report_id,
        }
        conn.execute(
            """
            update dataset_releases
            set status='superseded',revoked_at=coalesce(revoked_at,?),
                revoke_reason=coalesce(revoke_reason,'superseded_by_recertification')
            where status='active' and source=? and asset_class=? and market=?
              and coalesce(venue,'')=coalesce(?, '') and resolution=? and data_type=?
              and adjust_mode=? and id<>?
            """,
            (
                now,
                item["source"], item["asset_class"], item["market"], item.get("venue"),
                item["resolution"], item["data_type"], item["adjust"], release_id,
            ),
        )
        conn.execute(
            """
            insert into dataset_releases
                (id,dataset_key,dataset_version,source,asset_class,market,venue,resolution,
                 data_type,adjust_mode,parquet_dataset_id,file_manifest_sha256,qa_report_id,
                 status,is_production,is_certified,coverage_start,coverage_end,row_count,file_count,
                 certified_by,certified_at,metadata_json,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,'active',1,1,?,?,?,?,'parquet-consistency-v1',?,?,?)
            on conflict(id) do update set id=excluded.id
            """,
            (
                release_id, item["dataset_key"], dataset_version, item["source"],
                item["asset_class"], item["market"], item.get("venue"), item["resolution"],
                item["data_type"], item["adjust"], dataset_id, manifest_sha256, qa_report_id,
                item.get("coverage_start") or item.get("start_date"),
                item.get("coverage_end") or item.get("end_date"),
                int(item.get("row_count") or 0), int(item.get("file_count") or 0),
                now, json_dump(metadata), now,
            ),
        )
        conn.execute(
            "update parquet_datasets set dataset_release_id=? where id=?",
            (release_id, dataset_id),
        )
        conn.execute(
            """
            update dataset_versions
            set dataset_release_id=?,dataset_version=?,environment='production',
                is_production=1,is_certified=1,certified_at=?,certified_by='dataset-release-v1',
                qa_status='ok',qa_report_id=?
            where parquet_dataset_id=?
            """,
            (release_id, dataset_version, now, qa_report_id, dataset_id),
        )
        release = conn.execute("select * from dataset_releases where id=?", (release_id,)).fetchone()
        return row_to_dict(release) or {}


def active_release_for_dataset(dataset_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            """
            select dataset_release.* from dataset_releases dataset_release
            where dataset_release.parquet_dataset_id=? and dataset_release.status='active'
              and dataset_release.is_production=1 and dataset_release.is_certified=1
            order by dataset_release.certified_at desc limit 1
            """,
            (dataset_id,),
        ).fetchone()
    return row_to_dict(row)


def ensure_release_for_certified_dataset(
    dataset: dict[str, Any],
    *,
    manifest_sha256: str,
) -> dict[str, Any] | None:
    """One-time compatibility promotion for certifications created before migration 0040."""
    existing = active_release_for_dataset(str(dataset["id"]))
    if (
        existing
        and existing.get("dataset_version") == dataset.get("dataset_version")
        and existing.get("file_manifest_sha256") == manifest_sha256
    ):
        return existing
    if not dataset.get("dataset_version") or not dataset.get("qa_report_id"):
        return None
    return certify_parquet_dataset(
        str(dataset["id"]),
        dataset_version=str(dataset["dataset_version"]),
        manifest_sha256=manifest_sha256,
        qa_report_id=str(dataset["qa_report_id"]),
        certified_at=dataset.get("certified_at"),
    )


def revoke_scope(
    *,
    source: str,
    asset_class: str,
    market: str,
    venue: str | None,
    reason: str,
    connection: Any,
) -> int:
    now = utc_now()
    cursor = connection.execute(
        """
        update dataset_releases
        set status='revoked',is_certified=0,revoked_at=?,revoke_reason=?
        where status='active' and source=? and asset_class=? and market=?
          and coalesce(venue,?)=?
        """,
        (now, reason, source, asset_class, market, venue or market, venue or market),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def revoke_all_for_direct_market_reset(connection: Any, timestamp: str) -> int:
    """Keep maintenance revocation writes inside the declared table owner."""
    cursor = connection.execute(
        """
        update dataset_releases
        set status='revoked',revoked_at=?,revoke_reason='direct_market_reset'
        where status <> 'revoked'
        """,
        (timestamp,),
    )
    return int(getattr(cursor, "rowcount", 0) or 0)


def list_releases(*, status: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    clauses: list[str] = []
    values: list[Any] = []
    if status:
        clauses.append("status=?")
        values.append(status)
    where = f" where {' and '.join(clauses)}" if clauses else ""
    bounded_limit = max(1, min(int(limit), 200))
    bounded_offset = max(0, int(offset))
    with db() as connection:
        total = connection.execute(f"select count(*) as count from dataset_releases{where}", values).fetchone()
        rows = connection.execute(
            f"select * from dataset_releases{where} order by certified_at desc limit ? offset ?",
            [*values, bounded_limit, bounded_offset],
        ).fetchall()
    return {
        "items": rows_to_dicts(rows),
        "count": int(total["count"] or 0),
        "limit": bounded_limit,
        "offset": bounded_offset,
    }
