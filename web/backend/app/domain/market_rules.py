from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from .instruments import InstrumentContractError, InstrumentSpec


MARKET_RULE_SCHEMA_VERSION = 1


def _decimal(value: Decimal | str | int, field_name: str, *, allow_zero: bool = False) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InstrumentContractError("invalid_decimal", f"{field_name} must be decimal") from exc
    if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
        qualifier = "non-negative" if allow_zero else "positive"
        raise InstrumentContractError("invalid_decimal", f"{field_name} must be finite and {qualifier}")
    return number


def _date(value: str | None, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise InstrumentContractError("invalid_date", f"{field_name} must be an ISO date") from exc
    return text


def _d(value: Decimal) -> str:
    return format(value, "f")


@dataclass(frozen=True, kw_only=True)
class TradingSession:
    open_local: str
    close_local: str

    def to_manifest(self) -> dict[str, str]:
        return {"open_local": self.open_local, "close_local": self.close_local}


@dataclass(frozen=True, kw_only=True)
class SettlementRule:
    cash_cycle: str
    position_cycle: str
    sellable_cycle: str

    def to_manifest(self) -> dict[str, str]:
        return {
            "cash_cycle": self.cash_cycle,
            "position_cycle": self.position_cycle,
            "sellable_cycle": self.sellable_cycle,
        }


@dataclass(frozen=True, kw_only=True)
class FeeRule:
    code: str
    side: str
    rate: Decimal | str
    applies: bool
    source: str

    def __post_init__(self) -> None:
        side = str(self.side).strip().lower()
        if side not in {"buy", "sell", "both"}:
            raise InstrumentContractError("invalid_fee_side", f"unsupported fee side: {self.side!r}")
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "rate", _decimal(self.rate, "rate", allow_zero=True))
        if not str(self.code).strip() or not str(self.source).strip():
            raise InstrumentContractError("missing_field", "fee code and source are required")

    def to_manifest(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "side": self.side,
            "rate": _d(self.rate),
            "applies": self.applies,
            "source": self.source,
        }


@dataclass(frozen=True, kw_only=True)
class CorporateActionRule:
    adjustment_mode: str
    effective_time: str
    source: str

    def to_manifest(self) -> dict[str, str]:
        return {
            "adjustment_mode": self.adjustment_mode,
            "effective_time": self.effective_time,
            "source": self.source,
        }


@dataclass(frozen=True, kw_only=True)
class RiskBudgetProfile:
    profile_id: str
    asset_class: str
    subtype: str
    max_gross_exposure: Decimal | str
    max_single_instrument_weight: Decimal | str
    min_cash_weight: Decimal | str
    shorting_allowed: bool = False
    leverage_allowed: bool = False
    certification_scope: str = "research_validation_only"

    def __post_init__(self) -> None:
        gross = _decimal(self.max_gross_exposure, "max_gross_exposure")
        single = _decimal(self.max_single_instrument_weight, "max_single_instrument_weight")
        cash = _decimal(self.min_cash_weight, "min_cash_weight", allow_zero=True)
        if gross > Decimal("1"):
            raise InstrumentContractError("invalid_risk_budget", "max_gross_exposure cannot exceed 1 without leverage")
        if single > gross:
            raise InstrumentContractError("invalid_risk_budget", "single-instrument weight cannot exceed gross exposure")
        if cash >= Decimal("1"):
            raise InstrumentContractError("invalid_risk_budget", "min_cash_weight must be below 1")
        object.__setattr__(self, "max_gross_exposure", gross)
        object.__setattr__(self, "max_single_instrument_weight", single)
        object.__setattr__(self, "min_cash_weight", cash)

    def to_manifest(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "asset_class": self.asset_class,
            "subtype": self.subtype,
            "max_gross_exposure": _d(self.max_gross_exposure),
            "max_single_instrument_weight": _d(self.max_single_instrument_weight),
            "min_cash_weight": _d(self.min_cash_weight),
            "shorting_allowed": self.shorting_allowed,
            "leverage_allowed": self.leverage_allowed,
            "certification_scope": self.certification_scope,
        }


