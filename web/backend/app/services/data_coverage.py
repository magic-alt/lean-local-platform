from __future__ import annotations

from typing import Any

from ..db import db, row_to_dict, rows_to_dicts
from .ashare_multisource import quality_gate_range
from .ashare_repository import data_coverage, reference_data_coverage
from .data import provider_availability
from .source_gate import resolve_effective_data_source, source_certification
from . import market_lake


def _row_count(sql: str, params: tuple[Any, ...]) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute(sql, params).fetchone()
    return row_to_dict(row) or {}


def symbol_coverage(
    symbol: str,
    *,
    start_date: str,
    end_date: str,
    source: str | None = None,
    adjust: str = "raw",
) -> dict[str, Any]:
    source_policy = resolve_effective_data_source(source, start_date=start_date, end_date=end_date)
    provider_source = source_policy["effectiveSource"]
    bars = data_coverage(symbol, start_date, end_date, adjust, source=provider_source)
    status_rows = market_lake.query_matching(
        kind="trade_status", asset_class="equity", market="china", venue="china",
        columns="trade_date,is_suspended,is_st,is_limit_up,is_limit_down",
        predicates=("symbol = ?", "trade_date between ? and ?"),
        parameters=(symbol, start_date, end_date),
    )
    status_dates = sorted({str(row["trade_date"])[:10] for row in status_rows})
    status = {
        "rows": len(status_dates),
        "suspended_rows": sum(bool(row.get("is_suspended")) for row in status_rows),
        "st_rows": sum(bool(row.get("is_st")) for row in status_rows),
        "limit_up_rows": sum(bool(row.get("is_limit_up")) for row in status_rows),
        "limit_down_rows": sum(bool(row.get("is_limit_down")) for row in status_rows),
        "start_date": status_dates[0] if status_dates else None,
        "end_date": status_dates[-1] if status_dates else None,
    }
    factor_rows = market_lake.query_matching(
        kind="adjustment_factor", columns="trade_date",
        predicates=("symbol = ?", "trade_date between ? and ?"),
        parameters=(symbol, start_date, end_date),
    )
    factor_dates = sorted(str(row["trade_date"])[:10] for row in factor_rows)
    adjustments = {
        "rows": len(factor_rows),
        "start_date": factor_dates[0] if factor_dates else None,
        "end_date": factor_dates[-1] if factor_dates else None,
    }
    actions = _row_count(
        """
        select count(*) as rows, min(ex_date) as start_date, max(ex_date) as end_date
        from corporate_actions
        where symbol = ? and ex_date between ? and ?
        """,
        (symbol, start_date, end_date),
    )
    qa = quality_gate_range(symbol, start_date, end_date)
    certification = source_certification(provider_source)
    issues: list[str] = []
    warnings: list[str] = []
    bar_count = max(int(bars.get("bar_count") or 0), int(bars.get("market_bar_count") or 0))
    status_count = int(status.get("rows") or 0)
    if bar_count <= 0:
        issues.append("daily_bars_missing")
    if status_count < bar_count:
        issues.append("trade_status_incomplete")
    if int(adjustments.get("rows") or 0) <= 0:
        warnings.append("adjustment_factors_missing")
    if certification.get("environment") != "production" or not certification.get("isCertified"):
        issues.append(f"source_not_certified:{provider_source}")
    if not qa.get("passed"):
        issues.append("qa_critical")
    severity = "critical" if issues else ("warning" if warnings else "ok")
    return {
        "symbol": symbol,
        "source": provider_source,
        "sourcePolicy": source_policy,
        "startDate": start_date,
        "endDate": end_date,
        "severity": severity,
        "passed": severity == "ok",
        "issues": issues,
        "warnings": warnings,
        "dailyBars": bars,
        "tradeStatus": status,
        "adjustmentFactors": adjustments,
        "corporateActions": actions,
        "qa": qa,
        "sourceCertification": certification,
    }


def benchmark_coverage(
    symbol: str,
    *,
    start_date: str,
    end_date: str,
    source: str | None = None,
    adjust: str = "raw",
) -> dict[str, Any]:
    source_policy = resolve_effective_data_source(source, start_date=start_date, end_date=end_date)
    provider_source = source_policy["effectiveSource"]
    market_rows: list[dict[str, Any]] = []
    for asset_class in ("index", "equity"):
        market_rows.extend(
            market_lake.query_matching(
                kind="bars", asset_class=asset_class, market="china",
                resolution="daily", data_type="trade", adjust=adjust, source=provider_source,
                columns="trade_date", predicates=("symbol = ?", "trade_date between ? and ?"),
                parameters=(symbol, start_date, end_date),
            )
        )
    dates = sorted({str(item["trade_date"])[:10] for item in market_rows})
    row = {
        "rows": len(dates),
        "start_date": dates[0] if dates else None,
        "end_date": dates[-1] if dates else None,
    }
    rows = int(row.get("rows") or 0)
    issues = [] if rows > 0 else ["benchmark_missing"]
    return {
        "symbol": symbol,
        "source": provider_source,
        "sourcePolicy": source_policy,
        "startDate": start_date,
        "endDate": end_date,
        "severity": "ok" if rows > 0 else "critical",
        "passed": rows > 0,
        "issues": issues,
        "dailyBars": row,
    }


def ashare_coverage(
    *,
    symbols: list[str],
    benchmark: str = "000300",
    start_date: str,
    end_date: str,
    source: str | None = None,
    reference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_policy = resolve_effective_data_source(source, start_date=start_date, end_date=end_date)
    provider_source = source_policy["effectiveSource"]
    symbol_items = [symbol_coverage(symbol, start_date=start_date, end_date=end_date, source=provider_source) for symbol in symbols]
    benchmark_item = benchmark_coverage(benchmark, start_date=start_date, end_date=end_date, source=provider_source)
    reference = reference if reference is not None else reference_data_coverage("CSI300")
    providers = provider_availability()
    with db() as connection:
        qa_rows = connection.execute(
            """
            select id, report_type, symbol, severity, start_date, end_date, created_at
            from data_quality_reports
            where asset_class = 'equity' and market = 'china'
            order by created_at desc
            limit 20
            """
        ).fetchall()
    items = [*symbol_items, benchmark_item]
    severity = (
        "critical"
        if any(item["severity"] == "critical" for item in items) or reference.get("severity") == "critical"
        else ("warning" if reference.get("warnings") else "ok")
    )
    return {
        "source": provider_source,
        "sourcePolicy": source_policy,
        "symbols": symbol_items,
        "benchmark": benchmark_item,
        "reference": reference,
        "providerAvailability": providers,
        "qaReports": rows_to_dicts(qa_rows),
        "severity": severity,
        "passed": severity == "ok",
        "warnings": reference.get("warnings") or [],
        "issues": [
            *[issue for item in items for issue in item.get("issues", [])],
            *(reference.get("issues") or []),
        ],
    }
