from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from ..core.config import REPORTS_DIR
from ..core.errors import LeanWebError
from ..db import db, init_db
from ..research.factors import upsert_factor_values
from .ashare_repository import (
    create_import_batch,
    finish_import_batch,
    trade_dates_between,
    universe_as_of,
    upsert_corporate_actions,
    upsert_index_weights,
    upsert_security,
    upsert_trade_calendar,
    upsert_universe_membership,
)
from .data import import_ashare_research_data
from . import market_lake
from .pit_data import import_financial_statements
from .tushare_adapter import TushareAdapter


CSI300_UNIVERSE = "CSI300"
CSI300_INDEX_SYMBOL = "000300"
PIPELINE_SOURCE = "tushare:csi300_research"
RESEARCH_CORE_DATASETS = {
    "calendar",
    "securities",
    "universe",
    "index_weight",
    "daily",
    "suspend",
    "daily_basic",
    "dividend",
    "financials",
}


def _date(value: Any, field: str = "date") -> str:
    if value in (None, ""):
        raise LeanWebError(f"{field} is required.")
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return date.fromisoformat(text if fmt == "%Y-%m-%d" else f"{text[:4]}-{text[4:6]}-{text[6:8]}").isoformat()
        except ValueError:
            pass
    raise LeanWebError(f"Invalid {field}: {value!r}; expected YYYY-MM-DD or YYYYMMDD.")


def _parse_datasets(value: Any) -> set[str]:
    if value in (None, "", "research-core"):
        return set(RESEARCH_CORE_DATASETS)
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",") if item.strip()]
    else:
        raw_items = [str(item).strip() for item in value if str(item).strip()]
    datasets: set[str] = set()
    for item in raw_items:
        if item == "research-core":
            datasets.update(RESEARCH_CORE_DATASETS)
        else:
            datasets.add(item)
    return datasets


def _today() -> str:
    return date.today().isoformat()


def _window_start_for_calendar(end_date: str, days: int = 30) -> str:
    return (date.fromisoformat(end_date) - timedelta(days=days)).isoformat()


def _latest_local_csi300_bar_date() -> str | None:
    with db() as connection:
        members = connection.execute(
            "select distinct symbol from universe_membership where universe_code=?",
            (CSI300_UNIVERSE,),
        ).fetchall()
    symbols = [str(row["symbol"]) for row in members]
    if not symbols:
        return None
    rows = market_lake.query_rows(
        kind="bars", source="tushare", columns="max(trade_date) trade_date",
        predicates=(f"symbol in ({','.join('?' for _ in symbols)})",), parameters=symbols,
    )
    return str(rows[0]["trade_date"]) if rows and rows[0].get("trade_date") else None


def _previous_close(symbol: str, before_date: str, rows: list[dict[str, Any]]) -> float | None:
    current_rows = sorted(
        (row for row in rows if str(row.get("date") or "") < before_date and row.get("close") not in (None, "")),
        key=lambda row: str(row["date"]),
    )
    if current_rows:
        return float(current_rows[-1]["close"])
    stored = market_lake.query_matching(
        kind="bars", asset_class="equity", market="china", venue="china",
        resolution="daily", data_type="trade", adjust="raw", columns="close,trade_date",
        predicates=("symbol=?", "trade_date<?"), parameters=(symbol, before_date),
        order_by="trade_date desc", limit=1,
    )
    return float(stored[0]["close"]) if stored and stored[0].get("close") is not None else None


def _suspend_trade_dates(suspend_rows: list[dict[str, Any]], trade_dates: list[str], start_date: str, end_date: str) -> set[str]:
    available = {item for item in trade_dates if start_date <= item <= end_date}
    suspended: set[str] = set()
    for row in suspend_rows:
        if row.get("is_full_day") is False:
            continue
        suspend_start = max(_date(row["suspend_date"], "suspend_date"), start_date)
        resume_date = row.get("resume_date")
        suspend_end = end_date
        if resume_date:
            resume_day = _date(resume_date, "resume_date")
            suspend_end = min((date.fromisoformat(resume_day) - timedelta(days=1)).isoformat(), end_date)
        suspended.update(item for item in available if suspend_start <= item <= suspend_end)
    return suspended