@dataclass(frozen=True, kw_only=True)
class MarketRulePack:
    rule_pack_id: str
    version: int
    asset_class: str
    subtype: str
    market: str
    venue: str
    calendar_id: str
    timezone: str
    effective_from: str
    effective_to: str | None
    source: str
    sessions: tuple[TradingSession, ...]
    settlement: SettlementRule
    round_lot: Decimal | str
    quantity_increment: Decimal | str
    price_limit_policy: str
    suspension_policy: str
    corporate_action: CorporateActionRule
    fees: tuple[FeeRule, ...] = field(default_factory=tuple)
    benchmark_only: bool = False
    margin_policy: str = "unsupported"
    borrow_short_policy: str = "unsupported"
    roll_policy: str = "not_applicable"
    exercise_assignment_policy: str = "not_applicable"

    def __post_init__(self) -> None:
        if self.version <= 0:
            raise InstrumentContractError("invalid_rule_version", "market rule version must be positive")
        try:
            ZoneInfo(self.timezone)
        except Exception as exc:
            raise InstrumentContractError("invalid_timezone", f"unknown timezone: {self.timezone}") from exc
        start = _date(self.effective_from, "effective_from")
        end = _date(self.effective_to, "effective_to")
        if not start:
            raise InstrumentContractError("missing_field", "effective_from is required")
        if end and start > end:
            raise InstrumentContractError("invalid_rule_window", "effective_from must not be after effective_to")
        object.__setattr__(self, "effective_from", start)
        object.__setattr__(self, "effective_to", end)
        object.__setattr__(self, "round_lot", _decimal(self.round_lot, "round_lot"))
        object.__setattr__(self, "quantity_increment", _decimal(self.quantity_increment, "quantity_increment"))
        if not self.sessions:
            raise InstrumentContractError("missing_sessions", "at least one trading session is required")

    def active_on(self, as_of: str) -> bool:
        day = _date(as_of, "as_of")
        return self.effective_from <= day and (self.effective_to is None or day <= self.effective_to)

    def assert_matches(self, instrument: InstrumentSpec) -> None:
        if instrument.asset_class != self.asset_class or instrument.subtype != self.subtype:
            raise InstrumentContractError(
                "rule_pack_asset_mismatch",
                f"{self.rule_pack_id} does not match {instrument.asset_class}/{instrument.subtype}",
            )
        if instrument.market != self.market or instrument.venue != self.venue:
            raise InstrumentContractError(
                "rule_pack_market_mismatch",
                f"{self.rule_pack_id} does not match {instrument.market}/{instrument.venue}",
            )
        if instrument.calendar_id != self.calendar_id:
            raise InstrumentContractError(
                "rule_pack_calendar_mismatch",
                f"{self.rule_pack_id} calendar does not match {instrument.calendar_id}",
            )
        if instrument.lot_size != self.round_lot or instrument.quantity_increment != self.quantity_increment:
            raise InstrumentContractError(
                "rule_pack_unit_mismatch",
                f"{self.rule_pack_id} quantity rules do not match instrument units",
            )

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": MARKET_RULE_SCHEMA_VERSION,
            "rule_pack_id": self.rule_pack_id,
            "version": self.version,
            "asset_class": self.asset_class,
            "subtype": self.subtype,
            "market": self.market,
            "venue": self.venue,
            "calendar_id": self.calendar_id,
            "timezone": self.timezone,
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "source": self.source,
            "sessions": [session.to_manifest() for session in self.sessions],
            "settlement": self.settlement.to_manifest(),
            "round_lot": _d(self.round_lot),
            "quantity_increment": _d(self.quantity_increment),
            "price_limit_policy": self.price_limit_policy,
            "suspension_policy": self.suspension_policy,
            "corporate_action": self.corporate_action.to_manifest(),
            "fees": [fee.to_manifest() for fee in self.fees],
            "benchmark_only": self.benchmark_only,
            "margin_policy": self.margin_policy,
            "borrow_short_policy": self.borrow_short_policy,
            "roll_policy": self.roll_policy,
            "exercise_assignment_policy": self.exercise_assignment_policy,
        }


_CN_SESSIONS = (
    TradingSession(open_local="09:30:00", close_local="11:30:00"),
    TradingSession(open_local="13:00:00", close_local="15:00:00"),
)
_T1 = SettlementRule(cash_cycle="T+1", position_cycle="T+0", sellable_cycle="T+1")
_CORP_ACTION = CorporateActionRule(
    adjustment_mode="provider_factor",
    effective_time="exchange_effective_date",
    source="provider_corporate_action_and_adjustment_factor",
)


def _stock_pack(venue: str) -> MarketRulePack:
    venue_key = venue.upper()
    return MarketRulePack(
        rule_pack_id=f"cn_{venue_key.lower()}_common_stock_v1",
        version=1,
        asset_class="equity",
        subtype="common_stock",
        market="CN",
        venue=venue_key,
        calendar_id="cn_stock_v1",
        timezone="Asia/Shanghai",
        effective_from="2023-08-28",
        effective_to=None,
        source="platform-versioned-cn-equity-rules",
        sessions=_CN_SESSIONS,
        settlement=_T1,
        round_lot="100",
        quantity_increment="1",
        price_limit_policy="daily_reference_data_required",
        suspension_policy="daily_trade_status_required",
        corporate_action=_CORP_ACTION,
        fees=(
            FeeRule(
                code="stock_stamp_tax",
                side="sell",
                rate="0.0005",
                applies=True,
                source="versioned_statutory_tax_profile",
            ),
        ),
    )


