from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..db import db, rows_to_dicts
from ..lean_engine import data_paths
from ..lean_engine.data_writers import write_lean_daily_zip
from ..lean_engine.errors import LeanPlatformError
from ..lean_engine.symbols import normalize_symbol, symbol_key
from .db_object_store import latest_object, put_file, restore_to_path


LEAN_DATA_NAMESPACE = "lean-data-files"


def _data_relative(path: Path) -> str:
    try:
        return str(path.relative_to(data_paths.DATA_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _archive_data_file(path: Path, *, metadata: dict[str, Any] | None = None, content_type: str | None = None) -> dict[str, Any]:
    return put_file(
        LEAN_DATA_NAMESPACE,
        _data_relative(path),
        path,
        content_type=content_type,
        metadata={"relative_path": _data_relative(path), **(metadata or {})},
    )


def _lean_daily_path(symbol: str, market: str = "china") -> Path:
    ticker = symbol_key(normalize_symbol(symbol, market))
    return data_paths.DATA_DIR / "equity" / market / "daily" / f"{ticker}.zip"


def _lean_factor_path(symbol: str, market: str = "china") -> Path:
    ticker = symbol_key(normalize_symbol(symbol, market))
    return data_paths.DATA_DIR / "equity" / market / "factor_files" / f"{ticker}.csv"


def _lean_map_path(symbol: str, market: str = "china") -> Path:
    ticker = symbol_key(normalize_symbol(symbol, market))
    return data_paths.DATA_DIR / "equity" / market / "map_files" / f"{ticker}.csv"


def _rows_for_lean(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "date": str(row["trade_date"]),
            "open": str(row["open"]),
            "high": str(row["high"]),
            "low": str(row["low"]),
            "close": str(row["close"]),
            "volume": str(row["volume"]),
        }
        for row in rows
    ]


def _query_full_ashare_rows(symbol: str, *, source: str, adjust: str) -> list[dict[str, Any]]:
    symbol_key_value = normalize_symbol(symbol, "china")
    with db() as connection:
        rows = connection.execute(
            """
            select trade_date, open, high, low, close, volume, adj_factor, batch_id
            from market_daily_bars
            where symbol = ? and asset_class = 'equity' and market = 'china'
              and resolution = 'daily' and data_type = 'trade'
              and adjust = ? and source = ?
            order by trade_date asc
            """,
            (symbol_key_value, adjust or "raw", source),
        ).fetchall()
        if not rows:
            rows = connection.execute(
                """
                select trade_date, open, high, low, close, volume, adj_factor, batch_id
                from ashare_daily_bars
                where symbol = ? and adjust = ? and source = ?
                order by trade_date asc
                """,
                (symbol_key_value, adjust or "raw", source),
            ).fetchall()
    return rows_to_dicts(rows)


def _query_adjustment_rows(symbol: str, *, source: str) -> list[dict[str, Any]]:
    symbol_key_value = normalize_symbol(symbol, "china")
    with db() as connection:
        rows = connection.execute(
            """
            select trade_date, adj_factor
            from adjustment_factors
            where symbol = ? and source = ?
            order by trade_date asc
            """,
            (symbol_key_value, source),
        ).fetchall()
    return rows_to_dicts(rows)


def rebuild_ashare_lean_cache_from_db(
    symbol: str,
    *,
    source: str,
    adjust: str = "raw",
    market: str = "china",
    batch_id: str | None = None,
) -> dict[str, Any]:
    rows = _query_full_ashare_rows(symbol, source=source, adjust=adjust or "raw")
    if not rows:
        raise LeanPlatformError(f"No canonical A-share rows found for {symbol} source={source} adjust={adjust or 'raw'}.")
    metadata = write_lean_daily_zip(symbol, _rows_for_lean(rows), source, overwrite=True, market=market)
    factor_rows = _query_adjustment_rows(symbol, source=source) or rows
    factor_metadata = data_paths.write_equity_factor_file(symbol, factor_rows, market=market)
    zip_path = _lean_daily_path(symbol, market)
    factor_path = _lean_factor_path(symbol, market)
    map_path = _lean_map_path(symbol, market)
    ticker = symbol_key(normalize_symbol(symbol, market))
    first_map_date = str(rows[0]["trade_date"]).replace("-", "")
    map_path.write_text(f"{first_map_date},{ticker},P\n20501231,{ticker},P\n", encoding="utf-8")
    object_metadata = {
        "symbol": normalize_symbol(symbol, market),
        "source": source,
        "adjust": adjust or "raw",
        "batch_id": batch_id,
    }
    lean_object = _archive_data_file(zip_path, metadata=object_metadata, content_type="application/zip")
    factor_object = _archive_data_file(factor_path, metadata={**object_metadata, "kind": "factor"}, content_type="text/csv")
    map_object = _archive_data_file(map_path, metadata={**object_metadata, "kind": "map"}, content_type="text/csv")
    metadata.update(
        {
            "rows": len(rows),
            "first_date": str(rows[0]["trade_date"]),
            "last_date": str(rows[-1]["trade_date"]),
            "factor_file": factor_metadata,
            "map_file": str(map_path.relative_to(data_paths.REPO_ROOT)),
            "lean_object_id": lean_object.get("id"),
            "lean_object_sha256": lean_object.get("sha256"),
            "factor_object_id": factor_object.get("id"),
            "factor_object_sha256": factor_object.get("sha256"),
            "map_object_id": map_object.get("id"),
            "map_object_sha256": map_object.get("sha256"),
        }
    )
    return metadata


def _restore_or_verify(path: Path, *, namespace: str, key: str) -> dict[str, Any] | None:
    stored = latest_object(namespace, key)
    if not stored:
        return None
    current_sha = _file_sha256(path) if path.exists() else None
    if current_sha != stored.get("sha256"):
        restore_to_path(stored["id"], path)
        current_sha = _file_sha256(path)
    if current_sha != stored.get("sha256"):
        raise LeanPlatformError(f"LEAN cache restore failed hash check for {key}.")
    return {
        "object_id": stored.get("id"),
        "sha256": stored.get("sha256"),
        "path": str(path),
        "object_key": key,
        "restored": True,
    }


def ensure_ashare_lean_cache(
    symbol: str,
    *,
    source: str = "akshare",
    adjust: str = "raw",
    market: str = "china",
) -> dict[str, Any]:
    data_paths.ensure_equity_dirs(market)
    zip_path = _lean_daily_path(symbol, market)
    factor_path = _lean_factor_path(symbol, market)
    map_path = _lean_map_path(symbol, market)
    restored = {
        "daily": _restore_or_verify(zip_path, namespace=LEAN_DATA_NAMESPACE, key=_data_relative(zip_path)),
        "factor": _restore_or_verify(factor_path, namespace=LEAN_DATA_NAMESPACE, key=_data_relative(factor_path)),
        "map": _restore_or_verify(map_path, namespace=LEAN_DATA_NAMESPACE, key=_data_relative(map_path)),
    }
    if all(restored.values()):
        return {"symbol": normalize_symbol(symbol, market), "source": source, "adjust": adjust, "files": restored}
    rebuilt = rebuild_ashare_lean_cache_from_db(symbol, source=source, adjust=adjust, market=market)
    return {
        "symbol": normalize_symbol(symbol, market),
        "source": source,
        "adjust": adjust,
        "rebuilt": True,
        "files": {
            "daily": {
                "object_id": rebuilt.get("lean_object_id"),
                "sha256": rebuilt.get("lean_object_sha256"),
                "path": str(zip_path),
                "object_key": _data_relative(zip_path),
            },
            "factor": {
                "object_id": rebuilt.get("factor_object_id"),
                "sha256": rebuilt.get("factor_object_sha256"),
                "path": str(factor_path),
                "object_key": _data_relative(factor_path),
            },
            "map": {
                "object_id": rebuilt.get("map_object_id"),
                "sha256": rebuilt.get("map_object_sha256"),
                "path": str(map_path),
                "object_key": _data_relative(map_path),
            },
        },
    }
