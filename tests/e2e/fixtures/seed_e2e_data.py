from __future__ import annotations

import json
import math
import os
import shutil
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import DATA_DIR  # noqa: E402
from app.db import db, init_db, json_dump, rows_to_dicts, utc_now  # noqa: E402
from app.lean_engine.data_writers import write_lean_daily_zip  # noqa: E402
from app.services.ashare_repository import (  # noqa: E402
    import_security_master,
    upsert_daily_bars,
    upsert_trade_calendar,
    upsert_trade_status,
)
from app.services.lean_cache import rebuild_ashare_lean_cache_from_db  # noqa: E402


SOURCE = "jqdata"
ASHARE_BATCH_ID = "e2e-ashare-510300-2024"


def trading_days(start: date, end: date) -> list[str]:
    current = start
    days: list[str] = []
    while current <= end:
        if current.weekday() < 5:
            days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def synthetic_rows(symbol: str, dates: list[str], base: float, trend: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous = base
    for index, trade_date in enumerate(dates):
        seasonal = math.sin(index / 11) * 0.8
        close = max(1.0, base + index * trend + seasonal)
        open_price = previous
        high = max(open_price, close) * 1.01
        low = min(open_price, close) * 0.99
        rows.append({
            "symbol": symbol,
            "trade_date": trade_date,
            "date": trade_date,
            "open": round(open_price, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close, 4),
            "volume": 1_000_000 + index * 1000,
            "amount": round(close * (1_000_000 + index * 1000), 2),
            "prev_close": round(previous, 4),
            "pct_change": round((close - previous) / previous, 6) if previous else 0,
            "adj_factor": 1.0,
        })
        previous = close
    return rows


def cleanup_e2e_records() -> None:
    with db() as connection:
        project_rows = connection.execute(
            "select id, project_path from projects where name like ?",
            ("E2E_%",),
        ).fetchall()
        projects = rows_to_dicts(project_rows)
        run_rows = connection.execute(
            "select id, task_id, work_dir, results_dir from backtest_runs where name like ?",
            ("E2E_%",),
        ).fetchall()
        runs = rows_to_dicts(run_rows)
        run_ids = [row["id"] for row in runs]
        task_ids = [row["task_id"] for row in runs if row.get("task_id")]
        project_ids = [row["id"] for row in projects]
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            connection.execute(f"delete from reports where run_id in ({placeholders})", run_ids)
            connection.execute(f"delete from backtest_results where job_id in ({placeholders})", run_ids)
            connection.execute(f"delete from experiments where run_id in ({placeholders})", run_ids)
            connection.execute(f"delete from backtest_runs where id in ({placeholders})", run_ids)
        if task_ids:
            placeholders = ",".join("?" for _ in task_ids)
            connection.execute(f"delete from tasks where id in ({placeholders})", task_ids)
        if project_ids:
            placeholders = ",".join("?" for _ in project_ids)
            connection.execute(f"delete from projects where id in ({placeholders})", project_ids)
    for row in projects + runs:
        for key in ("project_path", "work_dir", "results_dir"):
            value = row.get(key)
            if value:
                path = Path(str(value))
                if path.exists() and "E2E_" in str(path):
                    shutil.rmtree(path, ignore_errors=True)


def upsert_e2e_batch() -> None:
    now = utc_now()
    qa_report = {
        "passed": True,
        "severity": "ok",
        "source": "e2e",
        "symbols": ["510300", "000300"],
        "notes": ["Synthetic deterministic E2E daily data; not production market data."],
    }
    with db() as connection:
        connection.execute(
            """
            insert into data_import_batches
                (id, provider, market, asset_class, status, config_json, qa_report_json, error, started_at, finished_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(id) do update set
                provider = excluded.provider,
                market = excluded.market,
                asset_class = excluded.asset_class,
                status = excluded.status,
                config_json = excluded.config_json,
                qa_report_json = excluded.qa_report_json,
                error = excluded.error,
                started_at = excluded.started_at,
                finished_at = excluded.finished_at
            """,
            (
                ASHARE_BATCH_ID,
                SOURCE,
                "china",
                "equity",
                "success",
                json_dump({"namespace": "E2E", "symbols": ["510300", "000300"]}),
                json_dump(qa_report),
                None,
                now,
                now,
            ),
        )


def seed_ashare() -> dict[str, Any]:
    dates = trading_days(date(2024, 1, 1), date(2024, 12, 31))
    upsert_e2e_batch()
    import_security_master([
        {"symbol": "510300", "name": "E2E CSI300 ETF", "exchange": "SSE", "listed_date": "2012-01-01", "status": "listed"},
        {"symbol": "000300", "name": "E2E CSI300 Index Benchmark", "exchange": "SSE", "listed_date": "2005-01-01", "status": "listed"},
    ], source=SOURCE, universe_code="E2E")
    upsert_trade_calendar("china", dates, source=f"{SOURCE}:e2e", batch_id=ASHARE_BATCH_ID)
    bars_510300 = synthetic_rows("510300", dates, base=3.8, trend=0.0015)
    bars_000300 = synthetic_rows("000300", dates, base=3500.0, trend=0.8)
    upsert_daily_bars(bars_510300, source=SOURCE, batch_id=ASHARE_BATCH_ID, adjust="raw")
    upsert_daily_bars(bars_000300, source=SOURCE, batch_id=ASHARE_BATCH_ID, adjust="raw")
    status_rows = [
        {
            "symbol": symbol,
            "trade_date": trade_date,
            "is_suspended": False,
            "can_buy": True,
            "can_sell": True,
            "is_st": False,
            "limit_up": None,
            "limit_down": None,
            "is_limit_up": False,
            "is_limit_down": False,
            "is_one_word_limit_up": False,
            "is_one_word_limit_down": False,
        }
        for symbol in ("510300", "000300")
        for trade_date in dates
    ]
    upsert_trade_status(status_rows, source=SOURCE, batch_id=ASHARE_BATCH_ID)
    cache = {
        "510300": rebuild_ashare_lean_cache_from_db("510300", source=SOURCE, adjust="raw", market="china", batch_id=ASHARE_BATCH_ID),
        "000300": rebuild_ashare_lean_cache_from_db("000300", source=SOURCE, adjust="raw", market="china", batch_id=ASHARE_BATCH_ID),
    }
    return {"dates": len(dates), "source": SOURCE, "cache": cache}


def copy_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def seed_spy() -> dict[str, Any]:
    ensure_usa_auxiliary_files()
    target_daily = DATA_DIR / "equity" / "usa" / "daily" / "spy.zip"
    source_roots = [
        Path(os.environ.get("E2E_REAL_LEAN_DATA_DIR", "")),
        Path("/Users/kaermax/Lean/Data"),
        Path("/Users/kaermax/Data"),
    ]
    for source_root in source_roots:
        if not str(source_root):
            continue
        source_daily = source_root / "equity" / "usa" / "daily" / "spy.zip"
        if copy_if_exists(source_daily, target_daily):
            for folder in ("factor_files", "map_files"):
                copy_if_exists(source_root / "equity" / "usa" / folder / "spy.csv", DATA_DIR / "equity" / "usa" / folder / "spy.csv")
            return {"symbol": "SPY", "source": str(source_daily), "mode": "copied"}
    dates = trading_days(date(2019, 12, 1), date(2021, 1, 31))
    rows = synthetic_rows("SPY", dates, base=320.0, trend=0.08)
    metadata = write_lean_daily_zip("SPY", rows, "e2e-synthetic", overwrite=True, market="usa")
    return {"symbol": "SPY", "source": "synthetic", "mode": "generated", "metadata": metadata}


def ensure_usa_auxiliary_files() -> None:
    symbol_properties = DATA_DIR / "symbol-properties" / "symbol-properties-database.csv"
    symbol_properties.parent.mkdir(parents=True, exist_ok=True)
    if not symbol_properties.exists():
        symbol_properties.write_text(
            "market,symbol,type,description,quote_currency,contract_multiplier,minimum_price_variation,lot_size,market_ticker,minimum_order_size,price_magnifier,strike_multiplier\n",
            encoding="utf-8",
        )
    text = symbol_properties.read_text(encoding="utf-8", errors="replace")
    usa_entry = "usa,[*],equity,,USD,1,0.01,1,,1\n"
    if "usa,[*],equity" not in text:
        with symbol_properties.open("a", encoding="utf-8") as file:
            file.write(usa_entry)

    market_hours = DATA_DIR / "market-hours" / "market-hours-database.json"
    market_hours.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {"entries": {}}
    if market_hours.exists() and market_hours.read_text(encoding="utf-8", errors="replace").strip():
        try:
            parsed = json.loads(market_hours.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                data = parsed
        except Exception:
            data = {"entries": {}}
    entries = data.setdefault("entries", {})
    if "Equity-usa-[*]" not in entries:
        weekday = [{"start": "09:30:00", "end": "16:00:00", "state": "market"}]
        entries["Equity-usa-[*]"] = {
            "dataTimeZone": "America/New_York",
            "exchangeTimeZone": "America/New_York",
            "sunday": [],
            "monday": weekday,
            "tuesday": weekday,
            "wednesday": weekday,
            "thursday": weekday,
            "friday": weekday,
            "saturday": [],
            "holidays": [],
            "earlyCloses": {},
            "lateOpens": {},
            "regularHolidays": [],
        }
        market_hours.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> None:
    init_db()
    cleanup_e2e_records()
    spy = seed_spy()
    ashare = seed_ashare()
    report_dir = REPO_ROOT / "tests" / "e2e" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "data-source.json").write_text(json.dumps({
        "generatedAt": utc_now(),
        "leanDataDir": str(DATA_DIR),
        "spy": spy,
        "ashare": ashare,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
