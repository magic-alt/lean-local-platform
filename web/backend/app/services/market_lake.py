from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import threading
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from ..core.config import MARKET_DATA_DIR as PARQUET_DIR, PARQUET_COMPRESSION

try:  # pragma: no cover - dependencies are mandatory in the runtime image.
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None

try:  # pragma: no cover
    import polars as pl
except Exception:  # pragma: no cover
    pl = None

try:  # pragma: no cover - fcntl is available on the supported Linux/macOS hosts.
    import fcntl
except Exception:  # pragma: no cover
    fcntl = None


MANIFEST_NAME = "_active_manifest.json"
MANIFEST_SCHEMA_VERSION = 2
KINDS = {"bars", "trade_status", "adjustment_factor", "daily_basic"}
PARTITION_FILE_NAME = "p.parquet"
_TUSHARE_SYMBOL_PARTITION = re.compile(r"^(?P<symbol>\d{6})\.(?P<venue>SH|SZ|BJ|HK)$", re.IGNORECASE)

BAR_COLUMNS = (
    "instrument_id", "symbol", "asset_class", "market", "venue", "trade_date",
    "timestamp", "resolution", "data_type", "open", "high", "low", "close",
    "settle", "volume", "amount", "turnover_rate", "open_interest", "prev_close",
    "pct_change", "adjust", "adj_factor", "source", "batch_id", "created_at",
)
BAR_KEY = ("instrument_id", "trade_date", "timestamp", "resolution", "data_type", "adjust", "source")
STATUS_COLUMNS = (
    "instrument_id", "symbol", "asset_class", "market", "venue", "trade_date",
    "is_tradeable", "is_suspended", "can_buy", "can_sell", "limit_up", "limit_down",
    "is_limit_up", "is_limit_down", "is_one_word_limit_up", "is_one_word_limit_down",
    "is_st", "status", "reason", "source", "batch_id", "updated_at",
)
STATUS_KEY = ("instrument_id", "trade_date", "source")
ADJUSTMENT_COLUMNS = ("symbol", "trade_date", "adj_factor", "source", "batch_id")
ADJUSTMENT_KEY = ("symbol", "trade_date", "source")
DAILY_BASIC_COLUMNS = (
    "symbol", "trade_date", "turnover_rate", "turnover_rate_float", "volume_ratio",
    "pe", "pe_ttm", "pb", "ps", "ps_ttm", "dividend_yield", "dividend_yield_ttm",
    "total_share_shares", "float_share_shares", "free_share_shares", "total_mv_cny",
    "circ_mv_cny", "source", "batch_id", "created_at",
)
DAILY_BASIC_KEY = ("symbol", "trade_date", "source")

DUCKDB_MEMORY_LIMIT = os.environ.get("LEAN_DUCKDB_MEMORY_LIMIT", "256MB").strip() or "256MB"
DUCKDB_THREADS = max(1, int(os.environ.get("LEAN_DUCKDB_THREADS", "2")))
DUCKDB_QUERY_CONCURRENCY = max(1, int(os.environ.get("LEAN_DUCKDB_QUERY_CONCURRENCY", "1")))
_DUCKDB_QUERY_SLOTS = threading.BoundedSemaphore(DUCKDB_QUERY_CONCURRENCY)


def _require_engine() -> None:
    if duckdb is None or pl is None:
        raise RuntimeError("duckdb and polars are required for the Parquet market lake")


def _clean(value: str | None, default: str) -> str:
    return (value or default).strip().lower() or default


def _filesystem_segment(value: str) -> str:
    normalized = (value or "").strip().lower() or "unknown"
    for char in (":", "/", chr(92), "*", "?", '"', "<", ">", "|"):
        normalized = normalized.replace(char, "_")
    if len(normalized) > 10:
        digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:6]
        normalized = f"{normalized[:1]}_{digest}"
    return normalized
def _scope(
    *,
    kind: str,
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = "tushare",
) -> dict[str, str]:
    kind = _clean(kind, "bars")
    if kind not in KINDS:
        raise ValueError(f"unsupported market lake kind: {kind}")
    market = _clean(market, "china")
    return {
        "kind": kind,
        "asset_class": _clean(asset_class, "equity"),
        "market": market,
        "venue": _clean(venue, market),
        "resolution": _clean(resolution, "daily"),
        "data_type": _clean(data_type, "trade"),
        "adjust": _clean(adjust, "raw"),
        "source": _clean(source, "tushare"),
    }


def dataset_key(**scope: str) -> str:
    prefix = "" if scope["kind"] == "bars" else f"kind={scope['kind']}/"
    return prefix + "/".join(
        (
            f"asset_class={scope['asset_class']}",
            f"market={scope['market']}",
            f"venue={scope['venue']}",
            f"resolution={scope['resolution']}",
            f"data_type={scope['data_type']}",
            f"adjust={scope['adjust']}",
            f"source={scope['source']}",
        )
    )


def dataset_root(**scope: str) -> Path:
    safe_scope = dict(scope)
    safe_scope["source"] = _filesystem_segment(scope["source"])
    return PARQUET_DIR / dataset_key(**safe_scope)


def _native_glob(scope: dict[str, str]) -> str | None:
    """Return the established qlib-platform lake relation for a logical kind."""
    if scope["resolution"] != "daily" or scope["market"] != "china":
        return None
    if scope["kind"] == "bars" and scope["asset_class"] == "equity" and scope["source"] == "tushare":
        return str(PARQUET_DIR / "silver" / "daily" / "current" / "trade_date=*" / "data.parquet")
    if scope["kind"] == "bars" and scope["asset_class"] == "index" and scope["source"] == "tushare":
        return str(PARQUET_DIR / "gold" / "qlib_staging" / "full" / "SH000300.parquet")
    if scope["kind"] == "adjustment_factor" and scope["source"] == "tushare":
        return str(PARQUET_DIR / "bronze" / "tushare" / "current" / "adj_factor" / "trade_date=*" / "data.parquet")
    if scope["kind"] == "daily_basic" and scope["source"] == "tushare:daily_basic":
        return str(PARQUET_DIR / "bronze" / "tushare" / "current" / "daily_basic" / "trade_date=*" / "data.parquet")
    if scope["kind"] == "trade_status" and scope["source"].startswith("tushare:"):
        return str(PARQUET_DIR / "silver" / "daily" / "current" / "trade_date=*" / "data.parquet")
    return None


def _native_files(scope: dict[str, str]) -> list[Path]:
    pattern = _native_glob(scope)
    if not pattern:
        return []
    if "*" not in pattern:
        path = Path(pattern)
        return [path] if path.is_file() else []
    root = Path(pattern.split("trade_date=*", 1)[0])
    return sorted(root.glob("trade_date=*/data.parquet")) if root.is_dir() else []


def _native_available(scope: dict[str, str]) -> bool:
    pattern = _native_glob(scope)
    if not pattern:
        return False
    if "*" not in pattern:
        return Path(pattern).is_file()
    return Path(pattern.split("trade_date=*", 1)[0]).is_dir()


