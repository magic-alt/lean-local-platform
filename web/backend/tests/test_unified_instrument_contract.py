from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path

import pytest

from app.domain.instruments import (
    ContinuousFutureSpec,
    FutureInstrumentSpec,
    InstrumentContractError,
    InstrumentSpec,
    OptionInstrumentSpec,
    SymbolAlias,
    ashare_etf_instrument,
    ashare_index_instrument,
    instrument_contract_id,
    legacy_ashare_instrument,
)
from app.domain.market_rules import market_rule_pack_for
from app.services.instrument_identity import instrument_id_for
from app.services import asset_capabilities
from app.services.instrument_kernel import (
    asset_kernel_descriptor,
    etf_validation_kernel,
    lean_security_mapping,
    require_execution_certified,
)


FIXTURE = Path(__file__).parent / "fixtures" / "instrument_contracts" / "v1_golden.json"

ETF_MARKET_DATA_EVIDENCE = {
    "instrumentSubtype": "etf",
    "datasets": {
        "etf_instrument_master": {
            "status": "covered",
            "lineageId": "fixture-etf-master-v1",
            "source": "recorded_fixture",
        },
        "etf_daily": {
            "status": "covered",
            "lineageId": "fixture-etf-daily-v1",
            "source": "recorded_fixture",
        },
        "etf_adjustment_factor": {
            "status": "covered",
            "lineageId": "fixture-etf-adjust-v1",
            "source": "recorded_fixture",
        },
        "trading_calendar": {
            "status": "covered",
            "lineageId": "fixture-cn-calendar-v1",
            "source": "recorded_fixture",
        },
    },
}


