def _rows():
    return [
        {
            "symbol": "600036",
            "trade_date": "2024-01-02",
            "open": 10.0,
            "high": 10.2,
            "low": 9.9,
            "close": 10.1,
            "volume": 1000.0,
            "adj_factor": 1.0,
        },
        {
            "symbol": "600036",
            "trade_date": "2024-01-04",
            "open": 10.1,
            "high": 10.3,
            "low": 10.0,
            "close": 10.2,
            "volume": 1200.0,
            "adj_factor": 1.0,
        },
    ]


def test_full_day_suspension_is_not_reported_as_missing_trade_date():
    from app.services.data_quality import validate_ashare_daily_rows

    report = validate_ashare_daily_rows(
        _rows(),
        calendar_dates=["2024-01-02", "2024-01-03", "2024-01-04"],
        suspended_trade_dates={"2024-01-03"},
        source="tushare",
        batch_id="batch",
    )

    assert report["passed"] is True
    assert report["missing_trade_dates"] == []
    assert report["resolved_suspension_dates"] == ["2024-01-03"]
    assert report["expected_session_count"] == 3


def test_unexplained_gap_remains_blocking():
    from app.services.data_quality import validate_ashare_daily_rows

    report = validate_ashare_daily_rows(
        _rows(),
        calendar_dates=["2024-01-02", "2024-01-03", "2024-01-04"],
        source="tushare",
        batch_id="batch",
    )

    assert report["passed"] is False
    assert report["missing_trade_dates"] == ["2024-01-03"]


def test_partial_day_suspension_is_not_a_full_day_gap_exception():
    from app.services.data import _classify_suspension_dates

    dates, evidence = _classify_suspension_dates(
        [
            {
                "suspend_date": "2024-01-03",
                "resume_date": "2024-01-04",
                "suspend_timing": "09:30-10:00",
                "is_full_day": False,
                "source": "tushare:suspend_d",
            }
        ],
        ["2024-01-02", "2024-01-03", "2024-01-04"],
    )

    assert dates == set()
    assert evidence == {}


def test_daily_normalization_converts_optional_nan_to_null():
    from app.services.data_quality import normalize_ashare_daily_rows

    rows = normalize_ashare_daily_rows(
        "600601",
        [
            {
                "date": "1990-12-19",
                "open": 10.0,
                "high": 10.2,
                "low": 9.8,
                "close": 10.1,
                "volume": 100,
                "amount": float("nan"),
                "prev_close": float("nan"),
                "pct_change": float("nan"),
            }
        ],
        source="tushare",
        batch_id="batch",
    )

    assert rows[0]["amount"] is None
    assert rows[0]["prev_close"] is None
    assert rows[0]["pct_change"] is None
