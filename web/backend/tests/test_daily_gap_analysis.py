from __future__ import annotations

from datetime import date, timedelta

import pytest


def _daily_rows(symbol: str, count: int = 66) -> list[dict]:
    rows = []
    for index in range(count):
        gap = -0.01 if index % 2 == 0 else 0.01
        open_price = 100 * (1 + gap)
        rows.append(
            {
                "symbol": symbol,
                "trade_date": (date(2026, 1, 1) + timedelta(days=index)).isoformat(),
                "open": open_price,
                "high": max(open_price, 100.0) + 0.1,
                "low": min(open_price, 100.0) - 0.1,
                "close": 100.0,
                "prev_close": 100.0,
                "volume": 1000.0,
                "amount": 100000.0,
            }
        )
    rows[-1].update(
        {
            "open": 97.0,
            "high": 100.0,
            "low": 96.0,
            "close": 99.0,
            "volume": 2000.0,
            "amount": 200000.0,
        }
    )
    return rows


def test_daily_gap_features_use_exchange_prev_close_and_prior_only_windows():
    from app.services.daily_gap_analysis import add_daily_gap_features

    rows = _daily_rows("512800.SH")
    features = add_daily_gap_features(rows)
    event = features[-1]

    assert event["gap"] == pytest.approx(-0.03)
    assert event["gapZ"] < -2
    assert event["side"] == "down"
    assert event["severity"] == "≥2.0σ"
    assert event["closeRebound"] is True
    assert event["halfFill"] is True
    assert event["fullFill"] is True
    assert event["fillRatioClose"] == pytest.approx(2 / 3)
    assert event["mfeFromOpen"] == pytest.approx(100 / 97 - 1)
    assert event["maeFromOpen"] == pytest.approx(96 / 97 - 1)
    assert event["volumeRatio"] == pytest.approx(2.0)
    assert event["amountRatio"] == pytest.approx(2.0)


def test_company_action_flag_excludes_an_otherwise_large_gap_event():
    from app.services.daily_gap_analysis import add_daily_gap_features

    rows = _daily_rows("512690.SH")
    rows.append(
        {
            "symbol": "512690.SH",
            "trade_date": "2026-04-01",
            "open": 90.0,
            "high": 96.0,
            "low": 89.0,
            "close": 95.0,
            "prev_close": 95.0,
            "volume": 1000.0,
            "amount": 100000.0,
        }
    )

    event = add_daily_gap_features(rows)[-1]

    assert event["previousActualClose"] == 99.0
    assert event["corporateActionFlag"] is True
    assert event["gap"] == pytest.approx(90 / 95 - 1)
    assert event["side"] is None
    assert event["severity"] is None


def test_high_gap_event_reports_close_fade_and_full_intraday_reversal():
    from app.services.daily_gap_analysis import add_daily_gap_features

    rows = _daily_rows("512400.SH")
    rows[-1].update({"open": 103.0, "high": 104.0, "low": 100.0, "close": 101.0})

    event = add_daily_gap_features(rows)[-1]

    assert event["gap"] == pytest.approx(0.03)
    assert event["gapZ"] > 2
    assert event["side"] == "up"
    assert event["closeFade"] is True
    assert event["fullReversalIntraday"] is True
    assert event["givebackRatioClose"] == pytest.approx(2 / 3)


def test_summaries_never_pool_different_sector_proxies():
    from app.services.daily_gap_analysis import add_daily_gap_features, summarize_daily_gap_events

    features = add_daily_gap_features(
        _daily_rows("512800.SH") + _daily_rows("512400.SH")
    )
    summary = summarize_daily_gap_events(features, "down")

    overall = [item for item in summary if item["severity"] == "全部≥1σ"]
    extreme = [item for item in summary if item["severity"] == "≥2.0σ"]
    assert {item["symbol"] for item in overall} == {"512800.SH", "512400.SH"}
    assert {item["symbol"] for item in extreme} == {"512800.SH", "512400.SH"}
    assert all(item["eventCount"] == 1 for item in extreme)


def test_research_template_runs_from_stored_daily_bars_and_states_daily_limits():
    from app.db import db, init_db, utc_now
    from app.services import research_analysis

    init_db()
    rows = _daily_rows("512800.SH")
    with db() as connection:
        connection.executemany(
            """
            insert into market_daily_bars
                (instrument_id,symbol,asset_class,market,venue,trade_date,resolution,
                 data_type,open,high,low,close,volume,amount,prev_close,adjust,source,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    "fund:china:china:512800.SH",
                    row["symbol"],
                    "fund",
                    "china",
                    "china",
                    row["trade_date"],
                    "daily",
                    "trade",
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row["volume"],
                    row["amount"],
                    row["prev_close"],
                    "raw",
                    "tushare",
                    utc_now(),
                )
                for row in rows
            ],
        )
    scope = {
        "asset": {
            "assetClass": "fund",
            "market": "china",
            "venue": "china",
            "resolution": "daily",
            "dataType": "trade",
        },
        "selection": {"type": "symbols", "values": ["512800.SH"]},
        "time": {"startDate": "2026-01-01", "endDate": "2026-12-31", "asOfDate": "2026-12-31"},
        "price": {"adjust": "raw"},
        "provider": {"source": "tushare", "mode": "strict", "allowResearchSource": False},
    }

    result = research_analysis.analyze("daily-gap-events", scope, {})

    assert result["summary"]["dailyOnly"] is True
    assert result["summary"]["pooledAcrossSymbols"] is False
    assert result["summary"]["gapDownEvents"] >= 1
    assert any("不能识别先涨后跌或先跌后涨" in warning for warning in result["warnings"])
    assert any("开盘时尚不可知" in warning for warning in result["warnings"])
    assert all("VWAP" not in column for table in result["tables"] for column in table["columns"])
