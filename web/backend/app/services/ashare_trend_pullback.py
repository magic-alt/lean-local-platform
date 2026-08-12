from __future__ import annotations

import gzip
import hashlib
import json
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from ..core.errors import LeanWebError
from ..db import db, rows_to_dicts


SNAPSHOT_FILE_NAME = "ashare-trend-pullback-input.json.gz"
SNAPSHOT_CONTAINER_PATH = f"/Lean/Run/{SNAPSHOT_FILE_NAME}"
SNAPSHOT_SCHEMA_VERSION = 1
SUPPORTED_UNIVERSES = {"CSI300", "CSI500", "CSI1000", "STAR50"}


def _loads(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError as exc:
        raise LeanWebError("Invalid JSON in the trend-pullback PIT schedule.") from exc
    return [dict(item) for item in parsed if isinstance(item, dict)]


def _chunks(values: Iterable[str], size: int = 350) -> list[list[str]]:
    items = sorted({str(value).strip().upper() for value in values if str(value).strip()})
    return [items[offset : offset + size] for offset in range(0, len(items), size)]


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _open_dates(start: str, end: str) -> list[str]:
    with db() as connection:
        rows = connection.execute(
            """
            select trade_date from trade_calendar
            where market='china' and is_open=1 and trade_date between ? and ?
            order by trade_date
            """,
            (start, end),
        ).fetchall()
    return [str(row["trade_date"])[:10] for row in rows]


def _warmup_start(start: str, sessions: int = 300) -> str:
    with db() as connection:
        rows = connection.execute(
            """
            select trade_date from trade_calendar
            where market='china' and is_open=1 and trade_date < ?
            order by trade_date desc limit ?
            """,
            (start, sessions),
        ).fetchall()
    if rows:
        return min(str(row["trade_date"])[:10] for row in rows)
    parsed = datetime.strptime(start, "%Y-%m-%d").date()
    return (parsed - timedelta(days=450)).isoformat()


def _rebalance_dates(open_dates: list[str], start: str) -> list[str]:
    by_week: dict[tuple[int, int], str] = {}
    for value in open_dates:
        parsed = date.fromisoformat(value)
        iso = parsed.isocalendar()
        by_week[(iso.year, iso.week)] = value
    return [value for _week, value in sorted(by_week.items()) if value >= start]


def _industry_schedule(symbols: list[str], end: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for chunk in _chunks(symbols):
        placeholders = ",".join("?" for _ in chunk)
        with db() as connection:
            rows = connection.execute(
                f"""
                select symbol,industry_code,industry_name,in_date,out_date
                from industry_membership
                where symbol in ({placeholders}) and taxonomy='SW2021' and level_no=1
                  and in_date<=?
                order by symbol,in_date,industry_code
                """,
                [*chunk, end],
            ).fetchall()
        result.extend(
            {
                "symbol": str(row["symbol"]).upper(),
                "industryCode": str(row["industry_code"]),
                "industryName": row["industry_name"],
                "inDate": str(row["in_date"])[:10],
                "outDate": str(row["out_date"])[:10] if row["out_date"] else None,
            }
            for row in rows
        )
    return result


def _security_lifecycle(symbols: list[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for chunk in _chunks(symbols):
        placeholders = ",".join("?" for _ in chunk)
        with db() as connection:
            rows = connection.execute(
                f"""
                select symbol,listed_date,delisted_date,status
                from securities where symbol in ({placeholders}) order by symbol
                """,
                chunk,
            ).fetchall()
        result.extend(
            {
                "symbol": str(row["symbol"]).upper(),
                "listedDate": str(row["listed_date"])[:10],
                "delistedDate": str(row["delisted_date"])[:10] if row["delisted_date"] else None,
                "status": str(row["status"] or ""),
            }
            for row in rows
        )
    return result


def _market_inputs(
    symbols: list[str],
    warmup_start: str,
    end: str,
    rebalance_dates: set[str],
    source: str | None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, dict[str, float]]], dict[str, int]]:
    factors: dict[str, list[dict[str, Any]]] = defaultdict(list)
    liquidity: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    bar_counts: dict[str, int] = defaultdict(int)
    for chunk in _chunks(symbols):
        placeholders = ",".join("?" for _ in chunk)
        source_clause = "and b.source=?" if source else ""
        parameters: list[Any] = [*chunk, warmup_start, end]
        if source:
            parameters.append(source)
        with db() as connection:
            rows = rows_to_dicts(
                connection.execute(
                    f"""
                    select b.symbol,b.trade_date,b.amount,
                           coalesce(a.adj_factor,b.adj_factor,1.0) adj_factor
                    from market_daily_bars b
                    left join adjustment_factors a
                      on a.symbol=b.symbol and a.trade_date=b.trade_date and a.source='tushare'
                    where b.asset_class='equity' and b.market='china' and b.venue='china'
                      and b.resolution='daily' and b.data_type='trade'
                      and b.symbol in ({placeholders}) and b.adjust='raw'
                      and b.trade_date between ? and ? {source_clause}
                    order by b.symbol,b.trade_date,b.source
                    """,
                    parameters,
                ).fetchall()
            )
        grouped: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for row in rows:
            grouped[str(row["symbol"]).upper()][str(row["trade_date"])[:10]] = row
        for symbol, dated in grouped.items():
            amounts: list[float] = []
            previous_factor: float | None = None
            for trade_date, row in sorted(dated.items()):
                factor = float(row.get("adj_factor") or 0)
                if factor <= 0:
                    raise LeanWebError(f"Non-positive adjustment factor for {symbol} on {trade_date}.")
                if previous_factor is None or factor != previous_factor:
                    factors[symbol].append({"date": trade_date, "value": factor})
                    previous_factor = factor
                amount = float(row.get("amount") or 0)
                amounts.append(amount)
                bar_counts[symbol] += 1
                if trade_date in rebalance_dates and len(amounts) >= 20:
                    last20 = amounts[-20:]
                    mean20 = sum(last20) / 20.0
                    liquidity[symbol][trade_date] = {
                        "amountMedian20Cny": float(statistics.median(last20)),
                        "amountRatio5To20": (sum(amounts[-5:]) / 5.0) / mean20 if mean20 > 0 else 0.0,
                    }
    return dict(factors), dict(liquidity), dict(bar_counts)


def build_trend_pullback_snapshot(parameters: dict[str, Any]) -> dict[str, Any]:
    start = str(parameters.get("start") or "")[:10]
    end = str(parameters.get("end") or "")[:10]
    if start < "2016-01-01":
        raise LeanWebError("A-share trend-pullback backtests require start >= 2016-01-01 for PIT ST coverage.")
    universe_code = str(parameters.get("universeCode") or "CSI300").upper()
    if universe_code not in SUPPORTED_UNIVERSES:
        raise LeanWebError("Trend-pullback supports CSI300, CSI500, CSI1000 and STAR50.")
    universe = _loads(parameters.get("universeSchedule"))
    fundamentals = _loads(parameters.get("fundamentalSchedule"))
    if not universe:
        raise LeanWebError("Trend-pullback requires a non-empty PIT universe schedule.")
    symbols = sorted({str(row.get("symbol") or "").upper() for row in universe if row.get("symbol")})
    warmup_floor = _warmup_start(start)
    calendar_end = (date.fromisoformat(end) + timedelta(days=7)).isoformat()
    calendar_open_dates = _open_dates(warmup_floor, calendar_end)
    open_dates = [value for value in calendar_open_dates if value <= end]
    if not open_dates:
        raise LeanWebError("Trend-pullback requires the China open-trading calendar.")
    warmup_start = min(open_dates)
    rebalance_dates = [
        value for value in _rebalance_dates(calendar_open_dates, start) if value <= end
    ]
    industries = _industry_schedule(symbols, end)
    factors, liquidity, bar_counts = _market_inputs(
        symbols,
        warmup_start,
        end,
        set(rebalance_dates),
        str(parameters.get("source") or "").strip() or None,
    )
    industry_symbols = {row["symbol"] for row in industries}
    fundamental_symbols = {str(row.get("symbol") or "").upper() for row in fundamentals}
    industry_coverage = len(industry_symbols) / len(symbols) if symbols else 0.0
    fundamental_coverage = len(fundamental_symbols) / len(symbols) if symbols else 0.0
    variant = str(parameters.get("modelVariant") or "B").upper()
    blocking: list[str] = []
    if variant in {"B", "C"} and industry_coverage < 0.95:
        blocking.append("industry_coverage_below_95pct")
    if variant == "C" and not fundamentals:
        blocking.append("pit_fundamentals_missing")
    if not factors:
        blocking.append("adjustment_factors_missing")
    if not liquidity:
        blocking.append("liquidity_snapshots_missing")
    payload = {
        "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
        "rulesVersion": "ashare-trend-pullback-v1",
        "universeCode": universe_code,
        "modelVariant": variant,
        "startDate": start,
        "endDate": end,
        "warmupStartDate": warmup_start,
        "source": parameters.get("source") or parameters.get("provider") or "database",
        "symbols": symbols,
        "openDates": open_dates,
        "rebalanceDates": rebalance_dates,
        "universeSchedule": universe,
        "industrySchedule": industries,
        "fundamentalSchedule": fundamentals,
        "securityLifecycle": _security_lifecycle(symbols),
        "factorChanges": factors,
        "liquidityByRebalanceDate": liquidity,
        "coverage": {
            "symbolCount": len(symbols),
            "symbolsWithBars": sum(1 for value in bar_counts.values() if value > 0),
            "symbolsWithIndustry": len(industry_symbols),
            "industryCoverage": round(industry_coverage, 8),
            "symbolsWithFundamentals": len(fundamental_symbols),
            "fundamentalCoverage": round(fundamental_coverage, 8),
            "factorSymbolCount": len(factors),
            "liquiditySymbolCount": len(liquidity),
            "blocking": blocking,
            "passed": not blocking,
        },
    }
    if blocking:
        raise LeanWebError("Trend-pullback PIT snapshot gate failed: " + ",".join(blocking))
    return payload


def write_trend_pullback_snapshot(run_dir: Path, parameters: dict[str, Any]) -> dict[str, Any]:
    payload = build_trend_pullback_snapshot(parameters)
    canonical = _canonical_bytes(payload)
    digest = hashlib.sha256(canonical).hexdigest()
    target = run_dir / SNAPSHOT_FILE_NAME
    run_dir.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write(canonical)
    return {
        "path": str(target),
        "containerPath": SNAPSHOT_CONTAINER_PATH,
        "sha256": digest,
        "schemaVersion": SNAPSHOT_SCHEMA_VERSION,
        "coverage": payload["coverage"],
    }
