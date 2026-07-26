from __future__ import annotations

import re
import base64
from datetime import datetime, timezone
import threading
from typing import Any
from urllib.request import Request, urlopen

from ..db import db
from ..core.config import (
    CLICKHOUSE_DATABASE,
    CLICKHOUSE_ENABLED,
    CLICKHOUSE_HOST,
    CLICKHOUSE_PASSWORD,
    CLICKHOUSE_PORT,
    CLICKHOUSE_USERNAME,
)
from ..lean_engine.symbols import market_key, normalize_symbol
from ..observability.metrics import set_dependency_status

try:
    import clickhouse_connect
except Exception:  # pragma: no cover - optional until infra deps are installed.
    clickhouse_connect = None


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BAR_COLUMNS = [
    "asset_class",
    "symbol",
    "venue",
    "resolution",
    "data_type",
    "source",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "imported_at",
]
_SCHEMA_READY = False
_SCHEMA_LOCK = threading.Lock()
INSERT_BATCH_SIZE = 100_000


def _normalize_query_market(asset_class: str, market: str | None, venue: str | None) -> str | None:
    if asset_class != "equity":
        return market or venue
    resolved = market or venue
    if not resolved:
        return None
    if resolved.strip().lower() in {"china", "usa", "hk", "hongkong"}:
        return market_key(resolved)
    return market_key(resolved)


def _looks_like_china_equity_symbol(value: str) -> bool:
    upper = value.strip().upper().replace("_", ".")
    if upper.startswith(("SH", "SZ", "SS", "BJ")):
        return True
    if upper.startswith(("SH.", "SZ.", "SS.", "BJ.")):
        return True
    if "." in upper:
        base, suffix = upper.rsplit(".", 1)
        if suffix in {"SH", "SZ", "SS", "BJ"}:
            return True
    return upper.isdigit() and len(upper) == 6


def _normalize_query_symbol(symbol: str, asset_class: str, market: str | None, venue: str | None) -> str:
    value = str(symbol).strip()
    if not value:
        raise ValueError("symbol is required")
    if asset_class != "equity":
        return value.upper()

    query_market = _normalize_query_market(asset_class, market, venue)
    if query_market == "china":
        return normalize_symbol(value, query_market)

    if query_market == "hongkong":
        return normalize_symbol(value, query_market)

    if query_market is None:
        if _looks_like_china_equity_symbol(value):
            return normalize_symbol(value, "china")
        return value.upper()

    return value.upper()


def _identifier(value: str) -> str:
    if not IDENTIFIER.match(value):
        raise ValueError(f"Invalid ClickHouse identifier: {value!r}")
    return value


def _table() -> str:
    return f"{_identifier(CLICKHOUSE_DATABASE)}.market_bars"


def enabled() -> bool:
    return CLICKHOUSE_ENABLED and clickhouse_connect is not None


def _client(database: str | None = None, *, timeout: int = 5):
    if clickhouse_connect is None:
        raise RuntimeError("clickhouse-connect is not installed.")
    return clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        username=CLICKHOUSE_USERNAME,
        password=CLICKHOUSE_PASSWORD,
        database=database or CLICKHOUSE_DATABASE,
        connect_timeout=1,
        send_receive_timeout=max(1, int(timeout)),
    )


def ensure_schema() -> bool:
    global _SCHEMA_READY
    if not enabled():
        return False
    if _SCHEMA_READY:
        return True
    with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return True
        base = _client("default")
        database = _identifier(CLICKHOUSE_DATABASE)
        base.command(f"CREATE DATABASE IF NOT EXISTS {database}")
        base.command(
            f"""
            CREATE TABLE IF NOT EXISTS {_table()}
            (
                asset_class LowCardinality(String),
                symbol String,
                venue LowCardinality(String),
                resolution LowCardinality(String),
                data_type LowCardinality(String),
                source LowCardinality(String),
                timestamp DateTime64(3, 'UTC'),
                open Float64,
                high Float64,
                low Float64,
                close Float64,
                volume Float64,
                imported_at DateTime64(3, 'UTC'),
                date Date MATERIALIZED toDate(timestamp)
            )
            ENGINE = ReplacingMergeTree(imported_at)
            PARTITION BY toYear(timestamp)
            ORDER BY (asset_class, venue, symbol, resolution, data_type, timestamp)
            """
        )
        partition_rows = base.query(
            f"SELECT partition_key FROM system.tables WHERE database = {_literal(database)} "
            f"AND name = {_literal('market_bars')}"
        ).result_rows
        partition_key = str(partition_rows[0][0]) if partition_rows else ""
        if partition_key != "toYear(timestamp)":
            raise RuntimeError(
                "clickhouse_schema_migration_required: market_bars must use toYear(timestamp) partitioning"
            )
        _SCHEMA_READY = True
    return True


