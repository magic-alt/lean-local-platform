from __future__ import annotations

import uuid
from typing import Any

from ..db import db, json_dump, rows_to_dicts, utc_now


DEFAULT_SOURCES = ["akshare", "adata", "baostock"]
REPORT_NAMESPACE = uuid.UUID("d30cc089-890e-46f6-9e1f-d8874c30c773")


def _source_key(source: str) -> str:
    return source.strip().lower()


def _bounded_mismatches(items: list[dict[str, Any]], limit: int = 200) -> list[dict[str, Any]]:
    return items[:limit]


def _query_rows(symbol: str, start_date: str | None, end_date: str | None, adjust: str, sources: list[str]) -> list[dict[str, Any]]:
    placeholders = ", ".join("?" for _ in sources)
    predicates = ["symbol = ?", "adjust = ?", f"source in ({placeholders})"]
    params: list[Any] = [symbol, adjust, *sources]
    if start_date:
        predicates.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        predicates.append("trade_date <= ?")
        params.append(end_date)
    with db() as connection:
        rows = connection.execute(
            f"""
            select symbol, trade_date, open, high, low, close, volume, amount, source
            from ashare_daily_bars
            where {" and ".join(predicates)}
            order by trade_date asc, source asc
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def _coverage(rows_by_source: dict[str, dict[str, dict[str, Any]]], all_dates: set[str]) -> dict[str, dict[str, Any]]:
    coverage: dict[str, dict[str, Any]] = {}
    for source, rows in rows_by_source.items():
        dates = set(rows)
        coverage[source] = {
            "rows": len(rows),
            "firstDate": min(dates) if dates else None,
            "lastDate": max(dates) if dates else None,
            "missingDates": sorted(all_dates - dates)[:200],
            "missingCount": len(all_dates - dates),
        }
    return coverage


def _price_mismatches(
    base_source: str,
    rows_by_source: dict[str, dict[str, dict[str, Any]]],
    *,
    price_abs_tolerance: float,
    price_rel_tolerance_bps: float,
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    base_rows = rows_by_source.get(base_source, {})
    for source, rows in rows_by_source.items():
        if source == base_source:
            continue
        common_dates = sorted(set(base_rows) & set(rows))
        for trade_date in common_dates:
            base = base_rows[trade_date]
            other = rows[trade_date]
            field_diffs: dict[str, Any] = {}
            for field in ("open", "high", "low", "close"):
                base_value = float(base[field])
                other_value = float(other[field])
                abs_diff = abs(other_value - base_value)
                rel_bps = abs_diff / abs(base_value) * 10000 if base_value else 0.0
                if abs_diff > price_abs_tolerance and rel_bps > price_rel_tolerance_bps:
                    field_diffs[field] = {
                        "base": base_value,
                        "other": other_value,
                        "absDiff": abs_diff,
                        "relBps": rel_bps,
                    }
            if field_diffs:
                mismatches.append({"tradeDate": trade_date, "baseSource": base_source, "source": source, "fields": field_diffs})
    return mismatches


def _volume_mismatches(
    base_source: str,
    rows_by_source: dict[str, dict[str, dict[str, Any]]],
    *,
    volume_rel_tolerance_pct: float,
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    base_rows = rows_by_source.get(base_source, {})
    for source, rows in rows_by_source.items():
        if source == base_source:
            continue
        common_dates = sorted(set(base_rows) & set(rows))
        for trade_date in common_dates:
            base_value = float(base_rows[trade_date]["volume"] or 0)
            other_value = float(rows[trade_date]["volume"] or 0)
            if base_value == 0 and other_value == 0:
                continue
            rel_pct = abs(other_value - base_value) / max(abs(base_value), 1.0) * 100.0
            if rel_pct > volume_rel_tolerance_pct:
                mismatches.append(
                    {
                        "tradeDate": trade_date,
                        "baseSource": base_source,
                        "source": source,
                        "base": base_value,
                        "other": other_value,
                        "relPct": rel_pct,
                    }
                )
    return mismatches


def _persist_report(report: dict[str, Any]) -> str:
    created_at = utc_now()
    seed = json_dump({**report, "createdAt": created_at})
    report_id = str(uuid.uuid5(REPORT_NAMESPACE, seed))
    with db() as connection:
        connection.execute(
            """
            insert into data_quality_reports
                (id, report_type, asset_class, market, symbol, start_date, end_date,
                 sources_json, severity, result_json, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                "ashare_daily_multisource",
                "equity",
                "china",
                report["symbol"],
                report.get("startDate"),
                report.get("endDate"),
                json_dump(report["sources"]),
                report["severity"],
                json_dump(report),
                created_at,
            ),
        )
    return report_id