def _etf_pack(venue: str) -> MarketRulePack:
    venue_key = venue.upper()
    return MarketRulePack(
        rule_pack_id=f"cn_{venue_key.lower()}_stock_etf_v1",
        version=1,
        asset_class="equity",
        subtype="etf",
        market="CN",
        venue=venue_key,
        calendar_id="cn_stock_v1",
        timezone="Asia/Shanghai",
        effective_from="2023-08-28",
        effective_to=None,
        source="platform-versioned-cn-stock-etf-rules",
        sessions=_CN_SESSIONS,
        settlement=_T1,
        round_lot="100",
        quantity_increment="1",
        price_limit_policy="daily_reference_data_required",
        suspension_policy="daily_trade_status_required",
        corporate_action=_CORP_ACTION,
        fees=(
            FeeRule(
                code="stock_stamp_tax",
                side="sell",
                rate="0",
                applies=False,
                source="etf_tax_profile_not_stock_transfer",
            ),
        ),
        borrow_short_policy="separate_instrument_entitlement_required",
    )


def _index_pack(venue: str) -> MarketRulePack:
    venue_key = venue.upper()
    return MarketRulePack(
        rule_pack_id=f"cn_{venue_key.lower()}_index_benchmark_v1",
        version=1,
        asset_class="index",
        subtype="index",
        market="CN",
        venue=venue_key,
        calendar_id="cn_stock_v1",
        timezone="Asia/Shanghai",
        effective_from="2005-04-08",
        effective_to=None,
        source="platform-benchmark-only-index-rules",
        sessions=_CN_SESSIONS,
        settlement=SettlementRule(cash_cycle="not_applicable", position_cycle="not_applicable", sellable_cycle="not_applicable"),
        round_lot="1",
        quantity_increment="1",
        price_limit_policy="not_applicable",
        suspension_policy="benchmark_availability_required",
        corporate_action=CorporateActionRule(
            adjustment_mode="index_methodology",
            effective_time="provider_available_at",
            source="index_provider_methodology",
        ),
        benchmark_only=True,
    )


MARKET_RULE_PACKS: tuple[MarketRulePack, ...] = (
    _stock_pack("XSHG"),
    _stock_pack("XSHE"),
    _stock_pack("XBSE"),
    _etf_pack("XSHG"),
    _etf_pack("XSHE"),
    _index_pack("XSHG"),
    _index_pack("XSHE"),
)


RISK_BUDGETS: dict[tuple[str, str], RiskBudgetProfile] = {
    ("equity", "etf"): RiskBudgetProfile(
        profile_id="cn_stock_etf_research_v1",
        asset_class="equity",
        subtype="etf",
        max_gross_exposure="1",
        max_single_instrument_weight="0.25",
        min_cash_weight="0",
        shorting_allowed=False,
        leverage_allowed=False,
    ),
}


def market_rule_pack_for(instrument: InstrumentSpec, *, as_of: str) -> MarketRulePack:
    candidates = [
        item
        for item in MARKET_RULE_PACKS
        if item.asset_class == instrument.asset_class
        and item.subtype == instrument.subtype
        and item.market == instrument.market
        and (item.venue == instrument.venue or (item.benchmark_only and instrument.subtype == "index"))
        and item.active_on(as_of)
    ]
    if not candidates:
        raise InstrumentContractError(
            "market_rule_pack_missing",
            f"no certified MarketRulePack for {instrument.instrument_id} at {as_of}",
        )
    candidates.sort(key=lambda item: item.version, reverse=True)
    selected = candidates[0]
    if instrument.market_rule_pack_id != selected.rule_pack_id:
        # Legacy mappers bind the current rule-pack family. As-of resolution is
        # still versioned; older dates may legitimately select the predecessor.
        family = instrument.market_rule_pack_id.rsplit("_v", 1)[0]
        if not selected.rule_pack_id.startswith(family):
            raise InstrumentContractError(
                "market_rule_pack_binding_mismatch",
                f"{instrument.instrument_id} is bound to {instrument.market_rule_pack_id}, got {selected.rule_pack_id}",
            )
    selected.assert_matches(instrument)
    return selected


def risk_budget_for(instrument: InstrumentSpec) -> RiskBudgetProfile:
    try:
        return RISK_BUDGETS[(instrument.asset_class, instrument.subtype)]
    except KeyError as exc:
        raise InstrumentContractError(
            "risk_budget_missing",
            f"no risk budget is registered for {instrument.asset_class}/{instrument.subtype}",
        ) from exc
