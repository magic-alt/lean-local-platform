from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


INSTRUMENT_SCHEMA_VERSION = 1
_CN_MIC_BY_SUFFIX = {"SH": "XSHG", "SZ": "XSHE", "BJ": "XBSE"}
_CN_SUFFIX_BY_MIC = {value: key for key, value in _CN_MIC_BY_SUFFIX.items()}
_CN_LEGACY_PREFIXES = tuple(_CN_MIC_BY_SUFFIX)


class InstrumentContractError(ValueError):
    """Raised when an instrument contract is incomplete or ambiguous."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _required_text(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise InstrumentContractError("missing_field", f"{field_name} is required")
    return text


def _positive_decimal(value: Decimal | str | int, field_name: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InstrumentContractError("invalid_decimal", f"{field_name} must be a decimal value") from exc
    if not number.is_finite() or number <= 0:
        raise InstrumentContractError("invalid_decimal", f"{field_name} must be finite and positive")
    return number


def _iso_date(value: str | None, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise InstrumentContractError("invalid_date", f"{field_name} must be an ISO date") from exc
    return text


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


@dataclass(frozen=True, kw_only=True)
class SymbolAlias:
    provider: str
    symbol: str
    valid_from: str | None = None
    valid_to: str | None = None
    purpose: str = "market_data"

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _required_text(self.provider, "provider").lower())
        object.__setattr__(self, "symbol", _required_text(self.symbol, "symbol").upper())
        object.__setattr__(self, "purpose", _required_text(self.purpose, "purpose").lower())
        start = _iso_date(self.valid_from, "valid_from")
        end = _iso_date(self.valid_to, "valid_to")
        if start and end and start > end:
            raise InstrumentContractError("invalid_alias_window", "valid_from must not be after valid_to")
        object.__setattr__(self, "valid_from", start)
        object.__setattr__(self, "valid_to", end)

    def active_on(self, as_of: str | None) -> bool:
        if as_of is None:
            return self.valid_to is None
        day = _iso_date(as_of, "as_of")
        return (self.valid_from is None or self.valid_from <= day) and (
            self.valid_to is None or day <= self.valid_to
        )

    def to_manifest(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "symbol": self.symbol,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "purpose": self.purpose,
        }


@dataclass(frozen=True, kw_only=True)
class InstrumentSpec:
    instrument_id: str
    canonical_symbol: str
    asset_class: str
    subtype: str
    market: str
    venue: str
    currency: str
    settlement_currency: str
    calendar_id: str
    price_tick: Decimal | str
    quantity_increment: Decimal | str
    quantity_unit: str
    lot_size: Decimal | str
    tradable: bool
    market_rule_pack_id: str
    aliases: tuple[SymbolAlias, ...] = field(default_factory=tuple)
    listed_from: str | None = None
    listed_to: str | None = None
    identity_kind: str = "instrument"
    continuous_series: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "instrument_id", "canonical_symbol", "asset_class", "subtype", "market",
            "venue", "currency", "settlement_currency", "calendar_id",
            "quantity_unit", "market_rule_pack_id",
        ):
            value = _required_text(getattr(self, field_name), field_name)
            if field_name in {"market", "venue", "currency", "settlement_currency"}:
                value = value.upper()
            elif field_name in {"asset_class", "subtype", "identity_kind", "quantity_unit"}:
                value = value.lower()
            elif field_name == "canonical_symbol":
                value = value.upper()
            object.__setattr__(self, field_name, value)
        if self.identity_kind not in {"instrument", "root", "continuous"}:
            raise InstrumentContractError("invalid_identity_kind", f"unsupported identity_kind: {self.identity_kind}")
        tick = _positive_decimal(self.price_tick, "price_tick")
        quantity_increment = _positive_decimal(self.quantity_increment, "quantity_increment")
        lot_size = _positive_decimal(self.lot_size, "lot_size")
        object.__setattr__(self, "price_tick", tick)
        object.__setattr__(self, "quantity_increment", quantity_increment)
        object.__setattr__(self, "lot_size", lot_size)
        listed_from = _iso_date(self.listed_from, "listed_from")
        listed_to = _iso_date(self.listed_to, "listed_to")
        if listed_from and listed_to and listed_from > listed_to:
            raise InstrumentContractError("invalid_listing_window", "listed_from must not be after listed_to")
        object.__setattr__(self, "listed_from", listed_from)
        object.__setattr__(self, "listed_to", listed_to)
        aliases = tuple(self.aliases)
        if len({(item.provider, item.symbol, item.valid_from, item.valid_to, item.purpose) for item in aliases}) != len(aliases):
            raise InstrumentContractError("duplicate_alias", f"duplicate aliases for {self.instrument_id}")
        object.__setattr__(self, "aliases", aliases)
        if self.continuous_series and self.identity_kind != "continuous":
            raise InstrumentContractError(
                "continuous_identity_mismatch",
                "continuous_series instruments must use identity_kind='continuous'",
            )
        if self.identity_kind != "instrument" and self.tradable:
            raise InstrumentContractError(
                "non_orderable_identity",
                f"{self.identity_kind} identities cannot be marked tradable",
            )

    def resolve_alias(self, provider: str, *, as_of: str | None = None, purpose: str | None = None) -> str:
        key = _required_text(provider, "provider").lower()
        purpose_key = str(purpose or "").strip().lower()
        matches = [
            alias
            for alias in self.aliases
            if alias.provider == key
            and (not purpose_key or alias.purpose == purpose_key)
            and alias.active_on(as_of)
        ]
        if not matches:
            raise InstrumentContractError(
                "alias_not_found",
                f"no active {key} alias for {self.instrument_id} at {as_of or 'current'}",
            )
        if len(matches) > 1:
            raise InstrumentContractError(
                "alias_ambiguous",
                f"multiple active {key} aliases for {self.instrument_id} at {as_of or 'current'}",
            )
        return matches[0].symbol

    def assert_orderable(self) -> None:
        if self.continuous_series or self.identity_kind != "instrument":
            raise InstrumentContractError("continuous_not_orderable", f"{self.instrument_id} is not orderable")
        if not self.tradable:
            raise InstrumentContractError("instrument_not_tradable", f"{self.instrument_id} is not tradable")

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": INSTRUMENT_SCHEMA_VERSION,
            "instrument_id": self.instrument_id,
            "canonical_symbol": self.canonical_symbol,
            "asset_class": self.asset_class,
            "subtype": self.subtype,
            "market": self.market,
            "venue": self.venue,
            "currency": self.currency,
            "settlement_currency": self.settlement_currency,
            "calendar_id": self.calendar_id,
            "price_tick": _decimal_text(self.price_tick),
            "quantity_increment": _decimal_text(self.quantity_increment),
            "quantity_unit": self.quantity_unit,
            "lot_size": _decimal_text(self.lot_size),
            "tradable": self.tradable,
            "market_rule_pack_id": self.market_rule_pack_id,
            "aliases": [alias.to_manifest() for alias in self.aliases],
            "listed_from": self.listed_from,
            "listed_to": self.listed_to,
            "identity_kind": self.identity_kind,
            "continuous_series": self.continuous_series,
        }


@dataclass(frozen=True, kw_only=True)
class FutureInstrumentSpec(InstrumentSpec):
    underlying_id: str
    expiry: str
    multiplier: Decimal | str

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "underlying_id", _required_text(self.underlying_id, "underlying_id"))
        object.__setattr__(self, "expiry", _iso_date(self.expiry, "expiry") or "")
        object.__setattr__(self, "multiplier", _positive_decimal(self.multiplier, "multiplier"))
        if not self.expiry:
            raise InstrumentContractError("missing_field", "expiry is required")

    def to_manifest(self) -> dict[str, Any]:
        payload = super().to_manifest()
        payload.update(
            {
                "underlying_id": self.underlying_id,
                "expiry": self.expiry,
                "multiplier": _decimal_text(self.multiplier),
            }
        )
        return payload


@dataclass(frozen=True, kw_only=True)
class ContinuousFutureSpec(InstrumentSpec):
    underlying_id: str
    multiplier: Decimal | str

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "underlying_id", _required_text(self.underlying_id, "underlying_id"))
        object.__setattr__(self, "multiplier", _positive_decimal(self.multiplier, "multiplier"))
        if not self.continuous_series or self.identity_kind != "continuous" or self.tradable:
            raise InstrumentContractError(
                "continuous_not_orderable",
                "continuous futures must be non-tradable continuous identities",
            )

    def to_manifest(self) -> dict[str, Any]:
        payload = super().to_manifest()
        payload.update(
            {
                "underlying_id": self.underlying_id,
                "multiplier": _decimal_text(self.multiplier),
            }
        )
        return payload


@dataclass(frozen=True, kw_only=True)
class OptionInstrumentSpec(FutureInstrumentSpec):
    strike: Decimal | str
    right: str
    exercise_style: str
    settlement_style: str

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "strike", _positive_decimal(self.strike, "strike"))
        right = str(self.right or "").strip().lower()
        if right not in {"call", "put"}:
            raise InstrumentContractError("invalid_option_right", "option right must be call or put")
        object.__setattr__(self, "right", right)
        object.__setattr__(self, "exercise_style", _required_text(self.exercise_style, "exercise_style").lower())
        object.__setattr__(self, "settlement_style", _required_text(self.settlement_style, "settlement_style").lower())

    def to_manifest(self) -> dict[str, Any]:
        payload = super().to_manifest()
        payload.update(
            {
                "strike": _decimal_text(self.strike),
                "right": self.right,
                "exercise_style": self.exercise_style,
                "settlement_style": self.settlement_style,
            }
        )
        return payload


def instrument_contract_id(
    *,
    market: str,
    venue: str,
    subtype: str,
    canonical_symbol: str,
    identity_kind: str = "instrument",
    expiry: str | None = None,
    strike: str | Decimal | None = None,
    right: str | None = None,
) -> str:
    """Build the provider-neutral contract ID shared with qlib-platform.

    This is additive and does not replace the legacy UUID IDs already persisted
    by ``services.instrument_identity``.
    """

    market_key = _required_text(market, "market").upper()
    venue_key = _required_text(venue, "venue").upper()
    subtype_key = _required_text(subtype, "subtype").lower()
    symbol_key = _required_text(canonical_symbol, "canonical_symbol").upper()
    kind = _required_text(identity_kind, "identity_kind").lower()
    token_by_subtype = {
        "common_stock": "EQUITY",
        "etf": "ETF",
        "index": "INDEX",
        "future_contract": "FUTURE",
        "future_root": "FUTURE_ROOT",
        "future_continuous": "FUTURE_CONTINUOUS",
        "option": "OPTION",
        "convertible_bond": "CONVERTIBLE_BOND",
    }
    token = token_by_subtype.get(subtype_key, subtype_key.upper())
    parts = [market_key, venue_key, token, symbol_key]
    if kind == "continuous" and subtype_key != "future_continuous":
        raise InstrumentContractError("identity_kind_mismatch", "continuous identity requires future_continuous subtype")
    if subtype_key in {"future_contract", "option"}:
        expiry_key = _iso_date(expiry, "expiry")
        if not expiry_key:
            raise InstrumentContractError("missing_field", "expiry is required in derivative identity")
        parts.append(expiry_key.replace("-", ""))
    if subtype_key == "option":
        if strike is None or right is None:
            raise InstrumentContractError("missing_field", "option strike and right are identity dimensions")
        strike_key = _decimal_text(_positive_decimal(strike, "strike"))
        right_key = str(right).strip().upper()
        if right_key not in {"CALL", "PUT"}:
            raise InstrumentContractError("invalid_option_right", "option right must be call or put")
        parts.extend([strike_key, right_key])
    return ".".join(parts)


def _legacy_cn_symbol(symbol: str, venue: str | None = None) -> tuple[str, str, str, str]:
    """Normalize one legacy A-share alias at the compatibility edge only.

    This helper exists to map historical Qlib/TuShare-facing identifiers. New
    Security Master writes should carry venue explicitly and must not use digit
    prefixes as a general cross-asset identity rule.
    """

    raw = _required_text(symbol, "symbol").upper()
    explicit_venue = str(venue or "").strip().upper()
    mic: str | None = None
    code = raw
    if "." in raw:
        code, suffix = raw.rsplit(".", 1)
        mic = _CN_MIC_BY_SUFFIX.get(suffix)
    elif raw.startswith(_CN_LEGACY_PREFIXES) and len(raw) > 2:
        suffix, code = raw[:2], raw[2:]
        mic = _CN_MIC_BY_SUFFIX.get(suffix)
    if explicit_venue:
        explicit_venue = _CN_MIC_BY_SUFFIX.get(explicit_venue, explicit_venue)
        if mic and mic != explicit_venue:
            raise InstrumentContractError("venue_conflict", f"symbol venue {mic} conflicts with {explicit_venue}")
        mic = explicit_venue
    if not mic:
        # Historical compatibility only. Do not reuse this heuristic for a new
        # asset family or canonical Security Master ingestion.
        if code.startswith(("6", "9")):
            mic = "XSHG"
        elif code.startswith(("0", "3")):
            mic = "XSHE"
        elif code.startswith("8"):
            mic = "XBSE"
        else:
            raise InstrumentContractError("venue_required", f"cannot infer legacy A-share venue for {symbol!r}")
    if mic not in _CN_SUFFIX_BY_MIC:
        raise InstrumentContractError("unsupported_cn_venue", f"unsupported China venue: {mic}")
    if not code.isdigit() or len(code) != 6:
        raise InstrumentContractError("invalid_cn_symbol", f"expected six-digit A-share symbol: {symbol!r}")
    suffix = _CN_SUFFIX_BY_MIC[mic]
    return code, mic, f"{suffix}{code}", f"{code}.{suffix}"


def legacy_ashare_instrument(
    symbol: str,
    *,
    venue: str | None = None,
    listed_from: str | None = None,
    listed_to: str | None = None,
    aliases: Iterable[SymbolAlias] = (),
) -> InstrumentSpec:
    code, mic, qlib_symbol, tushare_symbol = _legacy_cn_symbol(symbol, venue)
    extra_aliases = tuple(aliases)
    return InstrumentSpec(
        instrument_id=instrument_contract_id(
            market="CN", venue=mic, subtype="common_stock", canonical_symbol=code
        ),
        canonical_symbol=code,
        asset_class="equity",
        subtype="common_stock",
        market="CN",
        venue=mic,
        currency="CNY",
        settlement_currency="CNY",
        calendar_id="cn_stock_v1",
        price_tick="0.01",
        quantity_increment="1",
        quantity_unit="share",
        lot_size="100",
        tradable=True,
        market_rule_pack_id=f"cn_{mic.lower()}_common_stock_v1",
        aliases=(
            SymbolAlias(provider="qlib", symbol=qlib_symbol),
            SymbolAlias(provider="tushare", symbol=tushare_symbol),
            SymbolAlias(provider="lean", symbol=code, purpose="execution"),
            *extra_aliases,
        ),
        listed_from=listed_from,
        listed_to=listed_to,
    )


def ashare_etf_instrument(
    symbol: str,
    *,
    product_profile: str,
    venue: str | None = None,
    listed_from: str | None = None,
    listed_to: str | None = None,
    aliases: Iterable[SymbolAlias] = (),
) -> InstrumentSpec:
    if product_profile != "stock_etf_t1":
        raise InstrumentContractError(
            "unsupported_etf_product_profile",
            "the first ETF vertical slice only certifies stock_etf_t1 semantics",
        )
    code, mic, qlib_symbol, tushare_symbol = _legacy_cn_symbol(symbol, venue)
    if mic not in {"XSHG", "XSHE"}:
        raise InstrumentContractError("unsupported_etf_venue", f"ETF venue is not supported: {mic}")
    return InstrumentSpec(
        instrument_id=instrument_contract_id(
            market="CN", venue=mic, subtype="etf", canonical_symbol=code
        ),
        canonical_symbol=code,
        asset_class="equity",
        subtype="etf",
        market="CN",
        venue=mic,
        currency="CNY",
        settlement_currency="CNY",
        calendar_id="cn_stock_v1",
        price_tick="0.001",
        quantity_increment="1",
        quantity_unit="share",
        lot_size="100",
        tradable=True,
        market_rule_pack_id=f"cn_{mic.lower()}_stock_etf_v1",
        aliases=(
            SymbolAlias(provider="qlib", symbol=qlib_symbol),
            SymbolAlias(provider="tushare", symbol=tushare_symbol),
            SymbolAlias(provider="lean", symbol=code, purpose="execution"),
            *tuple(aliases),
        ),
        listed_from=listed_from,
        listed_to=listed_to,
    )


def ashare_index_instrument(symbol: str, *, venue: str | None = None) -> InstrumentSpec:
    code, mic, qlib_symbol, tushare_symbol = _legacy_cn_symbol(symbol, venue)
    return InstrumentSpec(
        instrument_id=instrument_contract_id(
            market="CN", venue=mic, subtype="index", canonical_symbol=code
        ),
        canonical_symbol=code,
        asset_class="index",
        subtype="index",
        market="CN",
        venue=mic,
        currency="CNY",
        settlement_currency="CNY",
        calendar_id="cn_stock_v1",
        price_tick="0.01",
        quantity_increment="1",
        quantity_unit="index_point",
        lot_size="1",
        tradable=False,
        market_rule_pack_id=f"cn_{mic.lower()}_index_benchmark_v1",
        aliases=(
            SymbolAlias(provider="qlib", symbol=qlib_symbol),
            SymbolAlias(provider="tushare", symbol=tushare_symbol),
        ),
    )
