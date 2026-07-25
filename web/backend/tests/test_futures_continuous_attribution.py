import pytest


def test_continuous_contract_persists_margin_fees_and_roll_attribution():
    from app.db import init_db
    from app.services.futures import (
        build_continuous_contract,
        import_contracts,
        import_daily_bars,
        set_fee_schedule,
    )

    init_db()
    import_contracts(
        [
            {
                "contract_code": "M2405",
                "product": "M",
                "exchange": "DCE",
                "multiplier": 10,
                "margin_rate": 0.1,
                "tick_size": 1,
                "last_trade_date": "2024-05-15",
            },
            {
                "contract_code": "M2409",
                "product": "M",
                "exchange": "DCE",
                "multiplier": 10,
                "margin_rate": 0.12,
                "tick_size": 1,
                "last_trade_date": "2024-09-15",
            },
        ],
        source="unit",
    )
    import_daily_bars(
        [
            {"contract_code": "M2405", "trade_date": "2024-01-02", "open": 99, "close": 100, "volume": 100, "open_interest": 1000},
            {"contract_code": "M2409", "trade_date": "2024-01-02", "open": 108, "close": 110, "volume": 90, "open_interest": 500},
            {"contract_code": "M2405", "trade_date": "2024-01-03", "open": 101, "close": 102, "volume": 100, "open_interest": 900},
            {"contract_code": "M2409", "trade_date": "2024-01-03", "open": 111, "close": 112, "volume": 120, "open_interest": 1500},
        ],
        source="unit",
    )
    set_fee_schedule(
        product="M",
        exchange="DCE",
        per_contract=2,
        slippage_ticks=1,
        version="dce-unit-v1",
        source="unit",
    )

    result = build_continuous_contract(
        product="M",
        exchange="DCE",
        start_date="2024-01-02",
        end_date="2024-01-03",
        adjustment="backward_ratio",
    )

    assert result["fee_schedule_version"] == "dce-unit-v1"
    assert result["summary"]["rolls"] == 1
    assert result["bars"][0]["margin_required"] == pytest.approx(100)
    assert result["bars"][1]["margin_required"] == pytest.approx(134.4)
    assert result["bars"][0]["adjusted_close"] == pytest.approx(100 * 112 / 102)
    assert result["rollEvents"][0]["roll_gap"] == pytest.approx(10)
    assert result["rollEvents"][0]["market_pnl"] == pytest.approx(20)
    assert result["summary"]["totalCommission"] == pytest.approx(6)
    assert result["summary"]["totalSlippage"] == pytest.approx(30)


def test_main_mapping_requires_configured_dominance_days():
    from app.db import db, init_db
    from app.services.futures import (
        import_contracts,
        import_daily_bars,
        refresh_main_mapping,
        set_main_rule,
    )

    init_db()
    import_contracts(
        [
            {"contract_code": "M2405", "product": "M", "exchange": "DCE", "last_trade_date": "2024-05-15"},
            {"contract_code": "M2409", "product": "M", "exchange": "DCE", "last_trade_date": "2024-09-15"},
        ],
        source="unit",
    )
    import_daily_bars(
        [
            {"contract_code": contract, "trade_date": trade_date, "close": close, "volume": 100, "open_interest": oi}
            for trade_date, old_oi, new_oi in (
                ("2024-01-02", 1000, 500),
                ("2024-01-03", 900, 1100),
                ("2024-01-04", 800, 1200),
            )
            for contract, close, oi in (("M2405", 100, old_oi), ("M2409", 110, new_oi))
        ],
        source="unit",
    )
    set_main_rule(
        product="M",
        exchange="DCE",
        min_open_interest_days=2,
        source="unit",
    )

    result = refresh_main_mapping(
        product="M",
        exchange="DCE",
        start_date="2024-01-02",
        end_date="2024-01-04",
        source="stability-test",
    )

    with db() as connection:
        rows = connection.execute(
            "select trade_date,main_symbol from futures_main_mapping where batch_id=? order by trade_date",
            (result["batchId"],),
        ).fetchall()
    assert [(row["trade_date"], row["main_symbol"]) for row in rows] == [
        ("2024-01-02", "M2405"),
        ("2024-01-03", "M2405"),
        ("2024-01-04", "M2409"),
    ]
