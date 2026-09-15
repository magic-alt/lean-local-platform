from __future__ import annotations

import json
from pathlib import Path

from app.services.ashare_source_adapters import (
    BAOSTOCK_DAILY_DESCRIPTOR,
    fetch_baostock_rows,
    normalize_baostock_daily_batch,
)
from app.services.provider_contracts import ProviderDataClass, ProviderErrorCode


FIXTURE = Path(__file__).parent / "fixtures" / "provider_contract" / "baostock_daily.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_baostock_descriptor_is_machine_readable_and_not_production_certified() -> None:
    descriptor = BAOSTOCK_DAILY_DESCRIPTOR.as_dict()

    assert descriptor["provider"] == "baostock"
    assert descriptor["dataClasses"] == [ProviderDataClass.HISTORICAL_DATA.value]
    assert descriptor["adjustmentModes"] == ["raw", "qfq", "hfq"]
    assert descriptor["auth"]["mode"] == "anonymous_login"
    assert descriptor["auth"]["required"] is False
    assert descriptor["productionCertified"] is False
    assert descriptor["redistribution"] == "not_asserted_by_adapter"


def test_baostock_daily_fixture_quarantines_bad_numeric_rows_and_keeps_true_zero_volume() -> None:
    fixture = _fixture()
    batch = normalize_baostock_daily_batch(
        fixture["symbol"],
        fixture["rows"],
        adjust=fixture["adjust"],
    )

    units = batch.units.as_dict()
    for key, value in fixture["expectedUnits"].items():
        assert units[key] == value

    assert len(batch.records) == 2
    assert batch.records[0]["volume"] == "0.0"
    assert batch.records[0]["amount"] == "0.0"
    assert all(float(row["open"]) > 0 for row in batch.records)
    assert batch.quarantine_count == 4

    codes = {
        issue.code
        for quarantined in batch.quarantined
        for issue in quarantined.issues
    }
    assert ProviderErrorCode.INVALID_VALUE in codes
    assert ProviderErrorCode.NON_FINITE_VALUE in codes
    assert ProviderErrorCode.MISSING_FIELD in codes
    assert json.loads(json.dumps(batch.as_dict()))["sourceMetadata"]["quarantinedRows"] == 4


def test_baostock_daily_adjustment_mode_is_explicit_in_batch_units() -> None:
    fixture = _fixture()
    batch = normalize_baostock_daily_batch(
        fixture["symbol"],
        fixture["rows"][:2],
        adjust="qfq",
    )

    assert batch.units.adjustment == "qfq"
    assert "qfq" in batch.descriptor.adjustment_modes


def test_legacy_baostock_rows_are_a_compatibility_view(monkeypatch) -> None:
    fixture = _fixture()
    expected_batch = normalize_baostock_daily_batch(
        fixture["symbol"],
        fixture["rows"][:2],
        adjust="raw",
    )

    def fake_batch(*args, **kwargs):
        return expected_batch

    monkeypatch.setattr(
        "app.services.ashare_source_adapters.fetch_baostock_batch",
        fake_batch,
    )

    assert fetch_baostock_rows("600519", start="2026-09-07", end="2026-09-08") == expected_batch.records
