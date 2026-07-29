import pytest


def test_etf_gate_requires_exchange_listing_metadata():
    from app.services.cross_asset_quality import validate_cross_asset_rows

    passed = validate_cross_asset_rows(
        "fund_basic",
        [{"ts_code": "510300.SH", "name": "沪深300ETF", "market": "E", "list_date": "2012-05-28"}],
    )
    failed = validate_cross_asset_rows(
        "fund_basic",
        [{"ts_code": "510300.SH", "name": "沪深300ETF", "market": "E"}],
    )

    assert passed["status"] == "passed"
    assert failed["status"] == "failed"
    assert failed["criticalErrors"][0]["code"] == "etf_list_date_missing"


def test_convertible_bond_gate_checks_terms_and_conversion_window():
    from app.services.cross_asset_quality import validate_cross_asset_rows

    result = validate_cross_asset_rows(
        "cb_basic",
        [
            {
                "ts_code": "113001.SH",
                "stk_code": "600001.SH",
                "par": 100,
                "conv_price": 10,
                "list_date": "2024-01-01",
                "maturity_date": "2030-01-01",
                "conv_start_date": "2024-07-01",
                "conv_end_date": "2029-12-31",
            }
        ],
    )

    assert result["status"] == "passed"
    broken = validate_cross_asset_rows(
        "cb_basic",
        [
            {
                "ts_code": "113001.SH",
                "par": 100,
                "conv_price": 0,
                "list_date": "2031-01-01",
                "maturity_date": "2030-01-01",
                "conv_start_date": "2030-01-01",
                "conv_end_date": "2029-01-01",
            }
        ],
    )
    assert {"convertible_underlying_missing", "invalid_positive_value", "convertible_lifecycle_invalid", "conversion_window_invalid"} <= {
        item["code"] for item in broken["criticalErrors"]
    }


@pytest.mark.parametrize(
    ("dataset", "row"),
    [
        (
            "fut_basic",
            {
                "ts_code": "IF2409.CFX",
                "exchange": "CFFEX",
                "multiplier": 300,
                "min_price_chg": 0.2,
                "list_date": "2024-01-01",
                "last_ddate": "2024-09-20",
            },
        ),
        (
            "opt_basic",
            {
                "ts_code": "10000001.SH",
                "exchange": "SSE",
                "call_put": "C",
                "exercise_price": 4.0,
                "per_unit": 10000,
                "min_price_chg": 0.0001,
                "list_date": "2024-01-01",
                "last_edate": "2024-06-26",
            },
        ),
    ],
)
def test_derivative_contract_metadata_gate(dataset, row):
    from app.services.cross_asset_quality import validate_cross_asset_rows

    assert validate_cross_asset_rows(dataset, [row])["status"] == "passed"


def test_provider_native_derivative_catalog_nulls_do_not_fail_the_dataset():
    from app.services.cross_asset_quality import validate_cross_asset_rows

    futures = validate_cross_asset_rows(
        "fut_basic",
        [
            {
                "ts_code": "JD2707.DCE",
                "exchange": "DCE",
                "multiplier": None,
                "per_unit": 5,
                "min_price_chg": None,
                "list_date": "2026-07-27",
                "delist_date": "2027-07-26",
                "last_ddate": float("nan"),
            },
            {
                "ts_code": "JDL.DCE",
                "exchange": "DCE",
                "multiplier": float("nan"),
                "per_unit": float("nan"),
                "list_date": float("nan"),
                "last_ddate": float("nan"),
            },
        ],
    )
    options = validate_cross_asset_rows(
        "opt_basic",
        [
            {
                "ts_code": "B2707-C-3200.DCE",
                "exchange": "DCE",
                "call_put": "C",
                "exercise_price": 3200,
                "per_unit": 10,
                "min_price_chg": "0.5",
                "list_date": "20260716",
                "last_edate": float("nan"),
                "maturity_date": "20270617",
            }
        ],
    )

    assert futures["status"] == "warning"
    assert futures["criticalErrors"] == []
    assert futures["warnings"][0]["code"] == "futures_continuous_catalog_row"
    assert options["status"] == "passed"


@pytest.mark.parametrize("dataset", ["fund_daily", "cb_daily", "fut_daily", "opt_daily"])
def test_cross_asset_daily_gate_rejects_broken_ohlc(dataset):
    from app.services.cross_asset_quality import validate_cross_asset_rows

    row = {
        "ts_code": "X",
        "trade_date": "2024-01-02",
        "open": 12,
        "high": 10,
        "low": 11,
        "close": 9,
        "volume": -1,
    }
    if dataset in {"fut_daily", "opt_daily"}:
        row.update({"settle": 10, "open_interest": 1})
    result = validate_cross_asset_rows(dataset, [row])

    assert result["status"] == "failed"
    assert {"ohlc_invariant_failed", "invalid_non_negative_value"} <= {
        item["code"] for item in result["criticalErrors"]
    }


def test_data_sync_manifest_validation_embeds_cross_asset_gate():
    from app.services import data_sync

    spec = next(item for item in data_sync.DATASET_REGISTRY if item.key == "opt_basic")
    with pytest.raises(ValueError, match="opt_basic validation gate failed"):
        data_sync._validate_dataset_rows(
            spec,
            [
                {
                    "ts_code": "BAD.SH",
                    "exchange": "SSE",
                    "call_put": "X",
                    "exercise_price": 0,
                    "per_unit": 0,
                    "min_price_chg": 0,
                    "list_date": "2025-01-01",
                    "last_edate": "2024-01-01",
                }
            ],
        )
