from __future__ import annotations

from typing import Any

from ..db import db, row_to_dict, rows_to_dicts
from .ashare_multisource import quality_gate_range
from .ashare_repository import data_coverage, reference_data_coverage
from .data import provider_availability
from .source_gate import normalize_source, source_certification


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
    provider_source = normalize_source(source)
    bars = data_coverage(symbol, start_date, end_date, adjust, source=provider_source)
    status = _row_count(
        """
        select count(distinct trade_date) as rows,
               sum(case when is_suspended = 1 then 1 else 0 end) as suspended_rows,
               sum(case when is_st = 1 then 1 else 0 end) as st_rows,
               sum(case when is_limit_up = 1 then 1 else 0 end) as limit_up_rows,
               sum(case when is_limit_down = 1 then 1 else 0 end) as limit_down_rows,
               min(trade_date) as start_date,
               max(trade_date) as end_date
        from ashare_trade_status
        where symbol = ? and trade_date between ? and ?
        """,
        (symbol, start_date, end_date),
    )
    adjustments = _row_count(
        """
        select count(*) as rows, min(trade_date) as start_date, max(trade_date) as end_date
        from adjustment_factors
        where symbol = ? and trade_date between ? and ?
        """,
        (symbol, start_date, end_date),
    )
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
    provider_source = normalize_source(source)
    row = _row_count(
        """
        select count(distinct trade_date) as rows, min(trade_date) as start_date, max(trade_date) as end_date
        from market_daily_bars
        where symbol = ? and asset_class = 'equity' and market = 'china'
          and resolution = 'daily' and data_type = 'trade' and adjust = ? and source = ?
          and trade_date between ? and ?
        """,
        (symbol, adjust, provider_source, start_date, end_date),
    )
    rows = int(row.get("rows") or 0)
    issues = [] if rows > 0 else ["benchmark_missing"]
    return {
        "symbol": symbol,
        "source": provider_source,
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
) -> dict[str, Any]:
    provider_source = normalize_source(source)
    symbol_items = [symbol_coverage(symbol, start_date=start_date, end_date=end_date, source=provider_source) for symbol in symbols]
    benchmark_item = benchmark_coverage(benchmark, start_date=start_date, end_date=end_date, source=provider_source)
    reference = reference_data_coverage("CSI300")
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
    severity = "critical" if any(item["severity"] == "critical" for item in items) else ("warning" if reference.get("warnings") else "ok")
    return {
        "source": provider_source,
        "symbols": symbol_items,
        "benchmark": benchmark_item,
        "reference": reference,
        "providerAvailability": providers,
        "qaReports": rows_to_dicts(qa_rows),
        "severity": severity,
        "passed": severity == "ok",
        "warnings": reference.get("warnings") or [],
        "issues": [issue for item in items for issue in item.get("issues", [])],
    }