def ping() -> dict[str, Any]:
    if not CLICKHOUSE_ENABLED:
        set_dependency_status("clickhouse", False)
        return {"service": "clickhouse", "ok": False, "detail": "disabled by CLICKHOUSE_ENABLED"}
    if clickhouse_connect is None:
        set_dependency_status("clickhouse", False)
        return {"service": "clickhouse", "ok": False, "detail": "clickhouse-connect is not installed"}
    try:
        request = Request(f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}/ping")
        credentials = f"{CLICKHOUSE_USERNAME}:{CLICKHOUSE_PASSWORD}".encode("utf-8")
        request.add_header("Authorization", "Basic " + base64.b64encode(credentials).decode("ascii"))
        with urlopen(request, timeout=1) as response:
            ok = response.status == 200
        if not ok:
            raise RuntimeError("ClickHouse ping failed")
        set_dependency_status("clickhouse", True)
        return {"service": "clickhouse", "ok": True, "detail": f"{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}"}
    except Exception as exc:
        set_dependency_status("clickhouse", False)
        return {"service": "clickhouse", "ok": False, "detail": str(exc)}


def _parse_timestamp(row: dict[str, str]) -> datetime:
    value = row.get("date") or row.get("timestamp") or row.get("time")
    if not value:
        raise ValueError("OHLCV row is missing a date/timestamp field.")
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            item_date = datetime.strptime(value[:10] if fmt != "%Y%m%d" else value[:8], fmt)
            return item_date.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(f"Invalid OHLCV timestamp: {value!r}") from exc


def _float(row: dict[str, str], key: str) -> float:
    return float(row[key])