def test_shared_contract_schema_is_valid_json_and_requires_core_boundaries():
    schema_path = (
        Path(__file__).parents[3]
        / "config"
        / "contracts"
        / "instrument-market-rules.v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["$schema"].endswith("2020-12/schema")
    assert schema["required"] == ["instrument", "marketRulePack"]
    instrument_required = set(schema["properties"]["instrument"]["required"])
    assert {"instrument_id", "subtype", "currency", "price_tick", "quantity_unit"} <= instrument_required
    rules_required = set(schema["properties"]["marketRulePack"]["required"])
    assert {"effective_from", "timezone", "settlement", "fees"} <= rules_required


def test_golden_instrument_and_market_rule_fixture():
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    stock = legacy_ashare_instrument("600000.SH")
    etf = ashare_etf_instrument("510300.SH", product_profile="stock_etf_t1")
    index = ashare_index_instrument("000300.SH")

    assert instrument_id_for(expected["legacyIdentity"]["symbol"]) == expected["legacyIdentity"]["legacyUuid"]
    assert stock.to_manifest() == expected["stock"]["instrument"]
    assert market_rule_pack_for(stock, as_of="2026-09-15").to_manifest() == expected["stock"]["rule"]
    assert etf.to_manifest() == expected["etf"]["instrument"]
    assert market_rule_pack_for(etf, as_of="2026-09-15").to_manifest() == expected["etf"]["rule"]
    assert asset_kernel_descriptor("etf", venue="XSHG") == expected["etf"]["capability"]
    assert index.to_manifest() == expected["index"]["instrument"]
    assert market_rule_pack_for(index, as_of="2026-09-15").to_manifest() == expected["index"]["rule"]


def _future(*, expiry: str = "2026-12-18", multiplier: str = "300") -> FutureInstrumentSpec:
    instrument_id = instrument_contract_id(
        market="CN",
        venue="CFFEX",
        subtype="future_contract",
        canonical_symbol="IF2612",
        expiry=expiry,
    )
    return FutureInstrumentSpec(
        instrument_id=instrument_id,
        canonical_symbol="IF2612",
        asset_class="future",
        subtype="future_contract",
        market="CN",
        venue="CFFEX",
        currency="CNY",
        settlement_currency="CNY",
        calendar_id="cn_cffex_v1",
        price_tick="0.2",
        quantity_increment="1",
        quantity_unit="contract",
        lot_size="1",
        tradable=True,
        market_rule_pack_id="unsupported_until_certified",
        aliases=(SymbolAlias(provider="lean", symbol="IF2612", purpose="execution"),),
        underlying_id="CN.XSHG.INDEX.000300",
        expiry=expiry,
        multiplier=multiplier,
    )


def _option(*, strike: str, right: str) -> OptionInstrumentSpec:
    instrument_id = instrument_contract_id(
        market="CN",
        venue="CFFEX",
        subtype="option",
        canonical_symbol="IO2612",
        expiry="2026-12-18",
        strike=strike,
        right=right,
    )
    return OptionInstrumentSpec(
        instrument_id=instrument_id,
        canonical_symbol="IO2612",
        asset_class="option",
        subtype="option",
        market="CN",
        venue="CFFEX",
        currency="CNY",
        settlement_currency="CNY",
        calendar_id="cn_cffex_v1",
        price_tick="0.2",
        quantity_increment="1",
        quantity_unit="contract",
        lot_size="1",
        tradable=True,
        market_rule_pack_id="unsupported_until_certified",
        aliases=(SymbolAlias(provider="lean", symbol="IO2612", purpose="execution"),),
        underlying_id="CN.XSHG.INDEX.000300",
        expiry="2026-12-18",
        multiplier="100",
        strike=strike,
        right=right,
        exercise_style="european",
        settlement_style="cash",
    )


def test_shared_qlib_identity_format_and_legacy_uuid_compatibility():
    stock = legacy_ashare_instrument("600000.SH")
    etf = ashare_etf_instrument("510300.SH", product_profile="stock_etf_t1")

    assert stock.instrument_id == "CN.XSHG.EQUITY.600000"
    assert etf.instrument_id == "CN.XSHG.ETF.510300"
    assert stock.resolve_alias("qlib") == "SH600000"
    assert stock.resolve_alias("tushare") == "600000.SH"
    assert etf.resolve_alias("qlib") == "SH510300"
    assert instrument_id_for("600000") == "1b2c42b6-401f-547a-bb2e-7762a5a389ec"


def test_same_ticker_different_market_is_not_the_same_instrument():
    sh = instrument_contract_id(
        market="CN", venue="XSHG", subtype="common_stock", canonical_symbol="000001"
    )
    sz = instrument_contract_id(
        market="CN", venue="XSHE", subtype="common_stock", canonical_symbol="000001"
    )
    hk = instrument_contract_id(
        market="HK", venue="XHKG", subtype="common_stock", canonical_symbol="000001"
    )
    assert len({sh, sz, hk}) == 3


def test_alias_windows_preserve_identity_across_rename_and_delisting():
    spec = replace(
        legacy_ashare_instrument("600000.SH", listed_from="1999-11-10", listed_to="2030-01-01"),
        aliases=(
            SymbolAlias(provider="broker", symbol="OLD600000", valid_to="2026-06-30", purpose="execution"),
            SymbolAlias(provider="broker", symbol="NEW600000", valid_from="2026-07-01", purpose="execution"),
        ),
    )
    assert spec.resolve_alias("broker", as_of="2026-06-30", purpose="execution") == "OLD600000"
    assert spec.resolve_alias("broker", as_of="2026-07-01", purpose="execution") == "NEW600000"
    assert spec.instrument_id == "CN.XSHG.EQUITY.600000"


def test_future_expiry_and_option_strike_right_are_identity_dimensions():
    dec = _future(expiry="2026-12-18")
    mar = _future(expiry="2027-03-19")
    call_4000 = _option(strike="4000", right="call")
    put_4000 = _option(strike="4000", right="put")
    call_4100 = _option(strike="4100", right="call")

    assert dec.instrument_id != mar.instrument_id
    assert len({call_4000.instrument_id, put_4000.instrument_id, call_4100.instrument_id}) == 3


def test_continuous_future_is_explicitly_non_orderable():
    continuous = ContinuousFutureSpec(
        instrument_id=instrument_contract_id(
            market="CN",
            venue="CFFEX",
            subtype="future_continuous",
            canonical_symbol="IF",
            identity_kind="continuous",
        ),
        canonical_symbol="IF",
        asset_class="future",
        subtype="future_continuous",
        market="CN",
        venue="CFFEX",
        currency="CNY",
        settlement_currency="CNY",
        calendar_id="cn_cffex_v1",
        price_tick="0.2",
        quantity_increment="1",
        quantity_unit="contract",
        lot_size="1",
        tradable=False,
        market_rule_pack_id="unsupported_until_certified",
        identity_kind="continuous",
        continuous_series=True,
        underlying_id="CN.XSHG.INDEX.000300",
        multiplier="300",
    )
    with pytest.raises(InstrumentContractError, match="not orderable"):
        continuous.assert_orderable()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("currency", ""),
        ("settlement_currency", ""),
        ("price_tick", "0"),
        ("quantity_increment", "NaN"),
        ("lot_size", "0"),
    ],
)
def test_incomplete_cash_instrument_contract_fails_closed(field: str, value: str):
    payload = legacy_ashare_instrument("600000.SH").__dict__.copy()
    payload[field] = value
    with pytest.raises(InstrumentContractError):
        InstrumentSpec(**payload)