def native_partition_summary(**raw_scope: str) -> dict[str, Any]:
    """Return cheap filesystem coverage without opening Parquet row groups."""
    scope = _scope(**raw_scope)
    pattern = _native_glob(scope)
    if not pattern:
        return {"available": False, "partitionCount": 0, "firstDate": None, "lastDate": None}
    if "trade_date=*" not in pattern:
        path = Path(pattern)
        return {
            "available": path.is_file(),
            "partitionCount": int(path.is_file()),
            "firstDate": None,
            "lastDate": None,
        }
    root = Path(pattern.split("trade_date=*", 1)[0])
    first_date: str | None = None
    last_date: str | None = None
    count = 0
    if root.is_dir():
        with os.scandir(root) as entries:
            for entry in entries:
                if not entry.is_dir() or not entry.name.startswith("trade_date="):
                    continue
                value = entry.name.split("=", 1)[1]
                if len(value) < 8 or not value[:8].isdigit():
                    continue
                normalized = f"{value[:4]}-{value[4:6]}-{value[6:8]}"
                first_date = normalized if first_date is None or normalized < first_date else first_date
                last_date = normalized if last_date is None or normalized > last_date else last_date
                count += 1
    return {
        "available": count > 0,
        "partitionCount": count,
        "firstDate": first_date,
        "lastDate": last_date,
    }


def _native_write_supported(scope: dict[str, str]) -> bool:
    """Limit writes to lake layers owned by lean-platform.

    In particular, ``gold/qlib_staging`` and ``qlib/`` are read-only inputs.
    They may be consumed for benchmark data, but this repository must never
    publish into or mutate Qlib-owned materializations.
    """
    if scope["resolution"] != "daily" or scope["market"] != "china":
        return False
    if scope["kind"] == "bars":
        return scope["asset_class"] == "equity" and scope["source"] == "tushare"
    if scope["kind"] == "adjustment_factor":
        return scope["source"] == "tushare"
    if scope["kind"] == "daily_basic":
        return scope["source"] == "tushare:daily_basic"
    if scope["kind"] == "trade_status":
        return scope["asset_class"] == "equity" and scope["source"].startswith("tushare:")
    return False


def _native_relation(
    scope: dict[str, str],
    pattern: str,
    *,
    files: Sequence[Path] = (),
) -> str:
    escaped_path = pattern.replace("'", "''")
    source = scope["source"].replace("'", "''")
    raw = (
        f"read_parquet([{_sql_paths(files)}], union_by_name=true, hive_partitioning=false)"
        if files
        else f"read_parquet('{escaped_path}', union_by_name=true, hive_partitioning=false)"
    )
    staging_index = scope["kind"] == "bars" and scope["asset_class"] == "index"
    raw_symbol = "symbol" if staging_index else "ts_code"
    raw_date = "date" if staging_index else "trade_date"
    symbol = f"regexp_replace(upper({raw_symbol}), '(^SH|^SZ|^BJ|[.]SH$|[.]SZ$|[.]BJ$)', '', 'g')"
    trade_date = f"case when length(cast({raw_date} as varchar))=8 then substr(cast({raw_date} as varchar),1,4)||'-'||substr(cast({raw_date} as varchar),5,2)||'-'||substr(cast({raw_date} as varchar),7,2) else substr(cast({raw_date} as varchar),1,10) end"
    if scope["kind"] == "bars":
        fields = {
            "instrument_id": f"'{scope['asset_class']}:china:china:'||{symbol}", "symbol": symbol,
            "asset_class": f"'{scope['asset_class']}'", "market": "'china'", "venue": "'china'",
            "trade_date": trade_date, "timestamp": "NULL", "resolution": "'daily'",
            "data_type": "'trade'", "open": "open", "high": "high", "low": "low",
            "close": "close", "settle": "NULL", "volume": "volume" if staging_index else "vol", "amount": "money" if staging_index else "amount",
            "turnover_rate": "turnover_rate", "open_interest": "NULL", "prev_close": "NULL" if staging_index else "pre_close",
            "pct_change": "change" if staging_index else "pct_chg", "adjust": "'raw'", "adj_factor": "factor" if staging_index else "adj_factor",
            "source": f"'{source}'", "batch_id": "NULL", "created_at": "NULL",
        }
        columns = BAR_COLUMNS
    elif scope["kind"] == "adjustment_factor":
        fields = {"symbol": symbol, "trade_date": trade_date, "adj_factor": "adj_factor", "source": f"'{source}'", "batch_id": "NULL"}
        columns = ADJUSTMENT_COLUMNS
    elif scope["kind"] == "daily_basic":
        fields = {
            "symbol": symbol, "trade_date": trade_date, "turnover_rate": "turnover_rate",
            "turnover_rate_float": "turnover_rate_f", "volume_ratio": "volume_ratio", "pe": "pe",
            "pe_ttm": "pe_ttm", "pb": "pb", "ps": "ps", "ps_ttm": "ps_ttm",
            "dividend_yield": "dv_ratio", "dividend_yield_ttm": "dv_ttm",
            "total_share_shares": "total_share", "float_share_shares": "float_share",
            "free_share_shares": "free_share", "total_mv_cny": "total_mv", "circ_mv_cny": "circ_mv",
            "source": f"'{source}'", "batch_id": "NULL", "created_at": "NULL",
        }
        columns = DAILY_BASIC_COLUMNS
    else:
        suspended = "coalesce(known_suspended,paused,0)"
        fields = {
            "instrument_id": f"'equity:china:china:'||{symbol}", "symbol": symbol,
            "asset_class": "'equity'", "market": "'china'", "venue": "'china'",
            "trade_date": trade_date, "is_tradeable": f"case when {suspended}=0 then 1 else 0 end",
            "is_suspended": suspended, "can_buy": f"case when {suspended}=0 then 1 else 0 end",
            "can_sell": f"case when {suspended}=0 then 1 else 0 end", "limit_up": "up_limit",
            "limit_down": "down_limit", "is_limit_up": "0", "is_limit_down": "0",
            "is_one_word_limit_up": "0", "is_one_word_limit_down": "0", "is_st": "coalesce(is_st,0)",
            "status": "NULL", "reason": "NULL", "source": f"'{source}'", "batch_id": "NULL", "updated_at": "NULL",
        }
        columns = STATUS_COLUMNS
    return "(select " + ",".join(f"{fields[column]} as {column}" for column in columns) + f" from {raw})"


