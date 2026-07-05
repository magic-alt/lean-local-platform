#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web" / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


SKIP_SOURCE_TABLES = {"sqlite_sequence"}
DEFAULT_COPY_CHUNK = 5000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate web/runtime/HS300.sqlite3 into the MySQL runtime database.")
    parser.add_argument("--source", default=str(ROOT / "web" / "runtime" / "HS300.sqlite3"), help="SQLite source file.")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("LEAN_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market",
        help="Target MySQL URL, e.g. mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market.",
    )
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_COPY_CHUNK)
    parser.add_argument("--recreate-database", action="store_true", help="Drop and recreate the target MySQL database before importing.")
    parser.add_argument("--no-truncate", action="store_true", help="Do not clear target tables before copying.")
    parser.add_argument("--no-canonical-backfill", action="store_true", help="Skip instruments/market_daily_bars backfill.")
    parser.add_argument("--no-archive-files", action="store_true", help="Skip filesystem file archival into stored_objects.")
    parser.add_argument("--data-dir", default=os.environ.get("LEAN_DATA_DIR") or str(ROOT.parent / "Data"))
    parser.add_argument("--runtime-dir", default=str(ROOT / "web" / "runtime"))
    return parser.parse_args()


def ensure_mysql_database(url: str, recreate: bool = False) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise RuntimeError("Migration target must be mysql+pymysql://...")
    try:
        import pymysql
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("pymysql is required. Install web/backend/requirements.txt first.") from exc
    database = (parsed.path or "/lean_market").lstrip("/")
    connection = pymysql.connect(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 3306,
        user=unquote(parsed.username or "lean"),
        password=unquote(parsed.password or "lean"),
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            if recreate:
                cursor.execute(f"drop database if exists `{database}`")
            cursor.execute(
                f"create database if not exists `{database}` character set utf8mb4 collate utf8mb4_0900_ai_ci"
            )
    finally:
        connection.close()


def sqlite_tables(source: sqlite3.Connection) -> list[str]:
    rows = source.execute(
        """
        select name
        from sqlite_master
        where type = 'table'
        order by name
        """
    ).fetchall()
    return [row["name"] for row in rows if row["name"] not in SKIP_SOURCE_TABLES]


def source_columns(source: sqlite3.Connection, table: str) -> list[str]:
    return [row["name"] for row in source.execute(f"pragma table_info({table})").fetchall()]


def target_columns(target, table: str) -> list[str]:
    rows = target.execute(f"show columns from `{table}`").fetchall()
    return [row["Field"] for row in rows]


def target_tables(target) -> set[str]:
    rows = target.execute(
        """
        select table_name as name
        from information_schema.tables
        where table_schema = database() and table_type = 'BASE TABLE'
        """
    ).fetchall()
    return {row["name"] for row in rows}


def copy_table(source: sqlite3.Connection, table: str, target, chunk_size: int) -> dict[str, Any]:
    src_cols = source_columns(source, table)
    tgt_cols = target_columns(target, table)
    columns = [column for column in src_cols if column in tgt_cols]
    if not columns:
        return {"table": table, "copied": 0, "columns": 0, "skipped": "no common columns"}
    placeholders = ",".join("?" for _ in columns)
    column_sql = ", ".join(f"`{column}`" for column in columns)
    insert_sql = f"insert into `{table}` ({column_sql}) values ({placeholders})"
    offset = 0
    copied = 0
    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    select_sql = f'select {quoted_columns} from "{table}" limit ? offset ?'
    while True:
        rows = source.execute(select_sql, (chunk_size, offset)).fetchall()
        if not rows:
            break
        params = [tuple(row[column] for column in columns) for row in rows]
        target.executemany(insert_sql, params)
        copied += len(params)
        offset += len(params)
    return {"table": table, "copied": copied, "columns": len(columns)}


def clear_target(target, tables: Iterable[str]) -> None:
    for table in sorted(tables, reverse=True):
        target.execute(f"delete from `{table}`")


def source_count(source: sqlite3.Connection, table: str) -> int:
    return int(source.execute(f"select count(*) as count from {table}").fetchone()["count"])


def target_count(target, table: str) -> int:
    return int(target.execute(f"select count(*) as count from `{table}`").fetchone()["count"])


def row_chunks(target, sql: str, chunk_size: int) -> Iterable[list[dict[str, Any]]]:
    offset = 0
    while True:
        rows = target.execute(sql + " limit ? offset ?", (chunk_size, offset)).fetchall()
        if not rows:
            break
        yield rows
        offset += len(rows)


def instrument_uuid(asset_class: str, market: str, symbol: str, venue: str | None = None) -> str:
    from app.services.market_repository import instrument_id

    return instrument_id(asset_class, market, symbol, venue or market)


def upsert_instrument_rows(target, rows: list[tuple[Any, ...]]) -> None:
    if not rows:
        return
    target.executemany(
        """
        insert into instruments
            (instrument_id, symbol, normalized_symbol, name, asset_class, market, exchange, venue,
             currency, underlying_symbol, listed_date, delisted_date, expiry_date, status, lot_size,
             tick_size, contract_multiplier, margin_rate, metadata_json, source, created_at, updated_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(instrument_id) do update set
            symbol = excluded.symbol,
            normalized_symbol = excluded.normalized_symbol,
            name = excluded.name,
            exchange = excluded.exchange,
            venue = excluded.venue,
            currency = excluded.currency,
            underlying_symbol = excluded.underlying_symbol,
            listed_date = excluded.listed_date,
            delisted_date = excluded.delisted_date,
            expiry_date = excluded.expiry_date,
            status = excluded.status,
            lot_size = excluded.lot_size,
            tick_size = excluded.tick_size,
            contract_multiplier = excluded.contract_multiplier,
            margin_rate = excluded.margin_rate,
            metadata_json = excluded.metadata_json,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        rows,
    )


def backfill_instruments(target) -> dict[str, int]:
    from app.db import json_dump, utc_now

    now = utc_now()
    security_rows = target.execute("select * from securities").fetchall()
    instrument_rows = []
    for row in security_rows:
        symbol = row["symbol"]
        instrument_rows.append(
            (
                instrument_uuid("equity", "china", symbol, "china"),
                symbol,
                symbol,
                row.get("name") or symbol,
                "equity",
                "china",
                row.get("exchange"),
                "china",
                "CNY",
                None,
                row.get("listed_date"),
                row.get("delisted_date"),
                None,
                "delisted" if row.get("status") == "delisted" else "active",
                100,
                0.01,
                None,
                None,
                json_dump({"security_status": row.get("status"), "is_st": row.get("is_st"), "industry": row.get("industry")}),
                "migration:securities",
                now,
                now,
            )
        )
    future_rows = target.execute("select * from futures_contracts").fetchall()
    for row in future_rows:
        symbol = row["contract_code"]
        exchange = row.get("exchange") or "future"
        instrument_rows.append(
            (
                instrument_uuid("future", "future", symbol, exchange),
                symbol,
                symbol,
                row.get("name") or symbol,
                "future",
                "future",
                exchange,
                exchange,
                None,
                row.get("product"),
                row.get("listed_date"),
                None,
                row.get("last_trade_date"),
                "active",
                None,
                row.get("tick_size"),
                row.get("multiplier"),
                row.get("margin_rate"),
                json_dump({"delivery_month": row.get("delivery_month"), "product": row.get("product")}),
                row.get("source") or "migration:futures_contracts",
                now,
                now,
            )
        )
    cbond_rows = target.execute("select * from cbond_securities").fetchall()
    for row in cbond_rows:
        symbol = row["bond_code"]
        instrument_rows.append(
            (
                instrument_uuid("cbond", "china", symbol, "china"),
                symbol,
                symbol,
                row.get("bond_name") or symbol,
                "cbond",
                "china",
                None,
                "china",
                "CNY",
                row.get("stock_symbol"),
                row.get("listed_date"),
                row.get("delisted_date"),
                row.get("maturity_date"),
                "active",
                None,
                None,
                None,
                None,
                json_dump({"rating": row.get("rating"), "conversion_price": row.get("conversion_price")}),
                row.get("source") or "migration:cbond_securities",
                now,
                now,
            )
        )
    upsert_instrument_rows(target, instrument_rows)
    return {"instruments": len(instrument_rows)}


def backfill_market_daily_bars(target, chunk_size: int) -> dict[str, int]:
    copied = {"ashare": 0, "future": 0, "cbond": 0}
    target.execute("delete from market_daily_bars")
    for rows in row_chunks(
        target,
        """
        select symbol, trade_date, open, high, low, close, volume, amount, turnover_rate, prev_close,
               pct_change, adjust, adj_factor, source, batch_id, created_at
        from ashare_daily_bars
        order by symbol, trade_date
        """,
        chunk_size,
    ):
        params = [
            (
                instrument_uuid("equity", "china", row["symbol"], "china"),
                row["symbol"],
                "equity",
                "china",
                "china",
                row["trade_date"],
                "daily",
                "trade",
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                None,
                row["volume"],
                row["amount"],
                row["turnover_rate"],
                None,
                row["prev_close"],
                row["pct_change"],
                row["adjust"] or "raw",
                row["adj_factor"],
                row["source"],
                row["batch_id"],
                row["created_at"],
            )
            for row in rows
        ]
        target.executemany(
            """
            insert into market_daily_bars
                (instrument_id, symbol, asset_class, market, venue, trade_date, resolution, data_type,
                 open, high, low, close, settle, volume, amount, turnover_rate, open_interest, prev_close,
                 pct_change, adjust, adj_factor, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(instrument_id, trade_date, resolution, data_type, adjust, source) do update set
                open = excluded.open, high = excluded.high, low = excluded.low, close = excluded.close,
                settle = excluded.settle, volume = excluded.volume, amount = excluded.amount,
                turnover_rate = excluded.turnover_rate, open_interest = excluded.open_interest,
                prev_close = excluded.prev_close, pct_change = excluded.pct_change,
                adj_factor = excluded.adj_factor, batch_id = excluded.batch_id, created_at = excluded.created_at
            """,
            params,
        )
        copied["ashare"] += len(params)
    futures_exchange = {
        row["contract_code"]: row.get("exchange") or "future"
        for row in target.execute("select contract_code, exchange from futures_contracts").fetchall()
    }
    for rows in row_chunks(
        target,
        """
        select contract_code, trade_date, open, high, low, close, volume, open_interest, source, batch_id, created_at
        from futures_daily_bars
        order by contract_code, trade_date
        """,
        chunk_size,
    ):
        params = [
            (
                instrument_uuid("future", "future", row["contract_code"], futures_exchange.get(row["contract_code"]) or "future"),
                row["contract_code"],
                "future",
                "future",
                futures_exchange.get(row["contract_code"]) or "future",
                row["trade_date"],
                "daily",
                "trade",
                row["open"],
                row["high"],
                row["low"],
                row["close"],
                None,
                row["volume"],
                None,
                None,
                row["open_interest"],
                None,
                None,
                "raw",
                None,
                row["source"],
                row["batch_id"],
                row["created_at"],
            )
            for row in rows
        ]
        target.executemany(
            """
            insert into market_daily_bars
                (instrument_id, symbol, asset_class, market, venue, trade_date, resolution, data_type,
                 open, high, low, close, settle, volume, amount, turnover_rate, open_interest, prev_close,
                 pct_change, adjust, adj_factor, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(instrument_id, trade_date, resolution, data_type, adjust, source) do update set
                open = excluded.open, high = excluded.high, low = excluded.low, close = excluded.close,
                volume = excluded.volume, open_interest = excluded.open_interest,
                batch_id = excluded.batch_id, created_at = excluded.created_at
            """,
            params,
        )
        copied["future"] += len(params)
    for rows in row_chunks(
        target,
        """
        select bond_code, trade_date, close, source, batch_id, created_at
        from cbond_daily_bars
        order by bond_code, trade_date
        """,
        chunk_size,
    ):
        params = [
            (
                instrument_uuid("cbond", "china", row["bond_code"], "china"),
                row["bond_code"],
                "cbond",
                "china",
                "china",
                row["trade_date"],
                "daily",
                "trade",
                row["close"],
                row["close"],
                row["close"],
                row["close"],
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "raw",
                None,
                row["source"],
                row["batch_id"],
                row["created_at"],
            )
            for row in rows
        ]
        target.executemany(
            """
            insert into market_daily_bars
                (instrument_id, symbol, asset_class, market, venue, trade_date, resolution, data_type,
                 open, high, low, close, settle, volume, amount, turnover_rate, open_interest, prev_close,
                 pct_change, adjust, adj_factor, source, batch_id, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(instrument_id, trade_date, resolution, data_type, adjust, source) do update set
                open = excluded.open, high = excluded.high, low = excluded.low, close = excluded.close,
                batch_id = excluded.batch_id, created_at = excluded.created_at
            """,
            params,
        )
        copied["cbond"] += len(params)
    return copied


def backfill_market_trade_status(target, chunk_size: int) -> dict[str, int]:
    copied = 0
    target.execute("delete from market_trade_status")
    for rows in row_chunks(
        target,
        """
        select symbol, trade_date, is_suspended, can_buy, can_sell, limit_up, limit_down, source, batch_id
        from ashare_trade_status
        order by symbol, trade_date
        """,
        chunk_size,
    ):
        params = [
            (
                instrument_uuid("equity", "china", row["symbol"], "china"),
                row["symbol"],
                "equity",
                "china",
                "china",
                row["trade_date"],
                1 if row["can_buy"] or row["can_sell"] else 0,
                row["is_suspended"],
                row["can_buy"],
                row["can_sell"],
                row["limit_up"],
                row["limit_down"],
                None,
                None,
                row["source"],
                row["batch_id"],
                None,
            )
            for row in rows
        ]
        target.executemany(
            """
            insert into market_trade_status
                (instrument_id, symbol, asset_class, market, venue, trade_date, is_tradeable,
                 is_suspended, can_buy, can_sell, limit_up, limit_down, status, reason, source, batch_id, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, coalesce(?, utc_timestamp()))
            on conflict(instrument_id, trade_date, source) do update set
                is_tradeable = excluded.is_tradeable,
                is_suspended = excluded.is_suspended,
                can_buy = excluded.can_buy,
                can_sell = excluded.can_sell,
                limit_up = excluded.limit_up,
                limit_down = excluded.limit_down,
                batch_id = excluded.batch_id,
                updated_at = excluded.updated_at
            """,
            params,
        )
        copied += len(params)
    return {"ashare_status": copied}


def archive_files(root: Path, namespace: str, key_prefix: str = "") -> dict[str, Any]:
    from app.services.db_object_store import put_file

    if not root.exists():
        return {"namespace": namespace, "root": str(root), "files": 0, "bytes": 0, "missing": True}
    files = 0
    bytes_total = 0
    for current, _, filenames in os.walk(root, followlinks=True):
        current_path = Path(current)
        for filename in filenames:
            path = current_path / filename
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            key = f"{key_prefix}/{relative}".strip("/")
            stored = put_file(namespace, key, path, metadata={"archive_root": str(root), "relative_path": relative})
            if stored:
                files += 1
                bytes_total += int(stored.get("size") or 0)
    return {"namespace": namespace, "root": str(root), "files": files, "bytes": bytes_total}


def main() -> int:
    args = parse_args()
    source_path = Path(args.source).expanduser().resolve()
    if not source_path.exists():
        raise SystemExit(f"SQLite source not found: {source_path}")
    ensure_mysql_database(args.database_url, recreate=args.recreate_database)
    os.environ["LEAN_DATABASE_URL"] = args.database_url
    os.environ["LEAN_SQLITE_MIGRATION_SOURCE"] = str(source_path)

    from app.db import db, init_db

    init_db()
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    summary: dict[str, Any] = {"source": str(source_path), "target": "mysql", "tables": [], "counts": {}}
    try:
        tables = sqlite_tables(source)
        with db() as target:
            available = target_tables(target)
            copyable = [table for table in tables if table in available]
            if not args.no_truncate:
                clear_target(target, copyable)
            for table in copyable:
                result = copy_table(source, table, target, max(1, args.chunk_size))
                result["source_count"] = source_count(source, table)
                result["target_count"] = target_count(target, table)
                summary["tables"].append(result)
        if not args.no_canonical_backfill:
            with db() as target:
                summary["canonical"] = {
                    **backfill_instruments(target),
                    **backfill_market_daily_bars(target, max(1, args.chunk_size)),
                    **backfill_market_trade_status(target, max(1, args.chunk_size)),
                }
        if not args.no_archive_files:
            runtime_dir = Path(args.runtime_dir).expanduser().resolve()
            data_dir = Path(args.data_dir).expanduser().resolve()
            summary["archived_files"] = [
                archive_files(data_dir, "lean-data-files"),
                archive_files(runtime_dir / "runs", "runtime-runs"),
                archive_files(runtime_dir / "object-store", "object-store"),
            ]
        with db() as target:
            for table in ("securities", "ashare_daily_bars", "market_daily_bars", "instruments", "stored_objects", "universe_membership"):
                if table in target_tables(target):
                    summary["counts"][table] = target_count(target, table)
    finally:
        source.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