def test_derivative_multiplier_and_expiry_are_required():
    payload = _future().__dict__.copy()
    payload["multiplier"] = "0"
    with pytest.raises(InstrumentContractError, match="multiplier"):
        FutureInstrumentSpec(**payload)

    payload = _future().__dict__.copy()
    payload["expiry"] = ""
    with pytest.raises(InstrumentContractError, match="expiry"):
        FutureInstrumentSpec(**payload)


def test_etf_rule_pack_is_independent_from_common_stock_and_exact_decimal_units():
    stock = legacy_ashare_instrument("600000.SH")
    etf = ashare_etf_instrument("510300.SH", product_profile="stock_etf_t1")
    stock_rules = market_rule_pack_for(stock, as_of="2026-09-15")
    etf_rules = market_rule_pack_for(etf, as_of="2026-09-15")

    assert stock.price_tick == Decimal("0.01")
    assert etf.price_tick == Decimal("0.001")
    assert stock_rules.subtype == "common_stock"
    assert etf_rules.subtype == "etf"
    assert stock_rules.rule_pack_id != etf_rules.rule_pack_id
    assert stock_rules.fees[0].applies is True
    assert stock_rules.fees[0].rate == Decimal("0.0005")
    assert etf_rules.fees[0].applies is False
    assert etf_rules.fees[0].rate == Decimal("0")

    with pytest.raises(InstrumentContractError, match="does not match"):
        stock_rules.assert_matches(etf)


def test_current_rules_are_not_retroactively_applied_to_uncovered_history():
    stock = legacy_ashare_instrument("600000.SH")
    with pytest.raises(InstrumentContractError, match="no certified MarketRulePack"):
        market_rule_pack_for(stock, as_of="2020-01-02")


def test_etf_validation_kernel_has_separate_lean_mapping_rule_pack_and_risk_budget():
    etf = ashare_etf_instrument("510300.SH", product_profile="stock_etf_t1")
    payload = etf_validation_kernel(
        etf,
        as_of="2026-09-15",
        market_data_evidence=ETF_MARKET_DATA_EVIDENCE,
    )

    assert payload["executionCertified"] is False
    assert payload["instrument"]["subtype"] == "etf"
    assert payload["marketRulePack"]["subtype"] == "etf"
    assert payload["lean"]["securityType"] == "Equity"
    assert payload["lean"]["instrumentSubtype"] == "etf"
    assert payload["riskBudget"]["profile_id"] == "cn_stock_etf_research_v1"
    assert payload["riskBudget"]["max_single_instrument_weight"] == "0.25"
    assert payload["benchmark"]["instrument_id"] == "CN.XSHG.INDEX.000300"
    assert payload["benchmark"]["tradable"] is False
    assert payload["marketDataCoverage"]["instrumentSubtype"] == "etf"
    assert payload["marketDataCoverage"]["sharedStorageCarrierOnly"] is True

    with pytest.raises(InstrumentContractError, match="not certified"):
        require_execution_certified(etf, as_of="2026-09-15")


def test_etf_validation_requires_subtype_specific_market_data_lineage():
    etf = ashare_etf_instrument("510300.SH", product_profile="stock_etf_t1")
    incomplete = {
        "instrumentSubtype": "etf",
        "datasets": {
            "etf_daily": {
                "status": "covered",
                "lineageId": "fixture-etf-daily-v1",
                "source": "recorded_fixture",
            }
        },
    }
    with pytest.raises(InstrumentContractError, match="coverage is incomplete"):
        etf_validation_kernel(etf, as_of="2026-09-15", market_data_evidence=incomplete)

    wrong_scope = {**ETF_MARKET_DATA_EVIDENCE, "instrumentSubtype": "common_stock"}
    with pytest.raises(InstrumentContractError, match="instrumentSubtype=etf"):
        etf_validation_kernel(etf, as_of="2026-09-15", market_data_evidence=wrong_scope)


