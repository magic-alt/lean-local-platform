from __future__ import annotations

import hashlib
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any

from ..db import db, row_to_dict, rows_to_dicts
from ..lean_engine import data_paths
from ..lean_engine.data_writers import write_lean_daily_zip
from ..lean_engine.errors import LeanPlatformError
from ..lean_engine.providers import fetch_yahoo_rows
from ..lean_engine.symbols import parse_date
from ..lean_engine.symbols import normalize_symbol, symbol_key
from .db_object_store import put_file, restore_to_path


LEAN_DATA_NAMESPACE = "lean-data-files"
RESULTS_ANALYZER_REFERENCE_SYMBOL = "SPY"
RESULTS_ANALYZER_REFERENCE_MARKET = "usa"


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


def _daily_zip_coverage(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"passed": False, "firstDate": None, "lastDate": None, "rows": 0}
    try:
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not names:
                return {"passed": False, "firstDate": None, "lastDate": None, "rows": 0}
            lines = archive.read(names[0]).decode("utf-8", errors="replace").splitlines()
    except (OSError, ValueError, zipfile.BadZipFile):
        return {"passed": False, "firstDate": None, "lastDate": None, "rows": 0}
    dates = [line[:8] for line in lines if len(line) >= 8 and line[:8].isdigit()]
    if not dates:
        return {"passed": False, "firstDate": None, "lastDate": None, "rows": 0}
    return {
        "passed": True,
        "firstDate": f"{dates[0][:4]}-{dates[0][4:6]}-{dates[0][6:8]}",
        "lastDate": f"{dates[-1][:4]}-{dates[-1][4:6]}-{dates[-1][6:8]}",
        "rows": len(dates),
    }


def ensure_lean_interest_rate_reference_data() -> dict[str, Any]:
    """Install the minimal valid LEAN risk-free rate series when data is absent.

    LEAN expands sparse observations forward, so a dated seed value is sufficient
    for deterministic local statistics while avoiding a hidden default-rate error.
    """
    path = data_paths.DATA_DIR / "alternative" / "interest-rate" / "usa" / "interest-rate.csv"
    if path.exists():
        lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        if len(lines) >= 2:
            return {"path": str(path), "created": False, "rows": len(lines) - 1}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("date,interest-rate\n1998-01-01,1.0\n", encoding="utf-8")
    return {"path": str(path), "created": True, "rows": 1}


def ensure_lean_results_analyzer_reference_data(start: str, end: str) -> dict[str, Any]:
    """Ensure LEAN's built-in ResultsAnalyzer can load its hard-coded SPY history."""
    interest_rate = ensure_lean_interest_rate_reference_data()
    requested_start = parse_date(start) - timedelta(days=3)
    requested_end = parse_date(end)
    zip_path = _lean_daily_path(RESULTS_ANALYZER_REFERENCE_SYMBOL, RESULTS_ANALYZER_REFERENCE_MARKET)
    coverage = _daily_zip_coverage(zip_path)
    if (
        coverage["passed"]
        and coverage["firstDate"] <= requested_start.isoformat()
        and coverage["lastDate"] >= requested_end.isoformat()
    ):
        return {
            "symbol": RESULTS_ANALYZER_REFERENCE_SYMBOL,
            "market": RESULTS_ANALYZER_REFERENCE_MARKET,
            "source": "local-cache",
            "coverage": coverage,
            "refreshed": False,
            "interestRate": interest_rate,
        }

    fetch_start = min(requested_start, parse_date("1993-01-29"))
    fetch_end = requested_end + timedelta(days=2)
    try:
        rows = fetch_yahoo_rows(
            RESULTS_ANALYZER_REFERENCE_SYMBOL,
            start=fetch_start.isoformat(),
            end=fetch_end.isoformat(),
        )
    except Exception as exc:
        raise LeanPlatformError(
            "LEAN results analyzer reference data is missing or stale for SPY and refresh failed: "
            f"{exc}"
        ) from exc
    rows = [row for row in rows if parse_date(row["date"][:10]) <= requested_end]
    if not rows:
        raise LeanPlatformError("LEAN results analyzer SPY refresh returned no rows in the requested window.")

    metadata = write_lean_daily_zip(
        RESULTS_ANALYZER_REFERENCE_SYMBOL,
        rows,
        "yahoo",
        overwrite=True,
        market=RESULTS_ANALYZER_REFERENCE_MARKET,
    )
    ticker = symbol_key(
        normalize_symbol(RESULTS_ANALYZER_REFERENCE_SYMBOL, RESULTS_ANALYZER_REFERENCE_MARKET)
    )
    factor_path = _lean_factor_path(RESULTS_ANALYZER_REFERENCE_SYMBOL, RESULTS_ANALYZER_REFERENCE_MARKET)
    map_path = _lean_map_path(RESULTS_ANALYZER_REFERENCE_SYMBOL, RESULTS_ANALYZER_REFERENCE_MARKET)
    first_date = str(rows[0]["date"])[:10].replace("-", "")
    factor_path.write_text(
        f"{first_date},1,1,0\n20501231,1,1,0\n",
        encoding="utf-8",
    )
    map_path.write_text(
        f"{first_date},{ticker},P\n20501231,{ticker},P\n",
        encoding="utf-8",
    )
    refreshed_coverage = _daily_zip_coverage(zip_path)
    if (
        not refreshed_coverage["passed"]
        or refreshed_coverage["firstDate"] > requested_start.isoformat()
        or refreshed_coverage["lastDate"] < requested_end.isoformat()
    ):
        raise LeanPlatformError(
            "LEAN results analyzer SPY refresh did not cover the requested backtest window: "
            f"{refreshed_coverage}"
        )
    return {
        "symbol": RESULTS_ANALYZER_REFERENCE_SYMBOL,
        "market": RESULTS_ANALYZER_REFERENCE_MARKET,
        "source": "yahoo",
        "coverage": refreshed_coverage,
        "refreshed": True,
        "daily": metadata,
        "factorFile": str(factor_path),
        "mapFile": str(map_path),
        "interestRate": interest_rate,
    }


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
    factor_metadata = data_paths.write_equity_factor_file(
        symbol,
        factor_rows,
        market=market,
        price_rows=rows,
        require_reference_prices=True,
    )
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