def _merge_suspensions(
    *,
    symbol: str,
    rows: list[dict[str, Any]],
    suspend_rows: list[dict[str, Any]],
    trade_dates: list[str],
    start_date: str,
    end_date: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if not suspend_rows:
        return rows, warnings
    suspended_dates = _suspend_trade_dates(suspend_rows, trade_dates, start_date, end_date)
    if not suspended_dates:
        return rows, warnings
    by_date = {str(row["date"]): dict(row) for row in rows}
    for trade_date in sorted(suspended_dates):
        if trade_date in by_date:
            by_date[trade_date]["isSuspended"] = True
            by_date[trade_date]["canBuy"] = False
            by_date[trade_date]["canSell"] = False
            continue
        warnings.append(f"{symbol}:{trade_date}:full_day_suspension_no_bar")
    return [by_date[item] for item in sorted(by_date)], warnings


def _factor_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        for factor_name, value in (row.get("factors") or {}).items():
            records.append(
                {
                    "symbol": row["symbol"],
                    "trade_date": row["trade_date"],
                    "factor_name": factor_name,
                    "value": value,
                    "source": row.get("source") or "tushare:daily_basic",
                }
            )
    return records


def _write_report(batch_id: str, payload: dict[str, Any]) -> str:
    report_dir = REPORTS_DIR / "data"
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / f"{batch_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _calendar_open_dates(
    *,
    adapter: TushareAdapter,
    start_date: str,
    end_date: str,
    dry_run: bool,
    batch_id: str | None,
) -> list[str]:
    rows = adapter.trade_calendar(start_date, end_date, exchange="SSE")
    open_dates = [str(row["trade_date"]) for row in rows if row.get("is_open") and row.get("trade_date")]
    if not dry_run:
        upsert_trade_calendar("china", open_dates, source="tushare:trade_cal:SSE", batch_id=batch_id)
    return open_dates


def _resolve_window(config: dict[str, Any], adapter: TushareAdapter, dry_run: bool, batch_id: str | None) -> tuple[str, str, list[str]]:
    mode = str(config.get("mode") or "daily").strip().lower()
    if mode not in {"daily", "incremental", "backfill"}:
        raise LeanWebError("mode must be daily, incremental, or backfill.")
    if mode == "backfill":
        start_date = _date(config.get("start") or config.get("startDate"), "start")
        end_date = _date(config.get("end") or config.get("endDate"), "end")
        open_dates = _calendar_open_dates(adapter=adapter, start_date=start_date, end_date=end_date, dry_run=dry_run, batch_id=batch_id)
        return start_date, end_date, open_dates

    requested_end = _date(config.get("end") or config.get("endDate") or _today(), "end")
    calendar_start = _window_start_for_calendar(requested_end)
    open_dates = _calendar_open_dates(adapter=adapter, start_date=calendar_start, end_date=requested_end, dry_run=dry_run, batch_id=batch_id)
    if not open_dates:
        open_dates = trade_dates_between("china", calendar_start, requested_end)
    if not open_dates:
        raise LeanWebError(f"No open China trade dates found through {requested_end}.")
    latest_open = max(open_dates)
    if mode == "daily":
        return latest_open, latest_open, [latest_open]

    if config.get("start") or config.get("startDate"):
        start_date = _date(config.get("start") or config.get("startDate"), "start")
    else:
        latest_local = _latest_local_csi300_bar_date()
        candidates = [item for item in open_dates if not latest_local or item > latest_local]
        start_date = min(candidates) if candidates else latest_open
    return start_date, latest_open, [item for item in open_dates if start_date <= item <= latest_open]


def _symbols_from_weights(rows: list[dict[str, Any]]) -> list[str]:
    latest_date = max((row["trade_date"] for row in rows), default=None)
    if not latest_date:
        return []
    return sorted({row["symbol"] for row in rows if row["trade_date"] == latest_date})


def _refresh_securities(adapter: TushareAdapter, symbols: list[str], *, dry_run: bool, warnings: list[str]) -> None:
    try:
        records = adapter.stock_basic(["L", "D", "P"])
    except Exception as exc:
        warnings.append(f"securities_degraded:{exc}")
        return
    wanted = set(symbols)
    selected = [record for record in records if record.get("symbol") in wanted]
    if selected and not dry_run:
        for record in selected:
            upsert_security(
                symbol=record["symbol"],
                name=record.get("name") or record["symbol"],
                exchange=record.get("exchange"),
                listed_date=record["listed_date"],
                delisted_date=record.get("delisted_date"),
                status=record.get("status") or "listed",
                industry=record.get("industry"),
            )


def _materialize_membership_if_empty(symbols: list[str], as_of_date: str, *, dry_run: bool, batch_id: str, warnings: list[str]) -> None:
    if dry_run or universe_as_of(CSI300_UNIVERSE, as_of_date):
        return
    # A current index-weight snapshot is not PIT evidence.  Persisting it as
    # history makes earlier research silently depend on today's constituents.
    warnings.append("universe_membership_missing_pit_evidence")
    raise LeanWebError(
        "CSI300 PIT membership is missing for the requested date; "
        "current index weights cannot be materialized as historical membership."
    )