def mirror_rows_batch(
    entries: list[tuple[dict[str, Any], list[dict[str, str]]]],
) -> list[dict[str, Any]]:
    """Mirror several assets through one ClickHouse client and insert stream."""
    if not entries:
        return []
    if not enabled():
        return [{"enabled": False, "inserted": 0} for _ in entries]
    try:
        ensure_schema()
    except Exception as exc:
        set_dependency_status("clickhouse", False)
        return [{"enabled": True, "inserted": 0, "error": str(exc)} for _ in entries]
    imported_at = datetime.now(timezone.utc)
    payload: list[tuple[Any, ...]] = []
    results: list[dict[str, Any]] = []
    for metadata, rows in entries:
        asset_class = str(metadata.get("asset_class") or metadata.get("assetClass") or "equity")
        symbol = _normalize_query_symbol(
            metadata["symbol"],
            asset_class.strip().lower(),
            str(metadata.get("market") or "").strip().lower() or None,
            str(metadata.get("venue") or "").strip().lower() or None,
        )
        venue = str(metadata.get("venue") or metadata.get("market") or "usa")
        resolution = str(metadata.get("resolution") or "daily")
        data_type = str(metadata.get("data_type") or metadata.get("dataType") or "trade")
        source = str(metadata.get("source") or metadata.get("provider") or "unknown")
        inserted = 0
        skipped = 0
        for row in rows:
            try:
                payload.append(
                    (
                        asset_class,
                        symbol,
                        venue,
                        resolution,
                        data_type,
                        source,
                        _parse_timestamp(row),
                        _float(row, "open"),
                        _float(row, "high"),
                        _float(row, "low"),
                        _float(row, "close"),
                        float(row.get("volume") or 0),
                        imported_at,
                    )
                )
                inserted += 1
            except Exception:
                skipped += 1
        results.append({"enabled": True, "inserted": inserted, "skipped": skipped, "batches": 0})
    batches = 0
    if payload:
        try:
            client = _client()
            # Keep each insert bounded to five calendar years. The table uses
            # yearly partitions so a full-history rebuild creates only a few
            # hundred parts rather than one part per month per batch.
            by_period: dict[int, list[tuple[Any, ...]]] = {}
            for item in payload:
                timestamp = item[6]
                by_period.setdefault(timestamp.year // 5, []).append(item)
            for period_rows in by_period.values():
                for offset in range(0, len(period_rows), INSERT_BATCH_SIZE):
                    client.insert(
                        "market_bars",
                        period_rows[offset : offset + INSERT_BATCH_SIZE],
                        column_names=BAR_COLUMNS,
                    )
                    batches += 1
            set_dependency_status("clickhouse", True)
        except Exception as exc:
            set_dependency_status("clickhouse", False)
            return [{**result, "error": str(exc)} for result in results]
    for result in results:
        result["batches"] = batches
    return results


def mirror_rows(metadata: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any]:
    return mirror_rows_batch([(metadata, rows)])[0]


def replace_china_equity_symbols_from_canonical(symbols: list[str]) -> dict[str, Any]:
    """Replace a bounded symbol set after authoritative snapshot pruning."""
    normalized = sorted(
        {
            _normalize_query_symbol(symbol, "equity", "china", "china")
            for symbol in symbols
            if str(symbol).strip()
        }
    )
    if not normalized:
        return {"enabled": enabled(), "symbols": [], "deleted": 0, "inserted": 0}
    if not enabled():
        return {"enabled": False, "symbols": normalized, "deleted": 0, "inserted": 0}
    ensure_schema()
    client = _client(timeout=300)
    symbol_list = ",".join(_literal(symbol) for symbol in normalized)
    before = int(
        client.query(
            f"""
            select count(*) from {_table()} FINAL
            where asset_class='equity' and venue='china' and resolution='daily'
              and data_type='trade' and source='tushare' and symbol in ({symbol_list})
            """
        ).result_rows[0][0]
    )
    client.command(
        f"""
        alter table {_table()} delete where
          asset_class='equity' and venue='china' and resolution='daily'
          and data_type='trade' and source='tushare' and symbol in ({symbol_list})
        settings mutations_sync=2
        """
    )
    entries = []
    for symbol in normalized:
        bars = query_database_bars(
            asset_class="equity",
            symbol=symbol,
            market="china",
            venue="china",
            resolution="daily",
            data_type="trade",
            provider_source="tushare",
            limit=0,
        )["items"]
        if bars:
            entries.append(
                (
                    {
                        "asset_class": "equity",
                        "symbol": symbol,
                        "market": "china",
                        "venue": "china",
                        "resolution": "daily",
                        "data_type": "trade",
                        "source": "tushare",
                    },
                    bars,
                )
            )
    results = mirror_rows_batch(entries)
    if any(result.get("error") for result in results):
        raise RuntimeError(f"clickhouse_symbol_replace_failed:{results}")
    inserted = sum(int(result.get("inserted") or 0) for result in results)
    return {
        "enabled": True,
        "symbols": normalized,
        "deleted": before,
        "inserted": inserted,
    }


def scope_stats(scope: dict[str, str]) -> dict[str, Any]:
    """Return deduplicated materialization coverage for one canonical scope."""
    if not enabled():
        return {"enabled": False, "rowCount": 0, "firstDate": None, "lastDate": None}
    ensure_schema()
    predicates = [
        f"asset_class = {_literal(scope['asset_class'])}",
        f"venue = {_literal(scope['venue'])}",
        f"resolution = {_literal(scope['resolution'])}",
        f"data_type = {_literal(scope['data_type'])}",
        f"source = {_literal(scope['source'])}",
    ]
    row = _client(timeout=300).query(
        f"""
        select count(),min(date),max(date)
        from {_table()} FINAL
        where {" and ".join(predicates)}
        """
    ).result_rows[0]
    return {
        "enabled": True,
        "rowCount": int(row[0] or 0),
        "firstDate": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1] or "") or None,
        "lastDate": row[2].isoformat() if hasattr(row[2], "isoformat") else str(row[2] or "") or None,
    }


