from __future__ import annotations

import importlib.util
import math
import uuid
from typing import Any

from ..core.errors import LeanWebError
from ..db import bulk_db, db, json_dump, rows_to_dicts, utc_now
from ..lean_engine.symbols import normalize_symbol, parse_date
from ..services.ashare_repository import trade_dates_between, universe_as_of
from ..services import market_lake


DAILY_BASIC_FACTOR_COLUMNS = {
    "turnover_rate": "turnover_rate",
    "turnover_rate_float": "turnover_rate_float",
    "volume_ratio": "volume_ratio",
    "pe": "pe",
    "pe_ttm": "pe_ttm",
    "pb": "pb",
    "ps": "ps",
    "ps_ttm": "ps_ttm",
    "dividend_yield": "dividend_yield",
    "dividend_yield_ttm": "dividend_yield_ttm",
    "total_share_shares": "total_share_shares",
    "float_share_shares": "float_share_shares",
    "free_share_shares": "free_share_shares",
    "total_mv_cny": "total_mv_cny",
    "circ_mv_cny": "circ_mv_cny",
}


def available_engines() -> dict[str, bool]:
    return {
        "python": True,
        "duckdb": importlib.util.find_spec("duckdb") is not None,
        "polars": importlib.util.find_spec("polars") is not None,
    }


def selected_engine(preferred: str | None = None) -> str:
    engines = available_engines()
    if preferred and preferred in engines and engines[preferred]:
        return preferred
    if engines["polars"]:
        return "polars"
    if engines["duckdb"]:
        return "duckdb"
    return "python"


def _date(value: str) -> str:
    return parse_date(value).isoformat()


def _symbol(value: str) -> str:
    return normalize_symbol(value, "china").upper()


def import_factor_values(records: list[dict[str, Any]], source: str = "manual") -> dict[str, Any]:
    batch_id = str(uuid.uuid4())
    count = upsert_factor_values(records, source=source, batch_id=batch_id)
    return {"batchId": batch_id, "count": count}


def upsert_factor_values(
    records: list[dict[str, Any]],
    source: str = "manual",
    batch_id: str | None = None,
    *,
    bulk: bool = False,
) -> int:
    if records and all(
        str(record.get("source") or source) == "tushare:daily_basic"
        and str(record.get("factor_name") or record.get("factorName")) in DAILY_BASIC_FACTOR_COLUMNS
        for record in records
    ):
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for record in records:
            symbol = str(record["symbol"])
            trade_date = str(record.get("trade_date") or record.get("tradeDate"))
            grouped.setdefault(
                (symbol, trade_date),
                {"symbol": symbol, "trade_date": trade_date, "factors": {}},
            )["factors"][str(record.get("factor_name") or record.get("factorName"))] = record["value"]
        upsert_daily_basic_factor_values(
            list(grouped.values()),
            source="tushare:daily_basic",
            batch_id=batch_id,
            bulk=bulk,
        )
        return len(records)
    now = utc_now()
    values = []
    for record in records:
        symbol = _symbol(record["symbol"])
        trade_date = _date(record.get("trade_date") or record.get("tradeDate"))
        factor_name = str(record.get("factor_name") or record.get("factorName")).strip()
        if not factor_name:
            raise LeanWebError("factor_name is required.")
        value = float(record["value"])
        if not math.isfinite(value):
            raise LeanWebError("factor value must be finite.")
        values.append((symbol, trade_date, factor_name, value, record.get("source") or source, batch_id, now))
    if values:
        connection_factory = bulk_db if bulk else db
        with connection_factory() as connection:
            connection.executemany(
                """
                insert into factor_values
                    (symbol, trade_date, factor_name, value, source, batch_id, created_at)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(symbol, trade_date, factor_name, source) do update set
                    value = excluded.value,
                    batch_id = excluded.batch_id,
                    created_at = excluded.created_at
                """,
                values,
            )
    return len(values)


def upsert_daily_basic_factor_values(
    records: list[dict[str, Any]],
    *,
    source: str = "tushare:daily_basic",
    batch_id: str | None = None,
    bulk: bool = False,
    chunk_rows: int = 25_000,
) -> int:
    """Persist one wide row per symbol/date instead of up to 15 EAV rows."""
    if not records:
        return 0
    written = 0
    rows_per_chunk = max(1, int(chunk_rows))
    for offset in range(0, len(records), rows_per_chunk):
        values: list[dict[str, Any]] = []
        for record in records[offset: offset + rows_per_chunk]:
            symbol = _symbol(record["symbol"])
            trade_date = _date(record.get("trade_date") or record.get("tradeDate"))
            factors = dict(record.get("factors") or {})
            unknown = set(factors) - set(DAILY_BASIC_FACTOR_COLUMNS)
            if unknown:
                raise LeanWebError(f"unsupported daily_basic factors: {', '.join(sorted(unknown))}")
            normalized: dict[str, float | None] = {}
            for name in DAILY_BASIC_FACTOR_COLUMNS:
                raw_value = factors.get(name)
                if raw_value is None:
                    normalized[name] = None
                    continue
                value = float(raw_value)
                if not math.isfinite(value):
                    raise LeanWebError("factor value must be finite.")
                normalized[name] = value
            values.append({
                "symbol": symbol, "trade_date": trade_date, **normalized,
                "source": source, "batch_id": batch_id,
            })
        if values:
            market_lake.upsert_rows(
                values, kind="daily_basic", asset_class="equity", market="china",
                venue="china", resolution="daily", data_type="metric", adjust="raw",
                source=source,
            )
            written += len(values)
    return written


