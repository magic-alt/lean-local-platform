from __future__ import annotations

from datetime import date
import hashlib
import json
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now


OFFERED_UNIVERSES: dict[str, dict[str, Any]] = {
    "CSI300": {
        "name": "沪深300",
        "indexSymbol": "000300.SH",
        "launchDate": "2005-04-08",
        "expectedMembers": 300,
        "trustedSources": {"csindex:official", "csi300_pit_public"},
    },
    "CSI500": {
        "name": "中证500",
        "indexSymbol": "000905.SH",
        "launchDate": "2007-01-15",
        "expectedMembers": 500,
        "trustedSources": {"csindex:official", "tushare:index_weight"},
    },
    "CSI1000": {
        "name": "中证1000",
        "indexSymbol": "000852.SH",
        "launchDate": "2014-10-17",
        "expectedMembers": 1000,
        "trustedSources": {"csindex:official", "tushare:index_weight", "jqdata:index_members"},
    },
    "SSE50": {
        "name": "上证50",
        "indexSymbol": "000016.SH",
        "launchDate": "2004-01-02",
        "expectedMembers": 50,
        "trustedSources": {"csindex:official", "sse:official", "tushare:index_weight"},
    },
    "STAR50": {
        "name": "科创50",
        "indexSymbol": "000688.SH",
        "launchDate": "2020-07-22",
        "expectedMembers": 50,
        "trustedSources": {"csindex:official", "sse:official", "tushare:index_weight"},
    },
    "ALL_A": {
        "name": "全A股",
        "indexSymbol": None,
        "launchDate": "1990-12-19",
        "expectedMembers": None,
        "trustedSources": {"tushare:stock_basic"},
    },
}


def universe_spec(universe_code: str) -> dict[str, Any] | None:
    code = str(universe_code or "").strip().upper()
    item = OFFERED_UNIVERSES.get(code)
    return {
        "universeCode": code,
        **item,
        "trustedSources": sorted(item["trustedSources"]),
    } if item else None


def _membership_digest(universe_code: str) -> tuple[int, int, str | None, str | None, str]:
    with db() as connection:
        rows = connection.execute(
            """
            select symbol,start_date,end_date,announce_date,effective_date,weight,source,batch_id
            from universe_membership
            where universe_code=?
            order by symbol,start_date,source
            """,
            (universe_code,),
        ).fetchall()
    items = rows_to_dicts(rows)
    digest = hashlib.sha256(
        json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    starts = [str(item["start_date"]) for item in items if item.get("start_date")]
    effective_dates = [str(item.get("effective_date") or item.get("start_date")) for item in items if item.get("start_date")]
    coverage_end = (
        date.today().isoformat()
        if any(item.get("end_date") in (None, "") for item in items)
        else max(effective_dates)
        if effective_dates
        else None
    )
    return len(items), len(set(effective_dates)), min(starts) if starts else None, coverage_end, digest


def record_universe_coverage(
    universe_code: str,
    *,
    coverage_start: str | None,
    coverage_end: str | None,
    status: str,
    source: str,
    batch_id: str | None = None,
    bundle_sha256: str | None = None,
    validation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    code = str(universe_code or "").strip().upper()
    spec = universe_spec(code)
    if not spec:
        raise ValueError(f"Unsupported universe {code}.")
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in {"missing", "partial", "complete", "failed"}:
        raise ValueError("Universe coverage status must be missing, partial, complete or failed.")
    membership_rows, observed_snapshots, actual_start, actual_end, digest = _membership_digest(code)
    resolved_start = coverage_start or actual_start
    resolved_end = coverage_end or actual_end
    trusted = source in spec["trustedSources"]
    complete = bool(
        normalized_status == "complete"
        and trusted
        and membership_rows > 0
        and resolved_start
        and resolved_start <= spec["launchDate"]
        and resolved_end
    )
    if normalized_status == "complete" and not complete:
        normalized_status = "failed"
    evidence = {
        **(validation or {}),
        "trustedSource": trusted,
        "actualMembershipStart": actual_start,
        "actualMembershipEnd": actual_end,
        "launchCovered": bool(resolved_start and resolved_start <= spec["launchDate"]),
        "membershipDigest": digest,
        "rulesVersion": "universe-coverage-v1",
    }
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into universe_coverage_watermarks
                (universe_code,launch_date,coverage_start,coverage_end,coverage_status,
                 source,expected_members,observed_snapshots,membership_rows,bundle_sha256,
                 last_batch_id,validation_json,validated_at,updated_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            on conflict(universe_code) do update set
                launch_date=excluded.launch_date,
                coverage_start=excluded.coverage_start,
                coverage_end=excluded.coverage_end,
                coverage_status=excluded.coverage_status,
                source=excluded.source,
                expected_members=excluded.expected_members,
                observed_snapshots=excluded.observed_snapshots,
                membership_rows=excluded.membership_rows,
                bundle_sha256=excluded.bundle_sha256,
                last_batch_id=excluded.last_batch_id,
                validation_json=excluded.validation_json,
                validated_at=excluded.validated_at,
                updated_at=excluded.updated_at
            """,
            (
                code,
                spec["launchDate"],
                resolved_start,
                resolved_end,
                normalized_status,
                source,
                spec["expectedMembers"],
                observed_snapshots,
                membership_rows,
                bundle_sha256 or digest,
                batch_id,
                json_dump(evidence),
                now,
                now,
            ),
        )
    return universe_coverage(code) or {}


def universe_coverage(universe_code: str) -> dict[str, Any] | None:
    code = str(universe_code or "").strip().upper()
    spec = universe_spec(code)
    if not spec:
        return None
    with db() as connection:
        row = connection.execute(
            "select * from universe_coverage_watermarks where universe_code=?",
            (code,),
        ).fetchone()
    item = row_to_dict(row)
    if item:
        return {**spec, **item}
    return {
        **spec,
        "coverage_status": "missing",
        "coverage_start": None,
        "coverage_end": None,
        "membership_rows": 0,
        "observed_snapshots": 0,
        "validation": {"rulesVersion": "universe-coverage-v1", "trustedSource": False},
    }


def universe_coverage_overview() -> dict[str, Any]:
    items = [universe_coverage(code) for code in OFFERED_UNIVERSES]
    output = [item for item in items if item is not None]
    complete = sum(1 for item in output if item.get("coverage_status") == "complete")
    return {
        "rulesVersion": "universe-coverage-v1",
        "items": output,
        "count": len(output),
        "complete": complete,
        "passed": complete == len(output),
        "asOfDate": date.today().isoformat(),
    }


def coverage_gap(universe_code: str, as_of_date: str) -> dict[str, Any] | None:
    item = universe_coverage(universe_code)
    if not item:
        return None
    code = str(item["universeCode"])
    start = item.get("coverage_start")
    end = item.get("coverage_end")
    status = item.get("coverage_status")
    if status == "complete" and start and start <= as_of_date and (not end or as_of_date <= end):
        return None
    if start and start <= as_of_date and (not end or as_of_date <= end):
        # Partial rows remain queryable for research, but the payload clearly
        # cannot be promoted as complete PIT evidence.
        return None
    missing_before = start or item["launchDate"]
    effective_certification = (
        "partial"
        if status == "complete"
        else status
    )
    return {
        "coverageStatus": "coverage_gap",
        "coverageStart": start,
        "coverageEnd": end,
        "missingHistoryBefore": missing_before,
        "isOfficialHistoryComplete": False,
        "coverageCertification": effective_certification,
        "storedCoverageCertification": status,
        "reason": f"{code} PIT coverage does not include {as_of_date}; certification status is {status}.",
    }
