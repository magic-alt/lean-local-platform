from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Generic, TypeVar


T = TypeVar("T")


class ProviderDataClass(str, Enum):
    HISTORICAL_DATA = "historical_data"
    REFERENCE_DATA = "reference_data"
    CORPORATE_ACTIONS = "corporate_actions"
    CALENDAR = "calendar"
    STREAMING = "streaming"


class ProviderErrorCode(str, Enum):
    MISSING_FIELD = "missing_field"
    INVALID_VALUE = "invalid_value"
    NON_FINITE_VALUE = "non_finite_value"
    AUTH_REQUIRED = "auth_required"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PAGINATION_INTERRUPTED = "pagination_interrupted"
    SCHEMA_CHANGED = "schema_changed"
    UPSTREAM_ERROR = "upstream_error"


@dataclass(frozen=True)
class ProviderAuthContract:
    mode: str
    required: bool
    account_scope: str
    entitlement_scope: tuple[str, ...] = ()
    credential_names: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "required": self.required,
            "accountScope": self.account_scope,
            "entitlementScope": list(self.entitlement_scope),
            "credentialNames": list(self.credential_names),
        }


@dataclass(frozen=True)
class ProviderDescriptor:
    provider: str
    adapter_version: str
    data_classes: tuple[ProviderDataClass, ...]
    asset_classes: tuple[str, ...]
    markets: tuple[str, ...]
    frequencies: tuple[str, ...]
    historical_coverage: str
    adjustment_modes: tuple[str, ...]
    pit_availability: str
    transports: tuple[str, ...]
    pagination: str
    rate_limit: str
    license: str
    redistribution: str
    auth: ProviderAuthContract
    health: str
    cross_source_caveats: tuple[str, ...] = ()
    production_certified: bool = False
    schema_version: str = "1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "provider": self.provider,
            "adapterVersion": self.adapter_version,
            "dataClasses": [item.value for item in self.data_classes],
            "assetClasses": list(self.asset_classes),
            "markets": list(self.markets),
            "frequencies": list(self.frequencies),
            "historicalCoverage": self.historical_coverage,
            "adjustmentModes": list(self.adjustment_modes),
            "pitAvailability": self.pit_availability,
            "transports": list(self.transports),
            "pagination": self.pagination,
            "rateLimit": self.rate_limit,
            "license": self.license,
            "redistribution": self.redistribution,
            "auth": self.auth.as_dict(),
            "health": self.health,
            "crossSourceCaveats": list(self.cross_source_caveats),
            "productionCertified": self.production_certified,
        }


@dataclass(frozen=True)
class CanonicalUnits:
    price_currency: str
    volume_unit: str
    amount_unit: str
    timezone: str
    adjustment: str
    price_scale: float = 1.0
    volume_scale: float = 1.0
    amount_scale: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "priceCurrency": self.price_currency,
            "volumeUnit": self.volume_unit,
            "amountUnit": self.amount_unit,
            "timezone": self.timezone,
            "adjustment": self.adjustment,
            "priceScale": self.price_scale,
            "volumeScale": self.volume_scale,
            "amountScale": self.amount_scale,
        }


@dataclass(frozen=True)
class ProviderIssue:
    code: ProviderErrorCode
    message: str
    retryable: bool = False
    field: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.field:
            payload["field"] = self.field
        return payload


@dataclass(frozen=True)
class QuarantinedRecord:
    row_index: int
    issues: tuple[ProviderIssue, ...]
    source_fields: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "rowIndex": self.row_index,
            "issues": [item.as_dict() for item in self.issues],
            "sourceFields": list(self.source_fields),
        }


@dataclass
class CanonicalBatch(Generic[T]):
    provider: str
    operation: str
    descriptor: ProviderDescriptor
    units: CanonicalUnits
    records: list[T]
    quarantined: list[QuarantinedRecord] = field(default_factory=list)
    warnings: list[ProviderIssue] = field(default_factory=list)
    source_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def quarantine_count(self) -> int:
        return len(self.quarantined)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "operation": self.operation,
            "descriptor": self.descriptor.as_dict(),
            "units": self.units.as_dict(),
            "records": self.records,
            "quarantined": [item.as_dict() for item in self.quarantined],
            "warnings": [item.as_dict() for item in self.warnings],
            "sourceMetadata": dict(self.source_metadata),
        }
