from __future__ import annotations

import argparse
from pathlib import Path

import polars as pl

from scripts import local_data_certification


def _write_fixture(data_dir: Path, *, duplicate: bool = False) -> None:
    equity_path = data_dir / "silver/daily/current/trade_date=20240102/data.parquet"
    daily_basic_path = data_dir / "bronze/tushare/current/daily_basic/trade_date=20240102/data.parquet"
    index_path = data_dir / "gold/qlib_staging/full/SH000300.parquet"
    for path in (equity_path, daily_basic_path, index_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    equity_row = {
        "ts_code": "600519.SH",
        "trade_date": "20240102",
        "open": 100.0,
        "high": 103.0,
        "low": 99.0,
        "close": 102.0,
        "vol": 1000.0,
    }
    pl.DataFrame([equity_row, equity_row] if duplicate else [equity_row]).write_parquet(equity_path)
    pl.DataFrame([
        {
            "ts_code": "600519.SH",
            "trade_date": "20240102",
            "pe_ttm": 25.0,
        }
    ]).write_parquet(daily_basic_path)
    pl.DataFrame([
        {
            "symbol": "000300",
            "date": "2024-01-02",
            "open": 3500.0,
            "high": 3530.0,
            "low": 3480.0,
            "close": 3520.0,
        }
    ]).write_parquet(index_path)


def _args(data_dir: Path, tmp_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        data_dir=data_dir,
        evidence=tmp_path / "evidence.json",
        work_dir=tmp_path / "work",
        symbol=None,
        lean_rows=1,
        min_equity_rows=1,
        min_equity_partitions=1,
        min_daily_basic_rows=1,
        min_daily_basic_partitions=1,
        min_index_rows=1,
        skip_deep=False,
        skip_lean_smoke=True,
        no_pull_image=True,
    )


def test_local_data_certification_accepts_canonical_read_only_lake(tmp_path):
    data_dir = tmp_path / "data"
    _write_fixture(data_dir)

    result = local_data_certification.certify(_args(data_dir, tmp_path))

    assert result["passed"] is True
    assert result["readOnlySource"] is True
    assert result["checks"]["equityUniqueKeys"] is True
    assert result["checks"]["dailyBasicPeTtmPresent"] is True
    assert result["checks"]["allParquetMetadataReadable"] is True


def test_local_data_certification_rejects_duplicate_equity_keys(tmp_path):
    data_dir = tmp_path / "data"
    _write_fixture(data_dir, duplicate=True)

    result = local_data_certification.certify(_args(data_dir, tmp_path))

    assert result["passed"] is False
    assert result["checks"]["equityUniqueKeys"] is False
