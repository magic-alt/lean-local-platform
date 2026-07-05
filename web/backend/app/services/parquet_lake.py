from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from ..core.config import PARQUET_COMPRESSION, PARQUET_DIR
from ..db import db, json_dump, rows_to_dicts, utc_now

try:  # pragma: no cover - exercised when dependency is installed.
    import duckdb
except Exception:  # pragma: no cover
    duckdb = None

try:  # pragma: no cover - exercised when dependency is installed.
    import polars as pl
except Exception:  # pragma: no cover
    pl = None


SCHEMA_VERSION = 1
DATASET_NAMESPACE = uuid.UUID("0c36692c-1d8d-4e19-9dc0-7c4435b2b8a6")
FILE_NAMESPACE = uuid.UUID("5bb3fc9a-6849-4d73-bd43-5d66d0b75f06")


def _clean(value: str | None, default: str = "") -> str:
    text = (value or default).strip().lower()
    return text or default


def _dataset_key(
    *,
    asset_class: str,
    market: str,
    venue: str,
    resolution: str,
    data_type: str,
    adjust: str,
    source: str,
) -> str:
    return "/".join(
        [
            f"asset_class={asset_class}",
            f"market={market}",
            f"venue={venue}",
            f"resolution={resolution}",
            f"data_type={data_type}",
            f"adjust={adjust}",
            f"source={source}",
        ]
    )


def _dataset_id(dataset_key: str) -> str:
    return str(uuid.uuid5(DATASET_NAMESPACE, dataset_key))


def _file_id(path: Path) -> str:
    return str(uuid.uuid5(FILE_NAMESPACE, str(path)))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(path: Path) -> str:
    try:
        return str(path.relative_to(PARQUET_DIR))
    except ValueError:
        return str(path)


def _normalize_scope(
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = "akshare",
) -> dict[str, str]:
    market_key = _clean(market, "china")
    return {
        "asset_class": _clean(asset_class, "equity"),
        "market": market_key,
        "venue": _clean(venue, market_key),
        "resolution": _clean(resolution, "daily"),
        "data_type": _clean(data_type, "trade"),
        "adjust": _clean(adjust, "raw"),
        "source": _clean(source, "akshare"),
    }


def _query_symbol(symbol: str, scope: dict[str, str]) -> str:
    value = symbol.strip().upper()
    if scope["asset_class"] == "equity" and scope["market"] == "china":
        if value.startswith(("SH", "SZ", "BJ")):
            return value[2:]
        if "." in value:
            return value.split(".", 1)[0]
    return value


def _dataset_root(scope: dict[str, str]) -> Path:
    path = PARQUET_DIR
    for part in (
        f"asset_class={scope['asset_class']}",
        f"market={scope['market']}",
        f"venue={scope['venue']}",
        f"resolution={scope['resolution']}",
        f"data_type={scope['data_type']}",
        f"adjust={scope['adjust']}",
        f"source={scope['source']}",
    ):
        path = path / part
    return path


def _fetch_market_rows(scope: dict[str, str], start_date: str | None, end_date: str | None) -> list[dict[str, Any]]:
    predicates = [
        "asset_class = ?",
        "market = ?",
        "venue = ?",
        "resolution = ?",
        "data_type = ?",
        "adjust = ?",
        "source = ?",
    ]
    params: list[Any] = [
        scope["asset_class"],
        scope["market"],
        scope["venue"],
        scope["resolution"],
        scope["data_type"],
        scope["adjust"],
        scope["source"],
    ]
    if start_date:
        predicates.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        predicates.append("trade_date <= ?")
        params.append(end_date)
    with db() as connection:
        rows = connection.execute(
            f"""
            select
                instrument_id,
                symbol,
                asset_class,
                market,
                venue,
                trade_date,
                resolution,
                data_type,
                open,
                high,
                low,
                close,
                settle,
                volume,
                amount,
                turnover_rate,
                open_interest,
                prev_close,
                pct_change,
                adjust,
                adj_factor,
                source,
                batch_id,
                created_at
            from market_daily_bars
            where {" and ".join(predicates)}
            order by trade_date asc, symbol asc
            """,
            params,
        ).fetchall()
    return rows_to_dicts(rows)


def _write_partition(frame: Any, root: Path, year: int) -> dict[str, Any]:
    partition_dir = root / f"year={year}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    path = partition_dir / "part-00000.parquet"
    temp_path = path.with_suffix(".parquet.tmp")
    frame.write_parquet(temp_path, compression=PARQUET_COMPRESSION)
    temp_path.replace(path)
    return {
        "path": path,
        "partition": {"year": year},
        "row_count": frame.height,
        "first_timestamp": frame.select(pl.col("trade_date").min()).item(),
        "last_timestamp": frame.select(pl.col("trade_date").max()).item(),
        "sha256": _sha256(path),
        "size": path.stat().st_size,
    }