def _factor_values(symbols: list[str], trade_date: str, factor_names: list[str]) -> dict[str, dict[str, float]]:
    if not symbols or not factor_names:
        return {}
    symbol_placeholders = ",".join("?" for _ in symbols)
    regular_names = [name for name in factor_names if name not in DAILY_BASIC_FACTOR_COLUMNS]
    rows: list[dict[str, Any]] = []
    if regular_names:
        regular_placeholders = ",".join("?" for _ in regular_names)
        with db() as connection:
            db_rows = connection.execute(
                f"""
                select symbol, factor_name, value from factor_values
                where trade_date = ?
                  and symbol in ({symbol_placeholders})
                  and factor_name in ({regular_placeholders})
                order by source desc
                """,
                [trade_date, *symbols, *regular_names],
            ).fetchall()
        rows.extend(rows_to_dicts(db_rows))
    daily_names = [name for name in factor_names if name in DAILY_BASIC_FACTOR_COLUMNS]
    if daily_names:
        daily_rows = market_lake.query_matching(
            kind="daily_basic", asset_class="equity", market="china", venue="china",
            resolution="daily", data_type="metric", adjust="raw",
            columns="*", predicates=("trade_date = ?", f"symbol in ({symbol_placeholders})"),
            parameters=[trade_date, *symbols],
        )
        for item in daily_rows:
            for name in daily_names:
                if item.get(name) is not None:
                    rows.append({"symbol": item["symbol"], "factor_name": name, "value": item[name]})
    values: dict[str, dict[str, float]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["symbol"], row["factor_name"])
        if key in seen:
            continue
        seen.add(key)
        values.setdefault(row["symbol"], {})[row["factor_name"]] = float(row["value"])
    return values


def _closes(symbols: list[str], trade_date: str) -> dict[str, float]:
    if not symbols:
        return {}
    placeholders = ",".join("?" for _ in symbols)
    rows = market_lake.query_matching(
        kind="bars", asset_class="equity", market="china", venue="china",
        resolution="daily", data_type="trade", adjust="raw",
        columns="symbol,close,source", predicates=("trade_date = ?", f"symbol in ({placeholders})"),
        parameters=[trade_date, *symbols], order_by="source desc",
    )
    closes: dict[str, float] = {}
    for row in rows:
        closes.setdefault(row["symbol"], float(row["close"]))
    return closes


def _dates_for_analysis(start_date: str, end_date: str) -> list[str]:
    dates = trade_dates_between("china", start_date, end_date)
    if dates:
        return dates
    rows = market_lake.query_matching(
        kind="bars", asset_class="equity", market="china", venue="china",
        resolution="daily", data_type="trade", adjust="raw",
        columns="distinct trade_date", predicates=("trade_date >= ?", "trade_date <= ?"),
        parameters=(start_date, end_date), order_by="trade_date asc",
    )
    return [row["trade_date"] for row in rows]


def factor_matrix(
    *,
    universe_code: str,
    start_date: str,
    end_date: str,
    factor_names: list[str],
    forward_days: int = 1,
) -> list[dict[str, Any]]:
    start = _date(start_date)
    end = _date(end_date)
    if forward_days < 1:
        raise LeanWebError("forward_days must be >= 1.")
    factors = [name.strip() for name in factor_names if name.strip()]
    if not factors:
        raise LeanWebError("At least one factor is required.")
    dates = _dates_for_analysis(start, end)
    rows: list[dict[str, Any]] = []
    for index, trade_date in enumerate(dates):
        future_index = index + forward_days
        if future_index >= len(dates):
            break
        future_date = dates[future_index]
        members = universe_as_of(universe_code.upper(), trade_date)
        symbols = [item["symbol"] for item in members]
        if not symbols:
            continue
        factor_map = _factor_values(symbols, trade_date, factors)
        close_now = _closes(symbols, trade_date)
        close_future = _closes(symbols, future_date)
        for symbol in symbols:
            if symbol not in factor_map or symbol not in close_now or symbol not in close_future:
                continue
            if close_now[symbol] <= 0:
                continue
            row_factors = factor_map[symbol]
            if any(name not in row_factors for name in factors):
                continue
            rows.append(
                {
                    "trade_date": trade_date,
                    "forward_date": future_date,
                    "symbol": symbol,
                    "factors": row_factors,
                    "close": close_now[symbol],
                    "forward_close": close_future[symbol],
                    "forward_return": close_future[symbol] / close_now[symbol] - 1.0,
                }
            )
    return rows