def compare_ashare_daily_sources(
    *,
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    sources: list[str] | None = None,
    adjust: str = "raw",
    price_abs_tolerance: float = 0.02,
    price_rel_tolerance_bps: float = 5.0,
    volume_rel_tolerance_pct: float = 5.0,
    persist: bool = True,
) -> dict[str, Any]:
    normalized_sources = [_source_key(source) for source in (sources or DEFAULT_SOURCES) if source.strip()]
    if not normalized_sources:
        raise ValueError("At least one data source is required.")
    symbol_key = symbol.strip().upper()
    adjust_key = adjust or "raw"
    rows = _query_rows(symbol_key, start_date, end_date, adjust_key, normalized_sources)
    rows_by_source: dict[str, dict[str, dict[str, Any]]] = {source: {} for source in normalized_sources}
    for row in rows:
        rows_by_source.setdefault(row["source"], {})[row["trade_date"]] = row
    all_dates = set().union(*(set(items) for items in rows_by_source.values())) if rows_by_source else set()
    base_source = normalized_sources[0]
    coverage = _coverage(rows_by_source, all_dates)
    price_diff_rows = _price_mismatches(
        base_source,
        rows_by_source,
        price_abs_tolerance=price_abs_tolerance,
        price_rel_tolerance_bps=price_rel_tolerance_bps,
    )
    volume_diff_rows = _volume_mismatches(
        base_source,
        rows_by_source,
        volume_rel_tolerance_pct=volume_rel_tolerance_pct,
    )
    empty_sources = [source for source, item in coverage.items() if item["rows"] == 0]
    missing_dates = sum(item["missingCount"] for item in coverage.values())
    if coverage.get(base_source, {}).get("rows", 0) == 0:
        severity = "critical"
    elif empty_sources or missing_dates or price_diff_rows or volume_diff_rows:
        severity = "warning"
    else:
        severity = "ok"
    report = {
        "symbol": symbol_key,
        "startDate": start_date,
        "endDate": end_date,
        "adjust": adjust_key,
        "sources": normalized_sources,
        "baseSource": base_source,
        "severity": severity,
        "passed": severity == "ok",
        "tolerances": {
            "priceAbs": price_abs_tolerance,
            "priceRelBps": price_rel_tolerance_bps,
            "volumeRelPct": volume_rel_tolerance_pct,
        },
        "sourceCoverage": coverage,
        "priceMismatchCount": len(price_diff_rows),
        "volumeMismatchCount": len(volume_diff_rows),
        "priceMismatches": _bounded_mismatches(price_diff_rows),
        "volumeMismatches": _bounded_mismatches(volume_diff_rows),
    }
    if persist:
        report["reportId"] = _persist_report(report)
    return report


def list_quality_reports(limit: int = 100) -> list[dict[str, Any]]:
    bounded_limit = max(1, min(int(limit), 1000))
    with db() as connection:
        rows = connection.execute(
            """
            select *
            from data_quality_reports
            order by created_at desc
            limit ?
            """,
            (bounded_limit,),
        ).fetchall()
    return rows_to_dicts(rows)