def _latest_matching_object(
    namespace: str,
    key: str,
    *,
    symbol: str,
    source: str,
    adjust: str,
    kind: str | None,
    market: str,
) -> dict[str, Any] | None:
    normalized_symbol = normalize_symbol(symbol, market)
    with db() as connection:
        rows = connection.execute(
            """
            select *
            from stored_objects
            where namespace = ? and object_key = ?
            order by updated_at desc, id desc
            """,
            (namespace, key),
        ).fetchall()
    for row in rows:
        stored = row_to_dict(row) or {}
        metadata = stored.get("metadata") or {}
        stored_kind = metadata.get("kind")
        if kind is None and stored_kind not in (None, "", "daily"):
            continue
        if kind is not None and stored_kind != kind:
            continue
        if metadata.get("symbol") != normalized_symbol:
            continue
        if metadata.get("source") != source:
            continue
        if (metadata.get("adjust") or "raw") != (adjust or "raw"):
            continue
        return stored
    return None


def _restore_or_verify(
    path: Path,
    *,
    namespace: str,
    key: str,
    symbol: str,
    source: str,
    adjust: str,
    market: str,
    kind: str | None = None,
) -> dict[str, Any] | None:
    stored = _latest_matching_object(
        namespace,
        key,
        symbol=symbol,
        source=source,
        adjust=adjust,
        market=market,
        kind=kind,
    )
    if not stored:
        return None
    current_sha = _file_sha256(path) if path.exists() else None
    restored = current_sha != stored.get("sha256")
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
        "restored": restored,
        "metadata": stored.get("metadata") or {},
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
        "daily": _restore_or_verify(
            zip_path,
            namespace=LEAN_DATA_NAMESPACE,
            key=_data_relative(zip_path),
            symbol=symbol,
            source=source,
            adjust=adjust or "raw",
            market=market,
        ),
        "factor": _restore_or_verify(
            factor_path,
            namespace=LEAN_DATA_NAMESPACE,
            key=_data_relative(factor_path),
            symbol=symbol,
            source=source,
            adjust=adjust or "raw",
            market=market,
            kind="factor",
        ),
        "map": _restore_or_verify(
            map_path,
            namespace=LEAN_DATA_NAMESPACE,
            key=_data_relative(map_path),
            symbol=symbol,
            source=source,
            adjust=adjust or "raw",
            market=market,
            kind="map",
        ),
    }
    factor_validation = data_paths.validate_equity_factor_file(factor_path)
    if all(restored.values()) and factor_validation["passed"]:
        return {
            "symbol": normalize_symbol(symbol, market),
            "source": source,
            "adjust": adjust,
            "files": restored,
            "factorValidation": factor_validation,
        }
    rebuilt = rebuild_ashare_lean_cache_from_db(symbol, source=source, adjust=adjust, market=market)
    return {
        "symbol": normalize_symbol(symbol, market),
        "source": source,
        "adjust": adjust,
        "rebuilt": True,
        "rebuildReason": None if factor_validation["passed"] else {
            "factorValidation": factor_validation,
        },
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
