from __future__ import annotations

import os
import hashlib
import json
from typing import Any

from ..db import DatabaseUnavailableError, database_backend, db, row_to_dict
from . import market_lake


PRIMARY_DATA_SOURCE = "tushare"
JQDATA_DATA_SOURCE = "jqdata"
FREE_SUPPLEMENTAL_DATA_SOURCE_PRIORITY = [
    "akshare",
    "baostock",
    "adata",
    "eastmoney",
    "sina",
    "efinance",
    "tencent",
    "tonghuashun",
    "yfinance",
]
OPTIONAL_CONNECTOR_DATA_SOURCE_PRIORITY = [
    "pytdx",
]
COMMERCIAL_DATA_SOURCE_PRIORITY = [
    JQDATA_DATA_SOURCE,
    "rqdata",
    "tickflow",
    "longbridge",
    "finnhub",
    "alpha_vantage",
]
SECONDARY_DATA_SOURCES = set(FREE_SUPPLEMENTAL_DATA_SOURCE_PRIORITY)
COMMERCIAL_DATA_SOURCES = set(COMMERCIAL_DATA_SOURCE_PRIORITY)
OPTIONAL_CONNECTOR_DATA_SOURCES = set(OPTIONAL_CONNECTOR_DATA_SOURCE_PRIORITY)
BACKUP_DATA_SOURCE_PRIORITY = [
    *FREE_SUPPLEMENTAL_DATA_SOURCE_PRIORITY,
    *OPTIONAL_CONNECTOR_DATA_SOURCE_PRIORITY,
    *COMMERCIAL_DATA_SOURCE_PRIORITY,
]
BACKUP_DATA_SOURCES = set(BACKUP_DATA_SOURCE_PRIORITY)
DEFAULT_PRODUCTION_SOURCE = PRIMARY_DATA_SOURCE
PRODUCTION_SOURCES = {PRIMARY_DATA_SOURCE}
RESEARCH_SOURCES = {
    "test",
    "unit",
    "manual",
    *SECONDARY_DATA_SOURCES,
    *OPTIONAL_CONNECTOR_DATA_SOURCES,
    *COMMERCIAL_DATA_SOURCES,
}
DATA_SOURCE_PRIORITY = [PRIMARY_DATA_SOURCE, *FREE_SUPPLEMENTAL_DATA_SOURCE_PRIORITY]
JQDATA_ENTITLEMENT_START = os.environ.get("JQDATA_DATA_RANGE_START", "2025-03-29")
JQDATA_ENTITLEMENT_END = os.environ.get("JQDATA_DATA_RANGE_END", "2026-04-05")
SOURCE_ALIASES = {
    "tushare_pro": PRIMARY_DATA_SOURCE,
    "tushare-pro": PRIMARY_DATA_SOURCE,
    "tushare pro": PRIMARY_DATA_SOURCE,
    "tu_share": PRIMARY_DATA_SOURCE,
    "tu-share": PRIMARY_DATA_SOURCE,
    "alphavantage": "alpha_vantage",
    "alpha-vantage": "alpha_vantage",
}


def normalize_source(source: str | None) -> str:
    value = (source or DEFAULT_PRODUCTION_SOURCE).strip().lower()
    return SOURCE_ALIASES.get(value, value) or DEFAULT_PRODUCTION_SOURCE


def is_research_source(source: str | None) -> bool:
    return normalize_source(source) in RESEARCH_SOURCES


def source_role(source: str | None) -> str:
    normalized = normalize_source(source)
    if normalized == PRIMARY_DATA_SOURCE:
        return "primary"
    if normalized in SECONDARY_DATA_SOURCES:
        return "supplemental"
    if normalized in COMMERCIAL_DATA_SOURCES:
        return "commercial"
    if normalized in OPTIONAL_CONNECTOR_DATA_SOURCES:
        return "backup"
    if normalized in RESEARCH_SOURCES:
        return "research"
    return "unknown"


