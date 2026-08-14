from __future__ import annotations

from pathlib import Path

import polars as pl

from app.db import db, init_db
from app.services.industry_release import export_industry_classification_pit


def test_export_industry_classification_pit_is_qlib_ready_and_hashed(tmp_path: Path):
    init_db()
    with db() as connection:
        connection.execute(
            """insert into securities
               (symbol,name,exchange,market,listed_date,status,is_st,created_at,updated_at)
               values ('000001','One','SZSE','china','2000-01-01','listed',0,
                       '2020-01-01','2020-01-01')"""
        )
        connection.executemany(
            """insert into industry_membership
               (id,symbol,industry_code,industry_name,taxonomy,level_no,
                in_date,out_date,source,payload_hash,created_at)
               values (?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (
                    "i1",
                    "000001",
                    "801010",
                    "Agriculture",
                    "SW2021",
                    1,
                    "2019-01-01",
                    "2021-12-31",
                    "unit",
                    "hash-1",
                    "2020-01-01",
                ),
                (
                    "i2",
                    "000001",
                    "801020",
                    "Mining",
                    "SW2021",
                    1,
                    "2022-01-01",
                    None,
                    "unit",
                    "hash-2",
                    "2022-01-01",
                ),
            ],
        )

    target = tmp_path / "release" / "industry.parquet"
    component = export_industry_classification_pit(
        target, start="2020-01-01", end="2025-12-31"
    )
    frame = pl.read_parquet(target)

    assert component["role"] == "industry_classification_pit"
    assert component["coverage"] == {"start": "2020-01-01", "end": "2025-12-31"}
    assert component["files"][0]["rowCount"] == 2
    assert len(component["files"][0]["sha256"]) == 64
    assert frame.select("instrument").to_series().to_list() == ["SZ000001", "SZ000001"]
    assert frame.select("effective_from").to_series().to_list() == [
        "2020-01-01",
        "2022-01-01",
    ]
    assert frame.select("effective_to").to_series().to_list() == [
        "2021-12-31",
        "2025-12-31",
    ]
