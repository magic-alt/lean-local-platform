from __future__ import annotations

import importlib.util
import json
import os
import time
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from ..core.errors import LeanWebError
from ..domain.assets import asset_class_key
from ..lean_engine.providers import (
    download_text,
    fetch_akshare_rows,
    fetch_alpha_vantage_rows,
    fetch_eastmoney_rows,
    fetch_sina_rows,
    fetch_stooq_rows,
    fetch_tonghuashun_rows,
    fetch_yahoo_rows,
)
from ..lean_engine.symbols import market_key, normalize_symbol, parse_date
from .ashare_source_adapters import fetch_adata_rows, fetch_baostock_rows
from .jqdata_adapter import fetch_jqdata_rows
from .source_gate import DATA_SOURCE_PRIORITY, jqdata_covers_window, resolve_effective_data_source, source_priority_for_window, source_role
from .tushare_adapter import fetch_tushare_rows


CredentialOption = list[str]


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    name: str
    priority: int
    markets: tuple[str, ...]
    asset_classes: tuple[str, ...] = ("equity",)
    venues: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    credentials: tuple[CredentialOption, ...] = ()
    supports_batch: bool = True
    production_certified: bool = False
    commercial: bool = False
    enabled_by_default: bool = True
    capabilities: tuple[str, ...] = ("fetch_daily_bars", "provider_availability")
    notes: str = ""
    optional_fetch: bool = False

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "requiresApiKey": bool(self.credentials),
            "supportsBatch": self.supports_batch,
            "markets": list(self.markets),
            "assetClasses": list(self.asset_classes),
            "venues": list(self.venues or self.markets),
            "capabilities": list(self.capabilities),
            "productionCertified": self.production_certified,
            "commercial": self.commercial,
            "enabledByDefault": self.enabled_by_default,
            "disabledByDefault": not self.enabled_by_default,
            "notes": self.notes,
        }


A_SHARE_PROVIDER_PRIORITY = list(DATA_SOURCE_PRIORITY)
US_PROVIDER_PRIORITY = ["yfinance", "yahoo", "stooq", "akshare", "sina"]
HK_PROVIDER_PRIORITY = ["akshare", "sina", "eastmoney", "yfinance"]


PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "jqdata": ProviderSpec(
        key="jqdata",
        name="JQData",
        priority=1,
        markets=("china",),
        venues=("china",),
        modules=("jqdatasdk",),
        credentials=(["JQDATA_TOKEN"], ["JQDATA_USERNAME", "JQDATA_PASSWORD"]),
        production_certified=True,
        commercial=True,
        enabled_by_default=False,
        notes="Optional commercial A-share source. It is diagnosed but not enabled in the default Web/provider chain.",
    ),
    "akshare": ProviderSpec(
        key="akshare",
        name="AKShare",
        priority=2,
        markets=("china", "hongkong", "usa"),
        venues=("china", "hongkong", "usa"),
        modules=("akshare",),
        production_certified=True,
        notes="Public A-share verification source and US/HK fallback.",
    ),
    "efinance": ProviderSpec(
        key="efinance",
        name="Efinance",
        priority=3,
        markets=("china",),
        venues=("china",),
        modules=("efinance",),
        notes="EastMoney-backed public A-share K-line source.",
    ),
    "tencent": ProviderSpec(
        key="tencent",
        name="Tencent",
        priority=4,
        markets=("china",),
        venues=("china",),
        modules=(),
        notes="Tencent direct A-share daily K-line endpoint.",
    ),
    "tushare": ProviderSpec(
        key="tushare",
        name="TuShare Pro",
        priority=0,
        markets=("china",),
        venues=("china",),
        modules=("tushare",),
        credentials=(["TUSHARE_TOKEN"],),
        production_certified=True,
        commercial=True,
        enabled_by_default=True,
        capabilities=(
            "fetch_security_master",
            "fetch_daily_bars",
            "fetch_trade_calendar",
            "fetch_adjustment_factors",
            "fetch_corporate_actions",
            "fetch_financial_statements",
            "fetch_index_membership_pit",
            "provider_availability",
        ),
        notes=(
            "Default professional A-share source with current TuShare Pro permissions for A-share/fund/futures/options basics, "
            "HK/US/FX basics, low-frequency quotes, financial statements, macro data, ST, stock connect, "
            "pledge/unlock/repurchase/holding-change references, LHB, and margin data."
        ),
    ),
    "tickflow": ProviderSpec(
        key="tickflow",
        name="TickFlow",
        priority=5,
        markets=("china",),
        venues=("china",),
        modules=("tickflow",),
        credentials=(["TICKFLOW_API_KEY"],),
        capabilities=("provider_availability",),
        commercial=True,
        enabled_by_default=False,
        optional_fetch=True,
        notes="Optional DSA-compatible provider. Availability is diagnosed; daily import adapter is not enabled yet.",
    ),
    "pytdx": ProviderSpec(
        key="pytdx",
        name="PyTDX",
        priority=6,
        markets=("china",),
        venues=("china",),
        modules=("pytdx",),
        capabilities=("provider_availability",),
        enabled_by_default=False,
        optional_fetch=True,
        notes="Optional TongDaXin connector. Availability is diagnosed; live fetch is intentionally not used in Level3+ pipeline.",
    ),
    "baostock": ProviderSpec(
        key="baostock",
        name="Baostock",
        priority=7,
        markets=("china",),
        venues=("china",),
        modules=("baostock",),
        notes="Free A-share historical fallback and cross-source QA source.",
    ),
    "adata": ProviderSpec(
        key="adata",
        name="AData",
        priority=8,
        markets=("china",),
        venues=("china",),
        modules=("adata",),
        notes="Free A-share fallback and cross-source QA source.",
    ),
    "eastmoney": ProviderSpec(
        key="eastmoney",
        name="EastMoney",
        priority=9,
        markets=("china", "hongkong"),
        venues=("china", "hongkong"),
        notes="Direct public EastMoney daily K-line endpoint.",
    ),
    "sina": ProviderSpec(
        key="sina",
        name="Sina Finance",
        priority=10,
        markets=("china", "hongkong", "usa"),
        venues=("china", "hongkong", "usa"),
        modules=("akshare",),
        notes="AKShare Sina-compatible daily data path.",
    ),
    "tonghuashun": ProviderSpec(
        key="tonghuashun",
        name="TongHuaShun",
        priority=11,
        markets=("china",),
        venues=("china",),
        modules=("akshare",),
        notes="A-share daily fallback routed through AKShare-compatible daily endpoint.",
    ),
    "yfinance": ProviderSpec(
        key="yfinance",
        name="YFinance",
        priority=12,
        markets=("usa", "hongkong", "china"),
        venues=("usa", "hongkong", "china"),
        modules=("yfinance",),
        notes="Yahoo Finance library route for US/HK and last-resort A-share daily data.",
    ),
    "yahoo": ProviderSpec(
        key="yahoo",
        name="Yahoo Finance",
        priority=13,
        markets=("usa",),
        venues=("usa",),
        notes="Built-in Yahoo chart endpoint for US daily data.",
    ),
    "stooq": ProviderSpec(
        key="stooq",
        name="Stooq",
        priority=14,
        markets=("usa",),
        venues=("usa",),
        notes="Built-in Stooq CSV endpoint for US daily data.",
    ),
    "alpha_vantage": ProviderSpec(
        key="alpha_vantage",
        name="Alpha Vantage",
        priority=15,
        markets=("usa",),
        venues=("usa",),
        credentials=(["ALPHAVANTAGE_API_KEY"],),
        commercial=True,
        enabled_by_default=False,
        notes="US daily data API; rate limits and key entitlement apply.",
    ),
    "finnhub": ProviderSpec(
        key="finnhub",
        name="Finnhub",
        priority=16,
        markets=("usa",),
        venues=("usa",),
        modules=("finnhub",),
        credentials=(["FINNHUB_API_KEY"],),
        capabilities=("provider_availability",),
        commercial=True,
        enabled_by_default=False,
        optional_fetch=True,
        notes="Optional US data provider. Availability is diagnosed; import adapter is not enabled yet.",
    ),
    "longbridge": ProviderSpec(
        key="longbridge",
        name="Longbridge",
        priority=17,
        markets=("usa", "hongkong"),
        venues=("usa", "hongkong"),
        modules=("longbridge",),
        credentials=(["LONGBRIDGE_APP_KEY", "LONGBRIDGE_APP_SECRET", "LONGBRIDGE_ACCESS_TOKEN"], ["LONGBRIDGE_OAUTH_CLIENT_ID"]),
        capabilities=("provider_availability",),
        commercial=True,
        enabled_by_default=False,
        optional_fetch=True,
        notes="Optional US/HK source. Availability is diagnosed; no broker/trading capability is used.",
    ),
    "binance": ProviderSpec(
        key="binance",
        name="Binance",
        priority=18,
        markets=("crypto",),
        asset_classes=("crypto",),
        venues=("binance",),
        capabilities=("fetch_daily_bars", "provider_availability"),
        notes="Public spot kline endpoint for crypto OHLCV. Availability depends on region and rate limits.",
    ),
    "rqdata": ProviderSpec(
        key="rqdata",
        name="RQData",
        priority=19,
        markets=("china",),
        venues=("china",),
        modules=("rqdatac",),
        credentials=(["RQDATA_USERNAME", "RQDATA_PASSWORD"],),
        capabilities=("provider_availability",),
        commercial=True,
        enabled_by_default=False,
        optional_fetch=True,
        notes="Backup interface placeholder for future professional data supplementation.",
    ),
}


