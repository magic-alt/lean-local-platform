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
    pl.DataFrame(
        [{"ts_code": "600519.SH", "trade_date": "20240102", "pe_ttm": 25.0}]
    ).write_parquet(daily_basic_path)
    pl.DataFrame(
        [
            {
                "symbol": "000300",
                "date": "2024-01-02",
                "open": 3500.0,
                "high": 3530.0,
                "low": 3480.0,
                "close": 3520.0,
            }
        ]
    ).write_parquet(index_path)


def _publish_release(data_dir: Path) -> dict:
    from app.services.data_releases import CORE_RESEARCH_COMPONENTS, publish_data_release

    paths = {
        "bars": "silver/daily/current/trade_date=20240102/data.parquet",
        "daily_basic": "bronze/tushare/current/daily_basic/trade_date=20240102/data.parquet",
        "benchmark": "gold/qlib_staging/full/SH000300.parquet",
    }
    components = []
    for role in sorted(CORE_RESEARCH_COMPONENTS):
        source = paths.get(role, paths["bars"])
        components.append(
            {
                "role": role,
                "componentReleaseId": f"{role}-fixture",
                "datasetKey": f"{role}-fixture",
                "schemaVersion": "1",
                "coverage": {"start": "2024-01-02", "end": "2024-01-02"},
                "files": [{"path": source, "rowCount": 1}],
            }
        )
    return publish_data_release(
        {
            "profile": "cn-equity-daily-research-v2",
            "assetClass": "equity",
            "market": "china",
            "universe": "fixture",
            "benchmark": "000300",
            "asOfTime": "2024-01-03T00:00:00Z",
            "coverage": {"start": "2024-01-02", "end": "2024-01-02"},
            "components": components,
            "lineage": {
                "source": "pytest",
                "batchId": "fixture-batch",
                "authority": "local-data-certification-test",
            },
        },
        data_dir,
        persist=False,
    )


def _args(data_dir: Path, tmp_path: Path, release_id: str) -> argparse.Namespace:
    return argparse.Namespace(
        data_dir=data_dir,
        data_release_id=release_id,
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


def test_local_data_certification_binds_immutable_release_identity_and_lineage(tmp_path):
    data_dir = tmp_path / "data"
    _write_fixture(data_dir)
    release = _publish_release(data_dir)

    result = local_data_certification.certify(
        _args(data_dir, tmp_path, release["dataReleaseId"])
    )

    assert result["passed"] is True
    assert result["schemaVersion"] == 2
    assert result["readOnlySource"] is True
    assert result["checks"]["equityUniqueKeys"] is True
    assert result["checks"]["dailyBasicPeTtmPresent"] is True
    assert result["checks"]["allParquetMetadataReadable"] is True
    assert result["checks"]["dataReleaseValid"] is True
    assert result["dataRelease"]["dataReleaseId"] == release["dataReleaseId"]
    assert result["dataRelease"]["manifestSha256"] == release["manifestSha256"]
    assert result["dataRelease"]["identitySha256"] == release["identitySha256"]
    assert result["dataRelease"]["lineage"]["batchId"] == "fixture-batch"
    assert result["dataRelease"]["checks"]["frozenFilesValid"] is True
    assert result["dataRelease"]["checks"]["barsPresent"] is True


def test_local_data_certification_rejects_duplicate_equity_keys(tmp_path):
    data_dir = tmp_path / "data"
    _write_fixture(data_dir, duplicate=True)
    release = _publish_release(data_dir)

    result = local_data_certification.certify(
        _args(data_dir, tmp_path, release["dataReleaseId"])
    )

    assert result["passed"] is False
    assert result["checks"]["equityUniqueKeys"] is False


def test_local_data_certification_rejects_tampered_release_lineage(tmp_path):
    data_dir = tmp_path / "data"
    _write_fixture(data_dir)
    release = _publish_release(data_dir)
    release_root = data_dir / "releases" / release["dataReleaseId"]
    (release_root / "lineage.json").write_text('{"source":"tampered"}', encoding="utf-8")

    result = local_data_certification.certify(
        _args(data_dir, tmp_path, release["dataReleaseId"])
    )

    assert result["passed"] is False
    assert result["checks"]["dataReleaseValid"] is False
    assert result["dataRelease"]["checks"]["lineageValid"] is False


def test_local_data_certification_rejects_tampered_frozen_bars(tmp_path):
    data_dir = tmp_path / "data"
    _write_fixture(data_dir)
    release = _publish_release(data_dir)
    release_root = data_dir / "releases" / release["dataReleaseId"]
    bars = next((release_root / "components" / "bars").glob("*.parquet"))
    bars.write_bytes(bars.read_bytes() + b"tamper")

    result = local_data_certification.certify(
        _args(data_dir, tmp_path, release["dataReleaseId"])
    )

    assert result["passed"] is False
    assert result["checks"]["dataReleaseValid"] is False
    assert result["dataRelease"]["checks"]["frozenFilesValid"] is False
