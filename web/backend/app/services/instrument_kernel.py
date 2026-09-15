from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.instruments import InstrumentContractError, InstrumentSpec, ashare_index_instrument
from ..domain.market_rules import market_rule_pack_for, risk_budget_for


@dataclass(frozen=True)
class AssetKernelDescriptor:
    public_asset_class: str
    instrument_asset_class: str
    instrument_subtype: str
    storage_asset_class: str
    benchmark_only: bool
    orderable: bool
    lean_security_type: str | None
    certification_scope: str
    operations: tuple[str, ...]
    execution_certified: bool
    benchmark_instrument_id: str | None = None
    required_market_data_evidence: tuple[str, ...] = ()
    unsupported_reason: str | None = None

    def to_manifest(self, *, venue: str) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "publicAssetClass": self.public_asset_class,
            "instrumentAssetClass": self.instrument_asset_class,
            "instrumentSubtype": self.instrument_subtype,
            "storageAssetClass": self.storage_asset_class,
            "benchmarkOnly": self.benchmark_only,
            "orderable": self.orderable,
            "leanSecurityType": self.lean_security_type,
            "certificationScopeKey": (
                f"{self.instrument_asset_class}:{self.instrument_subtype}:CN:{venue.upper()}"
            ),
            "operations": list(self.operations),
            "executionCertified": self.execution_certified,
            "benchmarkInstrumentId": self.benchmark_instrument_id,
            "requiredMarketDataEvidence": list(self.required_market_data_evidence),
            "unsupportedReason": self.unsupported_reason,
        }


ASSET_KERNEL_DESCRIPTORS: dict[str, AssetKernelDescriptor] = {
    "equity": AssetKernelDescriptor(
        public_asset_class="equity",
        instrument_asset_class="equity",
        instrument_subtype="common_stock",
        storage_asset_class="equity",
        benchmark_only=False,
        orderable=True,
        lean_security_type="Equity",
        certification_scope="cn_common_stock_v1",
        operations=("market_data", "benchmark_constituent", "backtest", "paper"),
        execution_certified=True,
    ),
    "etf": AssetKernelDescriptor(
        public_asset_class="etf",
        instrument_asset_class="equity",
        instrument_subtype="etf",
        storage_asset_class="equity",
        benchmark_only=False,
        orderable=True,
        lean_security_type="Equity",
        certification_scope="cn_stock_etf_v1",
        operations=("market_data", "benchmark", "research_validation", "lean_config_validation"),
        execution_certified=False,
        benchmark_instrument_id="CN.XSHG.INDEX.000300",
        required_market_data_evidence=(
            "etf_instrument_master",
            "etf_daily",
            "etf_adjustment_factor",
            "trading_calendar",
        ),
        unsupported_reason="etf_execution_adapter_not_certified",
    ),
    "index": AssetKernelDescriptor(
        public_asset_class="index",
        instrument_asset_class="index",
        instrument_subtype="index",
        storage_asset_class="index",
        benchmark_only=True,
        orderable=False,
        lean_security_type="Index",
        certification_scope="cn_index_benchmark_v1",
        operations=("market_data", "benchmark"),
        execution_certified=False,
        unsupported_reason="benchmark_only_non_orderable",
    ),
    "future": AssetKernelDescriptor(
        public_asset_class="future",
        instrument_asset_class="future",
        instrument_subtype="future_contract",
        storage_asset_class="future",
        benchmark_only=False,
        orderable=True,
        lean_security_type="Future",
        certification_scope="unregistered",
        operations=("market_data",),
        execution_certified=False,
        unsupported_reason="future_market_rule_pack_not_certified",
    ),
    "option": AssetKernelDescriptor(
        public_asset_class="option",
        instrument_asset_class="option",
        instrument_subtype="option",
        storage_asset_class="option",
        benchmark_only=False,
        orderable=True,
        lean_security_type="Option",
        certification_scope="unregistered",
        operations=("metadata",),
        execution_certified=False,
        unsupported_reason="option_market_rule_pack_not_certified",
    ),
    "convertible_bond": AssetKernelDescriptor(
        public_asset_class="convertible_bond",
        instrument_asset_class="bond",
        instrument_subtype="convertible_bond",
        storage_asset_class="convertible_bond",
        benchmark_only=False,
        orderable=True,
        lean_security_type=None,
        certification_scope="unregistered",
        operations=("market_data",),
        execution_certified=False,
        unsupported_reason="convertible_bond_execution_adapter_not_certified",
    ),
}


def asset_kernel_descriptor(asset_class: str, *, venue: str = "XSHG") -> dict[str, Any]:
    key = str(asset_class or "").strip().lower()
    if key == "cbond":
        key = "convertible_bond"
    try:
        descriptor = ASSET_KERNEL_DESCRIPTORS[key]
    except KeyError as exc:
        raise InstrumentContractError("asset_kernel_unregistered", f"unknown asset class: {asset_class!r}") from exc
    return descriptor.to_manifest(venue=venue)