@contextmanager
def _duckdb_connection() -> Iterator[Any]:
    """Open one bounded DuckDB connection suitable for the 2 GiB API container."""
    _require_engine()
    temp_root = Path(tempfile.gettempdir()) / "lean-platform-duckdb"
    temp_root.mkdir(parents=True, exist_ok=True)
    with _DUCKDB_QUERY_SLOTS:
        connection = duckdb.connect(database=":memory:")
        try:
            connection.execute("set memory_limit=?", [DUCKDB_MEMORY_LIMIT])
            connection.execute("set threads=?", [DUCKDB_THREADS])
            connection.execute("set temp_directory=?", [str(temp_root)])
            yield connection
        finally:
            connection.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(PARQUET_DIR.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _temp_parquet_path(target: Path) -> Path:
    """Return a short temporary parquet path to avoid Windows MAX_PATH regressions."""
    return target.with_name(f"{target.stem}.tmp")


def _temp_manifest_path(target: Path) -> Path:
    """Return a short temporary manifest path to avoid Windows MAX_PATH regressions."""
    return target.with_name(f"{target.stem}.tmp")


def _visible(path: str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else PARQUET_DIR / value


def _manifest_path(root: Path) -> Path:
    return root / MANIFEST_NAME


def _legacy_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.glob("year=*/*.parquet")
        if path.is_file() and "/release=" not in path.as_posix()
    )


def load_manifest(**scope: str) -> dict[str, Any]:
    root = dataset_root(**scope)
    path = _manifest_path(root)
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if int(payload.get("schemaVersion") or 0) != MANIFEST_SCHEMA_VERSION:
            raise RuntimeError(f"unsupported market manifest schema: {path}")
        return payload
    files = _legacy_files(root)
    return {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "datasetKey": dataset_key(**scope),
        "datasetVersion": None,
        "kind": scope["kind"],
        "files": [
            {"path": _relative(file), "year": int(file.parent.name.split("=", 1)[1])}
            for file in files
        ],
    }


def active_files(**scope: str) -> list[Path]:
    manifest = load_manifest(**scope)
    files = [_visible(str(item["path"])) for item in manifest.get("files") or []]
    missing = [str(path) for path in files if not path.is_file()]
    if missing:
        raise RuntimeError(f"market_lake_manifest_files_missing:{missing[:10]}")
    return files or _native_files(scope)


def adopt_legacy_files(**scope: str) -> dict[str, Any]:
    """Publish an immutable manifest for an existing year-partitioned lake."""
    _require_engine()
    normalized = _scope(**scope)
    native = _native_files(normalized)
    if native:
        entries: list[dict[str, Any]] = []
        for path in native:
            scan = pl.scan_parquet(path)
            partition_name = path.parent.name
            if partition_name.startswith("trade_date="):
                frame = scan.select(pl.len().alias("rows")).collect()
                compact_date = partition_name.split("=", 1)[1]
                date_start = date_end = _iso_date(compact_date)
            else:
                schema = scan.collect_schema()
                date_column = "trade_date" if "trade_date" in schema else "date"
                frame = scan.select(
                    pl.len().alias("rows"),
                    pl.col(date_column).min().alias("first"),
                    pl.col(date_column).max().alias("last"),
                ).collect()
                date_start = _iso_date(frame.item(0, "first"))
                date_end = _iso_date(frame.item(0, "last"))
            entries.append({
                "path": _relative(path), "year": int(date_start[:4]),
                "rowCount": int(frame.item(0, "rows")), "firstTimestamp": date_start,
                "lastTimestamp": date_end, "sha256": _sha256(path), "size": path.stat().st_size,
            })
        digest = hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return {
            "schemaVersion": MANIFEST_SCHEMA_VERSION, "datasetKey": dataset_key(**normalized),
            "datasetVersion": f"{normalized['source']}-{digest[:24]}", "kind": normalized["kind"],
            "scope": normalized, "manifestSha256": digest, "files": entries,
            "nativeLayout": True,
        }
    root = dataset_root(**normalized)
    current = load_manifest(**normalized)
    if current.get("manifestSha256"):
        return current
    files = _legacy_files(root)
    entries: list[dict[str, Any]] = []
    for path in files:
        frame = pl.scan_parquet(path).select(
            pl.len().alias("rows"),
            pl.col("trade_date").min().alias("first"),
            pl.col("trade_date").max().alias("last"),
        ).collect()
        entries.append(
            {
                "path": _relative(path),
                "year": int(path.parent.name.split("=", 1)[1]),
                "rowCount": int(frame.item(0, "rows")),
                "firstTimestamp": str(frame.item(0, "first")),
                "lastTimestamp": str(frame.item(0, "last")),
                "sha256": _sha256(path),
                "size": path.stat().st_size,
            }
        )
    digest = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    payload = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "datasetKey": dataset_key(**normalized),
        "datasetVersion": f"{normalized['source']}-{digest[:24]}",
        "kind": normalized["kind"],
        "scope": normalized,
        "manifestSha256": digest,
        "files": entries,
    }
    if entries:
        with _write_lock(root):
            _write_manifest(root, payload)
    return payload


def available(**scope: str) -> bool:
    return bool(active_files(**scope))


def _sql_paths(files: Sequence[Path]) -> str:
    return ",".join("'" + str(path).replace("'", "''") + "'" for path in files)