def _fetch_research_dataset(
    *,
    name: str,
    fetcher,
    strict: bool,
    warnings: list[str],
    degraded: list[str],
) -> list[dict[str, Any]]:
    try:
        return fetcher()
    except Exception as exc:
        degraded.append(name)
        warnings.append(f"{name}_degraded:{exc}")
        if strict:
            raise
        return []


def run_csi300_research_import(config: dict[str, Any]) -> dict[str, Any]:
    init_db()
    adapter = config.get("adapter") or TushareAdapter(token=config.get("apiKey") or config.get("token"))
    dry_run = bool(config.get("dryRun") or config.get("dry_run"))
    datasets = _parse_datasets(config.get("datasets"))
    mode = str(config.get("mode") or "daily").strip().lower()
    strict_market = bool(config.get("strictMarketData") or config.get("strict_market_data"))
    strict_research = bool(config.get("strictResearch") or config.get("strict_research"))
    sleep_seconds = float(config.get("sleep") or 0)
    limit = int(config.get("limit") or 0)
    warnings: list[str] = []
    degraded: list[str] = []
    failures: list[dict[str, Any]] = []
    successes: list[dict[str, Any]] = []
    batch = None if dry_run else create_import_batch("tushare", "china", "equity", {key: value for key, value in config.items() if key != "adapter"})
    batch_id = "dry-run" if dry_run else str(batch["id"])

    try:
        start_date, end_date, trade_dates = _resolve_window(config, adapter, dry_run, None if dry_run else batch_id)
        index_weight_rows: list[dict[str, Any]] = []
        if "index_weight" in datasets or "universe" in datasets:
            try:
                index_weight_rows = adapter.index_weight_rows(CSI300_INDEX_SYMBOL, start_date, end_date)
                if index_weight_rows and not dry_run:
                    upsert_index_weights(index_weight_rows, source="tushare:index_weight", batch_id=batch_id)
            except Exception as exc:
                degraded.append("index_weight")
                warnings.append(f"index_weight_degraded:{exc}")
                if strict_market:
                    raise
        symbols = _symbols_from_weights(index_weight_rows)
        if not symbols:
            existing = universe_as_of(CSI300_UNIVERSE, end_date)
            symbols = [item["symbol"] for item in existing]
            if not symbols:
                raise LeanWebError("CSI300 universe is empty; import PIT membership or enable TuShare index_weight first.")
            warnings.append("universe_from_existing_membership")
        if limit > 0:
            symbols = symbols[:limit]
        if "securities" in datasets:
            _refresh_securities(adapter, symbols, dry_run=dry_run, warnings=warnings)
        _materialize_membership_if_empty(symbols, end_date, dry_run=dry_run, batch_id=batch_id, warnings=warnings)

        import_symbols = list(symbols)
        if CSI300_INDEX_SYMBOL not in import_symbols:
            import_symbols.append(CSI300_INDEX_SYMBOL)

        factor_count = 0
        corporate_action_count = 0
        financial_count = 0
        suspended_count = 0
        market_rows = 0
        for index, symbol in enumerate(import_symbols, start=1):
            is_index = symbol == CSI300_INDEX_SYMBOL
            try:
                if "daily" in datasets:
                    rows = adapter.daily_rows(symbol, start_date, end_date, adjust="raw")
                    if not rows:
                        raise LeanWebError(f"No daily rows returned for {symbol}.")
                    suspend_rows: list[dict[str, Any]] = []
                    if "suspend" in datasets and not is_index:
                        suspend_rows = _fetch_research_dataset(
                            name="suspend",
                            fetcher=lambda symbol=symbol: adapter.suspend_rows(symbol, start_date, end_date),
                            strict=strict_market,
                            warnings=warnings,
                            degraded=degraded,
                        )
                        rows, suspend_warnings = _merge_suspensions(
                            symbol=symbol,
                            rows=rows,
                            suspend_rows=suspend_rows,
                            trade_dates=trade_dates,
                            start_date=start_date,
                            end_date=end_date,
                        )
                        warnings.extend(suspend_warnings)
                        suspended_count += len(_suspend_trade_dates(suspend_rows, trade_dates, start_date, end_date))
                    if not dry_run:
                        asset = import_ashare_research_data(
                            symbol=symbol,
                            provider="tushare",
                            market="china",
                            rows=rows,
                            source=PIPELINE_SOURCE,
                            overwrite=bool(config.get("overwrite", True)),
                            adjust="raw",
                            outputsize="",
                            asset_class="equity",
                            venue="china",
                            resolution="daily",
                            data_type="trade",
                            start_date=start_date,
                            end_date=end_date,
                            suspension_evidence_rows=suspend_rows,
                        )
                        successes.append({"symbol": symbol, "rows": asset.get("rows"), "batchId": asset.get("batch_id")})
                    else:
                        successes.append({"symbol": symbol, "rows": len(rows), "batchId": None})
                    market_rows += len(rows)

                if not is_index and "daily_basic" in datasets:
                    daily_basic_rows = _fetch_research_dataset(
                        name="daily_basic",
                        fetcher=lambda symbol=symbol: adapter.daily_basic_rows(symbol, start_date, end_date),
                        strict=strict_research,
                        warnings=warnings,
                        degraded=degraded,
                    )
                    records = _factor_records(daily_basic_rows)
                    if records and not dry_run:
                        factor_count += upsert_factor_values(records, source="tushare:daily_basic", batch_id=batch_id)
                    else:
                        factor_count += len(records)
                if not is_index and "dividend" in datasets:
                    dividend_rows = _fetch_research_dataset(
                        name="dividend",
                        fetcher=lambda symbol=symbol: adapter.dividend_rows(symbol, start_date, end_date),
                        strict=strict_research,
                        warnings=warnings,
                        degraded=degraded,
                    )
                    if dividend_rows and not dry_run:
                        corporate_action_count += upsert_corporate_actions(dividend_rows, source="tushare:dividend", batch_id=batch_id)["count"]
                    else:
                        corporate_action_count += len(dividend_rows)
                if not is_index and "financials" in datasets:
                    financial_rows: list[dict[str, Any]] = []
                    for method_name in ("income_rows", "balancesheet_rows", "cashflow_rows", "fina_indicator_rows"):
                        financial_rows.extend(
                            _fetch_research_dataset(
                                name=method_name.removesuffix("_rows"),
                                fetcher=lambda method_name=method_name, symbol=symbol: getattr(adapter, method_name)(symbol, start_date, end_date),
                                strict=strict_research,
                                warnings=warnings,
                                degraded=degraded,
                            )
                        )
                    if financial_rows and not dry_run:
                        financial_count += import_financial_statements(financial_rows, source="tushare:financials")["count"]
                    else:
                        financial_count += len(financial_rows)
                if "daily" not in datasets:
                    successes.append({"symbol": symbol, "rows": 0, "batchId": batch_id if not dry_run else None})
            except Exception as exc:
                failures.append({"symbol": symbol, "error": str(exc)})
                if strict_market or symbol == CSI300_INDEX_SYMBOL:
                    warnings.append(f"{symbol}:failed:{exc}")
                if strict_market:
                    break
            if sleep_seconds > 0 and index < len(import_symbols):
                time.sleep(sleep_seconds)

        coverage = {
            "symbolsRequested": len(import_symbols),
            "memberSymbols": len(symbols),
            "successSymbols": len(successes),
            "failedSymbols": len(failures),
            "tradeDates": len(trade_dates),
            "marketRows": market_rows,
            "suspendedRows": suspended_count,
            "indexWeights": len(index_weight_rows),
            "factorValues": factor_count,
            "corporateActions": corporate_action_count,
            "financialStatements": financial_count,
        }
        qa = {
            "passed": not failures,
            "warnings": warnings,
            "degradedDatasets": sorted(set(degraded)),
            "coverage": coverage,
            "failures": failures,
        }
        result = {
            "batchId": batch_id,
            "mode": mode,
            "startDate": start_date,
            "endDate": end_date,
            "datasets": sorted(datasets),
            "symbols": import_symbols,
            "successes": successes,
            "failures": failures,
            "coverage": coverage,
            "qa": qa,
            "artifacts": [],
            "dryRun": dry_run,
        }
        if not dry_run:
            result["artifacts"].append(_write_report(batch_id, result))
            finish_import_batch(batch_id, "success" if not failures else "failed", qa_report=qa, error=None if not failures else f"{len(failures)} symbol(s) failed.")
        return result
    except Exception as exc:
        qa = {"passed": False, "warnings": warnings, "degradedDatasets": sorted(set(degraded)), "failures": failures, "error": str(exc)}
        if not dry_run:
            finish_import_batch(batch_id, "failed", qa_report=qa, error=str(exc))
        raise