def _date_key(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    return text if text else None


def jqdata_entitlement() -> dict[str, Any]:
    return {
        "provider": JQDATA_DATA_SOURCE,
        "startDate": JQDATA_ENTITLEMENT_START,
        "endDate": JQDATA_ENTITLEMENT_END,
        "fallbackProvider": DEFAULT_PRODUCTION_SOURCE,
        "note": "JQData account data entitlement is limited to this date range; windows outside it use the default production source.",
    }


def jqdata_covers_window(start_date: str | None = None, end_date: str | None = None) -> bool:
    start = _date_key(start_date)
    end = _date_key(end_date)
    if start and start < JQDATA_ENTITLEMENT_START:
        return False
    if end and end > JQDATA_ENTITLEMENT_END:
        return False
    return True


def resolve_source_chain(
    source: str | None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[str]:
    requested = normalize_source(source)
    requested_effective = requested
    jqdata_available = jqdata_covers_window(start_date, end_date)
    if requested == JQDATA_DATA_SOURCE and not jqdata_available:
        requested_effective = DEFAULT_PRODUCTION_SOURCE

    chain: list[str] = [requested_effective]
    for item in DATA_SOURCE_PRIORITY:
        normalized = normalize_source(item)
        if normalized == JQDATA_DATA_SOURCE and not jqdata_available:
            continue
        if normalized not in chain:
            chain.append(normalized)
    return chain


def resolve_effective_data_source(
    source: str | None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    requested = normalize_source(source)
    effective = requested
    reason = None
    if requested == JQDATA_DATA_SOURCE and not jqdata_covers_window(start_date, end_date):
        effective = DEFAULT_PRODUCTION_SOURCE
        reason = "jqdata_entitlement_window_exceeded"
    chain = resolve_source_chain(source, start_date=start_date, end_date=end_date)
    return {
        "requestedSource": requested,
        "effectiveSource": effective,
        "fallbackApplied": effective != requested,
        "fallbackReason": reason,
        "sourceRole": source_role(effective),
        "requestedSourceRole": source_role(requested),
        "sourceChain": chain,
        "startDate": _date_key(start_date),
        "endDate": _date_key(end_date),
        "jqdataEntitlement": jqdata_entitlement(),
    }


def source_priority_for_window(
    *,
    source: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[str]:
    return resolve_source_chain(
        source,
        start_date=start_date,
        end_date=end_date,
    )


def require_source_allowed(source: str | None, *, allow_research_source: bool = False) -> str:
    normalized = normalize_source(source)
    if normalized in PRODUCTION_SOURCES:
        return normalized
    if allow_research_source:
        return normalized
    if normalized in COMMERCIAL_DATA_SOURCES:
        raise ValueError(
            f"source_disabled_by_default:{normalized}; commercial sources require explicit allowResearchSource=true"
        )
    raise ValueError(f"source_not_certified:{normalized}; set allowResearchSource=true for research/test sources")


def source_certification(source: str | None, *, asset_class: str = "equity", market: str = "china", venue: str | None = "china") -> dict[str, Any]:
    normalized = normalize_source(source)
    if (
        database_backend() == "postgresql"
        and os.environ.get("LEAN_SOURCE_CERTIFICATION_BACKEND", "database").strip().lower() != "database"
    ):
        local = _local_lake_certification(
            normalized,
            asset_class=asset_class,
            market=market,
            venue=venue,
        )
        if local["localAuthority"]:
            return local
    try:
        with db() as connection:
            row = connection.execute(
                """
                select *
                from parquet_datasets
                where source = ? and asset_class = ? and market = ? and coalesce(venue, ?) = ?
                order by is_certified desc, updated_at desc
                limit 1
                """,
                (normalized, asset_class.lower(), market.lower(), (venue or market).lower(), (venue or market).lower()),
            ).fetchone()
    except DatabaseUnavailableError:
        return _local_lake_certification(
            normalized,
            asset_class=asset_class,
            market=market,
            venue=venue,
        )
    item = row_to_dict(row)
    if item:
        dataset_id = item.get("id")
        dataset_version = item.get("dataset_version") or item.get("dataset_key")
        with db() as connection:
            file_rows = connection.execute(
                "select file_path, row_count, sha256 from parquet_files where dataset_id = ? order by file_path",
                (dataset_id,),
            ).fetchall()
        files = [
            {
                "path": str(file_row["file_path"]),
                "rowCount": int(file_row["row_count"] or 0),
                "sha256": str(file_row["sha256"] or ""),
            }
            for file_row in file_rows
        ]
        file_manifest_sha256 = (
            hashlib.sha256(
                json.dumps(files, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
            ).hexdigest()
            if files
            else None
        )
        qa_status = str(item.get("qa_status") or "").strip().lower()
        expected_dataset_version = (
            f"{normalized}-{str(dataset_id)[:12]}-{file_manifest_sha256[:12]}"
            if dataset_id and file_manifest_sha256
            else None
        )
        certification_valid = bool(
            item.get("is_production")
            and item.get("is_certified")
            and str(item.get("environment") or "").strip().lower() == "production"
            and qa_status == "ok"
            and dataset_version
            and file_manifest_sha256
            and dataset_version == expected_dataset_version
        )
        release = None
        if certification_valid and file_manifest_sha256 and item.get("qa_report_id"):
            from .dataset_releases import ensure_release_for_certified_dataset

            release = ensure_release_for_certified_dataset(
                item,
                manifest_sha256=file_manifest_sha256,
            )
            certification_valid = bool(
                release
                and release.get("status") == "active"
                and release.get("is_production")
                and release.get("is_certified")
                and release.get("file_manifest_sha256") == file_manifest_sha256
            )
        elif certification_valid and database_backend() == "postgresql":
            # Production never accepts the pre-0040 split authority. SQLite is
            # retained only for legacy unit fixtures that do not model QA rows.
            certification_valid = False
        if certification_valid and dataset_id:
            dataset_version = expected_dataset_version
        # The SQL registry may intentionally be absent or stale after the
        # quote-table cutover.  A readable mounted lake is the current
        # authority for market-data reads and takes precedence in that case.
        if not certification_valid:
            local = _local_lake_certification(
                normalized,
                asset_class=asset_class,
                market=market,
                venue=venue,
            )
            if local["localAuthority"]:
                return local
        return {
            "source": normalized,
            "sourceRole": source_role(normalized),
            "sourcePriority": DATA_SOURCE_PRIORITY.index(normalized) + 1 if normalized in DATA_SOURCE_PRIORITY else None,
            "datasetVersion": dataset_version,
            "environment": item.get("environment") or ("production" if normalized in PRODUCTION_SOURCES else "research"),
            "isProduction": bool(item.get("is_production")) and certification_valid,
            "isCertified": certification_valid,
            "certificationValid": certification_valid,
            "certificationError": None if certification_valid else (
                "dataset_version_manifest_mismatch"
                if dataset_version and expected_dataset_version and dataset_version != expected_dataset_version
                else "persisted_certification_incomplete"
            ),
            "certifiedAt": item.get("certified_at"),
            "certifiedBy": item.get("certified_by"),
            "coverageStart": item.get("coverage_start") or item.get("start_date"),
            "coverageEnd": item.get("coverage_end") or item.get("end_date"),
            "qaStatus": item.get("qa_status"),
            "qaReportId": item.get("qa_report_id"),
            "datasetId": dataset_id,
            "datasetReleaseId": release.get("id") if release else None,
            "fileCount": len(files),
            "fileManifestSha256": file_manifest_sha256,
        }
    local = _local_lake_certification(
        normalized,
        asset_class=asset_class,
        market=market,
        venue=venue,
    )
    if local["localAuthority"]:
        return local
    return {
        "source": normalized,
        "sourceRole": source_role(normalized),
        "sourcePriority": DATA_SOURCE_PRIORITY.index(normalized) + 1 if normalized in DATA_SOURCE_PRIORITY else None,
        "datasetVersion": None,
        "environment": "research",
        "isProduction": False,
        "isCertified": False,
        "certificationValid": False,
        "certificationError": "persisted_certification_missing",
        "certifiedAt": None,
        "certifiedBy": None,
        "coverageStart": None,
        "coverageEnd": None,
        "qaStatus": "unverified",
        "qaReportId": None,
        "datasetId": None,
        "datasetReleaseId": None,
        "fileCount": 0,
        "fileManifestSha256": None,
        "localAuthority": False,
    }


def _local_lake_certification(
    source: str,
    *,
    asset_class: str,
    market: str,
    venue: str | None,
) -> dict[str, Any]:
    """Describe a readable local Parquet scope without requiring SQL metadata.

    The lake is the market-data authority. PostgreSQL stores optional application
    governance metadata, so a missing database must not make already-present
    local quotes unavailable to chart, research, or backtest read paths.
    """
    scopes = market_lake.matching_scopes(
        kind="bars",
        asset_class=asset_class.lower(),
        market=market.lower(),
        venue=(venue or market).lower(),
        source=source,
    )
    file_count = 0
    summaries: list[dict[str, Any]] = []
    manifests = []
    for scope in scopes:
        summary = market_lake.native_partition_summary(**scope)
        manifest = market_lake.load_manifest(**scope)
        custom_files = manifest.get("files") or []
        available = bool(custom_files) or bool(summary["available"])
        if not available:
            continue
        file_count += len(custom_files) or int(summary.get("partitionCount") or 0)
        summaries.append({"datasetKey": market_lake.dataset_key(**scope), **summary})
        manifests.append(manifest)
    authority = bool(summaries)
    fingerprint = hashlib.sha256(
        json.dumps(summaries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest() if authority else None
    return {
        "source": source,
        "sourceRole": source_role(source),
        "sourcePriority": DATA_SOURCE_PRIORITY.index(source) + 1 if source in DATA_SOURCE_PRIORITY else None,
        "datasetVersion": f"local-{fingerprint[:24]}" if fingerprint else None,
        "environment": "local",
        "isProduction": False,
        "isCertified": authority,
        "certificationValid": authority,
        "certificationError": None if authority else "local_parquet_scope_missing",
        "certifiedAt": None,
        "certifiedBy": "local_parquet",
        "coverageStart": None,
        "coverageEnd": None,
        "qaStatus": "local",
        "qaReportId": None,
        "datasetId": None,
        "datasetReleaseId": None,
        "fileCount": file_count,
        "fileManifestSha256": fingerprint,
        "localAuthority": authority,
        "manifests": [item.get("datasetKey") for item in manifests],
    }


def invalidate_source_certification(
    source: str | None,
    *,
    asset_class: str,
    market: str,
    venue: str | None,
    connection: Any | None = None,
) -> bool:
    """Revoke derived certification whenever canonical rows in its scope change."""
    normalized = normalize_source(source)
    if normalized not in PRODUCTION_SOURCES:
        return False
    scope_venue = (venue or market).lower()
    parameters = (normalized, asset_class.lower(), market.lower(), scope_venue, scope_venue)
    sql = """
        update parquet_datasets
        set environment='research', is_production=0, is_certified=0,
            certified_at=null, certified_by=null, qa_status='stale', qa_report_id=null
        where source=? and asset_class=? and market=? and coalesce(venue,?)=?
          and (is_production=1 or is_certified=1)
    """
    if connection is not None:
        cursor = connection.execute(sql, parameters)
        from .dataset_releases import revoke_scope

        revoke_scope(
            source=normalized,
            asset_class=asset_class.lower(),
            market=market.lower(),
            venue=scope_venue,
            reason="canonical_source_changed",
            connection=connection,
        )
        return bool(int(getattr(cursor, "rowcount", 0) or 0))
    with db() as owned_connection:
        cursor = owned_connection.execute(
            sql,
            parameters,
        )
        from .dataset_releases import revoke_scope

        revoke_scope(
            source=normalized,
            asset_class=asset_class.lower(),
            market=market.lower(),
            venue=scope_venue,
            reason="canonical_source_changed",
            connection=owned_connection,
        )
    return bool(int(getattr(cursor, "rowcount", 0) or 0))


def resolve_source_context(
    parameters: dict[str, Any] | None,
    *,
    source: str | None = None,
    allow_research_source: bool | None = None,
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = "china",
) -> dict[str, Any]:
    params = parameters or {}
    requested = source or params.get("source") or params.get("providerSource") or params.get("provider")
    allow = bool(
        allow_research_source
        if allow_research_source is not None
        else params.get("allowResearchSource") or params.get("allow_research_source")
    )
    normalized = require_source_allowed(str(requested) if requested else None, allow_research_source=allow)
    certification = source_certification(normalized, asset_class=asset_class, market=market, venue=venue)
    trusted_production = (
        certification.get("isProduction")
        and certification.get("isCertified")
        and certification.get("environment") == "production"
        and str(certification.get("qaStatus") or "").lower() == "ok"
    )
    trusted_local_lake = bool(certification.get("localAuthority"))
    if not allow and not (trusted_production or trusted_local_lake):
        reason = certification.get("certificationError") or certification.get("qaStatus") or "unverified"
        raise ValueError(f"source_not_certified:{normalized}:{reason}")
    return {
        **certification,
        "allowResearchSource": allow,
        "requestedSource": requested,
        "isResearchSource": is_research_source(normalized),
        "sourceRole": source_role(normalized),
    }


def apply_source_context(parameters: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    result = dict(parameters)
    result["source"] = context["source"]
    result["providerSource"] = context["source"]
    result["datasetVersion"] = context.get("datasetVersion")
    result["datasetReleaseId"] = context.get("datasetReleaseId")
    result["datasetCertified"] = bool(context.get("isCertified"))
    result["datasetProduction"] = bool(context.get("isProduction"))
    result["datasetEnvironment"] = context.get("environment")
    result["datasetQaStatus"] = context.get("qaStatus")
    result["datasetQaReportId"] = context.get("qaReportId")
    result["allowResearchSource"] = bool(context.get("allowResearchSource"))
    return result