def test_cross_currency_etf_cannot_borrow_cn_execution_certification():
    etf = replace(
        ashare_etf_instrument("510300.SH", product_profile="stock_etf_t1"),
        currency="USD",
        settlement_currency="USD",
    )
    with pytest.raises(InstrumentContractError, match="CNY/CNY"):
        etf_validation_kernel(
            etf,
            as_of="2026-09-15",
            market_data_evidence=ETF_MARKET_DATA_EVIDENCE,
        )


def test_etf_requires_explicit_certified_product_profile():
    with pytest.raises(InstrumentContractError, match="stock_etf_t1"):
        ashare_etf_instrument("510300.SH", product_profile="cross_border_etf_t0")


def test_alias_representation_property_keeps_provider_neutral_identity_stable():
    for offset in range(50):
        sh_code = f"{600000 + offset:06d}"
        sz_code = f"{1 + offset:06d}"
        assert (
            legacy_ashare_instrument(f"SH{sh_code}").instrument_id
            == legacy_ashare_instrument(f"{sh_code}.SH").instrument_id
        )
        assert (
            legacy_ashare_instrument(f"SZ{sz_code}").instrument_id
            == legacy_ashare_instrument(f"{sz_code}.SZ").instrument_id
        )
        for instrument in (
            legacy_ashare_instrument(f"{sh_code}.SH"),
            legacy_ashare_instrument(f"{sz_code}.SZ"),
        ):
            manifest = instrument.to_manifest()
            assert Decimal(manifest["price_tick"]) == instrument.price_tick
            assert Decimal(manifest["quantity_increment"]) == instrument.quantity_increment
            assert Decimal(manifest["lot_size"]) == instrument.lot_size


def test_index_is_benchmark_only_and_non_orderable():
    index = ashare_index_instrument("000300.SH")
    descriptor = asset_kernel_descriptor("index", venue="XSHG")
    mapping = lean_security_mapping(index)

    assert descriptor["benchmarkOnly"] is True
    assert descriptor["orderable"] is False
    assert mapping["securityType"] == "Index"
    assert mapping["orderable"] is False
    with pytest.raises(InstrumentContractError, match="not tradable"):
        index.assert_orderable()


def test_etf_capability_descriptor_keeps_storage_and_certification_separate():
    descriptor = asset_kernel_descriptor("etf", venue="XSHG")
    stock = asset_kernel_descriptor("equity", venue="XSHG")

    assert descriptor["instrumentAssetClass"] == "equity"
    assert descriptor["instrumentSubtype"] == "etf"
    assert descriptor["storageAssetClass"] == "equity"
    assert descriptor["executionCertified"] is False
    assert descriptor["certificationScopeKey"] != stock["certificationScopeKey"]
    assert descriptor["unsupportedReason"] == "etf_execution_adapter_not_certified"


def test_local_capability_does_not_promote_shared_equity_carrier_to_etf(monkeypatch):
    def fake_matching_scopes(**scope):
        if scope.get("asset_class") == "equity" and scope.get("resolution") == "daily":
            return [{"asset_class": "equity"}]
        return []

    monkeypatch.setattr(asset_capabilities.market_lake, "matching_scopes", fake_matching_scopes)
    items = asset_capabilities._local_lake_capabilities()
    etf = next(item for item in items if item["asset_class"] == "etf")

    assert etf["state"] == "unavailable"
    assert etf["executable_reason"] == "instrument_subtype_evidence_missing"
    assert etf["instrument_contract"]["instrumentSubtype"] == "etf"
    assert etf["instrument_contract"]["storageAssetClass"] == "equity"
    assert etf["evidence"]["sharedStorageScopeAvailable"] is True
    assert etf["evidence"]["subtypeEvidenceRequired"] is True


def test_capability_payload_exposes_one_machine_readable_instrument_contract(monkeypatch):
    item = {
        "asset_class": "etf",
        "market": "china",
        "venue": "china",
        "resolution": "daily",
        "data_type": "trade",
        "state": "unavailable",
        "metadata_count": 0,
        "canonical_row_count": 0,
        "executable_reason": "instrument_subtype_evidence_missing",
        "evidence": {"schemaVersion": 2},
    }
    monkeypatch.setattr(
        asset_capabilities,
        "refresh_capabilities",
        lambda: [asset_capabilities._decorate(item)],
    )
    payload = asset_capabilities.capability_payload()

    assert payload["schemaVersion"] == 2
    assert payload["instrumentSchemaVersion"] == 1
    assert payload["items"][0]["instrument_contract"]["certificationScopeKey"].startswith("equity:etf:")