def scope_date_counts(scope: dict[str, str]) -> dict[str, int]:
    """Return deduplicated row counts by date for bounded drift repair."""
    if not enabled():
        return {}
    ensure_schema()
    predicates = [
        f"asset_class = {_literal(scope['asset_class'])}",
        f"venue = {_literal(scope['venue'])}",
        f"resolution = {_literal(scope['resolution'])}",
        f"data_type = {_literal(scope['data_type'])}",
        f"source = {_literal(scope['source'])}",
    ]
    rows = _client(timeout=300).query(
        f"""
        select date,count()
        from {_table()} FINAL
        where {" and ".join(predicates)}
        group by date
        order by date
        """
    ).result_rows
    return {
        item_date.isoformat() if hasattr(item_date, "isoformat") else str(item_date): int(row_count)
        for item_date, row_count in rows
    }


def _literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def query_bars(
    *,
    asset_class: str = "equity",
    symbol: str,
    market: str | None = None,
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    provider_source: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    if not enabled():
        return {"enabled": False, "items": [], "count": 0}
    health = ping()
    if not health["ok"]:
        return {"enabled": False, "items": [], "count": 0, "error": health["detail"]}
    ensure_schema()
    asset_class_key = asset_class.strip().lower()
    venue_key = str(market or venue or "").strip().lower() or None
    normalized_symbol = _normalize_query_symbol(symbol, asset_class_key, market, venue_key)

    predicates = [
        f"asset_class = {_literal(asset_class_key)}",
        f"symbol = {_literal(normalized_symbol)}",
        f"resolution = {_literal(resolution)}",
        f"data_type = {_literal(data_type)}",
    ]
    if venue_key:
        predicates.append(f"venue = {_literal(venue_key)}")
    if provider_source:
        predicates.append(f"source = {_literal(provider_source)}")
    if start_date:
        predicates.append(f"timestamp >= toDateTime64({_literal(start_date + ' 00:00:00')}, 3, 'UTC')")
    if end_date:
        predicates.append(f"timestamp <= toDateTime64({_literal(end_date + ' 23:59:59')}, 3, 'UTC')")
    bounded_limit = None if int(limit) <= 0 else max(1, min(int(limit), 5000))
    result = _client().query(
        f"""
        SELECT timestamp, open, high, low, close, volume, source
        FROM {_table()} FINAL
        WHERE {" AND ".join(predicates)}
        ORDER BY timestamp ASC
        {f"LIMIT {bounded_limit}" if bounded_limit else ""}
        """
    )
    items = [
        {
            "timestamp": row[0].isoformat() if hasattr(row[0], "isoformat") else str(row[0]),
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
            "volume": row[5],
            "source": row[6],
        }
        for row in result.result_rows
    ]
    return {"enabled": True, "items": items, "count": len(items)}


def _bounded_limit(limit: int) -> int | None:
    return None if int(limit) <= 0 else max(1, min(int(limit), 5000))


def query_database_bars(
    *,
    asset_class: str = "equity",
    symbol: str,
    market: str | None = None,
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    provider_source: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    asset_class_key = asset_class.strip().lower()
    market_value = (market or "").strip().lower()
    venue_key = (venue or market or "").strip().lower()
    normalized_symbol = _normalize_query_symbol(symbol, asset_class_key, market_value or None, venue_key)
    resolution_key = resolution.strip().lower()
    data_type_key = data_type.strip().lower()
    predicates = ["asset_class = ?", "symbol = ?", "resolution = ?", "data_type = ?"]
    params: list[Any] = [asset_class_key, normalized_symbol, resolution_key, data_type_key]
    if market_value:
        predicates.append("market = ?")
        params.append(market_value)
    if venue_key:
        predicates.append("venue = ?")
        params.append(venue_key)
    if provider_source:
        predicates.append("source = ?")
        params.append(provider_source)
    if start_date:
        predicates.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        predicates.append("trade_date <= ?")
        params.append(end_date)
    bounded_limit = _bounded_limit(limit)
    if bounded_limit is None:
        sql = f"""
            select trade_date, open, high, low, close, volume, source
            from market_daily_bars
            where {" and ".join(predicates)}
            order by trade_date asc, source asc
            """
    else:
        params.append(bounded_limit)
        sql = f"""
            select trade_date, open, high, low, close, volume, source
            from market_daily_bars
            where {" and ".join(predicates)}
            order by trade_date asc, source asc
            limit ?
            """
    with db() as connection:
        rows = connection.execute(sql, params).fetchall()
    items = [
        {
            "timestamp": row["trade_date"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
            "source": row["source"],
        }
        for row in rows
    ]
    return {"enabled": True, "source": "database", "items": items, "count": len(items)}
