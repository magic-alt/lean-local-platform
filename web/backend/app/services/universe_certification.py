from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..lean_engine.symbols import normalize_symbol
from .ashare_multisource import compare_ashare_daily_sources_batch
from .data_coverage import benchmark_coverage, symbol_coverage
from .instrument_identity import INDEX_SYMBOLS, identifier_coverage
from .provider_certification import add_warning_allowlist, warning_allowlist_status
from .source_gate import require_source_allowed, resolve_effective_data_source, source_priority_for_window


def _symbols(value: list[str] | None) -> list[str] | None:
    if not value:
        return None
    return sorted({normalize_symbol(item, "china") for item in value if str(item).strip()})


def _valid_until(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=max(1, int(days)))).date().isoformat()


def candidate_symbols(
    *,
    source: str,
    start_date: str,
    end_date: str,
    target_size: int,
    candidates: list[str] | None = None,
) -> list[str]:
    selected = _symbols(candidates)
    if selected:
        return [symbol for symbol in selected if symbol not in INDEX_SYMBOLS][: max(1, target_size)]
    rows_by_symbol: dict[str, dict[str, Any]] = {}
    with db() as connection:
        for row in connection.execute(
            """
            select symbol, count(distinct trade_date) as rows, avg(coalesce(amount, volume, 0)) as liquidity
            from ashare_daily_bars
            where source = ? and adjust = 'raw' and trade_date between ? and ?
            group by symbol
            """,
            (source, start_date, end_date),
        ).fetchall():
            rows_by_symbol[row["symbol"]] = {"symbol": row["symbol"], "rows": int(row["rows"] or 0), "liquidity": float(row["liquidity"] or 0)}
        for row in connection.execute(
            """
            select symbol, count(distinct trade_date) as rows, avg(coalesce(amount, volume, 0)) as liquidity
            from market_daily_bars
            where source = ? and asset_class = 'equity' and market = 'china'
              and resolution = 'daily' and data_type = 'trade' and adjust = 'raw'
              and trade_date between ? and ?
            group by symbol
            """,
            (source, start_date, end_date),
        ).fetchall():
            item = rows_by_symbol.setdefault(row["symbol"], {"symbol": row["symbol"], "rows": 0, "liquidity": 0.0})
            item["rows"] = max(int(item["rows"]), int(row["rows"] or 0))
            item["liquidity"] = max(float(item["liquidity"]), float(row["liquidity"] or 0))
    ranked = sorted(rows_by_symbol.values(), key=lambda item: (item["rows"], item["liquidity"], item["symbol"]), reverse=True)
    return [item["symbol"] for item in ranked if item["symbol"] not in INDEX_SYMBOLS][: max(1, int(target_size))]


def _coverage_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(items)
    if not count:
        return {
            "dailyBarsCoverage": 0.0,
            "tradeStatusCoverage": 0.0,
            "adjustmentFactorCoverage": 0.0,
            "stCoverage": 0.0,
            "suspendedCoverage": 0.0,
            "limitCoverage": 0.0,
            "corporateActionCoverage": 0.0,
        }
    return {
        "dailyBarsCoverage": sum(1 for item in items if max(int(item["coverage"]["dailyBars"].get("bar_count") or 0), int(item["coverage"]["dailyBars"].get("market_bar_count") or 0)) > 0) / count,
        "tradeStatusCoverage": sum(1 for item in items if int(item["coverage"]["tradeStatus"].get("rows") or 0) > 0) / count,
        "adjustmentFactorCoverage": sum(1 for item in items if int(item["coverage"]["adjustmentFactors"].get("rows") or 0) > 0) / count,
        "stCoverage": sum(1 for item in items if item["coverage"]["tradeStatus"].get("st_rows") is not None) / count,
        "suspendedCoverage": sum(1 for item in items if item["coverage"]["tradeStatus"].get("suspended_rows") is not None) / count,
        "limitCoverage": sum(1 for item in items if item["coverage"]["tradeStatus"].get("limit_up_rows") is not None and item["coverage"]["tradeStatus"].get("limit_down_rows") is not None) / count,
        "corporateActionCoverage": sum(1 for item in items if item["coverage"]["corporateActions"].get("rows") is not None) / count,
    }


