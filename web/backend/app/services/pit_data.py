from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any

from ..core.errors import LeanWebError
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..lean_engine.symbols import normalize_symbol, parse_date
from .ashare_repository import tradable_universe_as_of, universe_as_of, upsert_security, upsert_universe_membership


CSI300_OFFICIAL_COVERAGE_START = "2017-12-08"
INDEX_OFFICIAL_COVERAGE_STARTS = {"CSI300": CSI300_OFFICIAL_COVERAGE_START}


def _date(value: Any, field: str) -> str:
    if value in (None, ""):
        raise LeanWebError(f"{field} is required.")
    return parse_date(str(value)[:10]).isoformat()


def _optional_date(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return parse_date(str(value)[:10]).isoformat()


def _field_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_symbol(symbol: str, market: str = "china") -> str:
    return normalize_symbol(symbol, market).upper()


def assert_pit_dates(record: dict[str, Any], as_of_date: str) -> None:
    as_of = _date(as_of_date, "as_of_date")
    for field in ("announce_date", "effective_date"):
        value = record.get(field)
        if value and _date(value, field) > as_of:
            raise LeanWebError(f"PIT violation: {field}={value} is after as_of_date={as_of}.")


def index_coverage_gap(index_code: str, as_of_date: str) -> dict[str, Any] | None:
    code = str(index_code or "").strip().upper()
    as_of = _date(as_of_date, "as_of_date")
    coverage_start = INDEX_OFFICIAL_COVERAGE_STARTS.get(code)
    if not coverage_start or as_of >= coverage_start:
        return None
    return {
        "coverageStatus": "coverage_gap",
        "coverageStart": coverage_start,
        "missingHistoryBefore": coverage_start,
        "isOfficialHistoryComplete": False,
        "reason": f"{code} official PIT history before {coverage_start} has not been imported.",
    }


def index_members_as_of_payload(
    universe_code: str,
    as_of_date: str,
    *,
    requested_universe: str | None = None,
    tradable: bool = False,
    min_listed_days: int = 0,
    exclude_st: bool = True,
) -> dict[str, Any]:
    code = str(universe_code or "").strip().upper()
    requested = str(requested_universe or universe_code or "").strip().upper()
    as_of = _date(as_of_date, "as_of_date")
    gap = index_coverage_gap(code, as_of)
    if gap:
        return {"universe": code, "requestedUniverse": requested, "asOfDate": as_of, "items": [], "count": 0, **gap}
    if tradable:
        items = tradable_universe_as_of(code, as_of, min_listed_days=min_listed_days, exclude_st=exclude_st)
    else:
        items = universe_as_of(code, as_of)
    payload = {"universe": code, "requestedUniverse": requested, "asOfDate": as_of, "items": items, "count": len(items)}
    coverage_start = INDEX_OFFICIAL_COVERAGE_STARTS.get(code)
    if coverage_start:
        payload.update({"coverageStatus": "ok", "coverageStart": coverage_start, "isOfficialHistoryComplete": False})
    return payload


def import_financial_statement(
    *,
    symbol: str,
    statement_type: str,
    report_date: str,
    announce_date: str,
    fields: dict[str, Any],
    effective_date: str | None = None,
    fiscal_period: str | None = None,
    currency: str | None = "CNY",
    source: str = "manual",
    batch_id: str | None = None,
) -> dict[str, Any]:
    ticker = _clean_symbol(symbol)
    report = _date(report_date, "report_date")
    announce = _date(announce_date, "announce_date")
    effective = _optional_date(effective_date) or announce
    if effective < announce:
        raise LeanWebError("effective_date cannot be earlier than announce_date.")
    batch = batch_id or str(uuid.uuid4())
    now = utc_now()
    statement = statement_type.strip().lower()
    clean_fields = dict(fields or {})
    with db() as connection:
        connection.execute(
            """
            insert into financial_statements
                (symbol, statement_type, report_date, announce_date, effective_date,
                 fiscal_period, currency, fields_json, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(symbol, statement_type, report_date, announce_date, source) do update set
                effective_date = excluded.effective_date,
                fiscal_period = excluded.fiscal_period,
                currency = excluded.currency,
                fields_json = excluded.fields_json,
                batch_id = excluded.batch_id,
                created_at = excluded.created_at
            """,
            (
                ticker,
                statement,
                report,
                announce,
                effective,
                fiscal_period,
                currency,
                json_dump(clean_fields),
                source,
                batch,
                now,
            ),
        )
        for name, value in clean_fields.items():
            number = _field_number(value)
            if number is None:
                continue
            connection.execute(
                """
                insert into financial_facts
                    (symbol, field_name, report_date, announce_date, effective_date,
                     value, unit, source, batch_id, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(symbol, field_name, report_date, announce_date, source) do update set
                    effective_date = excluded.effective_date,
                    value = excluded.value,
                    unit = excluded.unit,
                    batch_id = excluded.batch_id,
                    created_at = excluded.created_at
                """,
                (ticker, str(name), report, announce, effective, number, currency, source, batch, now),
            )
    return financial_statement(ticker, statement, report, announce, source) or {}


def import_financial_statements(records: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    imported = []
    for record in records:
        imported.append(
            import_financial_statement(
                symbol=record["symbol"],
                statement_type=record.get("statement_type") or record.get("statementType") or "metrics",
                report_date=record["report_date"] if "report_date" in record else record["reportDate"],
                announce_date=record["announce_date"] if "announce_date" in record else record["announceDate"],
                effective_date=record.get("effective_date") or record.get("effectiveDate"),
                fiscal_period=record.get("fiscal_period") or record.get("fiscalPeriod"),
                currency=record.get("currency") or "CNY",
                fields=record.get("fields") or {},
                source=record.get("source") or source,
                batch_id=batch_id,
            )
        )
    return {"batchId": batch_id, "count": len(imported), "items": imported}


def financial_statement(
    symbol: str,
    statement_type: str,
    report_date: str,
    announce_date: str,
    source: str,
) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            """
            select * from financial_statements
            where symbol = ? and statement_type = ? and report_date = ? and announce_date = ? and source = ?
            """,
            (_clean_symbol(symbol), statement_type, report_date, announce_date, source),
        ).fetchone()
    return row_to_dict(row)


def financial_statements_as_of(
    symbol: str,
    as_of_date: str,
    statement_type: str | None = None,
) -> list[dict[str, Any]]:
    ticker = _clean_symbol(symbol)
    as_of = _date(as_of_date, "as_of_date")
    clauses = ["symbol = ?", "announce_date <= ?", "effective_date <= ?"]
    values: list[Any] = [ticker, as_of, as_of]
    if statement_type:
        clauses.append("statement_type = ?")
        values.append(statement_type.strip().lower())
    with db() as connection:
        rows = connection.execute(
            f"""
            select * from financial_statements
            where {" and ".join(clauses)}
            order by statement_type asc, report_date desc, announce_date desc
            """,
            values,
        ).fetchall()
    latest: dict[str, dict[str, Any]] = {}
    for item in rows_to_dicts(rows):
        latest.setdefault(item["statement_type"], item)
    return list(latest.values())


def financial_factors_as_of(
    symbols: list[str],
    as_of_date: str,
    fields: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    as_of = _date(as_of_date, "as_of_date")
    tickers = [_clean_symbol(symbol) for symbol in symbols]
    if not tickers:
        return {}
    placeholders = ",".join("?" for _ in tickers)
    values: list[Any] = [*tickers, as_of, as_of]
    field_clause = ""
    if fields:
        field_placeholders = ",".join("?" for _ in fields)
        field_clause = f" and field_name in ({field_placeholders})"
        values.extend(fields)
    with db() as connection:
        rows = connection.execute(
            f"""
            select * from financial_facts
            where symbol in ({placeholders})
              and announce_date <= ?
              and effective_date <= ?
              {field_clause}
            order by symbol asc, field_name asc, report_date desc, announce_date desc
            """,
            values,
        ).fetchall()
    result: dict[str, dict[str, Any]] = {symbol: {} for symbol in tickers}
    seen: set[tuple[str, str]] = set()
    for row in rows_to_dicts(rows):
        key = (row["symbol"], row["field_name"])
        if key in seen:
            continue
        seen.add(key)
        result[row["symbol"]][row["field_name"]] = {
            "value": row["value"],
            "report_date": row["report_date"],
            "announce_date": row["announce_date"],
            "effective_date": row["effective_date"],
            "source": row["source"],
        }
    return result


def import_index_members(records: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    imported = 0
    for record in records:
        symbol = _clean_symbol(record["symbol"])
        start_date = _date(record.get("start_date") or record.get("startDate"), "start_date")
        announce_date = _optional_date(record.get("announce_date") or record.get("announceDate"))
        effective_date = _optional_date(record.get("effective_date") or record.get("effectiveDate")) or start_date
        if announce_date and effective_date < announce_date:
            raise LeanWebError("Index member effective_date cannot be earlier than announce_date.")
        upsert_security(
            symbol=symbol,
            name=record.get("name") or symbol,
            listed_date=record.get("listed_date") or record.get("listedDate") or start_date,
            industry=record.get("industry"),
        )
        upsert_universe_membership(
            record["universe_code"] if "universe_code" in record else record["universeCode"],
            symbol,
            start_date,
            _optional_date(record.get("end_date") or record.get("endDate")),
            source=record.get("source") or source,
            batch_id=batch_id,
            weight=_field_number(record.get("weight")),
            announce_date=announce_date,
            effective_date=effective_date,
        )
        imported += 1
    return {"batchId": batch_id, "count": imported}


def fetch_tushare_financials(symbol: str, token: str | None = None) -> list[dict[str, Any]]:
    token = token or os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise LeanWebError("TUSHARE_TOKEN is required for TuShare prototype fetch.")
    try:
        import tushare as ts  # type: ignore
    except ImportError as exc:
        raise LeanWebError("tushare is not installed. Install it only if you want provider fetches.") from exc
    pro = ts.pro_api(token)
    ts_code = symbol if "." in symbol else f"{_clean_symbol(symbol)}.SH"
    frame = pro.fina_indicator(ts_code=ts_code)
    if frame is None or getattr(frame, "empty", True):
        return []
    records = []
    for item in frame.to_dict("records"):
        announce_date = item.get("ann_date")
        end_date = item.get("end_date")
        if not announce_date or not end_date:
            continue
        fields = {key: value for key, value in item.items() if key not in {"ts_code", "ann_date", "end_date"}}
        records.append(
            {
                "symbol": symbol,
                "statement_type": "financial_indicator",
                "report_date": datetime.strptime(str(end_date), "%Y%m%d").date().isoformat(),
                "announce_date": datetime.strptime(str(announce_date), "%Y%m%d").date().isoformat(),
                "fields": fields,
                "source": "tushare",
            }
        )
    return records


def fetch_jqdata_financials(symbol: str, username: str | None = None, password: str | None = None) -> list[dict[str, Any]]:
    username = username or os.environ.get("JQDATA_USERNAME")
    password = password or os.environ.get("JQDATA_PASSWORD")
    if not username or not password:
        raise LeanWebError("JQDATA_USERNAME and JQDATA_PASSWORD are required for JQData prototype fetch.")
    try:
        import jqdatasdk as jq  # type: ignore
    except ImportError as exc:
        raise LeanWebError("jqdatasdk is not installed. Install it only if you want provider fetches.") from exc
    jq.auth(username, password)
    code = symbol if "." in symbol else f"{_clean_symbol(symbol)}.XSHG"
    try:
        query = jq.query(jq.finance.STK_FIN_FORCAST).filter(jq.finance.STK_FIN_FORCAST.code == code)
        frame = jq.finance.run_query(query)
    except Exception as exc:
        raise LeanWebError(f"JQData financial prototype request failed: {exc}") from exc
    if frame is None or getattr(frame, "empty", True):
        return []
    records = []
    for item in frame.to_dict("records"):
        report_date = item.get("report_date") or item.get("end_date") or item.get("statDate")
        announce_date = item.get("pub_date") or item.get("announce_date") or item.get("day")
        if not report_date or not announce_date:
            continue
        fields = {key: value for key, value in item.items() if key not in {"code", "report_date", "end_date", "statDate", "pub_date", "announce_date", "day"}}
        records.append(
            {
                "symbol": symbol,
                "statement_type": "jq_financial_forecast",
                "report_date": str(report_date)[:10],
                "announce_date": str(announce_date)[:10],
                "fields": fields,
                "source": "jqdata",
            }
        )
    return records
