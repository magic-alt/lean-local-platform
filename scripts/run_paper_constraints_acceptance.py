#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import db, init_db, json_dump, utc_now  # noqa: E402
from app.services import market_lake  # noqa: E402
from app.services.ashare_repository import assert_benchmark_ready, reference_data_coverage, upsert_trade_status  # noqa: E402
from app.services.paper import _replay_dates, create_session, create_signal, list_orders, run_replay  # noqa: E402
from app.services.source_gate import PRIMARY_DATA_SOURCE  # noqa: E402


REQUIRED_REASONS = {"blacklisted", "observe_only", "st_blocked", "max_positions", "cash_floor", "not_in_watchlist", "qa_failed"}


def _symbols(value: str) -> list[str]:
    return [item.strip().zfill(6)[-6:] for item in value.split(",") if item.strip()]


def _trade_pair(symbols: list[str], start: str, end: str, source: str) -> tuple[str, str]:
    probe = create_session(
        {
            "symbol": symbols[0],
            "symbols": symbols,
            "assetClass": "equity",
            "market": "china",
            "cash": 100000,
            "source": source,
        }
    )
    dates = _replay_dates(probe, start, end)
    if len(dates) < 2:
        raise RuntimeError("insufficient_trading_days")
    return dates[0], dates[1]


def _find_fallback_symbol(
    exclude_symbol: str,
    source: str,
    trade_date: str,
    *,
    fallback: list[str] | None = None,
) -> str | None:
    rows = market_lake.query_rows(
        kind="bars", asset_class="equity", market="china", venue="china", source=source,
        columns="symbol", predicates=("trade_date=?", "symbol<>?"),
        parameters=(trade_date, exclude_symbol), order_by="symbol", limit=1,
    )
    row = rows[0] if rows else None
    if row and row["symbol"]:
        return str(row["symbol"]).zfill(6)[-6:]
    candidates = fallback or ["600519", "000001", "300750"]
    for candidate in candidates:
        candidate = str(candidate).strip().zfill(6)[-6:]
        if not candidate or candidate == exclude_symbol:
            continue
        exists = market_lake.query_rows(
            kind="bars", asset_class="equity", market="china", venue="china", source=source,
            columns="1 as found", predicates=("symbol=?", "trade_date=?"),
            parameters=(candidate, trade_date), limit=1,
        )
        if exists:
            return candidate
    return None


def _first_st_case(start: str, end: str, source: str) -> tuple[str, str, str] | None:
    statuses = market_lake.query_matching(
        kind="trade_status", asset_class="equity", market="china", venue="china",
        columns="symbol,trade_date", predicates=("is_st=1", "can_buy=1", "trade_date between ? and ?"),
        parameters=(start, end), order_by="trade_date,symbol", limit=500,
    )
    if not statuses:
        statuses = market_lake.query_matching(
            kind="trade_status", asset_class="equity", market="china", venue="china",
            columns="symbol,trade_date", predicates=("is_st=1", "can_buy=1"),
            order_by="trade_date desc,symbol", limit=500,
        )
    row = next(
        (
            item for item in statuses
            if market_lake.query_rows(
                kind="bars", asset_class="equity", market="china", venue="china", source=source,
                columns="1 as found", predicates=("symbol=?", "trade_date=?"),
                parameters=(item["symbol"], item["trade_date"]), limit=1,
            )
        ),
        None,
    )
    if row is None:
        return None
    signal = market_lake.aggregate(
        kind="bars", asset_class="equity", market="china", venue="china", source=source,
        columns="max(trade_date) as trade_date", predicates=("symbol=?", "trade_date<?"),
        parameters=(row["symbol"], row["trade_date"]),
    )
    if not signal or not signal["trade_date"]:
        return None
    return row["symbol"], signal["trade_date"], row["trade_date"]