def lean_security_mapping(instrument: InstrumentSpec) -> dict[str, Any]:
    descriptor = next(
        (
            item
            for item in ASSET_KERNEL_DESCRIPTORS.values()
            if item.instrument_asset_class == instrument.asset_class
            and item.instrument_subtype == instrument.subtype
        ),
        None,
    )
    if descriptor is None or descriptor.lean_security_type is None:
        raise InstrumentContractError(
            "lean_mapping_unsupported",
            f"no LEAN security mapping for {instrument.asset_class}/{instrument.subtype}",
        )
    symbol = instrument.resolve_alias("lean", purpose="execution") if instrument.tradable else instrument.canonical_symbol
    return {
        "securityType": descriptor.lean_security_type,
        "market": "China" if instrument.market == "CN" else instrument.market,
        "symbol": symbol,
        "instrumentId": instrument.instrument_id,
        "instrumentSubtype": instrument.subtype,
        "currency": instrument.currency,
        "settlementCurrency": instrument.settlement_currency,
        "calendarId": instrument.calendar_id,
        "marketRulePackId": instrument.market_rule_pack_id,
        "normalizationMode": "Raw",
        "orderable": descriptor.orderable and instrument.tradable,
    }


def validate_etf_market_data_coverage(evidence: dict[str, Any]) -> dict[str, Any]:
    """Require ETF-subtype lineage instead of borrowing generic equity storage evidence."""

    if not isinstance(evidence, dict):
        raise InstrumentContractError(
            "etf_market_data_evidence_required",
            "ETF validation requires explicit subtype market-data evidence",
        )
    if str(evidence.get("instrumentSubtype") or "").lower() != "etf":
        raise InstrumentContractError(
            "etf_market_data_scope_mismatch",
            "ETF market-data evidence must be scoped to instrumentSubtype=etf",
        )
    datasets = evidence.get("datasets")
    if not isinstance(datasets, dict):
        raise InstrumentContractError(
            "etf_market_data_evidence_required",
            "ETF market-data evidence must contain dataset coverage",
        )
    required = ASSET_KERNEL_DESCRIPTORS["etf"].required_market_data_evidence
    missing: list[str] = []
    normalized: dict[str, dict[str, Any]] = {}
    for key in required:
        item = datasets.get(key)
        if not isinstance(item, dict) or item.get("status") != "covered" or not item.get("lineageId"):
            missing.append(key)
            continue
        normalized[key] = {
            "status": "covered",
            "lineageId": str(item["lineageId"]),
            "source": str(item.get("source") or ""),
        }
    if missing:
        raise InstrumentContractError(
            "etf_market_data_incomplete",
            f"ETF subtype market-data coverage is incomplete: missing={sorted(missing)}",
        )
    return {
        "instrumentSubtype": "etf",
        "storageAssetClass": "equity",
        "sharedStorageCarrierOnly": True,
        "datasets": normalized,
    }


def etf_validation_kernel(
    instrument: InstrumentSpec,
    *,
    as_of: str,
    market_data_evidence: dict[str, Any],
) -> dict[str, Any]:
    if instrument.asset_class != "equity" or instrument.subtype != "etf":
        raise InstrumentContractError("etf_contract_required", "ETF validation requires equity/etf instrument semantics")
    if instrument.currency != "CNY" or instrument.settlement_currency != "CNY":
        raise InstrumentContractError(
            "cross_currency_not_certified",
            "the first ETF validation slice is CNY/CNY only",
        )
    coverage = validate_etf_market_data_coverage(market_data_evidence)
    rules = market_rule_pack_for(instrument, as_of=as_of)
    risk = risk_budget_for(instrument)
    mapping = lean_security_mapping(instrument)
    benchmark = ashare_index_instrument("000300.SH")
    return {
        "schemaVersion": 1,
        "instrument": instrument.to_manifest(),
        "marketRulePack": rules.to_manifest(),
        "marketDataCoverage": coverage,
        "benchmark": {
            **benchmark.to_manifest(),
            "role": "performance_reference",
        },
        "lean": mapping,
        "riskBudget": risk.to_manifest(),
        "executionCertified": False,
        "certificationScope": "etf_validation_only",
    }


def require_execution_certified(instrument: InstrumentSpec, *, as_of: str) -> dict[str, Any]:
    descriptor = next(
        (
            item
            for item in ASSET_KERNEL_DESCRIPTORS.values()
            if item.instrument_asset_class == instrument.asset_class
            and item.instrument_subtype == instrument.subtype
        ),
        None,
    )
    if descriptor is None or not descriptor.execution_certified:
        reason = descriptor.unsupported_reason if descriptor else "asset_kernel_unregistered"
        raise InstrumentContractError(
            "asset_execution_not_certified",
            f"asset execution is not certified: {reason}",
        )
    instrument.assert_orderable(as_of=as_of)
    if instrument.currency != "CNY" or instrument.settlement_currency != "CNY":
        raise InstrumentContractError(
            "cross_currency_not_certified",
            "current execution certification is CNY/CNY only",
        )
    rules = market_rule_pack_for(instrument, as_of=as_of)
    return {
        "instrument": instrument.to_manifest(),
        "marketRulePack": rules.to_manifest(),
        "lean": lean_security_mapping(instrument),
    }