def _upsert_dataset(scope: dict[str, str], root: Path, rows: list[dict[str, Any]], files: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    key = _dataset_key(**scope)
    dataset_id = _dataset_id(key)
    first_date = min((str(row["trade_date"]) for row in rows), default=None)
    last_date = max((str(row["trade_date"]) for row in rows), default=None)
    with db() as connection:
        connection.execute(
            """
            insert into parquet_datasets
                (id, dataset_key, asset_class, market, venue, resolution, data_type, adjust, source,
                 root_path, schema_version, start_date, end_date, row_count, file_count,
                 metadata_json, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(dataset_key) do update set
                asset_class = excluded.asset_class,
                market = excluded.market,
                venue = excluded.venue,
                resolution = excluded.resolution,
                data_type = excluded.data_type,
                adjust = excluded.adjust,
                source = excluded.source,
                root_path = excluded.root_path,
                schema_version = excluded.schema_version,
                start_date = excluded.start_date,
                end_date = excluded.end_date,
                row_count = excluded.row_count,
                file_count = excluded.file_count,
                metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                dataset_id,
                key,
                scope["asset_class"],
                scope["market"],
                scope["venue"],
                scope["resolution"],
                scope["data_type"],
                scope["adjust"],
                scope["source"],
                str(root),
                SCHEMA_VERSION,
                first_date,
                last_date,
                len(rows),
                len(files),
                json_dump(metadata),
                now,
                now,
            ),
        )
        connection.execute("delete from parquet_files where dataset_id = ?", (dataset_id,))
        for item in files:
            path = item["path"]
            connection.execute(
                """
                insert into parquet_files
                    (id, dataset_id, file_path, partition_json, row_count, first_timestamp,
                     last_timestamp, sha256, size, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _file_id(path),
                    dataset_id,
                    str(path),
                    json_dump(item["partition"]),
                    item["row_count"],
                    item["first_timestamp"],
                    item["last_timestamp"],
                    item["sha256"],
                    item["size"],
                    now,
                ),
            )
    return {
        "id": dataset_id,
        "datasetKey": key,
        "rootPath": str(root),
        "schemaVersion": SCHEMA_VERSION,
        "rowCount": len(rows),
        "fileCount": len(files),
        "startDate": first_date,
        "endDate": last_date,
        "files": [
            {
                "path": str(item["path"]),
                "relativePath": _relative_path(item["path"]),
                "partition": item["partition"],
                "rowCount": item["row_count"],
                "firstTimestamp": item["first_timestamp"],
                "lastTimestamp": item["last_timestamp"],
                "sha256": item["sha256"],
                "size": item["size"],
            }
            for item in files
        ],
    }


def export_market_daily_bars(
    *,
    asset_class: str = "equity",
    market: str = "china",
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    adjust: str = "raw",
    source: str = "akshare",
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    if pl is None:
        raise RuntimeError("polars is required to export Parquet datasets.")
    scope = _normalize_scope(asset_class, market, venue, resolution, data_type, adjust, source)
    rows = _fetch_market_rows(scope, start_date, end_date)
    root = _dataset_root(scope)
    root.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    if rows:
        frame = pl.DataFrame(rows).with_columns(pl.col("trade_date").str.slice(0, 4).cast(pl.Int32).alias("year"))
        for year in sorted(frame.get_column("year").unique().to_list()):
            partition = frame.filter(pl.col("year") == year).drop("year")
            files.append(_write_partition(partition, root, int(year)))
    metadata = {
        "exported_from": "market_daily_bars",
        "compression": PARQUET_COMPRESSION,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
    }
    return _upsert_dataset(scope, root, rows, files, metadata)


def list_datasets() -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select *
            from parquet_datasets
            order by updated_at desc, dataset_key asc
            """
        ).fetchall()
    return rows_to_dicts(rows)


def _sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _dataset_files(scope: dict[str, str]) -> tuple[dict[str, Any] | None, list[str]]:
    key = _dataset_key(**scope)
    with db() as connection:
        dataset = connection.execute("select * from parquet_datasets where dataset_key = ?", (key,)).fetchone()
        if dataset is None:
            return None, []
        files = connection.execute(
            """
            select file_path
            from parquet_files
            where dataset_id = ?
            order by first_timestamp asc, file_path asc
            """,
            (dataset["id"],),
        ).fetchall()
    return dict(dataset), [row["file_path"] for row in files]


def query_duckdb_bars(
    *,
    asset_class: str = "equity",
    symbol: str,
    market: str | None = None,
    venue: str | None = None,
    resolution: str = "daily",
    data_type: str = "trade",
    provider_source: str = "akshare",
    adjust: str = "raw",
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    if duckdb is None:
        return {"enabled": False, "source": "duckdb", "items": [], "count": 0, "error": "duckdb is not installed"}
    scope = _normalize_scope(asset_class, market or venue or "china", venue, resolution, data_type, adjust, provider_source)
    dataset, files = _dataset_files(scope)
    if not dataset or not files:
        return {"enabled": True, "source": "duckdb", "items": [], "count": 0, "message": "No matching Parquet dataset metadata found."}
    paths = ", ".join(_sql_string(path) for path in files)
    predicates = ["symbol = ?"]
    params: list[Any] = [_query_symbol(symbol, scope)]
    if start_date:
        predicates.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        predicates.append("trade_date <= ?")
        params.append(end_date)
    bounded_limit = max(1, min(int(limit), 5000))
    params.append(bounded_limit)
    sql = f"""
        select trade_date, open, high, low, close, volume, source
        from read_parquet([{paths}])
        where {" and ".join(predicates)}
        order by trade_date asc, source asc
        limit ?
    """
    rows = duckdb.connect(database=":memory:").execute(sql, params).fetchall()
    items = [
        {
            "timestamp": str(row[0]),
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
            "volume": row[5],
            "source": row[6],
        }
        for row in rows
    ]
    return {
        "enabled": True,
        "source": "duckdb",
        "dataset": {"id": dataset["id"], "datasetKey": dataset["dataset_key"]},
        "items": items,
        "count": len(items),
    }