def _pearson(x_values: list[float], y_values: list[float]) -> float | None:
    if len(x_values) < 2 or len(y_values) < 2 or len(x_values) != len(y_values):
        return None
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values))
    x_var = sum((x - x_mean) ** 2 for x in x_values)
    y_var = sum((y - y_mean) ** 2 for y in y_values)
    denominator = math.sqrt(x_var * y_var)
    return numerator / denominator if denominator else None


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        rank = (index + end + 2) / 2.0
        for offset in range(index, end + 1):
            ranks[ordered[offset][0]] = rank
        index = end + 1
    return ranks


def _quantile_bucket(rank_index: int, total: int, quantiles: int) -> int:
    return min(quantiles, int(rank_index * quantiles / total) + 1)


def evaluate_factor(
    *,
    factor_name: str,
    universe_code: str,
    start_date: str,
    end_date: str,
    forward_days: int = 1,
    quantiles: int = 5,
    engine: str | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    if quantiles < 2:
        raise LeanWebError("quantiles must be >= 2.")
    engine_name = selected_engine(engine)
    matrix = factor_matrix(
        universe_code=universe_code,
        start_date=start_date,
        end_date=end_date,
        factor_names=[factor_name],
        forward_days=forward_days,
    )
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in matrix:
        by_date.setdefault(row["trade_date"], []).append(row)
    ic_series = []
    rank_ic_series = []
    quantile_values: dict[int, list[float]] = {bucket: [] for bucket in range(1, quantiles + 1)}
    for trade_date, rows in sorted(by_date.items()):
        if len(rows) < 2:
            continue
        factor_values = [float(row["factors"][factor_name]) for row in rows]
        returns = [float(row["forward_return"]) for row in rows]
        ic = _pearson(factor_values, returns)
        rank_ic = _pearson(_ranks(factor_values), _ranks(returns))
        if ic is not None:
            ic_series.append({"trade_date": trade_date, "ic": ic, "count": len(rows)})
        if rank_ic is not None:
            rank_ic_series.append({"trade_date": trade_date, "rank_ic": rank_ic, "count": len(rows)})
        ranked_rows = sorted(rows, key=lambda row: float(row["factors"][factor_name]))
        for index, row in enumerate(ranked_rows):
            quantile_values[_quantile_bucket(index, len(ranked_rows), quantiles)].append(float(row["forward_return"]))
    quantile_returns = [
        {
            "quantile": bucket,
            "mean_return": sum(values) / len(values) if values else None,
            "count": len(values),
        }
        for bucket, values in quantile_values.items()
    ]
    result = {
        "factor": factor_name,
        "universe": universe_code.upper(),
        "start_date": _date(start_date),
        "end_date": _date(end_date),
        "forward_days": forward_days,
        "quantiles": quantiles,
        "engine": engine_name,
        "observations": len(matrix),
        "date_count": len(by_date),
        "ic_series": ic_series,
        "rank_ic_series": rank_ic_series,
        "mean_ic": sum(item["ic"] for item in ic_series) / len(ic_series) if ic_series else None,
        "mean_rank_ic": sum(item["rank_ic"] for item in rank_ic_series) / len(rank_ic_series) if rank_ic_series else None,
        "quantile_returns": quantile_returns,
        "matrix_preview": matrix[:100],
    }
    if persist:
        evaluation_id = str(uuid.uuid4())
        with db() as connection:
            connection.execute(
                """
                insert into factor_evaluations
                    (id, factor_name, universe_code, start_date, end_date, forward_days,
                     quantiles, engine, result_json, created_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation_id,
                    factor_name,
                    universe_code.upper(),
                    result["start_date"],
                    result["end_date"],
                    forward_days,
                    quantiles,
                    engine_name,
                    json_dump(result),
                    utc_now(),
                ),
            )
        result["id"] = evaluation_id
    return result


def batch_evaluate_factors(
    *,
    factor_names: list[str],
    universe_code: str,
    start_date: str,
    end_date: str,
    forward_days: int = 1,
    quantiles: int = 5,
    engine: str | None = None,
) -> dict[str, Any]:
    return {
        "engine": selected_engine(engine),
        "items": [
            evaluate_factor(
                factor_name=factor_name,
                universe_code=universe_code,
                start_date=start_date,
                end_date=end_date,
                forward_days=forward_days,
                quantiles=quantiles,
                engine=engine,
            )
            for factor_name in factor_names
        ],
    }


def list_factor_evaluations(limit: int = 50) -> list[dict[str, Any]]:
    bounded = max(1, min(int(limit), 500))
    with db() as connection:
        rows = connection.execute(
            "select * from factor_evaluations order by created_at desc limit ?",
            (bounded,),
        ).fetchall()
    return rows_to_dicts(rows)
