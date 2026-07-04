from __future__ import annotations

import re
import base64
from datetime import datetime, timezone
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


def _identifier(value: str) -> str:
    if not IDENTIFIER.match(value):
        raise ValueError(f"Invalid ClickHouse identifier: {value!r}")
    return value


def _table() -> str:
    return f"{_identifier(CLICKHOUSE_DATABASE)}.market_bars"


def enabled() -> bool:
    return CLICKHOUSE_ENABLED and clickhouse_connect is not None


def _client(database: str | None = None):
    if clickhouse_connect is None:
        raise RuntimeError("clickhouse-connect is not installed.")
    return clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        username=CLICKHOUSE_USERNAME,
        password=CLICKHOUSE_PASSWORD,
        database=database or CLICKHOUSE_DATABASE,
        connect_timeout=1,
        send_receive_timeout=5,
    )


def ensure_schema() -> bool:
    if not enabled():
        return False
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
        PARTITION BY toYYYYMM(timestamp)
        ORDER BY (asset_class, venue, symbol, resolution, data_type, timestamp)
        """
    )
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


def mirror_rows(metadata: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any]:
    if not enabled():
        return {"enabled": False, "inserted": 0}
    if not rows:
        return {"enabled": True, "inserted": 0}
    health = ping()
    if not health["ok"]:
        return {"enabled": True, "inserted": 0, "error": health["detail"]}
    ensure_schema()
    imported_at = datetime.now(timezone.utc)
    asset_class = str(metadata.get("asset_class") or metadata.get("assetClass") or "equity")
    symbol = str(metadata["symbol"]).upper()
    venue = str(metadata.get("venue") or metadata.get("market") or "usa")
    resolution = str(metadata.get("resolution") or "daily")
    data_type = str(metadata.get("data_type") or metadata.get("dataType") or "trade")
    source = str(metadata.get("source") or metadata.get("provider") or "unknown")
    payload = []
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
        except Exception:
            skipped += 1
    if payload:
        _client().insert("market_bars", payload, column_names=BAR_COLUMNS)
    return {"enabled": True, "inserted": len(payload), "skipped": skipped}


def _literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def query_bars(
    *,
    asset_class: str = "equity",
    symbol: str,
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
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
    predicates = [
        f"asset_class = {_literal(asset_class)}",
        f"symbol = {_literal(symbol.upper())}",
        f"resolution = {_literal(resolution)}",
        f"data_type = {_literal(data_type)}",
    ]
    if venue:
        predicates.append(f"venue = {_literal(venue)}")
    if start_date:
        predicates.append(f"timestamp >= toDateTime64({_literal(start_date + ' 00:00:00')}, 3, 'UTC')")
    if end_date:
        predicates.append(f"timestamp <= toDateTime64({_literal(end_date + ' 23:59:59')}, 3, 'UTC')")
    bounded_limit = max(1, min(int(limit), 5000))
    result = _client().query(
        f"""
        SELECT timestamp, open, high, low, close, volume, source
        FROM {_table()} FINAL
        WHERE {" AND ".join(predicates)}
        ORDER BY timestamp ASC
        LIMIT {bounded_limit}
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


def _bounded_limit(limit: int) -> int:
    return max(1, min(int(limit), 5000))


def _sqlite_symbol(symbol: str, venue: str | None = None) -> str:
    value = symbol.strip().upper()
    if venue and venue.lower() == "china":
        if value.startswith(("SH", "SZ", "BJ")):
            return value[2:]
        if "." in value:
            return value.split(".", 1)[0]
    return value


def query_sqlite_bars(
    *,
    asset_class: str = "equity",
    symbol: str,
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    asset_class_key = asset_class.strip().lower()
    venue_key = (venue or "").strip().lower()
    resolution_key = resolution.strip().lower()
    data_type_key = data_type.strip().lower()
    if (
        asset_class_key != "equity"
        or venue_key not in {"", "china"}
        or resolution_key != "daily"
        or data_type_key != "trade"
    ):
        return {
            "enabled": True,
            "source": "sqlite",
            "items": [],
            "count": 0,
            "message": "Local SQLite preview currently supports China equity daily trade bars.",
        }

    predicates = ["symbol = ?"]
    params: list[Any] = [_sqlite_symbol(symbol, "china")]
    if start_date:
        predicates.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        predicates.append("trade_date <= ?")
        params.append(end_date)
    params.append(_bounded_limit(limit))
    with db() as connection:
        rows = connection.execute(
            f"""
            select trade_date, open, high, low, close, volume, source
            from ashare_daily_bars
            where {" and ".join(predicates)}
            order by trade_date asc, source asc
            limit ?
            """,
            params,
        ).fetchall()
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
    return {"enabled": True, "source": "sqlite", "items": items, "count": len(items)}
