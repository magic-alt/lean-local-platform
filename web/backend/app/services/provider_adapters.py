from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PROVIDER_ENDPOINTS = [
    "fetch_security_master",
    "fetch_daily_bars",
    "fetch_trade_calendar",
    "fetch_adjustment_factors",
    "fetch_st_status",
    "fetch_suspend_status",
    "fetch_limit_prices",
    "fetch_corporate_actions",
    "fetch_index_daily",
    "fetch_index_membership_pit",
    "normalize",
    "upsert",
    "qa",
    "provider_availability",
]


@dataclass(frozen=True)
class EndpointSupport:
    endpoint: str
    supported: bool
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"endpoint": self.endpoint, "supported": self.supported, "reason": self.reason}


class ProviderAdapter:
    key = "base"
    production_certified = False

    def supported_endpoints(self) -> list[dict[str, Any]]:
        return [EndpointSupport(endpoint, False, "not_implemented").as_dict() for endpoint in PROVIDER_ENDPOINTS]

    def fetch_security_master(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def fetch_daily_bars(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def fetch_trade_calendar(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def fetch_adjustment_factors(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def fetch_st_status(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def fetch_suspend_status(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def fetch_limit_prices(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def fetch_corporate_actions(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def fetch_index_daily(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def fetch_index_membership_pit(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def normalize(self, rows: Any) -> Any:
        return rows

    def upsert(self, rows: Any) -> Any:
        raise NotImplementedError

    def qa(self, rows: Any) -> dict[str, Any]:
        return {"severity": "ok", "rows": len(rows or []) if hasattr(rows, "__len__") else None}

    def provider_availability(self) -> dict[str, Any]:
        return {"provider": self.key, "supportedEndpoints": self.supported_endpoints()}


class AkshareAdapter(ProviderAdapter):
    key = "akshare"
    production_certified = True

    def supported_endpoints(self) -> list[dict[str, Any]]:
        supported = {
            "fetch_security_master",
            "fetch_daily_bars",
            "fetch_trade_calendar",
            "fetch_adjustment_factors",
            "fetch_st_status",
            "fetch_suspend_status",
            "fetch_limit_prices",
            "fetch_corporate_actions",
            "fetch_index_daily",
            "normalize",
            "upsert",
            "qa",
            "provider_availability",
        }
        return [EndpointSupport(endpoint, endpoint in supported, None if endpoint in supported else "not_certified").as_dict() for endpoint in PROVIDER_ENDPOINTS]


class TushareAdapter(ProviderAdapter):
    key = "tushare"

    def supported_endpoints(self) -> list[dict[str, Any]]:
        supported = {
            "fetch_security_master",
            "fetch_daily_bars",
            "fetch_trade_calendar",
            "fetch_adjustment_factors",
            "fetch_st_status",
            "fetch_suspend_status",
            "fetch_limit_prices",
            "fetch_corporate_actions",
            "fetch_index_daily",
            "fetch_index_membership_pit",
            "normalize",
            "upsert",
            "qa",
            "provider_availability",
        }
        return [EndpointSupport(endpoint, endpoint in supported, None).as_dict() for endpoint in PROVIDER_ENDPOINTS]


class DiagnosticStubAdapter(ProviderAdapter):
    def __init__(self, key: str, *, endpoints: set[str] | None = None) -> None:
        self.key = key
        self._endpoints = endpoints or {"provider_availability"}

    def supported_endpoints(self) -> list[dict[str, Any]]:
        return [
            EndpointSupport(endpoint, endpoint in self._endpoints, None if endpoint in self._endpoints else "diagnostic_stub").as_dict()
            for endpoint in PROVIDER_ENDPOINTS
        ]


def adapter_for(provider: str) -> ProviderAdapter:
    key = provider.strip().lower()
    if key == "akshare":
        return AkshareAdapter()
    if key == "tushare":
        return TushareAdapter()
    if key in {"baostock", "adata"}:
        return DiagnosticStubAdapter(key, endpoints={"fetch_daily_bars", "normalize", "qa", "provider_availability"})
    if key in {"jqdata", "rqdata"}:
        return DiagnosticStubAdapter(key)
    return DiagnosticStubAdapter(key)