def _run_single_reason(
    reason: str,
    symbols: list[str],
    benchmark: str,
    source: str,
    start: str,
    end: str,
    *,
    reference_coverage: dict[str, Any],
) -> dict[str, Any]:
    signal_date, execution_date = _trade_pair(symbols, start, end, source)
    primary = symbols[0]
    secondary = symbols[1] if len(symbols) > 1 else _find_fallback_symbol(
        primary,
        source,
        execution_date,
        fallback=symbols,
    )
    if secondary is None:
        secondary = _find_fallback_symbol(
            primary,
            source,
            execution_date,
            fallback=["600519", "000001", "300750"],
        )
        if secondary is None:
            secondary = primary
    params: dict[str, Any] = {
        "symbol": primary,
        "symbols": symbols,
        "assetClass": "equity",
        "market": "china",
        "cash": 100000,
        "benchmarkSymbol": benchmark,
        "executionPolicy": "next_open",
        "source": source,
        "maxPositionWeight": 0.4,
        "watchlist": ",".join(symbols),
        "name": f"Paper Constraint Acceptance {reason}",
    }
    signal_symbol = primary
    target = 0.3
    cleanup_report_id: str | None = None
    acceptance_status_source: str | None = None
    if reason == "blacklisted":
        params["blacklist"] = primary
    elif reason == "observe_only":
        params["observeOnlySymbols"] = primary
    elif reason == "not_in_watchlist":
        params["watchlist"] = secondary
    elif reason == "cash_floor":
        params["minCash"] = params["cash"]
    elif reason == "max_positions":
        params["maxPositions"] = 1
        params["cash"] = 5000000
        params["maxPositionWeight"] = 0.4
        params["symbols"] = [primary, secondary]
        params["watchlist"] = ",".join([primary, secondary])
    elif reason == "st_blocked":
        signal_symbol = primary
        acceptance_status_source = "official:paper-acceptance-st"
        upsert_trade_status(
            [{
                "symbol": signal_symbol, "trade_date": execution_date,
                "is_suspended": False, "can_buy": True, "can_sell": True, "is_st": True,
            }],
            source=acceptance_status_source,
            batch_id="paper-acceptance-st",
        )
    elif reason == "qa_failed":
        cleanup_report_id = f"qa-paper-acceptance-{uuid.uuid4()}"
        with db() as connection:
            connection.execute(
                """
                insert into data_quality_reports
                    (id, report_type, asset_class, market, symbol, start_date, end_date,
                     sources_json, severity, result_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cleanup_report_id,
                    "ashare_daily_multisource",
                    "equity",
                    "china",
                    primary,
                    execution_date,
                    execution_date,
                    json_dump([source]),
                    "critical",
                    json_dump({"severity": "critical", "acceptance": True}),
                    utc_now(),
                ),
            )
    session = create_session(params)
    if reason == "max_positions":
        create_signal(session["id"], trade_date=signal_date, side="buy", symbol=primary, target_percent=0.2)
        create_signal(session["id"], trade_date=signal_date, side="buy", symbol=secondary, target_percent=0.2)
    else:
        create_signal(session["id"], trade_date=signal_date, side="buy", symbol=signal_symbol, target_percent=target)
    try:
        result = run_replay(
            session["id"],
            signal_date,
            execution_date,
            auto_signal=False,
            reference_coverage=reference_coverage,
        )
    finally:
        if cleanup_report_id:
            with db() as connection:
                connection.execute("delete from data_quality_reports where id = ?", (cleanup_report_id,))
        if acceptance_status_source:
            market_lake.delete_snapshot_absences(
                kind="trade_status", scopes=[(signal_symbol, execution_date, execution_date)],
                authoritative_keys=set(), asset_class="equity", market="china", venue="china",
                data_type="status", source=acceptance_status_source,
            )
    orders = list_orders(session["id"])
    rejects = [order for order in orders if order.get("status") == "rejected"]
    reasons = [str(order.get("reason") or "") for order in rejects]
    normalized = ["qa_failed" if item.startswith("qa_failed") else item for item in reasons]
    return {
        "reason": reason,
        "sessionId": session["id"],
        "tradingDays": result["tradingDays"],
        "fills": sum(1 for order in orders if order.get("status") == "filled"),
        "rejects": len(rejects),
        "rejectReasons": sorted(set(normalized)),
        "reports": len(result.get("reports") or []),
        "passed": reason in set(normalized),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic Paper constraint acceptance scenarios.")
    parser.add_argument("--symbols", default="600519,000001,300750")
    parser.add_argument("--benchmark", default="000300")
    parser.add_argument("--source", default=PRIMARY_DATA_SOURCE)
    parser.add_argument("--start-date", default="2026-06-01")
    parser.add_argument("--end-date", default="2026-06-30")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    symbols = _symbols(args.symbols)
    if args.dry_run:
        payload = {"status": "planned", "requiredRejectReasons": sorted(REQUIRED_REASONS), "symbols": symbols}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    init_db()
    warnings: list[str] = []
    errors: list[str] = []
    scenarios: list[dict[str, Any]] = []
    reference_coverage = reference_data_coverage("CSI300")
    try:
        assert_benchmark_ready(args.benchmark, args.start_date, args.end_date, source=args.source)
    except Exception as exc:
        errors.append(f"benchmark_ready_failed:{exc}")
    try:
        assert_benchmark_ready("999999", args.start_date, args.end_date, source=args.source)
        errors.append("benchmark_missing_did_not_fail")
    except Exception:
        pass
    try:
        create_session(
            {
                "symbol": symbols[0],
                "assetClass": "equity",
                "market": "china",
                "source": args.source,
                "executionPolicy": "same_close",
            }
        )
        errors.append("same_close_default_not_blocked")
    except Exception:
        pass
    for reason in sorted(REQUIRED_REASONS):
        try:
            scenarios.append(
                _run_single_reason(
                    reason,
                    symbols,
                    args.benchmark,
                    args.source,
                    args.start_date,
                    args.end_date,
                    reference_coverage=reference_coverage,
                )
            )
        except Exception as exc:
            errors.append(f"{reason}:{exc}")
    reject_reasons = sorted({reason for item in scenarios for reason in item.get("rejectReasons", [])})
    missing = sorted(REQUIRED_REASONS - set(reject_reasons))
    if missing:
        errors.append(f"missing_reject_reasons:{','.join(missing)}")
    payload = {
        "status": "passed" if not errors else "failed",
        "tradingDays": sum(int(item.get("tradingDays") or 0) for item in scenarios),
        "fills": sum(int(item.get("fills") or 0) for item in scenarios),
        "rejects": sum(int(item.get("rejects") or 0) for item in scenarios),
        "rejectReasons": reject_reasons,
        "requiredRejectReasons": sorted(REQUIRED_REASONS),
        "missingRejectReasons": missing,
        "reports": sum(int(item.get("reports") or 0) for item in scenarios),
        "sessionId": scenarios[-1]["sessionId"] if scenarios else None,
        "scenarios": scenarios,
        "warnings": warnings,
        "errors": errors,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
