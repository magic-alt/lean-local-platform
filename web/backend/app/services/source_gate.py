from __future__ import annotations

from typing import Any

from ..db import db, row_to_dict, utc_now


DEFAULT_PRODUCTION_SOURCE = "akshare"
PRODUCTION_SOURCES = {"akshare"}
RESEARCH_SOURCES = {"test", "unit", "manual", "baostock", "adata", "sina"}


def normalize_source(source: str | None) -> str:
    value = (source or DEFAULT_PRODUCTION_SOURCE).strip().lower()
    return value or DEFAULT_PRODUCTION_SOURCE


def is_research_source(source: str | None) -> bool:
    return normalize_source(source) in RESEARCH_SOURCES


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
