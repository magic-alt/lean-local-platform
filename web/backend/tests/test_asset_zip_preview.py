from __future__ import annotations

import zipfile
from datetime import date

import pytest

from app.domain import assets


def _write_zip(path, member: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, "\n".join(rows) + "\n")


def test_hour_preview_preserves_distinct_intraday_timestamps(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "DATA_DIR", tmp_path)
    request = assets.AssetRequest(
        asset_class="crypto",
        symbol="BTCUSD",
        venue="coinbase",
        resolution="hour",
        data_type="trade",
    )
    path = assets.lean_data_paths(request)[0]
    _write_zip(
        path,
        "btcusd_trade.csv",
        [
            "20260911 10:00,100,103,99,101,1",
            "20260911 11:00,101,104,100,102,2",
        ],
    )

    rows = assets.parse_lean_zip_ohlcv_series(
        request,
        date(2026, 9, 11),
        date(2026, 9, 11),
    )

    assert [row["time"] for row in rows] == [
        "2026-09-11T10:00:00+00:00",
        "2026-09-11T11:00:00+00:00",
    ]
    assert [row["close"] for row in rows] == [101.0, 102.0]


def test_daily_equity_preview_uses_exchange_local_trading_date(tmp_path, monkeypatch):
    monkeypatch.setattr(assets, "DATA_DIR", tmp_path)
    request = assets.AssetRequest(
        asset_class="equity",
        symbol="000001",
        venue="china",
        resolution="daily",
        data_type="trade",
    )
    path = assets.lean_data_paths(request)[0]
    _write_zip(path, "000001.csv", ["20260911,10000,10300,9900,10100,100"])

    rows = assets.parse_lean_zip_ohlcv_series(
        request,
        date(2026, 9, 11),
        date(2026, 9, 11),
    )

    assert rows == [
        {
            "time": "2026-09-11T00:00:00+08:00",
            "open": 1.0,
            "high": 1.03,
            "low": 0.99,
            "close": 1.01,
            "volume": 100.0,
        }
    ]


@pytest.mark.parametrize(
    ("resolution", "data_type", "message"),
    [
        ("daily", "quote", "typed codec"),
        ("daily", "open_interest", "typed codec"),
        ("tick", "trade", "typed tick codec"),
    ],
)
def test_preview_rejects_unsupported_row_shapes(resolution, data_type, message):
    request = assets.AssetRequest(
        asset_class="crypto",
        symbol="BTCUSD",
        venue="coinbase",
        resolution=resolution,
        data_type=data_type,
    )

    with pytest.raises(assets.AssetDomainError, match=message):
        assets.parse_lean_zip_ohlcv_series(request, None, None)
