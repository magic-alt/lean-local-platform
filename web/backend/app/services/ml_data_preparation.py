from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, timedelta
from typing import Any, Callable

from ..db import db, json_dump, utc_now
from ..research.factors import upsert_factor_values
from .ashare_repository import upsert_index_weights, upsert_universe_membership
from .pit_data import import_financial_statements
from .tushare_adapter import TushareAdapter


DEFAULT_DATASETS = [
    "daily_basic", "income", "balancesheet", "cashflow", "fina_indicator",
    "namechange", "sw_industry",
]


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _update_item(run_id: str, key: str, *, status: str, processed: int = 0, error: str | None = None) -> None:
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            update data_sync_items set status=?, processed=?, inserted=?, failed=?, error=?,
                started_at=coalesce(started_at, ?), finished_at=?
            where run_id=? and dataset_key=?
            """,
            (status, processed, processed if status == "success" else 0, 1 if error else 0,
             error, now, now if status in {"success", "failed"} else None, run_id, key),
        )


def _materialize_membership(rows: list[dict[str, Any]], batch_id: str) -> list[str]:
    by_date: dict[str, dict[str, float]] = {}
    for row in rows:
        by_date.setdefault(str(row["trade_date"]), {})[str(row["symbol"])] = float(row["weight"])
    snapshots = sorted(by_date)
    if not snapshots:
        return []
    all_symbols = sorted({symbol for members in by_date.values() for symbol in members})
    for symbol in all_symbols:
        active_start: str | None = None
        active_weight: float | None = None
        for index, snapshot in enumerate(snapshots):
            present = symbol in by_date[snapshot]
            if present and active_start is None:
                active_start = snapshot
                active_weight = by_date[snapshot][symbol]
            next_present = index + 1 < len(snapshots) and symbol in by_date[snapshots[index + 1]]
            if active_start and (not next_present or index == len(snapshots) - 1):
                end_date = None
                if index < len(snapshots) - 1:
                    end_date = (date.fromisoformat(snapshots[index + 1]) - timedelta(days=1)).isoformat()
                with db() as connection:
                    existing = connection.execute(
                        "select source from universe_membership where universe_code='CSI300' and symbol=? and start_date=?",
                        (symbol, active_start),
                    ).fetchone()
                authoritative = bool(existing and str(existing["source"] or "").startswith(("csindex:", "sse:")))
                if not authoritative:
                    upsert_universe_membership(
                        "CSI300", symbol, active_start, end_date,
                        source="tushare:index_weight:pit_snapshot", batch_id=batch_id,
                        weight=active_weight, announce_date=active_start, effective_date=active_start,
                    )
                active_start = None
                active_weight = None
    return all_symbols


def _upsert_names(rows: list[dict[str, Any]]) -> int:
    now = utc_now()
    parameters = [
        (
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"name:{row['symbol']}:{row['start_date']}:{row['name']}")),
            row["symbol"], row["name"], row["start_date"], row.get("end_date"),
            int(bool(row.get("is_st"))), row.get("source") or "tushare:namechange", _digest(row), now,
        )
        for row in rows
    ]
    if parameters:
        with db() as connection:
            connection.executemany(
                """
                insert into security_name_history
                    (id,symbol,name,start_date,end_date,is_st,source,payload_hash,created_at)
                values (?,?,?,?,?,?,?,?,?)
                on conflict(symbol,start_date,name) do update set
                    end_date=excluded.end_date,is_st=excluded.is_st,
                    source=excluded.source,payload_hash=excluded.payload_hash
                """,
                parameters,
            )
    return len(parameters)


def _upsert_industries(rows: list[dict[str, Any]]) -> int:
    now = utc_now()
    parameters = [
        (
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"industry:{row['symbol']}:{row['industry_code']}:{row['in_date']}")),
            row["symbol"], row["industry_code"], row.get("industry_name"), row["taxonomy"],
            row["level_no"], row["in_date"], row.get("out_date"), row["source"], _digest(row), now,
        )
        for row in rows
    ]
    if parameters:
        with db() as connection:
            connection.executemany(
                """
                insert into industry_membership
                    (id,symbol,industry_code,industry_name,taxonomy,level_no,in_date,out_date,
                     source,payload_hash,created_at)
                values (?,?,?,?,?,?,?,?,?,?,?)
                on conflict(symbol,industry_code,taxonomy,in_date) do update set
                    industry_name=excluded.industry_name,out_date=excluded.out_date,
                    source=excluded.source,payload_hash=excluded.payload_hash
                """,
                parameters,
            )
    return len(parameters)


def preparation_preview(start_date: str, end_date: str) -> dict[str, Any]:
    with db() as connection:
        member_row = connection.execute(
            """select count(distinct symbol) symbols, min(start_date) first_date, max(coalesce(end_date, start_date)) last_date
               from universe_membership where universe_code='CSI300' and start_date <= ? and coalesce(end_date, ?) >= ?""",
            (end_date, end_date, start_date),
        ).fetchone()
        counts = {}
        for key, sql in {
            "dailyBasic": "select count(*) n from daily_basic_factor_values where trade_date between ? and ?",
            "financial": "select count(*) n from financial_statements where effective_date <= ? and report_date >= ?",
            "nameHistory": "select count(*) n from security_name_history where start_date <= ?",
            "industry": "select count(*) n from industry_membership where in_date <= ?",
        }.items():
            params = (start_date, end_date) if key == "dailyBasic" else (end_date, "2013-01-01") if key == "financial" else (end_date,)
            counts[key] = int(connection.execute(sql, params).fetchone()["n"] or 0)
        bars = connection.execute(
            """select count(*) n,count(distinct symbol) symbols,min(trade_date) first_date,max(trade_date) last_date
               from ashare_daily_bars where adjust='raw' and trade_date between ? and ?""",
            (start_date, end_date),
        ).fetchone()
        counts["dailyBars"] = int(bars["n"] or 0)
        counts["benchmarkBars"] = int(connection.execute(
            """select count(*) n from market_daily_bars where symbol='000300' and asset_class='index'
               and adjust='raw' and trade_date between ? and ?""",
            (start_date, end_date),
        ).fetchone()["n"] or 0)
        counts["tradeStatus"] = int(connection.execute(
            "select count(*) n from ashare_trade_status where trade_date between ? and ?",
            (start_date, end_date),
        ).fetchone()["n"] or 0)
    member = dict(member_row) if member_row else {}
    symbols = int(member.get("symbols") or 0)
    blocking = []
    if symbols < 300:
        blocking.append("csi300_pit_membership_incomplete")
    if not counts["dailyBasic"]:
        blocking.append("daily_basic_missing")
    if not counts["financial"]:
        blocking.append("financial_pit_missing")
    if not counts["nameHistory"]:
        blocking.append("st_history_missing")
    if not counts["industry"]:
        blocking.append("sw2021_industry_missing")
    if not counts["dailyBars"]:
        blocking.append("raw_daily_bars_missing")
    if not counts["benchmarkBars"]:
        blocking.append("csi300_benchmark_bars_missing")
    if not counts["tradeStatus"]:
        blocking.append("tradability_history_missing")
    counts.update({
        "rows": counts["dailyBars"], "symbols": int(bars["symbols"] or 0),
        "first_date": bars["first_date"], "last_date": bars["last_date"],
    })
    return {
        "universeCode": "CSI300", "startDate": start_date, "endDate": end_date,
        "historicalMemberSymbols": symbols, "coverage": counts, "blocking": blocking,
        "ready": not blocking,
        "preparationRequest": {
            "mode": "universe_backfill", "datasets": DEFAULT_DATASETS,
            "scope": {"type": "pit_universe_union", "universeCode": "CSI300", "startDate": start_date, "endDate": end_date},
        },
    }


def run_universe_backfill(
    run_id: str, *, log: Callable[[str], None] | None = None, cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    emit = log or (lambda _message: None)
    with db() as connection:
        run = connection.execute("select * from data_sync_runs where id=?", (run_id,)).fetchone()
    if not run:
        raise KeyError("Data synchronization run not found.")
    run = dict(run)
    scope = json.loads(run.get("request_scope_json") or "{}")
    start_date = str(scope.get("startDate") or "2015-01-01")[:10]
    end_date = str(scope.get("endDate") or date.today().isoformat())[:10]
    requested = json.loads(run.get("requested_datasets_json") or "[]") or DEFAULT_DATASETS
    adapter = TushareAdapter()
    with db() as connection:
        connection.execute("update data_sync_runs set status='running', started_at=?, heartbeat_at=? where id=?", (utc_now(), utc_now(), run_id))
    emit("Fetching CSI300 monthly PIT snapshots and freezing the historical member union.")
    weights = adapter.index_weight_rows("000300", start_date, end_date)
    if weights:
        upsert_index_weights(weights, source="tushare:index_weight", batch_id=run_id)
    symbols = _materialize_membership(weights, run_id)
    if not symbols:
        with db() as connection:
            symbols = [row["symbol"] for row in connection.execute(
                "select distinct symbol from universe_membership where universe_code='CSI300' and start_date <= ? and coalesce(end_date, ?) >= ?",
                (end_date, end_date, start_date),
            ).fetchall()]
    if not symbols:
        raise ValueError("CSI300 PIT historical member union is empty.")
    universe_hash = _digest(symbols)
    financial_start = f"{max(1990, int(start_date[:4]) - 2):04d}-01-01"
    totals = {key: 0 for key in requested}
    failures: list[dict[str, str]] = []
    for index, symbol in enumerate(symbols, start=1):
        if cancelled and cancelled():
            with db() as connection:
                connection.execute("update data_sync_runs set status='cancelled', finished_at=? where id=?", (utc_now(), run_id))
            return {"status": "cancelled", "symbols": index - 1, "universeHash": universe_hash}
        try:
            if "daily_basic" in requested:
                records = []
                for row in adapter.daily_basic_rows(symbol, start_date, end_date):
                    records.extend({"symbol": row["symbol"], "trade_date": row["trade_date"], "factor_name": name, "value": value} for name, value in row["factors"].items())
                totals["daily_basic"] += upsert_factor_values(records, source="tushare:daily_basic", batch_id=run_id, bulk=True) if records else 0
            financial_rows = []
            for key in ("income", "balancesheet", "cashflow", "fina_indicator"):
                if key in requested:
                    rows = getattr(adapter, f"{key}_rows")(symbol, financial_start, end_date)
                    financial_rows.extend(rows)
                    totals[key] += len(rows)
            if financial_rows:
                import_financial_statements(financial_rows, source="tushare:financials", bulk=True)
            if "namechange" in requested:
                totals["namechange"] += _upsert_names(adapter.namechange_rows(symbol))
            if "sw_industry" in requested or "index_member_all" in requested:
                count = _upsert_industries(adapter.sw_industry_membership_rows(symbol))
                if "sw_industry" in totals:
                    totals["sw_industry"] += count
                if "index_member_all" in totals:
                    totals["index_member_all"] += count
        except Exception as exc:
            failures.append({"symbol": symbol, "error": str(exc)})
        if index == 1 or index % 25 == 0 or index == len(symbols):
            emit(f"Prepared {index}/{len(symbols)} historical CSI300 members; failures={len(failures)}.")
            with db() as connection:
                connection.execute("update data_sync_runs set heartbeat_at=? where id=?", (utc_now(), run_id))
    for key in requested:
        _update_item(run_id, key, status="success" if totals.get(key, 0) or key in {"namechange", "sw_industry"} else "failed", processed=totals.get(key, 0), error=None if totals.get(key, 0) else "no_rows")
    summary = {
        "historicalMemberSymbols": len(symbols), "universeHash": universe_hash,
        "startDate": start_date, "endDate": end_date, "rows": totals, "failures": failures[:100],
    }
    status = "success" if len(failures) <= max(1, int(len(symbols) * 0.01)) else "partial"
    with db() as connection:
        connection.execute(
            "update data_sync_runs set status=?, canonical_status=?, summary_json=?, error=?, finished_at=? where id=?",
            (status, "ready" if status == "success" else "failed", json_dump(summary), None if status == "success" else f"{len(failures)} symbols failed", utc_now(), run_id),
        )
    return {"status": status, **summary}
