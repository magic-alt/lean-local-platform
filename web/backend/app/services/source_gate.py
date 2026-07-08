from __future__ import annotations

import os
from typing import Any

from ..db import db, row_to_dict, utc_now


PRIMARY_DATA_SOURCE = "jqdata"
SECONDARY_DATA_SOURCES = {"akshare"}
BACKUP_DATA_SOURCE_PRIORITY = ["tushare", "rqdata", "baostock", "adata"]
BACKUP_DATA_SOURCES = set(BACKUP_DATA_SOURCE_PRIORITY)
DEFAULT_PRODUCTION_SOURCE = PRIMARY_DATA_SOURCE
PRODUCTION_SOURCES = {PRIMARY_DATA_SOURCE, *SECONDARY_DATA_SOURCES}
RESEARCH_SOURCES = {"test", "unit", "manual", "sina", *BACKUP_DATA_SOURCES}
DATA_SOURCE_PRIORITY = [PRIMARY_DATA_SOURCE, "akshare", *BACKUP_DATA_SOURCE_PRIORITY]
JQDATA_ENTITLEMENT_START = os.environ.get("JQDATA_DATA_RANGE_START", "2025-03-29")
JQDATA_ENTITLEMENT_END = os.environ.get("JQDATA_DATA_RANGE_END", "2026-04-05")


def normalize_source(source: str | None) -> str:
    value = (source or DEFAULT_PRODUCTION_SOURCE).strip().lower()
    return value or DEFAULT_PRODUCTION_SOURCE


def is_research_source(source: str | None) -> bool:
    return normalize_source(source) in RESEARCH_SOURCES


def source_role(source: str | None) -> str:
    normalized = normalize_source(source)
    if normalized == PRIMARY_DATA_SOURCE:
        return "primary"
    if normalized in SECONDARY_DATA_SOURCES:
        return "secondary"
    if normalized in BACKUP_DATA_SOURCES:
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
        "provider": PRIMARY_DATA_SOURCE,
        "startDate": JQDATA_ENTITLEMENT_START,
        "endDate": JQDATA_ENTITLEMENT_END,
        "fallbackProvider": "akshare",
        "note": "JQData account data entitlement is limited to this date range; windows outside it use AKShare.",
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
    if requested == PRIMARY_DATA_SOURCE and not jqdata_covers_window(start_date, end_date):
        requested_effective = "akshare"

    chain: list[str] = [requested_effective]
    for item in DATA_SOURCE_PRIORITY:
        normalized = normalize_source(item)
        if normalized not in chain:
            chain.append(normalized)
    if requested != requested_effective and requested in chain:
        # requested source is temporarily out-of-window; prefer the effective source.
        chain = [requested_effective, requested, *[item for item in chain if item not in {requested_effective, requested}]]
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
    if requested == PRIMARY_DATA_SOURCE and not jqdata_covers_window(start_date, end_date):
        effective = "akshare"
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
    raise ValueError(f"source_not_certified:{normalized}; set allowResearchSource=true for research/test sources")


def source_certification(source: str | None, *, asset_class: str = "equity", market: str = "china", venue: str | None = "china") -> dict[str, Any]:
    normalized = normalize_source(source)
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
    item = row_to_dict(row)
    if item:
        dataset_id = item.get("id")
        dataset_version = item.get("dataset_version") or item.get("dataset_key")
        if item.get("is_certified") and dataset_id:
            dataset_version = f"{normalized}-{str(dataset_id)[:12]}"
        return {
            "source": normalized,
            "sourceRole": source_role(normalized),
            "sourcePriority": DATA_SOURCE_PRIORITY.index(normalized) + 1 if normalized in DATA_SOURCE_PRIORITY else None,
            "datasetVersion": dataset_version,
            "environment": item.get("environment") or ("production" if normalized in PRODUCTION_SOURCES else "research"),
            "isProduction": bool(item.get("is_production")),
            "isCertified": bool(item.get("is_certified")),
            "certifiedAt": item.get("certified_at"),
            "certifiedBy": item.get("certified_by"),
            "coverageStart": item.get("coverage_start") or item.get("start_date"),
            "coverageEnd": item.get("coverage_end") or item.get("end_date"),
            "qaStatus": item.get("qa_status"),
            "qaReportId": item.get("qa_report_id"),
            "datasetId": dataset_id,
        }
    production = normalized in PRODUCTION_SOURCES
    return {
        "source": normalized,
        "sourceRole": source_role(normalized),
        "sourcePriority": DATA_SOURCE_PRIORITY.index(normalized) + 1 if normalized in DATA_SOURCE_PRIORITY else None,
        "datasetVersion": normalized,
        "environment": "production" if production else "research",
        "isProduction": production,
        "isCertified": production,
        "certifiedAt": utc_now() if production else None,
        "certifiedBy": "system-default" if production else None,
        "coverageStart": None,
        "coverageEnd": None,
        "qaStatus": "ok" if production else "research",
        "qaReportId": None,
        "datasetId": None,
    }


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
    result["datasetCertified"] = bool(context.get("isCertified"))
    result["datasetProduction"] = bool(context.get("isProduction"))
    result["datasetEnvironment"] = context.get("environment")
    result["datasetQaStatus"] = context.get("qaStatus")
    result["datasetQaReportId"] = context.get("qaReportId")
    result["allowResearchSource"] = bool(context.get("allowResearchSource"))
    return result