def build_certified_universe(
    *,
    universe_code: str,
    source: str,
    benchmark: str,
    start_date: str,
    end_date: str,
    target_size: int,
    min_size: int,
    candidates: list[str] | None = None,
    allow_warning_codes: list[str] | None = None,
    warning_expiry_days: int = 30,
    approved_by: str = "level3plus-cli",
) -> dict[str, Any]:
    now = utc_now()
    code = universe_code.strip().upper()
    source_policy = resolve_effective_data_source(source, start_date=start_date, end_date=end_date)
    source_key = require_source_allowed(source_policy["effectiveSource"])
    target = max(1, int(target_size))
    minimum = max(1, int(min_size))
    allow_codes = sorted({item.strip() for item in (allow_warning_codes or []) if item.strip()})
    selected = candidate_symbols(source=source_key, start_date=start_date, end_date=end_date, target_size=target, candidates=candidates)
    benchmark_item = benchmark_coverage(benchmark, start_date=start_date, end_date=end_date, source=source_key)
    id_cov = identifier_coverage(selected)
    qa = compare_ashare_daily_sources_batch(
        symbols=selected,
        sources=source_priority_for_window(source=source, start_date=start_date, end_date=end_date),
        start_date=start_date,
        end_date=end_date,
        persist=True,
        persist_symbol_reports=True,
    ) if selected else {"severity": "critical", "criticalSymbols": [], "warningSymbols": [], "reportId": None}
    qa_warning_code = "provider_secondary_missing" if qa.get("severity") == "warning" else None
    symbol_items: list[dict[str, Any]] = []
    certified: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    for symbol in selected:
        coverage = symbol_coverage(symbol, start_date=start_date, end_date=end_date, source=source_key)
        item_warnings = list(coverage.get("warnings") or [])
        item_errors = list(coverage.get("issues") or [])
        if symbol in set(qa.get("criticalSymbols") or []):
            item_errors.append("qa_critical")
        if symbol in set(qa.get("warningSymbols") or []) and qa_warning_code:
            item_warnings.append(qa_warning_code)
        if id_cov["counts"].get(symbol, 0) <= 0 or symbol in id_cov.get("missingReasons", {}):
            item_errors.append("identifier_missing")
        unaccepted = [warning for warning in item_warnings if warning not in allow_codes]
        status = "certified" if not item_errors and not unaccepted else "failed"
        if status == "certified":
            certified.append(symbol)
        errors.extend(f"{symbol}:{error}" for error in item_errors)
        warnings.extend(f"{symbol}:{warning}" for warning in item_warnings)
        symbol_items.append(
            {
                "symbol": symbol,
                "status": status,
                "coverage": coverage,
                "qa": {"batchReportId": qa.get("reportId"), "severity": "critical" if symbol in set(qa.get("criticalSymbols") or []) else ("warning" if symbol in set(qa.get("warningSymbols") or []) else "ok")},
                "warnings": item_warnings,
                "errors": item_errors + [f"unaccepted_warning:{warning}" for warning in unaccepted],
            }
        )
    accepted_records = []
    accepted_codes = sorted({warning.split(":", 1)[1] for warning in warnings if ":" in warning and warning.split(":", 1)[1] in allow_codes})
    for warning_code in accepted_codes:
        accepted_records.append(
            add_warning_allowlist(
                warning_code=warning_code,
                reason=f"Accepted for {code} certification window {start_date}..{end_date}",
                valid_until=_valid_until(warning_expiry_days),
                approved_by=approved_by,
                affected_symbols=selected,
                scope={"universeCode": code, "source": source_key, "startDate": start_date, "endDate": end_date},
            )
        )
    warning_status = warning_allowlist_status(accepted_codes, affected_symbols=selected, scope={"universeCode": code})
    if benchmark_item["severity"] == "critical":
        errors.append("benchmark_missing")
    if len(certified) < minimum:
        errors.append("certified_symbol_count_below_minimum")
    severity = "critical" if errors or qa.get("severity") == "critical" or benchmark_item["severity"] == "critical" else ("warning" if warnings else "ok")
    certification_status = "certified" if severity in {"ok", "warning"} and len(certified) >= minimum and not warning_status["expiredWarnings"] else "failed"
    metrics = _coverage_metrics(symbol_items)
    coverage_report = {
        "universeCode": code,
        "symbolCount": len(certified),
        "candidateCount": len(selected),
        "identifierCoverage": 1.0 if not certified else identifier_coverage(certified)["coverageRatio"],
        "allIdentifierCoverage": id_cov,
        "benchmark": benchmark_item,
        "sourcePolicy": source_policy,
        **metrics,
        "symbols": symbol_items,
    }
    report_id = str(uuid.uuid4())
    cert_id = str(uuid.uuid5(uuid.UUID("4f69c6eb-72dc-4a9f-b3ff-5f8e28d51810"), f"{code}:{source_key}:{start_date}:{end_date}"))
    with db() as connection:
        connection.execute(
            """
            insert into paper_universe_certifications
                (id, universe_code, source, benchmark_symbol, certification_status, certification_date,
                 start_date, end_date, target_size, min_size, symbol_count, coverage_report_id,
                 qa_report_id, valid_from, valid_to, coverage_json, qa_report_json,
                 warnings_json, errors_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(universe_code, source, start_date, end_date) do update set
                benchmark_symbol = excluded.benchmark_symbol,
                certification_status = excluded.certification_status,
                certification_date = excluded.certification_date,
                target_size = excluded.target_size,
                min_size = excluded.min_size,
                symbol_count = excluded.symbol_count,
                coverage_report_id = excluded.coverage_report_id,
                qa_report_id = excluded.qa_report_id,
                valid_from = excluded.valid_from,
                valid_to = excluded.valid_to,
                coverage_json = excluded.coverage_json,
                qa_report_json = excluded.qa_report_json,
                warnings_json = excluded.warnings_json,
                errors_json = excluded.errors_json,
                updated_at = excluded.updated_at
            """,
            (
                cert_id,
                code,
                source_key,
                benchmark,
                certification_status,
                now,
                start_date,
                end_date,
                target,
                minimum,
                len(certified),
                report_id,
                qa.get("reportId"),
                start_date,
                end_date,
                json_dump(coverage_report),
                json_dump(qa),
                json_dump(sorted(set(warnings))),
                json_dump(sorted(set(errors))),
                now,
                now,
            ),
        )
        for item in symbol_items:
            row_id = str(uuid.uuid5(uuid.UUID("169d9513-5101-47fc-b3c3-378744c72ed5"), f"{code}:{item['symbol']}:{start_date}"))
            connection.execute(
                """
                insert into paper_universe_symbols
                    (id, universe_code, symbol, source, certification_status, certification_date,
                     coverage_report_id, qa_report_id, valid_from, valid_to, coverage_json,
                     qa_json, warnings_json, errors_json, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(universe_code, symbol, valid_from) do update set
                    source = excluded.source,
                    certification_status = excluded.certification_status,
                    certification_date = excluded.certification_date,
                    coverage_report_id = excluded.coverage_report_id,
                    qa_report_id = excluded.qa_report_id,
                    valid_to = excluded.valid_to,
                    coverage_json = excluded.coverage_json,
                    qa_json = excluded.qa_json,
                    warnings_json = excluded.warnings_json,
                    errors_json = excluded.errors_json,
                    updated_at = excluded.updated_at
                """,
                (
                    row_id,
                    code,
                    item["symbol"],
                    source_key,
                    item["status"],
                    now,
                    report_id,
                    qa.get("reportId"),
                    start_date,
                    end_date,
                    json_dump(item["coverage"]),
                    json_dump(item["qa"]),
                    json_dump(item["warnings"]),
                    json_dump(item["errors"]),
                    now,
                    now,
                ),
            )
    return {
        "status": certification_status,
        "severity": severity,
        "universeCode": code,
        "source": source_key,
        "requestedSource": source_policy["requestedSource"],
        "sourcePolicy": source_policy,
        "benchmark": benchmark,
        "symbolCount": len(certified),
        "candidateCount": len(selected),
        "symbols": certified,
        "coverageReportId": report_id,
        "qaReportId": qa.get("reportId"),
        "coverage": coverage_report,
        "qa": qa,
        "acceptedWarnings": accepted_records,
        "expiredWarnings": warning_status["expiredWarnings"],
        "warnings": sorted(set(warnings)),
        "errors": sorted(set(errors)),
    }


def get_certified_universe(universe_code: str) -> dict[str, Any]:
    code = universe_code.strip().upper()
    with db() as connection:
        cert = connection.execute(
            """
            select *
            from paper_universe_certifications
            where universe_code = ?
            order by certification_date desc
            limit 1
            """,
            (code,),
        ).fetchone()
        rows = connection.execute(
            """
            select *
            from paper_universe_symbols
            where universe_code = ?
            order by symbol asc
            """,
            (code,),
        ).fetchall()
    return {"certification": row_to_dict(cert), "symbols": rows_to_dicts(rows), "universeCode": code}


def certified_symbols(universe_code: str) -> list[str]:
    with db() as connection:
        rows = connection.execute(
            """
            select symbol
            from paper_universe_symbols
            where universe_code = ? and certification_status = 'certified'
            order by symbol asc
            """,
            (universe_code.strip().upper(),),
        ).fetchall()
    return [row["symbol"] for row in rows]