def query_rows(
    *,
    kind: str = "bars",
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = "tushare",
    columns: str = "*",
    predicates: Sequence[str] = (),
    parameters: Sequence[Any] = (),
    group_by: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    recent_partitions: int | None = None,
) -> list[dict[str, Any]]:
    _require_engine()
    scope = _scope(
        kind=kind, asset_class=asset_class, market=market, venue=venue,
        resolution=resolution, data_type=data_type, adjust=adjust, source=source,
    )
    root = dataset_root(**scope)
    custom_files = [_visible(str(item["path"])) for item in load_manifest(**scope).get("files") or []]
    native_pattern = _native_glob(scope) if not custom_files else None
    if native_pattern and scope["kind"] == "bars" and scope["asset_class"] == "index":
        exact_symbol = next(
            (
                str(value).strip().upper()
                for predicate, value in zip(predicates, parameters, strict=False)
                if predicate.replace(" ", "").lower() == "symbol=?"
            ),
            "",
        )
        if exact_symbol:
            code = exact_symbol.split(".", 1)[0]
            prefix = "SZ" if code.startswith("399") else "SH"
            candidate = PARQUET_DIR / "gold" / "qlib_staging" / "full" / f"{prefix}{code}.parquet"
            native_pattern = str(candidate)
    native_exists = bool(
        native_pattern
        and (
            (Path(native_pattern).is_file() if "*" not in native_pattern else Path(native_pattern.split("trade_date=*", 1)[0]).is_dir())
        )
    )
    files = custom_files
    if not files and not native_exists:
        return []
    where = f" where {' and '.join(predicates)}" if predicates else ""
    grouping = f" group by {group_by}" if group_by else ""
    ordering = f" order by {order_by}" if order_by else ""
    bounded = f" limit {max(1, int(limit))}" if limit is not None else ""
    skipped = f" offset {max(0, int(offset))}" if offset else ""
    selected_native_files: list[Path] = []
    if native_pattern and recent_partitions and "*" in native_pattern:
        selected_native_files = _native_files(scope)[-max(1, int(recent_partitions)) :]
    relation = (
        _native_relation(scope, native_pattern, files=selected_native_files)
        if native_pattern
        # These files already contain canonical scope columns. Disable DuckDB's
        # automatic Hive parsing so filesystem-safe partition segments do not
        # overwrite values such as the original provider/source identifier.
        else f"read_parquet([{_sql_paths(files)}], union_by_name=true, hive_partitioning=false)"
    )
    sql = f"select {columns} from {relation}{where}{grouping}{ordering}{bounded}{skipped}"
    with _duckdb_connection() as connection:
        cursor = connection.execute(sql, list(parameters))
        names = [item[0] for item in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def aggregate(
    *,
    kind: str = "bars",
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = "tushare",
    columns: str = "count(*) as row_count",
    predicates: Sequence[str] = (),
    parameters: Sequence[Any] = (),
) -> dict[str, Any]:
    rows = query_rows(
        kind=kind, asset_class=asset_class, market=market, venue=venue,
        resolution=resolution, data_type=data_type, adjust=adjust, source=source,
        columns=columns, predicates=predicates, parameters=parameters, limit=None,
    )
    return rows[0] if rows else {}


def _scope_from_dataset_root(*, prefix: Path, source_dir: Path, kind: str) -> dict[str, str] | None:
    parts = {}
    for item in source_dir.relative_to(prefix).parts:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        parts[key] = value
    manifest = source_dir / MANIFEST_NAME
    if manifest.is_file():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            scope = payload.get("scope")
            if isinstance(scope, dict):
                return _scope(
                    kind=scope.get("kind", kind),
                    asset_class=str(scope.get("asset_class", "equity")),
                    market=str(scope.get("market", "china")),
                    venue=str(scope.get("venue", "china")),
                    resolution=str(scope.get("resolution", "daily")),
                    data_type=str(scope.get("data_type", "trade")),
                    adjust=str(scope.get("adjust", "raw")),
                    source=str(scope.get("source", "tushare")),
                )
        except (OSError, json.JSONDecodeError):
            pass
    if "kind" not in parts:
        parts["kind"] = kind
    try:
        return _scope(**parts)
    except (KeyError, TypeError):
        return None


def all_scopes(*, kind: str = "bars") -> list[dict[str, str]]:
    prefix = PARQUET_DIR if kind == "bars" else PARQUET_DIR / f"kind={kind}"
    result = []
    if prefix.exists():
        for source_dir in prefix.glob("asset_class=*/market=*/venue=*/resolution=*/data_type=*/adjust=*/source=*"):
            scope = _scope_from_dataset_root(prefix=prefix, source_dir=source_dir, kind=kind)
            if scope is not None:
                result.append(scope)
    native_candidates = {
        "bars": [_scope(kind="bars", source="tushare"), _scope(kind="bars", asset_class="index", source="tushare")],
        "adjustment_factor": [_scope(kind="adjustment_factor", data_type="factor", source="tushare")],
        "daily_basic": [_scope(kind="daily_basic", data_type="metric", source="tushare:daily_basic")],
        "trade_status": [
            _scope(kind="trade_status", data_type="status", source=source)
            for source in ("tushare:stk_limit", "tushare:suspend_d", "tushare:ohlcv_inferred")
        ],
    }.get(kind, [])
    known = {dataset_key(**item) for item in result}
    for candidate in native_candidates:
        if dataset_key(**candidate) not in known and _native_available(candidate):
            result.append(candidate)
    return sorted(result, key=lambda item: dataset_key(**item))


def matching_scopes(
    *,
    kind: str = "bars",
    asset_class: str | None = None,
    market: str | None = None,
    venue: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
    adjust: str | None = None,
    source: str | None = None,
) -> list[dict[str, str]]:
    filters = {
        "asset_class": asset_class, "market": market, "venue": venue,
        "resolution": resolution, "data_type": data_type, "adjust": adjust, "source": source,
    }
    return [
        scope for scope in all_scopes(kind=kind)
        if all(value is None or scope[key] == str(value).strip().lower() for key, value in filters.items())
    ]


def query_matching(
    *,
    kind: str = "bars",
    asset_class: str | None = None,
    market: str | None = None,
    venue: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
    adjust: str | None = None,
    source: str | None = None,
    columns: str = "*",
    predicates: Sequence[str] = (),
    parameters: Sequence[Any] = (),
    order_by: str | None = None,
    limit: int | None = None,
    offset: int = 0,
    recent_partitions: int | None = None,
) -> list[dict[str, Any]]:
    bounded_offset = max(0, int(offset))
    bounded_limit = max(1, int(limit)) if limit is not None else None
    # Apply a bound inside DuckDB for every scope.  The old implementation
    # collected every matching Parquet row in Python before slicing, which can
    # exhaust the API process for wide, long-lived datasets such as
    # ``daily_basic``.
    per_scope_limit = bounded_offset + bounded_limit if bounded_limit is not None else None
    result: list[dict[str, Any]] = []
    for scope in matching_scopes(
        kind=kind, asset_class=asset_class, market=market, venue=venue,
        resolution=resolution, data_type=data_type, adjust=adjust, source=source,
    ):
        result.extend(
            query_rows(
                **scope, columns=columns, predicates=predicates, parameters=parameters,
                order_by=order_by, limit=per_scope_limit, recent_partitions=recent_partitions,
            )
        )
    if order_by:
        # Cross-scope ordering is uncommon and bounded. Use DuckDB for complex
        # ordering at call sites; this covers the date/source order used by APIs.
        terms = [term.strip().split() for term in order_by.split(",")]
        for term in reversed(terms):
            column = term[0]
            reverse = len(term) > 1 and term[1].lower() == "desc"
            result.sort(key=lambda item: (item.get(column) is None, item.get(column)), reverse=reverse)
    if bounded_limit is None:
        return result
    return result[bounded_offset : bounded_offset + bounded_limit]


def count_matching(
    *,
    kind: str = "bars",
    asset_class: str | None = None,
    market: str | None = None,
    venue: str | None = None,
    resolution: str | None = None,
    data_type: str | None = None,
    adjust: str | None = None,
    source: str | None = None,
    predicates: Sequence[str] = (),
    parameters: Sequence[Any] = (),
) -> int:
    """Count matching rows in DuckDB without materialising the result set."""
    return sum(
        int(
            aggregate(
                **scope,
                columns="count(*) as row_count",
                predicates=predicates,
                parameters=parameters,
            ).get("row_count")
            or 0
        )
        for scope in matching_scopes(
            kind=kind, asset_class=asset_class, market=market, venue=venue,
            resolution=resolution, data_type=data_type, adjust=adjust, source=source,
        )
    )


def query_daily_basic_preview(
    *,
    factor_names: Sequence[str],
    predicates: Sequence[str] = (),
    parameters: Sequence[Any] = (),
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], bool]:
    """Page daily-basic factors in DuckDB instead of expanding the full lake.

    The native daily dataset is a wide table.  This query performs the
    unpivot, filtering, counting, and pagination in DuckDB, so a preview never
    transfers the complete history (potentially millions of wide rows) to the
    API process.
    """
    _require_engine()
    fields = [name for name in factor_names if name in DAILY_BASIC_COLUMNS]
    if not fields:
        return [], False
    scopes = matching_scopes(
        kind="daily_basic", asset_class="equity", market="china", resolution="daily",
        data_type="metric", adjust="raw", source="tushare:daily_basic",
    )
    relations: list[str] = []
    requested_rows = max(1, int(offset)) + max(1, int(limit)) + 1
    exact_symbol = any(predicate.replace(" ", "").lower() == "symbol=?" for predicate in predicates)
    for scope in scopes:
        custom_files = [_visible(str(item["path"])) for item in load_manifest(**scope).get("files") or []]
        native_pattern = _native_glob(scope) if not custom_files else None
        native_exists = bool(
            native_pattern
            and (
                Path(native_pattern).is_file()
                if "*" not in native_pattern
                else Path(native_pattern.split("trade_date=*", 1)[0]).is_dir()
            )
        )
        selected_native_files: list[Path] = []
        if native_pattern and native_exists and "*" in native_pattern:
            native_files = _native_files(scope)
            if not exact_symbol:
                partition_limit = max(1, requested_rows // max(1, len(fields) * 4000) + 1)
                selected_native_files = native_files[-min(len(native_files), partition_limit) :]
        if custom_files or native_exists:
            relations.append(
                _native_relation(scope, native_pattern, files=selected_native_files)
                if native_pattern
                else f"read_parquet([{_sql_paths(custom_files)}], union_by_name=true)"
            )
    if not relations:
        return [], False
    source_relation = " union all ".join(f"select * from {relation}" for relation in relations)
    fields_sql = ",".join(fields)
    unpivoted = (
        "(unpivot (select * from ("
        + source_relation
        + f") as daily_basic_source) on {fields_sql} into name factor_name value factor_value)"
    )
    where_parts = ["factor_value is not null", *predicates]
    where = " where " + " and ".join(where_parts)
    with _duckdb_connection() as connection:
        cursor = connection.execute(
            "select symbol,trade_date,factor_name,factor_value as value,source "
            f"from {unpivoted}{where} "
            "order by trade_date desc,symbol,factor_name limit ? offset ?",
            [*parameters, max(1, int(limit)) + 1, max(0, int(offset))],
        )
        names = [item[0] for item in cursor.description]
        rows = [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
        return rows[: max(1, int(limit))], len(rows) > max(1, int(limit))


def _iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    raise ValueError(f"invalid market date: {value!r}")


def _kind_definition(kind: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return {
        "bars": (BAR_COLUMNS, BAR_KEY),
        "trade_status": (STATUS_COLUMNS, STATUS_KEY),
        "adjustment_factor": (ADJUSTMENT_COLUMNS, ADJUSTMENT_KEY),
        "daily_basic": (DAILY_BASIC_COLUMNS, DAILY_BASIC_KEY),
    }[kind]


def _normalise_rows(rows: Iterable[dict[str, Any]], scope: dict[str, str]) -> list[dict[str, Any]]:
    columns, _ = _kind_definition(scope["kind"])
    now = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    result: list[dict[str, Any]] = []
    for raw in rows:
        item = {column: raw.get(column) for column in columns}
        item["symbol"] = str(raw.get("symbol") or raw.get("code") or raw.get("ts_code") or "").split(".", 1)[0].upper()
        if not item["symbol"]:
            raise ValueError("symbol is required for market lake rows")
        item["trade_date"] = _iso_date(raw.get("trade_date") or raw.get("tradeDate") or raw.get("date") or raw.get("timestamp"))
        if scope["kind"] in {"bars", "trade_status"}:
            item["asset_class"] = scope["asset_class"]
            item["market"] = scope["market"]
            item["venue"] = scope["venue"]
            item["instrument_id"] = raw.get("instrument_id") or f"{scope['asset_class']}:{scope['market']}:{scope['venue']}:{item['symbol']}"
        if scope["kind"] == "bars":
            item["timestamp"] = raw.get("timestamp")
            item["resolution"] = scope["resolution"]
            item["data_type"] = scope["data_type"]
            item["adjust"] = scope["adjust"]
            item["source"] = scope["source"]
            item["created_at"] = raw.get("created_at") or now
        elif scope["kind"] == "trade_status":
            item["source"] = str(raw.get("source") or scope["source"])
            item["updated_at"] = raw.get("updated_at") or now
            for column, default in (
                ("is_tradeable", 1), ("is_suspended", 0), ("can_buy", 1),
                ("can_sell", 1), ("is_limit_up", 0), ("is_limit_down", 0),
                ("is_one_word_limit_up", 0), ("is_one_word_limit_down", 0), ("is_st", 0),
            ):
                item[column] = int(bool(raw.get(column, default)))
        else:
            item["source"] = str(raw.get("source") or scope["source"])
            if scope["kind"] == "daily_basic":
                item["created_at"] = raw.get("created_at") or now
        result.append(item)
    return result


def _ts_code(symbol: str) -> str:
    suffix = "SH" if symbol.startswith(("5", "6", "9")) else "BJ" if symbol.startswith(("4", "8")) else "SZ"
    return f"{symbol}.{suffix}"


def _native_target(scope: dict[str, str], trade_date: str) -> Path:
    compact = trade_date.replace("-", "")
    if scope["kind"] == "adjustment_factor":
        base = PARQUET_DIR / "bronze" / "tushare" / "current" / "adj_factor"
    elif scope["kind"] == "daily_basic":
        base = PARQUET_DIR / "bronze" / "tushare" / "current" / "daily_basic"
    else:
        base = PARQUET_DIR / "silver" / "daily" / "current"
    return base / f"trade_date={compact}" / "data.parquet"


def _native_patch(item: dict[str, Any], scope: dict[str, str]) -> dict[str, Any]:
    patch: dict[str, Any] = {"ts_code": _ts_code(str(item["symbol"])), "trade_date": str(item["trade_date"]).replace("-", "")}
    if scope["kind"] == "bars":
        aliases = {"prev_close": "pre_close", "pct_change": "pct_chg", "volume": "vol"}
        for name in ("open", "high", "low", "close", "prev_close", "pct_change", "volume", "amount", "adj_factor", "turnover_rate"):
            if item.get(name) is not None:
                patch[aliases.get(name, name)] = item[name]
    elif scope["kind"] == "adjustment_factor":
        patch["adj_factor"] = item.get("adj_factor")
    elif scope["kind"] == "daily_basic":
        aliases = {
            "turnover_rate_float": "turnover_rate_f", "dividend_yield": "dv_ratio",
            "dividend_yield_ttm": "dv_ttm", "total_share_shares": "total_share",
            "float_share_shares": "float_share", "free_share_shares": "free_share",
            "total_mv_cny": "total_mv", "circ_mv_cny": "circ_mv",
        }
        for name in DAILY_BASIC_COLUMNS[2:-3]:
            if item.get(name) is not None:
                patch[aliases.get(name, name)] = item[name]
    else:
        if item.get("is_suspended") is not None:
            patch.update({"known_suspended": float(bool(item["is_suspended"])), "paused": float(bool(item["is_suspended"]))})
        if item.get("is_st") is not None:
            patch["is_st"] = float(bool(item["is_st"]))
        if item.get("limit_up") is not None:
            patch["up_limit"] = item["limit_up"]
        if item.get("limit_down") is not None:
            patch["down_limit"] = item["limit_down"]
    return patch


def _write_native_partition(
    target: Path,
    patches: list[dict[str, Any]],
    *,
    scope: dict[str, str],
    revision_key: str,
    manifest_extra: dict[str, Any] | None = None,
) -> tuple[Any, int]:
    """Merge one date partition, archiving only a genuinely changed prior version."""
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = pl.read_parquet(target).to_dicts() if target.is_file() else []
    by_symbol = {str(row.get("ts_code") or "").upper(): row for row in existing}
    changed = 0
    for patch in patches:
        key = str(patch["ts_code"]).upper()
        before = dict(by_symbol.get(key) or {})
        by_symbol.setdefault(key, {}).update(patch)
        changed += int(before != by_symbol[key])
    # TuShare market-wide incremental endpoints may be replayed after a
    # restarted worker. Do not rewrite an identical published partition: doing
    # so would create a misleading revision even though no provider correction
    # occurred.
    if target.is_file() and changed == 0:
        return pl.read_parquet(target), 0
    frame = pl.DataFrame(list(by_symbol.values()), infer_schema_length=None)
    temporary = _temp_manifest_path(target)
    frame.write_parquet(temporary, compression=PARQUET_COMPRESSION)
    if target.is_file():
        prior_hash = _sha256(target)
        revision = (
            PARQUET_DIR / "bronze" / "tushare" / "revisions" / revision_key
            / target.parent.name / prior_hash
        )
        revision.mkdir(parents=True, exist_ok=True)
        archived = revision / "data.parquet"
        if not archived.exists():
            shutil.copy2(target, archived)
        old_manifest = target.with_name("manifest.json")
        archived_manifest = revision / "manifest.json"
        if old_manifest.is_file() and not archived_manifest.exists():
            shutil.copy2(old_manifest, archived_manifest)
    os.replace(temporary, target)
    digest = _sha256(target)
    manifest = {
        "trade_date": str(patches[0]["trade_date"]),
        "rows": frame.height,
        "sha256": digest,
        "content_sha256": digest,
        "source": scope["source"],
        "status": "success",
        "written_at_utc": datetime.now(UTC).isoformat(),
        "writer": "lean-platform",
        **(manifest_extra or {}),
    }
    manifest_path = target.with_name("manifest.json")
    manifest_tmp = _temp_manifest_path(manifest_path)
    manifest_tmp.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(manifest_tmp, manifest_path)
    return frame, changed


def _upsert_native_locked(prepared: list[dict[str, Any]], scope: dict[str, str]) -> dict[str, Any]:
    """Atomically update the established date partitions without a parallel store."""
    changed = 0
    files: list[dict[str, Any]] = []
    for trade_date in sorted({str(item["trade_date"]) for item in prepared}):
        day_items = [item for item in prepared if str(item["trade_date"]) == trade_date]
        patches = [_native_patch(item, scope) for item in day_items]
        if scope["kind"] == "bars":
            # Preserve the provider-shaped raw daily response before publishing
            # the normalized silver partition. Qlib materializations remain
            # outside this write path and are never mutated here.
            compact = trade_date.replace("-", "")
            raw_target = (
                PARQUET_DIR / "bronze" / "tushare" / "current" / "daily"
                / f"trade_date={compact}" / "data.parquet"
            )
            _write_native_partition(
                raw_target,
                patches,
                scope=scope,
                revision_key="lean_daily",
                manifest_extra={
                    "api": "daily",
                    "dataset": "daily",
                    "columns": list(patches[0]),
                    "params": {"trade_date": compact},
                },
            )
        target = _native_target(scope, trade_date)
        frame, partition_changed = _write_native_partition(
            target, patches, scope=scope, revision_key=f"lean_{scope['kind']}"
        )
        changed += partition_changed
        files.append({"path": _relative(target), "rowCount": frame.height, "sha256": _sha256(target)})
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode("utf-8")).hexdigest()
    return {"rows": len(prepared), "changedRows": changed, "datasetKey": dataset_key(**scope),
            "datasetVersion": f"{scope['source']}-{digest[:24]}", "manifestSha256": digest,
            "fileCount": len(files), "files": files}


@contextmanager
def _write_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".write.lock"
    with lock_path.open("a+b") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _upsert_native(prepared: list[dict[str, Any]], scope: dict[str, str]) -> dict[str, Any]:
    lock_key = hashlib.sha256(dataset_key(**scope).encode("utf-8")).hexdigest()[:24]
    with _write_lock(PARQUET_DIR / ".locks" / lock_key):
        return _upsert_native_locked(prepared, scope)


def _write_manifest(root: Path, payload: dict[str, Any]) -> None:
    target = _manifest_path(root)
    temporary = _temp_manifest_path(target)
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(temporary, target)


def write_tushare_bronze_partition(
    dataset: str,
    trade_date: str,
    rows: Iterable[dict[str, Any]],
    *,
    columns: Sequence[str],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Atomically publish one provider-shaped TuShare Bronze partition.

    These partitions are the durable cursor for market-wide endpoints.  They
    deliberately retain the provider column names (``ts_code``, ``trade_date``)
    rather than the normalized lake representation.  An unchanged replay is a
    no-op; a real provider correction retains the previous partition once.
    """
    _require_engine()
    compact_date = str(trade_date).replace("-", "")
    if len(compact_date) != 8 or not compact_date.isdigit():
        raise ValueError(f"invalid TuShare trade date: {trade_date!r}")
    if not dataset or "/" in dataset or "\\" in dataset:
        raise ValueError(f"invalid TuShare dataset: {dataset!r}")
    ordered_columns = tuple(str(column) for column in columns)
    if not ordered_columns:
        raise ValueError("TuShare Bronze partitions require an explicit schema.")
    materialized = [{column: row.get(column) for column in ordered_columns} for row in rows]
    frame = pl.DataFrame(materialized, schema=list(ordered_columns), strict=False)
    sort_columns = [column for column in ("trade_date", "ts_code") if column in frame.columns]
    if sort_columns:
        frame = frame.sort(sort_columns)
    canonical = json.dumps(
        frame.to_dicts(), ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"),
    ).encode("utf-8")
    content_sha256 = hashlib.sha256(canonical).hexdigest()
    root = PARQUET_DIR / "bronze" / "tushare" / "current" / dataset / f"trade_date={compact_date}"
    target = root / "data.parquet"
    manifest_path = root / "manifest.json"
    lock_key = hashlib.sha256(f"tushare-bronze:{dataset}".encode("utf-8")).hexdigest()[:24]
    with _write_lock(PARQUET_DIR / ".locks" / lock_key):
        current_hash = ""
        if manifest_path.is_file():
            try:
                current_hash = str(json.loads(manifest_path.read_text(encoding="utf-8")).get("content_sha256") or "")
            except (OSError, ValueError, TypeError):
                current_hash = ""
        if target.is_file() and current_hash == content_sha256:
            return {"changed": False, "rows": frame.height, "contentSha256": content_sha256}
        if target.is_file():
            prior_hash = current_hash or _sha256(target)
            revision = PARQUET_DIR / "bronze" / "tushare" / "revisions" / dataset / f"trade_date={compact_date}" / prior_hash
            revision.mkdir(parents=True, exist_ok=True)
            if not (revision / "data.parquet").exists():
                shutil.copy2(target, revision / "data.parquet")
            if manifest_path.is_file() and not (revision / "manifest.json").exists():
                shutil.copy2(manifest_path, revision / "manifest.json")
        root.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        frame.write_parquet(temporary, compression=PARQUET_COMPRESSION)
        os.replace(temporary, target)
        payload = {
            "dataset": dataset,
            "trade_date": compact_date,
            "status": "empty" if frame.height == 0 else "success",
            "rows": frame.height,
            "columns": list(ordered_columns),
            "sha256": _sha256(target),
            "content_sha256": content_sha256,
            "written_at_utc": datetime.now(UTC).isoformat(),
            "writer": "lean-platform",
            **(metadata or {}),
        }
        manifest_tmp = manifest_path.with_name(f".{manifest_path.name}.{uuid.uuid4().hex}.tmp")
        manifest_tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        os.replace(manifest_tmp, manifest_path)
    return {"changed": True, "rows": frame.height, "contentSha256": content_sha256}


def write_tushare_extended_bronze_partition(
    dataset: str,
    partition: str,
    rows: Iterable[dict[str, Any]],
    *,
    columns: Sequence[str],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Atomically publish one provider-shaped extended TuShare partition.

    Extended endpoints use several partition keys (trade date and report
    period today; historical bootstraps may also contain symbols or ranges),
    so this writer deliberately does not impose the daily writer's eight-digit
    date restriction. Published corrections retain the previous partition in
    the revisions tree and unchanged replays do not mutate the manifest.
    """
    _require_engine()
    safe_dataset = str(dataset).strip()
    safe_partition = str(partition).strip()
    # Symbol partitions used to be written with a dot (``000001.SZ``), while
    # the incremental synchronizer uses a filesystem-stable underscore
    # (``000001_SZ``). Normalize at the writer boundary so every caller shares
    # one immutable current-partition identity.
    symbol_partition = _TUSHARE_SYMBOL_PARTITION.fullmatch(safe_partition)
    if symbol_partition:
        safe_partition = f"{symbol_partition.group('symbol')}_{symbol_partition.group('venue').upper()}"
    if (
        not safe_dataset
        or not safe_partition
        or any(token in safe_dataset or token in safe_partition for token in ("/", "\\", ".."))
    ):
        raise ValueError(f"invalid TuShare extended partition: {dataset!r}/{partition!r}")
    ordered_columns = tuple(str(column) for column in columns)
    if not ordered_columns:
        raise ValueError("TuShare extended Bronze partitions require an explicit schema.")
    materialized = [
        {
            column: (
                None
                if isinstance(row.get(column), float) and not math.isfinite(row[column])
                else row.get(column)
            )
            for column in ordered_columns
        }
        for row in rows
    ]
    # Financial VIP responses often begin with a long null run and later
    # contain a finite number or NaN. Infer against the full bounded provider
    # partition so the first 100 rows cannot lock an incompatible dtype.
    frame = pl.DataFrame(
        materialized, schema=list(ordered_columns), strict=False, infer_schema_length=None
    )
    sort_columns = [
        column
        for column in ("trade_date", "ts_code", "end_date", "ann_date")
        if column in frame.columns
    ]
    if sort_columns:
        frame = frame.sort(sort_columns)
    canonical = json.dumps(
        frame.to_dicts(), ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"),
    ).encode("utf-8")
    content_sha256 = hashlib.sha256(canonical).hexdigest()
    relative = Path("extended") / safe_dataset / f"trade_date={safe_partition}"
    root = PARQUET_DIR / "bronze" / "tushare" / "current" / relative
    target = root / "data.parquet"
    manifest_path = root / "manifest.json"
    lock_key = hashlib.sha256(
        f"tushare-bronze:extended:{safe_dataset}".encode("utf-8")
    ).hexdigest()[:24]
    with _write_lock(PARQUET_DIR / ".locks" / lock_key):
        current_hash = ""
        if manifest_path.is_file():
            try:
                current_hash = str(
                    json.loads(manifest_path.read_text(encoding="utf-8")).get("content_sha256") or ""
                )
            except (OSError, ValueError, TypeError):
                current_hash = ""
        if target.is_file() and current_hash == content_sha256:
            # A no-op replay is still authoritative evidence that the provider
            # was checked. Keep the published content identity and
            # ``written_at_utc`` immutable, but atomically advance an explicit
            # freshness field so consumers do not mistake an unchanged report
            # period for a stalled dataset.
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                manifest = {}
            manifest["last_checked_at_utc"] = datetime.now(UTC).isoformat()
            if metadata and metadata.get("ingest_run_id"):
                manifest["last_checked_run_id"] = str(metadata["ingest_run_id"])
            manifest_tmp = manifest_path.with_name(f".{manifest_path.name}.{uuid.uuid4().hex}.tmp")
            manifest_tmp.write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8"
            )
            os.replace(manifest_tmp, manifest_path)
            return {"changed": False, "rows": frame.height, "contentSha256": content_sha256, "checked": True}
        if target.is_file():
            prior_hash = current_hash or _sha256(target)
            revision = (
                PARQUET_DIR
                / "bronze"
                / "tushare"
                / "revisions"
                / relative
                / prior_hash
            )
            revision.mkdir(parents=True, exist_ok=True)
            if not (revision / "data.parquet").exists():
                shutil.copy2(target, revision / "data.parquet")
            if manifest_path.is_file() and not (revision / "manifest.json").exists():
                shutil.copy2(manifest_path, revision / "manifest.json")
        root.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        frame.write_parquet(temporary, compression=PARQUET_COMPRESSION)
        os.replace(temporary, target)
        payload = {
            "dataset": safe_dataset,
            "partition": safe_partition,
            "trade_date": safe_partition,
            "status": "empty" if frame.height == 0 else "success",
            "rows": frame.height,
            "columns": list(ordered_columns),
            "sha256": _sha256(target),
            "content_sha256": content_sha256,
            "content_hash_kind": "logical_frame_v1",
            "written_at_utc": datetime.now(UTC).isoformat(),
            "last_checked_at_utc": datetime.now(UTC).isoformat(),
            "writer": "lean-platform",
            **(metadata or {}),
        }
        manifest_tmp = manifest_path.with_name(f".{manifest_path.name}.{uuid.uuid4().hex}.tmp")
        manifest_tmp.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8"
        )
        os.replace(manifest_tmp, manifest_path)
    return {"changed": True, "rows": frame.height, "contentSha256": content_sha256}


def upsert_rows(
    rows: Iterable[dict[str, Any]],
    *,
    kind: str = "bars",
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = "tushare",
) -> dict[str, Any]:
    """Merge rows into the canonical lake and atomically publish their manifest."""
    _require_engine()
    scope = _scope(
        kind=kind, asset_class=asset_class, market=market, venue=venue,
        resolution=resolution, data_type=data_type, adjust=adjust, source=source,
    )
    prepared = _normalise_rows(rows, scope)
    if not prepared:
        return {"rows": 0, "changedRows": 0, "datasetKey": dataset_key(**scope)}
    if _native_write_supported(scope) and _native_available(scope):
        return _upsert_native(prepared, scope)
    root = dataset_root(**scope)
    columns, key = _kind_definition(kind)
    years = sorted({int(item["trade_date"][:4]) for item in prepared})
    with _write_lock(root):
        previous = load_manifest(**scope)
        previous_files = list(previous.get("files") or [])
        retained = [item for item in previous_files if int(item.get("year") or 0) not in years]
        new_files: list[dict[str, Any]] = []
        total_changed = 0
        for year in years:
            incoming_rows = [item for item in prepared if int(item["trade_date"][:4]) == year]
            current_paths = [_visible(str(item["path"])) for item in previous_files if int(item.get("year") or 0) == year]
            frames = []
            if current_paths:
                frames.append(pl.read_parquet([str(path) for path in current_paths]))
            frames.append(pl.DataFrame(incoming_rows, infer_schema_length=None))
            frame = pl.concat(frames, how="diagonal_relaxed") if len(frames) > 1 else frames[0]
            for column in columns:
                if column not in frame.columns:
                    frame = frame.with_columns(pl.lit(None).alias(column))
            frame = frame.select(list(columns)).unique(subset=list(key), keep="last", maintain_order=True)
            sort_columns = [column for column in ("trade_date", "timestamp", "symbol", "source") if column in frame.columns]
            frame = frame.sort(sort_columns)
            release_seed = hashlib.sha256(
                json.dumps(incoming_rows, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:16]
            release_dir = root / f"r={year}_{release_seed[:8]}"
            release_dir.mkdir(parents=True, exist_ok=True)
            target = release_dir / PARTITION_FILE_NAME
            temporary = _temp_parquet_path(target)
            frame.write_parquet(temporary, compression=PARQUET_COMPRESSION)
            os.replace(temporary, target)
            checksum = _sha256(target)
            new_files.append(
                {
                    "path": _relative(target), "year": year, "rowCount": frame.height,
                    "firstTimestamp": str(frame.get_column("trade_date").min()),
                    "lastTimestamp": str(frame.get_column("trade_date").max()),
                    "sha256": checksum, "size": target.stat().st_size,
                }
            )
            total_changed += len(incoming_rows)
        manifest_files = sorted([*retained, *new_files], key=lambda item: (int(item.get("year") or 0), str(item["path"])))
        manifest_digest = hashlib.sha256(
            json.dumps(manifest_files, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        version = f"{scope['source']}-{manifest_digest[:24]}"
        payload = {
            "schemaVersion": MANIFEST_SCHEMA_VERSION,
            "datasetKey": dataset_key(**scope),
            "datasetVersion": version,
            "kind": kind,
            "scope": scope,
            "manifestSha256": manifest_digest,
            "files": manifest_files,
        }
        _write_manifest(root, payload)
    return {
        "rows": len(prepared), "changedRows": total_changed,
        "datasetKey": payload["datasetKey"], "datasetVersion": version,
        "manifestSha256": manifest_digest, "fileCount": len(manifest_files),
    }


def delete_snapshot_absences(
    *,
    kind: str,
    scopes: Sequence[tuple[str, str, str]],
    authoritative_keys: set[tuple[str, str]],
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = "tushare",
) -> int:
    """Remove rows absent from authoritative symbol/date snapshot windows.

    The current manifest remains the only publication pointer. Old Parquet
    files are intentionally retained as immutable revisions.
    """
    _require_engine()
    if not scopes:
        return 0
    scope = _scope(
        kind=kind,
        asset_class=asset_class,
        market=market,
        venue=venue,
        resolution=resolution,
        data_type=data_type,
        adjust=adjust,
        source=source,
    )
    if _native_available(scope):
        # Status is materialized as columns on the same silver bar rows. The
        # bar reconciliation below removes stale rows; a second status delete
        # must not remove otherwise valid market bars.
        if kind != "bars" or not _native_write_supported(scope):
            return 0
        normalized_scopes = {
            str(symbol).split(".", 1)[0].upper(): (str(start), str(end))
            for symbol, start, end in scopes
        }
        normalized_keys = {
            (str(symbol).split(".", 1)[0].upper(), str(trade_date))
            for symbol, trade_date in authoritative_keys
        }
        deleted = 0
        for target in _native_files(scope):
            compact = target.parent.name.split("=", 1)[-1]
            trade_date = _iso_date(compact)
            applicable = {
                symbol for symbol, (start, end) in normalized_scopes.items()
                if start <= trade_date <= end
            }
            if not applicable:
                continue
            frame = pl.read_parquet(target)
            rows = frame.to_dicts()
            kept = []
            for row in rows:
                symbol = str(row.get("ts_code") or row.get("symbol") or "").split(".", 1)[0].upper()
                remove = symbol in applicable and (symbol, trade_date) not in normalized_keys
                deleted += int(remove)
                if not remove:
                    kept.append(row)
            if len(kept) == len(rows):
                continue
            prior_hash = _sha256(target)
            revision = (
                PARQUET_DIR / "bronze" / "tushare" / "revisions" / "lean_snapshot_delete"
                / target.parent.name / prior_hash
            )
            revision.mkdir(parents=True, exist_ok=True)
            archived = revision / "data.parquet"
            if not archived.exists():
                shutil.copy2(target, archived)
            updated = pl.DataFrame(kept, schema=frame.schema) if kept else frame.head(0)
            temporary = _temp_manifest_path(target)
            updated.write_parquet(temporary, compression=PARQUET_COMPRESSION)
            os.replace(temporary, target)
            manifest_path = target.with_name("manifest.json")
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
            except (OSError, json.JSONDecodeError):
                manifest = {}
            manifest.update(
                {
                    "trade_date": compact,
                    "rows": updated.height,
                    "sha256": _sha256(target),
                    "written_at_utc": datetime.now(UTC).isoformat(),
                    "writer": "lean-platform:snapshot-reconcile",
                }
            )
            manifest_tmp = _temp_manifest_path(manifest_path)
            manifest_tmp.write_text(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8"
            )
            os.replace(manifest_tmp, manifest_path)
        return deleted
    root = dataset_root(**scope)
    columns, _ = _kind_definition(kind)
    scope_frame = pl.DataFrame(
        {
            "symbol": [item[0] for item in scopes],
            "_snapshot_start": [item[1] for item in scopes],
            "_snapshot_end": [item[2] for item in scopes],
        }
    ).unique(subset=["symbol"], keep="last")
    key_frame = pl.DataFrame(
        {
            "symbol": [item[0] for item in authoritative_keys],
            "trade_date": [item[1] for item in authoritative_keys],
            "_authoritative": [True] * len(authoritative_keys),
        }
    )
    deleted = 0
    with _write_lock(root):
        previous = load_manifest(**scope)
        previous_files = list(previous.get("files") or [])
        replacements: list[dict[str, Any]] = []
        retained: list[dict[str, Any]] = []
        for year in sorted({int(item.get("year") or 0) for item in previous_files}):
            year_files = [item for item in previous_files if int(item.get("year") or 0) == year]
            if not any(start[:4] <= str(year) <= end[:4] for _, start, end in scopes):
                retained.extend(year_files)
                continue
            paths = [_visible(str(item["path"])) for item in year_files]
            frame = pl.read_parquet([str(path) for path in paths])
            before = frame.height
            staged = frame.join(scope_frame, on="symbol", how="left")
            if not key_frame.is_empty():
                staged = staged.join(key_frame, on=["symbol", "trade_date"], how="left")
            else:
                staged = staged.with_columns(pl.lit(None).alias("_authoritative"))
            absent = (
                pl.col("_snapshot_start").is_not_null()
                & (pl.col("trade_date") >= pl.col("_snapshot_start"))
                & (pl.col("trade_date") <= pl.col("_snapshot_end"))
                & pl.col("_authoritative").is_null()
            )
            frame = staged.filter(~absent).select([column for column in frame.columns])
            year_deleted = before - frame.height
            if year_deleted <= 0:
                retained.extend(year_files)
                continue
            deleted += year_deleted
            for column in columns:
                if column not in frame.columns:
                    frame = frame.with_columns(pl.lit(None).alias(column))
            frame = frame.select(list(columns))
            revision = hashlib.sha256(
                json.dumps(
                    {
                        "operation": "snapshot-delete",
                        "year": year,
                        "scopes": scopes,
                        "authoritative": sorted(authoritative_keys),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:16]
            release_dir = root / f"r={year}_{revision[:8]}"
            release_dir.mkdir(parents=True, exist_ok=True)
            target = release_dir / PARTITION_FILE_NAME
            temporary = _temp_parquet_path(target)
            frame.write_parquet(temporary, compression=PARQUET_COMPRESSION)
            os.replace(temporary, target)
            replacements.append(
                {
                    "path": _relative(target),
                    "year": year,
                    "rowCount": frame.height,
                    "firstTimestamp": str(frame.get_column("trade_date").min()),
                    "lastTimestamp": str(frame.get_column("trade_date").max()),
                    "sha256": _sha256(target),
                    "size": target.stat().st_size,
                }
            )
        if deleted:
            manifest_files = sorted(
                [*retained, *replacements],
                key=lambda item: (int(item.get("year") or 0), str(item["path"])),
            )
            digest = hashlib.sha256(
                json.dumps(manifest_files, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            _write_manifest(
                root,
                {
                    "schemaVersion": MANIFEST_SCHEMA_VERSION,
                    "datasetKey": dataset_key(**scope),
                    "datasetVersion": f"{scope['source']}-{digest[:24]}",
                    "kind": kind,
                    "scope": scope,
                    "manifestSha256": digest,
                    "files": manifest_files,
                },
            )
    return deleted


def integrity_report(*, manifest: dict[str, Any] | None = None, **scope: str) -> dict[str, Any]:
    manifest = manifest or load_manifest(**scope)
    issues: list[str] = []
    rows = 0
    for item in manifest.get("files") or []:
        path = _visible(str(item["path"]))
        if not path.is_file():
            issues.append(f"missing:{item['path']}")
            continue
        if item.get("size") is not None and path.stat().st_size != int(item["size"]):
            issues.append(f"size:{item['path']}")
        if item.get("sha256") and _sha256(path) != item["sha256"]:
            issues.append(f"sha256:{item['path']}")
        rows += int(item.get("rowCount") or 0)
    return {
        "passed": not issues,
        "datasetKey": manifest.get("datasetKey"),
        "datasetVersion": manifest.get("datasetVersion"),
        "fileCount": len(manifest.get("files") or []),
        "manifestRows": rows,
        "issues": issues,
    }
