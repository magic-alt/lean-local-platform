from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from .data_provider_manager import provider_availability_item, provider_requirements
from .source_gate import (
    BACKUP_DATA_SOURCES,
    DATA_SOURCE_PRIORITY,
    JQDATA_DATA_SOURCE,
    PRIMARY_DATA_SOURCE,
    PRODUCTION_SOURCES,
    SECONDARY_DATA_SOURCES,
    jqdata_covers_window,
    jqdata_entitlement,
    source_role,
)
from . import market_lake


_PROVIDER_REQUIREMENTS = provider_requirements()
PROVIDER_MODULES = {key: value.get("modules", []) for key, value in _PROVIDER_REQUIREMENTS.items()}
PROVIDER_CREDENTIALS = {key: value.get("env", []) for key, value in _PROVIDER_REQUIREMENTS.items()}


def _utc_date(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date().isoformat()


def _source_coverage(provider: str, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    clauses: list[str] = []
    params: list[Any] = []
    if start_date:
        clauses.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("trade_date <= ?")
        params.append(end_date)
    rows = market_lake.query_matching(
        kind="bars", asset_class="equity", market="china", venue="china",
        resolution="daily", data_type="trade", source=provider,
        columns="symbol,trade_date", predicates=clauses, parameters=params,
    )
    dates = sorted(str(row["trade_date"])[:10] for row in rows)
    item = {
        "rows": len(rows), "symbols": len({str(row["symbol"]) for row in rows}),
        "first_date": dates[0] if dates else None, "last_date": dates[-1] if dates else None,
    }
    return {
        "rows": int(item.get("rows") or 0),
        "symbols": int(item.get("symbols") or 0),
        "firstDate": item.get("first_date"),
        "lastDate": item.get("last_date"),
        "startDate": start_date,
        "endDate": end_date,
    }


def provider_availability_report(
    providers: list[str] | None = None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    persist: bool = False,
) -> dict[str, Any]:
    selected = [item.strip().lower() for item in (providers or DATA_SOURCE_PRIORITY) if item.strip()]
    checked_at = utc_now()
    items: list[dict[str, Any]] = []
    for provider in selected:
        availability = provider_availability_item(provider, start_date=start_date, end_date=end_date)
        coverage = _source_coverage(provider, start_date, end_date)
        unavailable_reasons: list[str] = []
        if availability.get("unavailableReason"):
            unavailable_reasons.extend(str(availability["unavailableReason"]).split(";"))
        if provider in PRODUCTION_SOURCES and coverage["rows"] == 0:
            unavailable_reasons.append("provider_returned_empty")
        elif provider not in PRODUCTION_SOURCES and coverage["rows"] == 0:
            unavailable_reasons.append("coverage_gap")
        entitlement = jqdata_entitlement() if provider == JQDATA_DATA_SOURCE else None
        if provider == JQDATA_DATA_SOURCE and not jqdata_covers_window(start_date, end_date):
            if "entitlement_window_exceeded" not in unavailable_reasons:
                unavailable_reasons.append("entitlement_window_exceeded")
        installed = bool(availability.get("installed"))
        configured = bool(availability.get("configured"))
        production_certified = provider in PRODUCTION_SOURCES and installed and configured
        status = "available" if not unavailable_reasons else ("degraded" if provider in PRODUCTION_SOURCES and installed else "unavailable")
        item = {
            "provider": provider,
            "role": source_role(provider),
            "priority": DATA_SOURCE_PRIORITY.index(provider) + 1 if provider in DATA_SOURCE_PRIORITY else None,
            "installed": installed,
            "configured": configured,
            "credentials": availability.get("credentials") or ("present" if configured else "credential_missing"),
            "supportedEndpoints": availability.get("supportedEndpoints") or [],
            "unavailableReason": ";".join(unavailable_reasons) if unavailable_reasons else None,
            "coverage": coverage,
            "entitlement": entitlement,
            "productionCertified": production_certified,
            "status": status,
            "diagnostics": availability.get("diagnostics") or {},
        }
        items.append(item)
        if persist:
            record_provider_availability(item, checked_at=checked_at)
    severity = "critical" if any(item["provider"] == PRIMARY_DATA_SOURCE and item["status"] == "unavailable" for item in items) else (
        "warning" if any(item["provider"] in PRODUCTION_SOURCES and item["status"] != "available" for item in items) else (
            "warning" if any(item["provider"] in {*SECONDARY_DATA_SOURCES, *BACKUP_DATA_SOURCES} and item["status"] == "unavailable" for item in items) else "ok"
        )
    )
    return {
        "checkedAt": checked_at,
        "primaryProvider": PRIMARY_DATA_SOURCE,
        "secondaryProviders": sorted(SECONDARY_DATA_SOURCES),
        "backupProviders": [item for item in DATA_SOURCE_PRIORITY if item in BACKUP_DATA_SOURCES],
        "providerPriority": DATA_SOURCE_PRIORITY,
        "providers": items,
        "items": items,
        "count": len(items),
        "severity": severity,
    }


def record_provider_availability(item: dict[str, Any], *, checked_at: str | None = None) -> dict[str, Any]:
    record_id = str(uuid.uuid4())
    checked = checked_at or utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into provider_availability_log
                (id, provider, status, installed, configured, credentials_status, unavailable_reason,
                 supported_endpoints_json, coverage_json, production_certified, checked_at, metadata_json)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                item["provider"],
                item["status"],
                1 if item.get("installed") else 0,
                1 if item.get("configured") else 0,
                item.get("credentials") or "unknown",
                item.get("unavailableReason"),
                json_dump(item.get("supportedEndpoints") or []),
                json_dump(item.get("coverage") or {}),
                1 if item.get("productionCertified") else 0,
                checked,
                json_dump(item.get("diagnostics") or {}),
            ),
        )
    return {"id": record_id, **item, "checkedAt": checked}