def provider_spec(provider: str) -> ProviderSpec | None:
    return PROVIDER_SPECS.get(_normalize_provider(provider))


def provider_specs() -> list[ProviderSpec]:
    return sorted(PROVIDER_SPECS.values(), key=lambda item: (item.priority, item.key))


def provider_requirements() -> dict[str, dict[str, Any]]:
    return {
        key: {"modules": list(spec.modules), "env": [list(option) for option in spec.credentials]}
        for key, spec in PROVIDER_SPECS.items()
    }


def _normalize_provider(provider: str | None) -> str:
    value = str(provider or "auto").strip().lower()
    aliases = {
        "": "auto",
        "automatic": "auto",
        "database": "auto",
        "local": "auto",
        "tushare_pro": "tushare",
        "tushare-pro": "tushare",
        "tushare pro": "tushare",
        "tu_share": "tushare",
        "tu-share": "tushare",
        "alphavantage": "alpha_vantage",
        "alpha-vantage": "alpha_vantage",
    }
    return aliases.get(value, value)


def _enabled_by_default(provider: str) -> bool:
    spec = PROVIDER_SPECS.get(provider)
    return bool(spec and spec.enabled_by_default)


def _compact_date(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    text = str(value).strip()
    if len(text) >= 8 and text[:8].isdigit():
        return text[:8]
    return parse_date(text).strftime("%Y%m%d")


def _adjust_key(adjust: str | None) -> str:
    value = str(adjust or "raw").strip().lower()
    return "raw" if value in {"", "none", "normal"} else value


def _records(frame_or_records: Any) -> list[dict[str, Any]]:
    if frame_or_records is None:
        return []
    if isinstance(frame_or_records, list):
        return [dict(item) for item in frame_or_records if isinstance(item, dict)]
    if isinstance(frame_or_records, dict):
        return [frame_or_records]
    if hasattr(frame_or_records, "to_dict"):
        try:
            return [dict(item) for item in frame_or_records.to_dict("records")]
        except TypeError:
            value = frame_or_records.to_dict()
            if isinstance(value, list):
                return [dict(item) for item in value]
    return []


def _first_value(row: dict[str, Any], *keys: str) -> Any:
    lowered = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        if key in row:
            return row[key]
        value = lowered.get(key.lower())
        if value is not None:
            return value
    return None


def _date_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _float_text(value: Any, default: float = 0.0) -> str:
    if value in (None, ""):
        return str(default)
    try:
        return str(float(value))
    except (TypeError, ValueError):
        return str(default)


def _normalize_daily_records(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for row in rows:
        trade_date = _date_text(_first_value(row, "date", "日期", "trade_date", "tradeDate", "time", "datetime", "Date"))
        open_value = _first_value(row, "open", "开盘", "Open")
        high_value = _first_value(row, "high", "最高", "High")
        low_value = _first_value(row, "low", "最低", "Low")
        close_value = _first_value(row, "close", "收盘", "Close")
        if trade_date is None or open_value is None or high_value is None or low_value is None or close_value is None:
            continue
        item = {
            "date": trade_date,
            "open": _float_text(open_value),
            "high": _float_text(high_value),
            "low": _float_text(low_value),
            "close": _float_text(close_value),
            "volume": _float_text(_first_value(row, "volume", "vol", "成交量", "Volume")),
        }
        amount = _first_value(row, "amount", "成交额", "money")
        if amount is not None:
            item["amount"] = _float_text(amount)
        prev_close = _first_value(row, "prev_close", "pre_close", "preclose", "昨收")
        if prev_close is not None:
            item["prev_close"] = _float_text(prev_close)
        pct_change = _first_value(row, "pct_change", "pct_chg", "涨跌幅")
        if pct_change is not None:
            item["pct_change"] = _float_text(pct_change)
        normalized.append(item)
    normalized.sort(key=lambda item: item["date"])
    return normalized


def _module_status(modules: tuple[str, ...]) -> list[dict[str, Any]]:
    return [{"name": module, "available": importlib.util.find_spec(module) is not None} for module in modules]


def _credential_status(credentials: tuple[CredentialOption, ...]) -> tuple[bool, list[str], list[dict[str, Any]]]:
    names = sorted({name for option in credentials for name in option})
    items = [{"name": name, "present": bool(os.environ.get(name))} for name in names]
    configured = not credentials or any(all(os.environ.get(name) for name in option) for option in credentials)
    missing = [] if configured else [name for name in names if not os.environ.get(name)]
    return configured, missing, items


def provider_availability_item(provider: str, *, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]:
    key = _normalize_provider(provider)
    spec = PROVIDER_SPECS.get(key)
    if spec is None:
        return {
            "key": key,
            "provider": key,
            "name": key,
            "installed": False,
            "configured": False,
            "available": False,
            "status": "unavailable",
            "reason": "unsupported_provider",
            "unavailableReason": "unsupported_provider",
            "diagnostics": {"modules": [], "env": [], "networkChecked": False, "networkCheck": "not_run"},
        }
    modules = _module_status(spec.modules)
    missing_modules = [item["name"] for item in modules if not item["available"]]
    credentials_configured, missing_credentials, credentials = _credential_status(spec.credentials)
    reasons: list[str] = []
    if missing_modules:
        reasons.append("dependency_missing:" + ",".join(missing_modules))
    if missing_credentials:
        reasons.append("credential_missing:" + ",".join(missing_credentials))
    if key == "jqdata" and not jqdata_covers_window(start_date, end_date):
        reasons.append("entitlement_window_exceeded")
    installed = not missing_modules
    configured = credentials_configured
    available = installed and configured and not (key == "jqdata" and not jqdata_covers_window(start_date, end_date))
    return {
        **spec.as_public_dict(),
        "provider": key,
        "role": source_role(key),
        "priority": spec.priority + 1,
        "installed": installed,
        "configured": configured,
        "available": available,
        "status": "available" if available else ("degraded" if installed and configured else "unavailable"),
        "reason": "ok" if not reasons else ";".join(reasons),
        "unavailableReason": None if not reasons else ";".join(reasons),
        "credentials": "not_required" if not spec.credentials else ("present" if configured else "credential_missing"),
        "supportedEndpoints": [
            {"endpoint": capability, "supported": True, "reason": None}
            for capability in spec.capabilities
        ],
        "diagnostics": {
            "modules": modules,
            "env": credentials,
            "credentials": credentials,
            "networkChecked": False,
            "networkCheck": "not_run",
            "networkStatus": "not_run",
        },
    }


def provider_availability_items(
    providers: list[str] | None = None,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    selected = [_normalize_provider(item) for item in (providers or [spec.key for spec in provider_specs()]) if str(item).strip()]
    return [provider_availability_item(provider, start_date=start_date, end_date=end_date) for provider in selected]


def provider_chain(
    provider: str | None,
    *,
    market: str = "usa",
    asset_class: str = "equity",
    start_date: str | None = None,
    end_date: str | None = None,
    strict: bool = False,
) -> list[str]:
    asset = asset_class_key(asset_class)
    market_value = market_key(market) if asset == "equity" else str(market or "").strip().lower()
    requested = _normalize_provider(provider)
    if asset != "equity":
        return [requested] if requested != "auto" else []

    if market_value == "china":
        default_chain = source_priority_for_window(
            source=None if requested == "auto" else requested,
            start_date=start_date,
            end_date=end_date,
        )
        default_chain = [item for item in default_chain if item in A_SHARE_PROVIDER_PRIORITY]
        for item in A_SHARE_PROVIDER_PRIORITY:
            if item == "jqdata" and not jqdata_covers_window(start_date, end_date):
                continue
            if item not in default_chain:
                default_chain.append(item)
        default_chain = [item for item in default_chain if _enabled_by_default(item)]
        if requested != "auto":
            if requested == "jqdata" and not jqdata_covers_window(start_date, end_date):
                return [] if strict else default_chain
            return [requested] if strict else [requested, *[item for item in default_chain if item != requested]]
        return default_chain
    if market_value == "hongkong":
        chain = HK_PROVIDER_PRIORITY
    else:
        chain = US_PROVIDER_PRIORITY
    if requested != "auto":
        ordered = [requested, *[item for item in chain if item != requested]]
        return [requested] if strict else ordered
    return [item for item in chain if _enabled_by_default(item)]


def source_policy(
    provider: str | None,
    *,
    market: str = "china",
    asset_class: str = "equity",
    start_date: str | None = None,
    end_date: str | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    requested = _normalize_provider(provider)
    if asset_class_key(asset_class) == "equity" and market_key(market) == "china":
        policy = resolve_effective_data_source(None if requested == "auto" else requested, start_date=start_date, end_date=end_date)
    else:
        policy = {
            "requestedSource": requested,
            "effectiveSource": requested,
            "fallbackApplied": False,
            "fallbackReason": None,
            "sourceRole": source_role(requested),
            "requestedSourceRole": source_role(requested),
            "sourceChain": [],
            "startDate": start_date,
            "endDate": end_date,
        }
    chain = provider_chain(provider, market=market, asset_class=asset_class, start_date=start_date, end_date=end_date, strict=strict)
    policy["sourceChain"] = chain
    policy["providerMode"] = "strict" if strict else "auto"
    return policy


def _fetch_efinance_rows(symbol: str, start: str | None, end: str | None, adjust: str | None) -> list[dict[str, str]]:
    try:
        import efinance as ef  # type: ignore
    except Exception as exc:
        raise LeanWebError("efinance is not installed. Install it before using provider=efinance.") from exc
    fqt = {"raw": 0, "": 0, "qfq": 1, "hfq": 2}.get(_adjust_key(adjust))
    if fqt is None:
        raise LeanWebError(f"Unsupported efinance adjust value: {adjust!r}")
    frame = ef.stock.get_quote_history(
        stock_codes=normalize_symbol(symbol, "china"),
        beg=_compact_date(start, "19900101"),
        end=_compact_date(end, date.today().strftime("%Y%m%d")),
        klt=101,
        fqt=fqt,
    )
    rows = _records(frame)
    normalized = _normalize_daily_records(rows)
    if not normalized:
        raise LeanWebError(f"Efinance returned no daily rows for {symbol}.")
    return normalized


def _tencent_symbol(symbol: str) -> str:
    ticker = normalize_symbol(symbol, "china")
    if ticker.startswith(("6", "5", "9")):
        return f"sh{ticker}"
    if ticker.startswith(("4", "8")):
        return f"bj{ticker}"
    return f"sz{ticker}"


def _fetch_tencent_rows(symbol: str, start: str | None, end: str | None, adjust: str | None) -> list[dict[str, str]]:
    if _adjust_key(adjust) not in {"raw", "qfq"}:
        raise LeanWebError("Tencent provider currently supports raw/qfq daily bars only.")
    start_date = parse_date(start) if start else parse_date("1990-01-01")
    end_date = parse_date(end) if end else date.today()
    lookback = max(30, min(800, int((end_date - start_date).days * 1.8) + 20))
    tencent_symbol = _tencent_symbol(symbol)
    fq_key = "qfq" if _adjust_key(adjust) == "qfq" else ""
    params = urllib.parse.urlencode(
        {
            "param": f"{tencent_symbol},day,{start_date.isoformat()},{end_date.isoformat()},{lookback},{fq_key}",
        }
    )
    payload = json.loads(download_text("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + params))
    data = payload.get("data") if isinstance(payload, dict) else None
    item = data.get(tencent_symbol) if isinstance(data, dict) else None
    rows = (item or {}).get("qfqday") or (item or {}).get("day") or []
    normalized: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        normalized.append(
            {
                "date": str(row[0]),
                "open": _float_text(row[1]),
                "close": _float_text(row[2]),
                "high": _float_text(row[3]),
                "low": _float_text(row[4]),
                "volume": _float_text(float(row[5]) * 100),
                **({"amount": _float_text(row[6])} if len(row) > 6 else {}),
            }
        )
    if not normalized:
        raise LeanWebError(f"Tencent returned no daily rows for {symbol}.")
    normalized.sort(key=lambda item: item["date"])
    return normalized


def _yfinance_symbol(symbol: str, market: str) -> str:
    ticker = normalize_symbol(symbol, market)
    if market == "china":
        if ticker.startswith(("6", "5", "9")):
            return f"{ticker}.SS"
        if ticker.startswith(("4", "8")):
            return f"{ticker}.BJ"
        return f"{ticker}.SZ"
    if market == "hongkong":
        return f"{ticker.zfill(4)}.HK"
    return ticker.upper()


def _fetch_yfinance_rows(symbol: str, market: str, start: str | None, end: str | None) -> list[dict[str, str]]:
    try:
        import yfinance as yf  # type: ignore
    except Exception as exc:
        raise LeanWebError("yfinance is not installed. Install it before using provider=yfinance.") from exc
    ticker = _yfinance_symbol(symbol, market)
    frame = yf.download(
        ticker,
        start=start or "1990-01-01",
        end=end or date.today().isoformat(),
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    rows = _records(frame.reset_index() if hasattr(frame, "reset_index") else frame)
    normalized = _normalize_daily_records(rows)
    if not normalized:
        raise LeanWebError(f"YFinance returned no daily rows for {symbol}.")
    return normalized


class DataProviderManager:
    def providers(self) -> list[dict[str, Any]]:
        return [spec.as_public_dict() for spec in provider_specs()]

    def availability(
        self,
        providers: list[str] | None = None,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        return provider_availability_items(providers, start_date=start_date, end_date=end_date)

    def chain(
        self,
        provider: str | None,
        *,
        market: str = "usa",
        asset_class: str = "equity",
        start_date: str | None = None,
        end_date: str | None = None,
        strict: bool = False,
    ) -> list[str]:
        return provider_chain(provider, market=market, asset_class=asset_class, start_date=start_date, end_date=end_date, strict=strict)

    def fetch_provider_rows(
        self,
        provider: str,
        symbol: str,
        *,
        market: str = "usa",
        asset_class: str = "equity",
        api_key: str | None = None,
        outputsize: str = "compact",
        start_date: str | None = None,
        end_date: str | None = None,
        adjust: str = "",
    ) -> list[dict[str, str]]:
        asset = asset_class_key(asset_class)
        if asset != "equity":
            raise ValueError(f"Provider downloads are not enabled for asset class {asset}.")
        key = _normalize_provider(provider)
        market_value = market_key(market)
        symbol_value = normalize_symbol(symbol, market_value)
        if key == "jqdata":
            if market_value != "china":
                raise ValueError("JQData only supports China A-share imports in this platform.")
            if not jqdata_covers_window(start_date, end_date):
                raise LeanWebError("JQData entitlement window exceeded for requested date range.")
            return fetch_jqdata_rows(symbol_value, start_date, end_date, adjust=adjust)
        if key == "akshare":
            return fetch_akshare_rows(symbol_value, market_value, start=start_date, end=end_date, adjust=adjust)
        if key == "efinance":
            if market_value != "china":
                raise ValueError("Efinance only supports China A-share imports in this platform.")
            return _fetch_efinance_rows(symbol_value, start_date, end_date, adjust)
        if key == "tencent":
            if market_value != "china":
                raise ValueError("Tencent only supports China A-share imports in this platform.")
            return _fetch_tencent_rows(symbol_value, start_date, end_date, adjust)
        if key == "tushare":
            if market_value != "china":
                raise ValueError("TuShare Pro only supports China A-share imports in this platform.")
            return fetch_tushare_rows(symbol_value, start_date, end_date, token=api_key, adjust=adjust)
        if key == "baostock":
            if market_value != "china":
                raise ValueError("Baostock only supports China A-share imports in this platform.")
            return fetch_baostock_rows(symbol_value, start=start_date, end=end_date, adjust=adjust or "raw")
        if key == "adata":
            if market_value != "china":
                raise ValueError("AData only supports China A-share imports in this platform.")
            return fetch_adata_rows(symbol_value, start=start_date, end=end_date, adjust=adjust or "raw")
        if key == "eastmoney":
            return fetch_eastmoney_rows(symbol_value, market_value, start=start_date, end=end_date, adjust=adjust)
        if key == "sina":
            return fetch_sina_rows(symbol_value, market_value, start=start_date, end=end_date, adjust=adjust)
        if key == "tonghuashun":
            return fetch_tonghuashun_rows(symbol_value, market_value, start=start_date, end=end_date, adjust=adjust)
        if key == "yfinance":
            return _fetch_yfinance_rows(symbol_value, market_value, start_date, end_date)
        if key == "yahoo":
            if market_value != "usa":
                raise ValueError("Yahoo only supports US equities in this platform.")
            return fetch_yahoo_rows(symbol_value, start=start_date or "2000-01-01", end=end_date)
        if key == "stooq":
            if market_value != "usa":
                raise ValueError("Stooq only supports US equities in this platform.")
            return fetch_stooq_rows(symbol_value)
        if key == "alpha_vantage":
            if market_value != "usa":
                raise ValueError("Alpha Vantage only supports US equities in this platform.")
            key_value = api_key or os.environ.get("ALPHAVANTAGE_API_KEY")
            if not key_value:
                raise ValueError("Alpha Vantage API key is required.")
            return fetch_alpha_vantage_rows(symbol_value, key_value, outputsize)
        raise LeanWebError(f"{key} daily-bar import is not enabled; availability diagnostics are still reported.")

    def fetch_daily_with_fallback(
        self,
        *,
        symbol: str,
        provider: str | None,
        market: str,
        asset_class: str,
        api_key: str | None = None,
        outputsize: str = "compact",
        start_date: str | None = None,
        end_date: str | None = None,
        adjust: str = "",
        strict: bool = False,
    ) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        chain = self.chain(provider, market=market, asset_class=asset_class, start_date=start_date, end_date=end_date, strict=strict)
        last_error: Exception | None = None
        for source in chain:
            t0 = time.perf_counter()
            availability = provider_availability_item(source, start_date=start_date, end_date=end_date)
            if not availability.get("available"):
                attempts.append(
                    {
                        "source": source,
                        "status": "skipped",
                        "rows": 0,
                        "error": availability.get("unavailableReason") or availability.get("reason"),
                        "durationMs": round((time.perf_counter() - t0) * 1000, 2),
                    }
                )
                continue
            try:
                rows = self.fetch_provider_rows(
                    source,
                    symbol,
                    market=market,
                    asset_class=asset_class,
                    api_key=api_key,
                    outputsize=outputsize,
                    start_date=start_date,
                    end_date=end_date,
                    adjust=adjust,
                )
                elapsed = (time.perf_counter() - t0) * 1000
                if rows:
                    attempts.append({"source": source, "status": "success", "rows": len(rows), "durationMs": round(elapsed, 2)})
                    return {
                        "provider": source,
                        "rows": rows,
                        "attempts": attempts,
                        "policy": source_policy(
                            provider,
                            market=market,
                            asset_class=asset_class,
                            start_date=start_date,
                            end_date=end_date,
                            strict=strict,
                        ),
                    }
                attempts.append({"source": source, "status": "empty", "rows": 0, "durationMs": round(elapsed, 2)})
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                attempts.append(
                    {
                        "source": source,
                        "status": "failed",
                        "rows": 0,
                        "error": str(exc),
                        "durationMs": round((time.perf_counter() - t0) * 1000, 2),
                    }
                )
        raise ValueError(
            "No active source returned data; attempted: "
            + ", ".join(f"{item['source']}:{item['status']}" for item in attempts)
        ) from last_error


DATA_PROVIDER_MANAGER = DataProviderManager()
