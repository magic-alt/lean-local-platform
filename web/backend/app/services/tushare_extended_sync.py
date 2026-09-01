"""Governed daily refresh for provider-shaped TuShare extended Bronze data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import json
import os
from pathlib import Path
from typing import Any, Callable, Iterable

from . import market_lake
from .tushare_contracts import contract_for


@dataclass(frozen=True)
class ExtendedDailyEndpoint:
    name: str
    group: str
    plan: str
    min_date: str = "1990-01-01"
    period_parameter: str = "period"
    exchanges: tuple[str, ...] = ()


# All extended endpoints are now part of the unattended incremental job.  The
# per-symbol endpoints are bounded to the active stock universe and are
# idempotent at the partition level; date-range endpoints are replayed over a
# recent window so late corporate-action disclosures are picked up.
EXTENDED_DAILY_ENDPOINTS: tuple[ExtendedDailyEndpoint, ...] = (
    ExtendedDailyEndpoint("stock_company", "basic", "exchange", exchanges=("SSE", "SZSE", "BSE")),
    ExtendedDailyEndpoint("namechange", "basic", "symbol"),
    ExtendedDailyEndpoint("new_share", "basic", "date_range"),
    ExtendedDailyEndpoint("income_vip", "financial", "report_period"),
    ExtendedDailyEndpoint("balancesheet_vip", "financial", "report_period"),
    ExtendedDailyEndpoint("cashflow_vip", "financial", "report_period"),
    ExtendedDailyEndpoint("fina_indicator_vip", "financial", "report_period"),
    ExtendedDailyEndpoint("forecast_vip", "financial", "report_period"),
    ExtendedDailyEndpoint("express_vip", "financial", "report_period"),
    ExtendedDailyEndpoint("fina_mainbz_vip", "financial", "report_period"),
    ExtendedDailyEndpoint(
        "disclosure_date", "financial", "report_period", period_parameter="end_date"
    ),
    ExtendedDailyEndpoint("limit_list_d", "market_reference", "trade_date", "2016-01-01"),
    ExtendedDailyEndpoint("block_trade", "market_reference", "trade_date", "2010-01-01"),
    ExtendedDailyEndpoint("top_list", "market_reference", "trade_date", "2000-01-01"),
    ExtendedDailyEndpoint("margin", "market_reference", "trade_date", "2010-01-01"),
    ExtendedDailyEndpoint("margin_detail", "market_reference", "trade_date", "2010-01-01"),
    ExtendedDailyEndpoint("moneyflow_hsgt", "market_reference", "trade_date", "2014-11-17"),
    ExtendedDailyEndpoint("hsgt_top10", "market_reference", "trade_date", "2014-11-17"),
    ExtendedDailyEndpoint("share_float", "corporate_action", "date_range"),
    ExtendedDailyEndpoint("dividend", "corporate_action", "symbol"),
    ExtendedDailyEndpoint("repurchase", "corporate_action", "date_range"),
    ExtendedDailyEndpoint("pledge_stat", "corporate_action", "symbol"),
    ExtendedDailyEndpoint("pledge_detail", "corporate_action", "symbol"),
    ExtendedDailyEndpoint("stk_holdernumber", "holder", "date_range"),
    ExtendedDailyEndpoint("top10_holders", "holder", "date_range"),
    ExtendedDailyEndpoint("top10_floatholders", "holder", "date_range"),
    ExtendedDailyEndpoint("stk_managers", "holder", "symbol"),
    ExtendedDailyEndpoint("stk_rewards", "holder", "symbol"),
)


def _quarter_periods(start_date: date, end_date: date) -> list[str]:
    periods: list[str] = []
    for year in range(start_date.year, end_date.year + 1):
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            value = date(year, month, day)
            if start_date <= value <= end_date:
                periods.append(value.strftime("%Y%m%d"))
    return periods


def _partition_manifest(dataset: str, partition: str) -> dict[str, Any]:
    path = (
        market_lake.PARQUET_DIR
        / "bronze"
        / "tushare"
        / "current"
        / "extended"
        / dataset
        / f"trade_date={partition}"
        / "manifest.json"
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _terminal_partition(dataset: str, partition: str) -> bool:
    manifest = _partition_manifest(dataset, partition)
    status = str(manifest.get("status") or "").lower()
    data_path = (
        market_lake.PARQUET_DIR
        / "bronze"
        / "tushare"
        / "current"
        / "extended"
        / dataset
        / f"trade_date={partition}"
        / "data.parquet"
    )
    return status in {"success", "empty"} and data_path.is_file()


def _columns(dataset: str, rows: list[dict[str, Any]]) -> tuple[str, ...]:
    if rows:
        return tuple(str(column) for column in rows[0])
    root = (
        market_lake.PARQUET_DIR
        / "bronze"
        / "tushare"
        / "current"
        / "extended"
        / dataset
    )
    for path in sorted(root.glob("trade_date=*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        columns = tuple(str(column) for column in manifest.get("columns") or ())
        if columns:
            return columns
    contract = contract_for(dataset)
    return tuple(str(field["providerName"]) for field in (contract or {}).get("fields") or ())


def _fetch_rows(adapter: Any, endpoint: str, params: dict[str, str]) -> list[dict[str, Any]]:
    method = getattr(adapter.pro, endpoint)
    if hasattr(adapter, "_paged_records"):
        return adapter._paged_records(method, page_size=5_000, **params)
    frame = method(**params)
    if frame is None or getattr(frame, "empty", False):
        return []
    if isinstance(frame, list):
        return [dict(row) for row in frame]
    return [dict(row) for row in frame.to_dict("records")]


def _symbols(adapter: Any) -> list[str]:
    """Return the active stock universe for per-symbol extended endpoints."""
    frame = adapter.pro.stock_basic(list_status="L", fields="ts_code")
    if frame is None or getattr(frame, "empty", False):
        return []
    rows = frame if isinstance(frame, list) else frame.to_dict("records")
    return sorted({str(row.get("ts_code") or "").upper() for row in rows if row.get("ts_code")})


def _symbol_partition_due(dataset: str, partition: str) -> bool:
    """Return whether a symbol snapshot is absent or old enough to refresh."""
    manifest = _partition_manifest(dataset, partition)
    if not _terminal_partition(dataset, partition):
        return True
    written_at = str(manifest.get("written_at_utc") or "")
    try:
        written_day = date.fromisoformat(written_at[:10])
    except ValueError:
        return True
    refresh_days = max(1, min(365, int(os.environ.get("LEAN_DATA_EXTENDED_SYMBOL_REFRESH_DAYS", "30"))))
    return written_day <= date.today() - timedelta(days=refresh_days)


def _endpoint_latest_manifest_mtime(endpoint: ExtendedDailyEndpoint) -> float:
    """Return the latest published partition time without reading its rows."""
    root = market_lake.PARQUET_DIR / "bronze" / "tushare" / "current" / "extended" / endpoint.name
    try:
        return max((path.stat().st_mtime for path in root.glob("trade_date=*/manifest.json")), default=0.0)
    except OSError:
        return 0.0


_EXTENDED_PLAN_PRIORITY = {
    "exchange": 0,
    "report_period": 1,
    "trade_date": 2,
    "date_range": 3,
    "symbol": 4,
}


def sync_extended_daily(
    adapter: Any,
    *,
    run_id: str,
    end_date: str,
    open_dates: Iterable[str],
    financial_lookback_calendar_days: int = 400,
    symbol_batch_size: int | None = None,
    heartbeat: Callable[[], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
    failure_reporter: Callable[[dict[str, str]], None] | None = None,
) -> dict[str, Any]:
    """Fill market-reference holes and replay recent financial periods."""
    end = date.fromisoformat(end_date)
    open_sessions = sorted(
        value for value in {str(item) for item in open_dates} if value <= end_date
    )
    counters = {"processed": 0, "changed": 0, "rows": 0, "failed": 0, "skipped": 0}
    failures: list[dict[str, str]] = []
    endpoint_counts: dict[str, int] = {}
    deferred_symbol_tasks = 0
    if symbol_batch_size is None:
        symbol_batch_size = int(os.environ.get("LEAN_DATA_EXTENDED_SYMBOLS_PER_RUN", "200"))
    symbol_batch_size = max(1, min(1_000, symbol_batch_size))
    # Bounded market/date/report/exchange calls must land before the expensive
    # active-universe sweep. A worker restart or cancellation during thousands
    # of per-symbol calls must not starve the remaining daily datasets.
    endpoint_order = sorted(
        enumerate(EXTENDED_DAILY_ENDPOINTS),
        key=lambda item: (
            _EXTENDED_PLAN_PRIORITY.get(item[1].plan, 99),
            _endpoint_latest_manifest_mtime(item[1]) if item[1].plan == "symbol" else item[0],
            item[0],
        ),
    )
    for _, endpoint in endpoint_order:
        if endpoint.plan == "trade_date":
            tasks = [
                (trade_date.replace("-", ""), {"trade_date": trade_date.replace("-", "")})
                for trade_date in open_sessions
                if trade_date >= endpoint.min_date
                and not _terminal_partition(endpoint.name, trade_date.replace("-", ""))
            ]
        elif endpoint.plan == "report_period":
            start = end - timedelta(days=financial_lookback_calendar_days)
            tasks = [
                (period, {endpoint.period_parameter: period})
                for period in _quarter_periods(start, end)
            ]
        elif endpoint.plan == "date_range":
            start = end - timedelta(days=financial_lookback_calendar_days)
            cursor = start.replace(day=1)
            tasks = []
            while cursor <= end:
                window_end = min(
                    date(cursor.year + (cursor.month == 12), 1 if cursor.month == 12 else cursor.month + 1, 1)
                    - timedelta(days=1),
                    end,
                )
                tasks.append((f"{cursor:%Y%m%d}_{window_end:%Y%m%d}", {
                    "start_date": f"{cursor:%Y%m%d}", "end_date": f"{window_end:%Y%m%d}"
                }))
                cursor = window_end + timedelta(days=1)
        elif endpoint.plan == "symbol":
            due_tasks = [
                (symbol.replace(".", "_"), {"ts_code": symbol})
                for symbol in _symbols(adapter)
                if _symbol_partition_due(endpoint.name, symbol.replace(".", "_"))
            ]
            tasks = due_tasks[:symbol_batch_size]
            deferred_symbol_tasks += max(0, len(due_tasks) - len(tasks))
        elif endpoint.plan == "exchange":
            tasks = [(exchange, {"exchange": exchange}) for exchange in endpoint.exchanges]
        else:
            tasks = [(end_date.replace("-", ""), {})]
        for partition, params in tasks:
            if cancelled and cancelled():
                return {
                    **counters,
                    "endpointCounts": endpoint_counts,
                    "failures": failures,
                    "deferredSymbolTasks": deferred_symbol_tasks,
                    "cancelled": True,
                }
            counters["processed"] += 1
            try:
                rows = _fetch_rows(adapter, endpoint.name, params)
                columns = _columns(endpoint.name, rows)
                if not columns:
                    raise RuntimeError(f"extended_schema_unavailable:{endpoint.name}")
                result = market_lake.write_tushare_extended_bronze_partition(
                    endpoint.name,
                    partition,
                    rows,
                    columns=columns,
                    metadata={
                        "api": endpoint.name,
                        "group": endpoint.group,
                        "params": params,
                        "ingest_run_id": run_id,
                    },
                )
                endpoint_counts[endpoint.name] = endpoint_counts.get(endpoint.name, 0) + 1
                counters["rows"] += len(rows)
                counters["changed"] += int(bool(result["changed"]))
                counters["skipped"] += int(not bool(result["changed"]))
            except Exception as exc:  # noqa: BLE001 - preserve good partitions and report partial work.
                counters["failed"] += 1
                failure = {"dataset": endpoint.name, "partition": partition, "error": str(exc)}
                if len(failures) < 20:
                    failures.append(failure)
                if failure_reporter:
                    failure_reporter(failure)
            finally:
                if heartbeat:
                    heartbeat()
    return {
        **counters,
        "endpointCounts": endpoint_counts,
        "failures": failures,
        "deferredSymbolTasks": deferred_symbol_tasks,
        "cancelled": False,
    }