def add_warning_allowlist(
    *,
    warning_code: str,
    reason: str,
    valid_until: str | None = None,
    approved_by: str = "level3plus-cli",
    affected_symbols: list[str] | None = None,
    scope: dict[str, Any] | None = None,
    valid_days: int = 30,
) -> dict[str, Any]:
    code = warning_code.strip()
    if not code:
        raise ValueError("warning_code is required")
    if "critical" in code.lower():
        raise ValueError("critical warnings cannot be accepted")
    now = utc_now()
    item_id = str(uuid.uuid4())
    until = valid_until or _utc_date(valid_days)
    with db() as connection:
        connection.execute(
            """
            insert into qa_warning_allowlist
                (id, warning_code, reason, valid_until, approved_by, affected_symbols_json,
                 scope_json, status, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item_id,
                code,
                reason,
                until,
                approved_by,
                json_dump(sorted(set(affected_symbols or []))),
                json_dump(scope or {}),
                "active",
                now,
                now,
            ),
        )
    return {"id": item_id, "warningCode": code, "validUntil": until, "approvedBy": approved_by}


def warning_allowlist_status(
    warning_codes: list[str],
    *,
    affected_symbols: list[str] | None = None,
    scope: dict[str, Any] | None = None,
    as_of: str | None = None,
) -> dict[str, Any]:
    codes = sorted({code for code in warning_codes if code})
    if not codes:
        return {"acceptedWarnings": [], "expiredWarnings": [], "unacceptedWarnings": [], "passed": True}
    placeholders = ", ".join("?" for _ in codes)
    with db() as connection:
        rows = connection.execute(
            f"""
            select *
            from qa_warning_allowlist
            where status = 'active' and warning_code in ({placeholders})
            order by valid_until desc
            """,
            codes,
        ).fetchall()
    today = as_of or datetime.now(timezone.utc).date().isoformat()
    records = rows_to_dicts(rows)
    accepted: list[dict[str, Any]] = []
    expired: list[dict[str, Any]] = []
    accepted_codes: set[str] = set()
    for record in records:
        code = record.get("warning_code") or record.get("warningCode")
        if str(record.get("valid_until") or record.get("validUntil") or "") < today:
            expired.append(record)
        else:
            accepted.append(record)
            accepted_codes.add(str(code))
    unaccepted = [code for code in codes if code not in accepted_codes]
    return {
        "acceptedWarnings": accepted,
        "expiredWarnings": expired,
        "unacceptedWarnings": unaccepted,
        "affectedSymbols": affected_symbols or [],
        "scope": scope or {},
        "passed": not expired and not unaccepted,
    }


def latest_provider_logs(limit: int = 100) -> list[dict[str, Any]]:
    bounded = max(1, min(int(limit), 1000))
    with db() as connection:
        rows = connection.execute(
            """
            select *
            from provider_availability_log
            order by checked_at desc
            limit ?
            """,
            (bounded,),
        ).fetchall()
    return rows_to_dicts(rows)
