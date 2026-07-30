from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..core.config import (
    ASHARE_TECH_AGENT_MODE,
    INSIGHTS_LLM_API_KEY,
    INSIGHTS_LLM_BASE_URL,
    INSIGHTS_LLM_MODEL,
    INSIGHTS_LLM_PROVIDER,
    INSIGHTS_LLM_TIMEOUT_SECONDS,
    insights_llm_public_catalog,
    resolve_insights_llm_runtime,
)
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from .tasks import append_log
from .tushare_adapter import TushareAdapter


AGENT_PROMPT_VERSION = "ashare-tech-agent-v3"
BUILTIN_PROMPT_VERSION_ID = "builtin:ashare-tech-agent-v3"
AGENT_STAGES = (
    {"key": "technical", "name": "技术趋势 Agent", "sequence": 1},
    {"key": "fundamental", "name": "基本面与催化 Agent", "sequence": 2},
    {"key": "bull", "name": "多头研究 Agent", "sequence": 3},
    {"key": "bear", "name": "空头研究 Agent", "sequence": 4},
    {"key": "risk", "name": "风险审查 Agent", "sequence": 5},
    {"key": "final", "name": "最终选股 Agent", "sequence": 6},
)
AGENT_STAGE_BY_KEY = {item["key"]: item for item in AGENT_STAGES}
HORIZONS = (1, 5, 20)
DIRECTIONS = {"bullish", "neutral", "bearish"}
FUNDAMENTAL_FIELD_ALIASES = {
    "roe": "roe",
    "roe_waa": "roe",
    "roe_dt": "roe",
    "or_yoy": "revenueGrowth",
    "revenue_yoy": "revenueGrowth",
    "q_sales_yoy": "revenueGrowth",
    "tr_yoy": "revenueGrowth",
    "netprofit_yoy": "profitGrowth",
    "net_profit_yoy": "profitGrowth",
    "q_profit_yoy": "profitGrowth",
    "debt_to_assets": "debtRatio",
    "debt_assets_ratio": "debtRatio",
    "n_income": "netProfit",
    "net_profit": "netProfit",
}
VALUATION_FACTORS = {"pe": "pe", "pe_ttm": "pe", "pb": "pb", "total_mv_cny": "totalMarketValue"}


class AgentOutputError(ValueError):
    pass


def _runtime(provider: str | None = None, model: str | None = None) -> dict[str, Any]:
    # Preserve module-level overrides used by tests and legacy single-provider deployments.
    provider_key = str(provider or INSIGHTS_LLM_PROVIDER or "").strip().lower()
    if provider_key == str(INSIGHTS_LLM_PROVIDER or "").strip().lower():
        runtime = {
            "provider": provider_key,
            "api_key": INSIGHTS_LLM_API_KEY,
            "base_url": INSIGHTS_LLM_BASE_URL,
            "model": model or INSIGHTS_LLM_MODEL,
            "models": [],
            "invalid_model": False,
        }
        catalog_entry = next(
            (item for item in insights_llm_public_catalog() if item["provider"] == provider_key),
            None,
        )
        if catalog_entry:
            runtime["models"] = catalog_entry["models"]
            allowed = {str(item["id"]) for item in catalog_entry["models"]}
            runtime["invalid_model"] = bool(model and model not in allowed)
        return runtime
    return dict(resolve_insights_llm_runtime(provider_key, model))


def _configured(provider: str | None = None, model: str | None = None) -> bool:
    runtime = _runtime(provider, model)
    return bool(
        runtime.get("base_url")
        and runtime.get("api_key")
        and runtime.get("model")
        and not runtime.get("invalid_model")
    )


def _endpoint(runtime: dict[str, Any] | None = None) -> str:
    selected = runtime or _runtime()
    base = str(selected.get("base_url") or "").rstrip("/")
    if selected.get("provider") == "anthropic":
        return base if base.endswith("/messages") else f"{base}/messages"
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def agent_capabilities() -> dict[str, Any]:
    configured = _configured()
    providers = insights_llm_public_catalog()
    return {
        "configured": configured,
        "provider": INSIGHTS_LLM_PROVIDER or None,
        "model": INSIGHTS_LLM_MODEL or None,
        "endpointHost": urlparse(INSIGHTS_LLM_BASE_URL).netloc if INSIGHTS_LLM_BASE_URL else None,
        "apiStyle": "Structured JSON (OpenAI-compatible or Anthropic Messages)",
        "agentMode": ASHARE_TECH_AGENT_MODE,
        "defaultAnalysisMode": "hybrid_multi_agent" if configured else "deterministic",
        "stages": list(AGENT_STAGES),
        "evaluationHorizons": list(HORIZONS),
        "agentPromptVersion": AGENT_PROMPT_VERSION,
        "providers": providers,
    }


def _safe_error(exc: Exception, api_key: str | None = None) -> str:
    message = str(exc)
    secret = api_key or INSIGHTS_LLM_API_KEY
    if secret:
        message = message.replace(secret, "[REDACTED]")
    return message[:2000]


def _error_category(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        if exc.code in {401, 403}:
            return "authentication"
        if exc.code == 429:
            return "rate_limit"
        return "provider_http"
    if isinstance(exc, (TimeoutError, URLError)):
        return "network"
    if isinstance(exc, (json.JSONDecodeError, AgentOutputError)):
        return "invalid_output"
    return "unknown"


def _extract_content(response: dict[str, Any]) -> dict[str, Any]:
    if isinstance(response.get("content"), list):
        content = "".join(
            str(item.get("text") or "")
            for item in response["content"]
            if isinstance(item, dict) and item.get("type") == "text"
        )
    else:
        content = ((((response.get("choices") or [{}])[0].get("message") or {}).get("content")))
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise AgentOutputError("Model response must be a JSON object.")
    return parsed


def _post_structured(
    system: str,
    payload_data: dict[str, Any],
    *,
    runtime: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], int]:
    selected = runtime or _runtime()
    payload: dict[str, Any] = {
        "model": selected["model"],
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload_data, ensure_ascii=False, separators=(",", ":"))},
        ],
    }
    headers = {
        "Authorization": f"Bearer {selected['api_key']}",
        "Content-Type": "application/json",
    }
    if selected["provider"] == "anthropic":
        payload = {
            "model": selected["model"],
            "max_tokens": 8192,
            "system": system,
            "messages": [{
                "role": "user",
                "content": (
                    "Return exactly one valid JSON object and no markdown.\n"
                    + json.dumps(payload_data, ensure_ascii=False, separators=(",", ":"))
                ),
            }],
        }
        headers = {
            "x-api-key": str(selected["api_key"]),
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
    if selected["provider"] == "kimi":
        payload["thinking"] = {"type": "disabled"}
    started = time.perf_counter()
    request = Request(
        _endpoint(selected),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers=headers,
    )
    with urlopen(request, timeout=INSIGHTS_LLM_TIMEOUT_SECONDS) as response:  # noqa: S310 - configured model endpoint
        raw = json.loads(response.read().decode("utf-8"))
    latency_ms = int((time.perf_counter() - started) * 1000)
    return _extract_content(raw), raw.get("usage") or {}, latency_ms


def model_diagnostics(
    requester: Callable[[str, dict[str, Any]], tuple[dict[str, Any], dict[str, Any], int]] = _post_structured,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    checked_at = utc_now()
    selected = _runtime(provider, model)
    capability = {
        **agent_capabilities(),
        "provider": selected.get("provider"),
        "model": selected.get("model"),
        "endpointHost": urlparse(str(selected.get("base_url") or "")).netloc or None,
    }
    if not _configured(provider, model):
        return {**capability, "status": "unconfigured", "checkedAt": checked_at}
    effective_requester = requester
    if requester is _post_structured:
        effective_requester = lambda system, payload: _post_structured(system, payload, runtime=selected)
    try:
        output, usage, latency_ms = effective_requester(
            "Return exactly one JSON object with ok=true. Do not add prose.",
            {"test": "ashare-tech-structured-json"},
        )
        if output.get("ok") is not True:
            raise AgentOutputError("Structured diagnostic did not return ok=true.")
        return {
            **capability,
            "status": "ok",
            "structuredJson": True,
            "latencyMs": latency_ms,
            "usage": usage,
            "checkedAt": checked_at,
        }
    except Exception as exc:
        return {
            **capability,
            "status": "error",
            "structuredJson": False,
            "errorCategory": _error_category(exc),
            "error": _safe_error(exc, str(selected.get("api_key") or "")),
            "checkedAt": checked_at,
        }


def _latest_fundamentals(symbols: list[str], as_of_date: str) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    placeholders = ",".join("?" for _ in symbols)
    raw_fields = sorted(FUNDAMENTAL_FIELD_ALIASES)
    field_placeholders = ",".join("?" for _ in raw_fields)
    result: dict[str, dict[str, Any]] = {symbol: {"metrics": {}, "evidence": []} for symbol in symbols}
    with db() as connection:
        facts = connection.execute(
            f"""
            select symbol,field_name,value,effective_date,announce_date,report_date,source
            from financial_facts
            where symbol in ({placeholders})
              and field_name in ({field_placeholders})
              and announce_date <= effective_date and effective_date <= ?
            order by symbol,effective_date,announce_date,report_date
            """,
            [*symbols, *raw_fields, as_of_date],
        ).fetchall()
        factor_placeholders = ",".join("?" for _ in VALUATION_FACTORS)
        factors = connection.execute(
            f"""
            select symbol,factor_name,value,trade_date,source
            from factor_values
            where symbol in ({placeholders})
              and factor_name in ({factor_placeholders}) and trade_date <= ?
            order by symbol,trade_date,factor_name
            """,
            [*symbols, *VALUATION_FACTORS, as_of_date],
        ).fetchall()
    for row in rows_to_dicts(facts):
        symbol = str(row["symbol"])
        canonical = FUNDAMENTAL_FIELD_ALIASES[str(row["field_name"])]
        result[symbol]["metrics"][canonical] = row.get("value")
        result[symbol]["evidence"] = [
            item for item in result[symbol]["evidence"] if item["field"] != canonical
        ] + [{
            "field": canonical,
            "date": str(row.get("effective_date"))[:10],
            "reportDate": str(row.get("report_date"))[:10],
            "source": row.get("source"),
        }]
    for row in rows_to_dicts(factors):
        symbol = str(row["symbol"])
        canonical = VALUATION_FACTORS[str(row["factor_name"])]
        result[symbol]["metrics"][canonical] = row.get("value")
        result[symbol]["evidence"] = [
            item for item in result[symbol]["evidence"] if item["field"] != canonical
        ] + [{
            "field": canonical,
            "date": str(row.get("trade_date"))[:10],
            "source": row.get("source"),
        }]
    for value in result.values():
        value["coverage"] = len(value["metrics"])
    return result


def build_fact_context(report: dict[str, Any]) -> dict[str, Any]:
    stocks = report.get("fullPool") or []
    symbols = [str(item.get("code")) for item in stocks if item.get("code")]
    fundamentals = _latest_fundamentals(symbols, str(report.get("analysisDate") or ""))
    facts: list[dict[str, Any]] = []
    for item in stocks:
        symbol = str(item["code"])
        facts.append({
            "id": f"TECH-{symbol}",
            "kind": "technical",
            "symbol": symbol,
            "name": item.get("name"),
            "date": item.get("date"),
            "values": {
                key: item.get(key)
                for key in (
                    "close", "changePct", "ma5", "ma10", "ma20", "ma60", "ma120",
                    "ma20Direction", "ma60Direction", "macdStatus", "return5Pct",
                    "return10Pct", "volatility20", "drawdown20Pct", "volumeRatio20",
                    "amountRatio20", "turnoverRate", "priceStructure", "conclusion",
                    "keySupport", "invalidation",
                )
            },
            "announcementRisk": item.get("announcementRisk"),
            "dataCompleteness": item.get("dataCompleteness"),
            "source": "TuShare Pro + deterministic rule engine",
        })
        fundamental = fundamentals.get(symbol) or {"metrics": {}, "evidence": [], "coverage": 0}
        facts.append({
            "id": f"FUND-{symbol}",
            "kind": "fundamental",
            "symbol": symbol,
            **fundamental,
            "status": "available" if fundamental.get("coverage") else "missing",
        })
        for index, announcement in enumerate(item.get("announcements") or [], 1):
            facts.append({
                "id": f"ANN-{symbol}-{index:02d}",
                "kind": "announcement",
                "symbol": symbol,
                **announcement,
            })
    for index, item in enumerate(report.get("marketEnvironment") or [], 1):
        facts.append({"id": f"MARKET-{index:02d}", "kind": "market", **item})
    for index, item in enumerate(report.get("policyEvidence") or [], 1):
        facts.append({"id": f"POLICY-{index:02d}", "kind": "policy", **item})
    return {
        "asOfDate": report.get("analysisDate"),
        "facts": facts,
        "symbols": symbols,
        "hardRuleConclusions": {str(item["code"]): item.get("conclusion") for item in stocks},
    }


def _all_evidence_ids(context: dict[str, Any]) -> set[str]:
    return {str(item["id"]) for item in context.get("facts") or [] if item.get("id")}


def _validate_evidence(value: Any, allowed: set[str]) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "evidenceIds":
                if (
                    not isinstance(nested, list)
                    or not nested
                    or any(str(item) not in allowed for item in nested)
                ):
                    raise AgentOutputError("Output contains missing or unknown evidenceIds.")
            else:
                _validate_evidence(nested, allowed)
    elif isinstance(value, list):
        for nested in value:
            _validate_evidence(nested, allowed)


def _number(value: Any, *, low: float = 0.0, high: float = 100.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AgentOutputError("Expected numeric score.") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise AgentOutputError(f"Numeric value must be between {low} and {high}.")
    return result


SIGNAL_INTENT_ALIASES = {
    "buy": "enter", "open": "enter", "open_position": "enter",
    "accumulate": "add", "increase": "add", "keep": "hold",
    "wait": "hold", "observe": "hold", "no_trade": "hold",
    "sell": "exit", "close": "exit", "close_position": "exit",
    "trim": "reduce", "decrease": "reduce",
}
SIGNAL_HORIZONS = {"1d", "5d", "20d", "swing"}


def _enum(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _unit_interval(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if 1 < number <= 100:
        number /= 100
    return max(0.0, min(number, 1.0)) if math.isfinite(number) else 0.0


def _signal_score(value: Any) -> int:
    number = _unit_interval(value)
    try:
        raw = float(value)
    except (TypeError, ValueError):
        raw = 0
    if raw > 1:
        number = max(0.0, min(raw / 100, 1.0))
    return int(round(number * 100))


def _optional_number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _candidate_signal(value: Any, fallback_forecast: dict[str, Any]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    direction = _enum(source.get("direction") or fallback_forecast.get("direction") or "flat")
    if direction == "bullish":
        direction = "long"
    elif direction == "bearish":
        direction = "flat"
    if direction not in {"long", "flat", "short"}:
        direction = "flat"
    stance = _enum(source.get("stance") or fallback_forecast.get("direction") or "neutral")
    if stance not in DIRECTIONS:
        stance = "neutral"
    raw_intent = _enum(source.get("intent") or ("enter" if direction == "long" else "hold"))
    intent = SIGNAL_INTENT_ALIASES.get(raw_intent, raw_intent)
    if intent not in {"enter", "add", "hold", "reduce", "exit"}:
        intent = "hold"
    horizon = _enum(source.get("horizon") or "5d")
    if horizon in {"1", "5", "20"}:
        horizon = f"{horizon}d"
    if horizon not in SIGNAL_HORIZONS:
        horizon = "swing"
    evidence_ids = [str(item) for item in source.get("evidenceIds") or fallback_forecast.get("evidenceIds") or []]
    return {
        "stance": stance,
        "direction": direction,
        "intent": intent,
        "targetExposure": _unit_interval(source.get("targetExposure")),
        "confidence": _unit_interval(source.get("confidence") if source.get("confidence") is not None else max((fallback_forecast.get("probabilities") or {}).values(), default=0)),
        "score": _signal_score(source.get("score") if source.get("score") is not None else fallback_forecast.get("trendScore")),
        "horizon": horizon,
        "entryLow": _optional_number(source.get("entryLow")),
        "entryHigh": _optional_number(source.get("entryHigh")),
        "stopLoss": _optional_number(source.get("stopLoss")),
        "targetPrice": _optional_number(source.get("targetPrice")),
        "invalidation": str(source.get("invalidation") or fallback_forecast.get("invalidation") or "")[:500],
        "reason": str(source.get("reason") or fallback_forecast.get("rationale") or "")[:1000],
        "evidenceIds": evidence_ids,
    }


def _validate_technical(value: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    symbols = set(context["symbols"])
    stocks = value.get("stocks")
    if not isinstance(stocks, list):
        raise AgentOutputError("technical.stocks must be an array.")
    output = []
    seen: set[str] = set()
    for item in stocks:
        symbol = str(item.get("symbol") or "")
        if symbol not in symbols or symbol in seen:
            raise AgentOutputError("technical output contains unknown or duplicate symbol.")
        forecasts = item.get("forecasts")
        if not isinstance(forecasts, list):
            raise AgentOutputError("technical forecasts must be an array.")
        normalized_forecasts = []
        horizons: set[int] = set()
        for forecast in forecasts:
            horizon = int(forecast.get("horizonDays") or 0)
            direction = str(forecast.get("direction") or "")
            probabilities = forecast.get("probabilities")
            if horizon not in HORIZONS or horizon in horizons or direction not in DIRECTIONS:
                raise AgentOutputError("technical forecast has invalid horizon or direction.")
            if not isinstance(probabilities, dict) or set(probabilities) != DIRECTIONS:
                raise AgentOutputError("technical probabilities must contain bullish, neutral and bearish.")
            normalized_probabilities = {key: _number(probabilities[key], low=0, high=1) for key in DIRECTIONS}
            if abs(sum(normalized_probabilities.values()) - 1.0) > 0.02:
                raise AgentOutputError("technical probabilities must sum to 1.")
            if normalized_probabilities[direction] < max(normalized_probabilities.values()) - 1e-9:
                raise AgentOutputError("technical direction must match the highest probability.")
            evidence_ids = [str(entry) for entry in forecast.get("evidenceIds") or []]
            normalized_forecasts.append({
                "horizonDays": horizon,
                "direction": direction,
                "probabilities": normalized_probabilities,
                "trendScore": _number(forecast.get("trendScore")),
                "rationale": str(forecast.get("rationale") or "")[:800],
                "evidenceIds": evidence_ids,
                "invalidation": str(forecast.get("invalidation") or "")[:500],
            })
            horizons.add(horizon)
        if horizons != set(HORIZONS):
            raise AgentOutputError("technical output must contain 1, 5 and 20 day forecasts.")
        five_day = next(item for item in normalized_forecasts if item["horizonDays"] == 5)
        candidate = _candidate_signal(item.get("candidateSignal"), five_day)
        output.append({"symbol": symbol, "forecasts": normalized_forecasts, "candidateSignal": candidate})
        seen.add(symbol)
    if seen != symbols:
        raise AgentOutputError("technical output must cover every observation-pool symbol.")
    normalized = {"stocks": output}
    _validate_evidence(normalized, _all_evidence_ids(context))
    return normalized


def _validate_stock_scores(value: dict[str, Any], context: dict[str, Any], key: str) -> dict[str, Any]:
    items = value.get("stocks")
    if not isinstance(items, list):
        raise AgentOutputError(f"{key}.stocks must be an array.")
    symbols = set(context["symbols"])
    output = []
    seen: set[str] = set()
    for item in items:
        symbol = str(item.get("symbol") or "")
        if symbol not in symbols or symbol in seen:
            raise AgentOutputError(f"{key} contains unknown or duplicate symbol.")
        normalized = {
            "symbol": symbol,
            "score": _number(item.get("score")),
            "summary": str(item.get("summary") or "")[:800],
            "evidenceIds": [str(entry) for entry in item.get("evidenceIds") or []],
        }
        for list_key in ("catalysts", "risks", "arguments"):
            if list_key in item:
                normalized[list_key] = [str(entry)[:500] for entry in (item.get(list_key) or [])][:8]
        if key == "fundamental":
            quality = str(item.get("quality") or "")
            if quality not in {"strong", "neutral", "weak", "unknown"}:
                raise AgentOutputError("fundamental quality is invalid.")
            normalized["quality"] = quality
            normalized["coverage"] = int(item.get("coverage") or 0)
        output.append(normalized)
        seen.add(symbol)
    if seen != symbols:
        raise AgentOutputError(f"{key} output must cover every observation-pool symbol.")
    result = {"stocks": output}
    _validate_evidence(result, _all_evidence_ids(context))
    return result


def _validate_risk(value: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    result = _validate_stock_scores(value, context, "risk")
    source = {str(item.get("symbol")): item for item in value.get("stocks") or []}
    for item in result["stocks"]:
        status = str(source[item["symbol"]].get("status") or "")
        if status not in {"pass", "downgrade", "veto"}:
            raise AgentOutputError("risk status must be pass, downgrade or veto.")
        item["status"] = status
    return result


def _hard_vetoes(report: dict[str, Any]) -> dict[str, list[str]]:
    output: dict[str, list[str]] = {}
    conflict_symbols = {str(item.get("code")) for item in report.get("sourceConflicts") or []}
    for item in report.get("fullPool") or []:
        symbol = str(item["code"])
        reasons: list[str] = []
        if item.get("conclusion") == "风险较高":
            reasons.append("deterministic_high_risk")
        if item.get("announcementRisk") and item.get("announcementRisk") != "未发现重大负面":
            reasons.append("announcement_risk")
        if (item.get("dataCompleteness") or {}).get("missing"):
            reasons.append("critical_data_incomplete")
        if symbol in conflict_symbols:
            reasons.append("source_conflict")
        if reasons:
            output[symbol] = reasons
    return output


def _validate_final(value: dict[str, Any], context: dict[str, Any], hard_vetoes: dict[str, list[str]]) -> dict[str, Any]:
    selections = value.get("selections")
    if not isinstance(selections, list):
        raise AgentOutputError("final.selections must be an array.")
    symbols = set(context["symbols"])
    output = []
    seen: set[str] = set()
    ranks: set[int] = set()
    for item in selections:
        symbol = str(item.get("symbol") or "")
        rank = int(item.get("rank") or 0)
        if symbol not in symbols or symbol in seen or rank < 1 or rank > 10 or rank in ranks:
            raise AgentOutputError("final selection has invalid symbol or rank.")
        if symbol in hard_vetoes:
            continue
        tier = "priority" if rank <= 5 else "watch"
        output.append({
            "rank": rank,
            "symbol": symbol,
            "tier": tier,
            "consensusScore": _number(item.get("consensusScore")),
            "rationale": str(item.get("rationale") or "")[:1000],
            "evidenceIds": [str(entry) for entry in item.get("evidenceIds") or []],
        })
        seen.add(symbol)
        ranks.add(rank)
    output.sort(key=lambda item: item["rank"])
    for index, item in enumerate(output, 1):
        item["rank"] = index
        item["tier"] = "priority" if index <= 5 else "watch"
    normalized = {
        "marketRegime": str(value.get("marketRegime") or "unknown")[:300],
        "summary": str(value.get("summary") or "")[:1500],
        "selections": output[:10],
        "vetoes": [{"symbol": symbol, "reasons": reasons} for symbol, reasons in sorted(hard_vetoes.items())],
    }
    _validate_evidence(normalized, _all_evidence_ids(context))
    return normalized


def _rule_profile(label: str) -> tuple[str, float, dict[str, float]]:
    profiles = {
        "小仓试错前置": ("bullish", 82, {"bullish": 0.68, "neutral": 0.24, "bearish": 0.08}),
        "重点观察": ("bullish", 76, {"bullish": 0.62, "neutral": 0.28, "bearish": 0.10}),
        "低吸观察": ("bullish", 70, {"bullish": 0.56, "neutral": 0.34, "bearish": 0.10}),
        "观察": ("neutral", 52, {"bullish": 0.28, "neutral": 0.52, "bearish": 0.20}),
        "不追高": ("neutral", 46, {"bullish": 0.24, "neutral": 0.51, "bearish": 0.25}),
        "继续等待": ("bearish", 34, {"bullish": 0.14, "neutral": 0.38, "bearish": 0.48}),
        "风险较高": ("bearish", 18, {"bullish": 0.06, "neutral": 0.20, "bearish": 0.74}),
    }
    return profiles.get(label, profiles["观察"])


def _fallback_technical(report: dict[str, Any]) -> dict[str, Any]:
    stocks = []
    for row in report.get("fullPool") or []:
        direction, score, probabilities = _rule_profile(str(row.get("conclusion") or "观察"))
        forecasts = []
        for horizon in HORIZONS:
            horizon_direction = direction
            horizon_probabilities = dict(probabilities)
            if horizon == 1 and row.get("conclusion") in {"低吸观察", "不追高"}:
                horizon_direction = "neutral"
                horizon_probabilities = {"bullish": 0.32, "neutral": 0.52, "bearish": 0.16}
            forecasts.append({
                "horizonDays": horizon,
                "direction": horizon_direction,
                "probabilities": horizon_probabilities,
                "trendScore": score,
                "rationale": f"确定性规则回退：{row.get('conclusion')} / {row.get('triggerType')}",
                "evidenceIds": [f"TECH-{row['code']}"],
                "invalidation": f"收盘低于 {row.get('invalidation')}" if row.get("invalidation") else "关键数据缺失",
            })
        close = _optional_number(row.get("close"))
        support = _optional_number(row.get("keySupport"))
        entry_low = _optional_number((row.get("observationZone") or [None, None])[0])
        entry_high = _optional_number((row.get("observationZone") or [None, None])[-1])
        intent = "enter" if row.get("conclusion") in {"低吸观察", "小仓试错前置", "重点观察"} else "hold"
        exposure = 0.15 if row.get("conclusion") == "小仓试错前置" else 0.1 if intent == "enter" else 0
        five_day = next(item for item in forecasts if item["horizonDays"] == 5)
        candidate = {
            "stance": direction,
            "direction": "long" if intent == "enter" else "flat",
            "intent": intent,
            "targetExposure": exposure,
            "confidence": max(five_day["probabilities"].values()),
            "score": int(score),
            "horizon": "5d",
            "entryLow": entry_low or close,
            "entryHigh": entry_high or close,
            "stopLoss": _optional_number(row.get("invalidation")) or (support * 0.97 if support else None),
            "targetPrice": _optional_number(row.get("high20")),
            "invalidation": five_day["invalidation"],
            "reason": five_day["rationale"],
            "evidenceIds": five_day["evidenceIds"],
        }
        stocks.append({"symbol": str(row["code"]), "forecasts": forecasts, "candidateSignal": candidate})
    return {"stocks": stocks}


def _fallback_fundamental(context: dict[str, Any]) -> dict[str, Any]:
    facts = {item["symbol"]: item for item in context["facts"] if item.get("kind") == "fundamental"}
    stocks = []
    for symbol in context["symbols"]:
        fact = facts.get(symbol) or {"coverage": 0, "metrics": {}}
        coverage = int(fact.get("coverage") or 0)
        metrics = fact.get("metrics") or {}
        positives = sum(1 for value in metrics.values() if isinstance(value, (int, float)) and value > 0)
        score = 50 if not coverage else min(85, 35 + positives * 8)
        stocks.append({
            "symbol": symbol,
            "score": score,
            "quality": "unknown" if not coverage else "strong" if score >= 70 else "neutral",
            "coverage": coverage,
            "summary": "基本面数据缺失" if not coverage else f"截至时点可见字段 {coverage} 项",
            "catalysts": [],
            "risks": ["基本面覆盖不足"] if coverage < 2 else [],
            "evidenceIds": [f"FUND-{symbol}"],
        })
    return {"stocks": stocks}


def _fallback_debate(context: dict[str, Any], technical: dict[str, Any], *, bullish: bool) -> dict[str, Any]:
    technical_by_symbol = {item["symbol"]: item for item in technical["stocks"]}
    stocks = []
    for symbol in context["symbols"]:
        forecast = next(item for item in technical_by_symbol[symbol]["forecasts"] if item["horizonDays"] == 5)
        base = float(forecast["trendScore"])
        score = min(100, base + 5) if bullish else min(100, 100 - base + 5)
        stocks.append({
            "symbol": symbol,
            "score": score,
            "summary": "规则事实支持趋势延续" if bullish else "规则事实提示反转与数据风险",
            "arguments": [forecast["rationale"]],
            "evidenceIds": forecast["evidenceIds"],
        })
    return {"stocks": stocks}


def _fallback_risk(report: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    vetoes = _hard_vetoes(report)
    stocks = []
    for symbol in context["symbols"]:
        reasons = vetoes.get(symbol) or []
        status = "veto" if reasons else "pass"
        stocks.append({
            "symbol": symbol,
            "score": 90 if reasons else 20,
            "status": status,
            "summary": "；".join(reasons) if reasons else "未触发确定性硬风险门禁",
            "risks": reasons,
            "evidenceIds": [f"TECH-{symbol}"],
        })
    return {"stocks": stocks}


def _fallback_final(
    report: dict[str, Any], context: dict[str, Any], technical: dict[str, Any], risk: dict[str, Any],
) -> dict[str, Any]:
    vetoes = {item["symbol"] for item in risk["stocks"] if item.get("status") == "veto"}
    technical_by_symbol = {item["symbol"]: item for item in technical["stocks"]}
    ranked = []
    for row in report.get("fullPool") or []:
        symbol = str(row["code"])
        if symbol in vetoes:
            continue
        forecast = next(item for item in technical_by_symbol[symbol]["forecasts"] if item["horizonDays"] == 5)
        ranked.append((float(forecast["trendScore"]), symbol, forecast))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selections = [{
        "rank": index,
        "symbol": symbol,
        "tier": "priority" if index <= 5 else "watch",
        "consensusScore": score,
        "rationale": forecast["rationale"],
        "evidenceIds": forecast["evidenceIds"],
    } for index, (score, symbol, forecast) in enumerate(ranked[:10], 1)]
    return {
        "marketRegime": report.get("finalThreeLines", {}).get("overallStage") or "unknown",
        "summary": "模型阶段不可用，按确定性规则排名。",
        "selections": selections,
        "vetoes": [{"symbol": item["symbol"], "reasons": item.get("risks") or []} for item in risk["stocks"] if item.get("status") == "veto"],
    }


STAGE_SYSTEMS = {
    "technical": (
        "你是A股技术趋势分析Agent。只使用FACTS，覆盖全部股票并预测1/5/20个交易日趋势。"
        "返回JSON stocks数组；每项含symbol和三个forecasts；forecast含horizonDays、direction、"
        "bullish/neutral/bearish probabilities、trendScore、rationale、evidenceIds、invalidation。"
        "每只股票还要给出candidateSignal，包含stance、direction、intent、targetExposure、confidence、"
        "score、horizon、entryLow、entryHigh、stopLoss、targetPrice、invalidation、reason、evidenceIds。"
        "targetExposure只代表该股票的独立研究信号。"
    ),
    "fundamental": (
        "你是PIT基本面与催化分析Agent。只使用截至分析日可见的FUND/ANN/POLICY事实，覆盖全部股票。"
        "返回JSON stocks数组；每项含symbol、score、quality(strong/neutral/weak/unknown)、coverage、"
        "summary、catalysts、risks、evidenceIds。缺失必须标unknown，不得补造财务或新闻。"
    ),
    "bull": (
        "你是多头研究Agent。审阅技术和基本面结构化结果，对全部股票提出可证伪的多头论据。"
        "返回JSON stocks数组；每项含symbol、score、summary、arguments、evidenceIds。不得新增事实或给出订单。"
    ),
    "bear": (
        "你是空头研究Agent。审阅技术和基本面结构化结果，对全部股票寻找反例、拥挤和下行风险。"
        "返回JSON stocks数组；每项含symbol、score、summary、arguments、evidenceIds。不得新增事实或给出订单。"
    ),
    "risk": (
        "你是风险审查Agent。覆盖全部股票，输出pass/downgrade/veto。"
        "返回JSON stocks数组；每项含symbol、score、status、summary、risks、evidenceIds。"
        "数据缺失、来源冲突、官方负面或确定性高风险不得被放行。"
    ),
    "final": (
        "你是最终选股Agent，仅做研究排序。综合前序输出，从未被否决的股票中最多选择10只。"
        "返回JSON marketRegime、summary、selections；selection含rank、symbol、consensusScore、rationale、evidenceIds。"
        "不得输出仓位、订单、买卖指令或收益承诺。"
    ),
}

STAGE_CONTRACTS = {
    "technical": (
        "硬性契约：输出必须是单个JSON对象并覆盖CONTEXT.symbols中的每只股票。"
        "forecasts必须恰好包含1/5/20日，三类概率均在0到1且合计为1。"
        "candidateSignal的intent只能是enter/add/hold/reduce/exit，direction只能是long/flat/short；"
        "targetExposure与confidence使用0到1小数，score使用0到100。所有evidenceIds必须来自CONTEXT。"
    ),
    "fundamental": (
        "硬性契约：输出单个JSON对象，stocks覆盖全部股票；quality只能是strong/neutral/weak/unknown；"
        "不得补造缺失数据，所有evidenceIds必须来自CONTEXT。"
    ),
    "bull": "硬性契约：输出单个JSON对象，stocks覆盖全部股票，所有evidenceIds必须来自CONTEXT，不得新增事实。",
    "bear": "硬性契约：输出单个JSON对象，stocks覆盖全部股票，所有evidenceIds必须来自CONTEXT，不得新增事实。",
    "risk": (
        "硬性契约：输出单个JSON对象，stocks覆盖全部股票，status只能是pass/downgrade/veto；"
        "确定性硬风险不得放行，所有evidenceIds必须来自CONTEXT。"
    ),
    "final": (
        "硬性契约：输出单个JSON对象，selections最多10只且不得包含硬否决股票；"
        "只做研究排序，不创建Paper信号或订单，所有evidenceIds必须来自CONTEXT。"
    ),
}


def _prompt_payload(
    *,
    prompt_id: str,
    template_key: str,
    name: str,
    description: str,
    version_no: int,
    stage_prompts: dict[str, str],
    fingerprint: str,
    created_at: str | None,
    builtin: bool,
) -> dict[str, Any]:
    return {
        "id": prompt_id,
        "templateKey": template_key,
        "name": name,
        "description": description,
        "version": version_no,
        "stagePrompts": stage_prompts,
        "fingerprint": fingerprint,
        "createdAt": created_at,
        "builtin": builtin,
    }


def builtin_prompt_version() -> dict[str, Any]:
    prompts = dict(STAGE_SYSTEMS)
    fingerprint = hashlib.sha256(json_dump(prompts).encode("utf-8")).hexdigest()
    return _prompt_payload(
        prompt_id=BUILTIN_PROMPT_VERSION_ID,
        template_key="builtin",
        name="A股科技日报内置模板",
        description="随代码发布的六阶段默认分析指令",
        version_no=1,
        stage_prompts=prompts,
        fingerprint=fingerprint,
        created_at=None,
        builtin=True,
    )


def list_prompt_templates(template_key: str | None = None) -> dict[str, Any]:
    with db() as connection:
        if template_key:
            rows = connection.execute(
                """
                select * from ashare_tech_prompt_templates
                where template_key=?
                order by version_no desc
                """,
                (template_key,),
            ).fetchall()
        else:
            rows = connection.execute(
                "select * from ashare_tech_prompt_templates order by template_key,version_no desc"
            ).fetchall()
    items = [builtin_prompt_version()] if template_key in {None, "builtin"} else []
    items.extend(
        _prompt_payload(
            prompt_id=str(item["id"]),
            template_key=str(item["template_key"]),
            name=str(item["name"]),
            description=str(item.get("description") or ""),
            version_no=int(item["version_no"]),
            stage_prompts=dict(item.get("stagePrompts") or {}),
            fingerprint=str(item["prompt_fingerprint"]),
            created_at=str(item["created_at"]),
            builtin=False,
        )
        for item in rows_to_dicts(rows)
    )
    return {"items": items, "count": len(items)}


def get_prompt_version(prompt_version_id: str | None) -> dict[str, Any]:
    if not prompt_version_id or prompt_version_id == BUILTIN_PROMPT_VERSION_ID:
        return builtin_prompt_version()
    with db() as connection:
        row = row_to_dict(connection.execute(
            "select * from ashare_tech_prompt_templates where id=?",
            (prompt_version_id,),
        ).fetchone())
    if not row:
        raise KeyError("Prompt version not found.")
    return _prompt_payload(
        prompt_id=str(row["id"]),
        template_key=str(row["template_key"]),
        name=str(row["name"]),
        description=str(row.get("description") or ""),
        version_no=int(row["version_no"]),
        stage_prompts=dict(row.get("stagePrompts") or {}),
        fingerprint=str(row["prompt_fingerprint"]),
        created_at=str(row["created_at"]),
        builtin=False,
    )


def save_prompt_version(
    *,
    name: str,
    description: str = "",
    stage_prompts: dict[str, str],
    template_key: str | None = None,
) -> dict[str, Any]:
    clean_name = name.strip()
    if not clean_name:
        raise AgentOutputError("Prompt template name is required.")
    expected = set(AGENT_STAGE_BY_KEY)
    if set(stage_prompts) != expected:
        raise AgentOutputError("Prompt template must contain all six Agent stages.")
    clean_prompts = {key: str(stage_prompts[key]).strip() for key in expected}
    if any(not value for value in clean_prompts.values()):
        raise AgentOutputError("Agent stage prompts cannot be empty.")
    key = re.sub(r"[^a-z0-9_-]+", "-", str(template_key or "").strip().lower()).strip("-")
    if not key or key == "builtin":
        key = f"custom-{uuid.uuid4().hex[:12]}"
    fingerprint = hashlib.sha256(json_dump(clean_prompts).encode("utf-8")).hexdigest()
    now = utc_now()
    with db() as connection:
        row = connection.execute(
            "select max(version_no) as version_no from ashare_tech_prompt_templates where template_key=?",
            (key,),
        ).fetchone()
        version_no = int(row["version_no"] or 0) + 1
        prompt_id = str(uuid.uuid4())
        connection.execute(
            """
            insert into ashare_tech_prompt_templates
                (id,template_key,name,description,version_no,stage_prompts_json,prompt_fingerprint,created_at)
            values (?,?,?,?,?,?,?,?)
            """,
            (
                prompt_id, key, clean_name, description.strip(), version_no,
                json_dump(clean_prompts), fingerprint, now,
            ),
        )
    return get_prompt_version(prompt_id)


def get_production_profile() -> dict[str, Any] | None:
    with db() as connection:
        row = row_to_dict(connection.execute(
            "select * from ashare_tech_agent_profiles where profile_key='scheduled-default'"
        ).fetchone())
    if row:
        return {
            "provider": row["provider"],
            "model": row["model"],
            "promptVersionId": row["prompt_version_id"],
            "updatedAt": row["updated_at"],
            "source": "published",
        }
    selected = _runtime()
    if not _configured():
        return None
    return {
        "provider": selected["provider"],
        "model": selected["model"],
        "promptVersionId": BUILTIN_PROMPT_VERSION_ID,
        "updatedAt": None,
        "source": "legacy-environment",
    }


def set_production_profile(provider: str, model: str, prompt_version_id: str) -> dict[str, Any]:
    selected = _runtime(provider, model)
    if not _configured(provider, model):
        raise AgentOutputError("Selected Provider/model is not configured or allowed.")
    get_prompt_version(prompt_version_id)
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into ashare_tech_agent_profiles(profile_key,provider,model,prompt_version_id,updated_at)
            values ('scheduled-default',?,?,?,?)
            on conflict(profile_key) do update set
                provider=excluded.provider,model=excluded.model,
                prompt_version_id=excluded.prompt_version_id,updated_at=excluded.updated_at
            """,
            (selected["provider"], selected["model"], prompt_version_id, now),
        )
    return get_production_profile() or {}


def _render_stage_prompt(stage_key: str, prompt: str) -> str:
    return f"{prompt.strip()}\n\n{STAGE_CONTRACTS[stage_key]}"


def _persist_stage_start(
    run_id: str,
    stage_key: str,
    input_fingerprint: str,
    fact_ids: list[str],
    *,
    runtime: dict[str, Any],
    prompt_version: str,
    prompt_version_id: str,
    system_prompt: str,
) -> str:
    now = utc_now()
    stage = AGENT_STAGE_BY_KEY[stage_key]
    with db() as connection:
        existing = connection.execute(
            "select * from ashare_tech_agent_stages where run_id=? and stage_key=?",
            (run_id, stage_key),
        ).fetchone()
        if existing and existing["status"] == "success" and existing["input_fingerprint"] == input_fingerprint:
            return str(existing["id"])
        stage_id = str(existing["id"]) if existing else str(uuid.uuid4())
        connection.execute(
            """
            insert into ashare_tech_agent_stages
                (id,run_id,stage_key,sequence_no,status,provider,model,prompt_version,input_fingerprint,
                 input_fact_ids_json,usage_json,attempt_count,started_at,updated_at,prompt_version_id,system_prompt)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            on conflict(run_id,stage_key) do update set
                status=excluded.status,provider=excluded.provider,model=excluded.model,
                prompt_version=excluded.prompt_version,input_fingerprint=excluded.input_fingerprint,
                input_fact_ids_json=excluded.input_fact_ids_json,attempt_count=0,error_category=null,
                error=null,started_at=excluded.started_at,finished_at=null,updated_at=excluded.updated_at,
                prompt_version_id=excluded.prompt_version_id,system_prompt=excluded.system_prompt
            """,
            (
                stage_id, run_id, stage_key, stage["sequence"], "running", runtime["provider"],
                runtime["model"], prompt_version, input_fingerprint, json_dump(fact_ids),
                "{}", 0, now, now, prompt_version_id, system_prompt,
            ),
        )
    return stage_id


def _run_stage(
    run_id: str,
    stage_key: str,
    context: dict[str, Any],
    stage_input: dict[str, Any],
    validator: Callable[[dict[str, Any]], dict[str, Any]],
    fallback: Callable[[], dict[str, Any]],
    requester: Callable[[str, dict[str, Any]], tuple[dict[str, Any], dict[str, Any], int]],
    runtime: dict[str, Any],
    prompt_version: str,
    prompt_version_id: str,
    stage_prompts: dict[str, str],
) -> tuple[dict[str, Any], str]:
    fact_ids = sorted(_all_evidence_ids(context))
    input_fingerprint = hashlib.sha256(json_dump(stage_input).encode("utf-8")).hexdigest()
    system_prompt = _render_stage_prompt(stage_key, stage_prompts[stage_key])
    stage_id = _persist_stage_start(
        run_id, stage_key, input_fingerprint, fact_ids,
        runtime=runtime, prompt_version=prompt_version,
        prompt_version_id=prompt_version_id, system_prompt=system_prompt,
    )
    last_error: Exception | None = None
    for attempt in range(1, 3):
        try:
            raw, usage, latency_ms = requester(system_prompt, stage_input)
            output = validator(raw)
            with db() as connection:
                connection.execute(
                    """
                    update ashare_tech_agent_stages
                    set status='success',output_json=?,usage_json=?,latency_ms=?,attempt_count=?,
                        error_category=null,error=null,finished_at=?,updated_at=?
                    where id=?
                    """,
                    (json_dump(output), json_dump(usage), latency_ms, attempt, utc_now(), utc_now(), stage_id),
                )
            return output, "success"
        except Exception as exc:
            last_error = exc
    output = fallback()
    with db() as connection:
        connection.execute(
            """
            update ashare_tech_agent_stages
            set status='fallback',output_json=?,usage_json='{}',attempt_count=2,error_category=?,error=?,
                finished_at=?,updated_at=?
            where id=?
            """,
            (
                json_dump(output), _error_category(last_error or AgentOutputError("unknown")),
                _safe_error(last_error or AgentOutputError("unknown"), str(runtime.get("api_key") or "")),
                utc_now(), utc_now(), stage_id,
            ),
        )
    return output, "fallback"


def _stage_payload(context: dict[str, Any], **prior: Any) -> dict[str, Any]:
    return {"CONTEXT": context, **prior}


def _stage_summary(run_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            """
            select stage_key,sequence_no,status,provider,model,prompt_version,prompt_version_id,
                   system_prompt,latency_ms,attempt_count,error_category,error,usage_json,started_at,finished_at
            from ashare_tech_agent_stages where run_id=? order by sequence_no
            """,
            (run_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def _create_skipped_stages(
    run_id: str,
    reason: str,
    *,
    runtime: dict[str, Any],
    prompt_version: str,
    prompt_version_id: str,
    stage_prompts: dict[str, str],
) -> None:
    now = utc_now()
    with db() as connection:
        for stage in AGENT_STAGES:
            connection.execute(
                """
                insert into ashare_tech_agent_stages
                    (id,run_id,stage_key,sequence_no,status,provider,model,prompt_version,input_fingerprint,
                     input_fact_ids_json,usage_json,attempt_count,error_category,error,finished_at,updated_at,
                     prompt_version_id,system_prompt)
                values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                on conflict(run_id,stage_key) do nothing
                """,
                (
                    str(uuid.uuid4()), run_id, stage["key"], stage["sequence"], "skipped",
                    runtime.get("provider"), runtime.get("model"), prompt_version,
                    "deterministic", "[]", "{}", 0, "unconfigured", reason, now, now,
                    prompt_version_id, _render_stage_prompt(stage["key"], stage_prompts[stage["key"]]),
                ),
            )


def _benchmark_for_symbol(symbol: str) -> str:
    if symbol.startswith("688"):
        return "000688"
    if symbol.startswith(("300", "301")):
        return "399006"
    if symbol.startswith(("0", "2", "3")):
        return "399001"
    return "000001"


def _neutral_band_pct(volatility20: Any, horizon: int) -> float:
    try:
        volatility = abs(float(volatility20))
    except (TypeError, ValueError):
        volatility = 0.02
    return round(max(0.5, min(5.0, 0.5 * volatility * math.sqrt(horizon) * 100)), 4)


def _guard_candidate_signal(
    raw: dict[str, Any],
    stock: dict[str, Any],
    risk: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    signal = dict(raw)
    violations: list[str] = []
    normalized_fields: list[str] = []
    direction = str(signal.get("direction") or "flat")
    intent = str(signal.get("intent") or "hold")
    exposure = _unit_interval(signal.get("targetExposure"))
    confidence = _unit_interval(signal.get("confidence"))
    if direction == "short":
        direction, exposure = "flat", 0.0
        if intent in {"enter", "add"}:
            intent = "exit"
        violations.append("spot_short_exposure_blocked")
    risk_status = str(risk.get("status") or "pass")
    if risk_status == "veto":
        violations.append("risk_veto")
    elif risk_status == "downgrade" and exposure > 0.05:
        normalized_fields.append(f"targetExposure:{exposure:g}->0.05")
        exposure = 0.05
        violations.append("risk_downgrade")
    missing = list((stock.get("dataCompleteness") or {}).get("missing") or [])
    if missing:
        violations.append("data_quality_degraded")
    if stock.get("announcementRisk") and stock.get("announcementRisk") != "未发现重大负面":
        violations.append("announcement_risk")
    if not signal.get("evidenceIds"):
        violations.append("evidence_missing")
    levels = {
        key: _optional_number(signal.get(key))
        for key in ("entryLow", "entryHigh", "stopLoss", "targetPrice")
    }
    if direction == "long" and intent in {"enter", "add"}:
        if any(value is None for value in levels.values()):
            violations.append("price_plan_incomplete")
        elif not (
            levels["stopLoss"] < levels["entryLow"]
            <= levels["entryHigh"] < levels["targetPrice"]
        ):
            violations.append("invalid_long_price_plan")
    blocking = {
        "risk_veto", "data_quality_degraded", "announcement_risk", "evidence_missing",
        "price_plan_incomplete", "invalid_long_price_plan",
    }
    actionable = (
        direction == "long"
        and intent in {"enter", "add"}
        and exposure > 0
        and not any(item in blocking for item in violations)
    )
    if not actionable:
        direction, intent, exposure = "flat", "hold", 0.0
    final = {
        **signal,
        "direction": direction,
        "intent": intent,
        "targetExposure": round(exposure, 4),
        "confidence": round(confidence, 4),
        "actionable": actionable,
        **levels,
    }
    guardrail = {
        "passed": not violations,
        "adjusted": bool(violations or normalized_fields),
        "violations": sorted(set(violations)),
        "normalizedFields": normalized_fields,
        "riskStatus": risk_status,
    }
    return final, guardrail


def _persist_candidate_signals(
    *,
    run_id: str,
    report_id: str,
    report: dict[str, Any],
    technical: dict[str, Any],
    risk: dict[str, Any],
    runtime: dict[str, Any],
    prompt_version: str,
    source_type: str,
) -> list[dict[str, Any]]:
    stocks = {str(item["code"]): item for item in report.get("fullPool") or []}
    risks = {str(item["symbol"]): item for item in risk.get("stocks") or []}
    persisted: list[dict[str, Any]] = []
    now = utc_now()
    with db() as connection:
        for item in technical.get("stocks") or []:
            symbol = str(item["symbol"])
            raw = dict(item.get("candidateSignal") or {})
            final, guardrail = _guard_candidate_signal(
                raw,
                stocks.get(symbol) or {},
                risks.get(symbol) or {},
            )
            signal_id = str(uuid.uuid4())
            status = "active" if final["actionable"] else "veto" if "risk_veto" in guardrail["violations"] else "observation"
            connection.execute(
                """
                insert into ashare_tech_candidate_signals
                    (id,run_id,report_id,symbol,provider,model,prompt_version,source_type,
                     raw_signal_json,final_signal_json,guardrail_json,status,created_at)
                values (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    signal_id, run_id, report_id, symbol, runtime.get("provider"), runtime.get("model"),
                    prompt_version, source_type, json_dump(raw), json_dump(final), json_dump(guardrail),
                    status, now,
                ),
            )
            persisted.append({
                "id": signal_id,
                "run_id": run_id,
                "report_id": report_id,
                "symbol": symbol,
                "provider": runtime.get("provider"),
                "model": runtime.get("model"),
                "prompt_version": prompt_version,
                "source_type": source_type,
                "rawSignal": raw,
                "finalSignal": final,
                "guardrail": guardrail,
                "status": status,
                "created_at": now,
            })
    return persisted


def _persist_predictions(
    run_id: str,
    report_id: str,
    report: dict[str, Any],
    technical: dict[str, Any],
    final: dict[str, Any],
    runtime: dict[str, Any],
    prompt_version: str,
) -> list[dict[str, Any]]:
    rows_by_symbol = {str(item["code"]): item for item in report.get("fullPool") or []}
    selections = {str(item["symbol"]): item for item in final.get("selections") or []}
    now = utc_now()
    persisted: list[dict[str, Any]] = []
    with db() as connection:
        for stock in technical["stocks"]:
            symbol = str(stock["symbol"])
            row = rows_by_symbol[symbol]
            selection = selections.get(symbol)
            for forecast in stock["forecasts"]:
                horizon = int(forecast["horizonDays"])
                probabilities = forecast["probabilities"]
                prediction_id = str(uuid.uuid4())
                confidence = max(float(value) for value in probabilities.values())
                connection.execute(
                    """
                    insert into ashare_tech_predictions
                        (id,run_id,report_id,symbol,horizon_days,predicted_direction,probabilities_json,
                         confidence,trend_score,rule_conclusion,selection_rank,selection_tier,rationale,
                         evidence_ids_json,neutral_band_pct,entry_date,entry_close,benchmark_code,model,
                         prompt_version,provider,created_at)
                    values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        prediction_id, run_id, report_id, symbol, horizon, forecast["direction"],
                        json_dump(probabilities), confidence, forecast["trendScore"], row.get("conclusion"),
                        selection.get("rank") if selection else None,
                        selection.get("tier") if selection else "unranked", forecast["rationale"],
                        json_dump(forecast["evidenceIds"]),
                        _neutral_band_pct(row.get("volatility20"), horizon),
                        str(report.get("analysisDate")), float(row.get("close")),
                        _benchmark_for_symbol(symbol), runtime["model"], prompt_version, runtime["provider"], now,
                    ),
                )
                persisted.append({
                    "id": prediction_id,
                    "symbol": symbol,
                    "horizonDays": horizon,
                    "direction": forecast["direction"],
                    "probabilities": probabilities,
                    "confidence": confidence,
                    "trendScore": forecast["trendScore"],
                    "selectionRank": selection.get("rank") if selection else None,
                    "selectionTier": selection.get("tier") if selection else "unranked",
                })
    return persisted


def run_agent_pipeline(
    *,
    task_id: str,
    report_id: str,
    report: dict[str, Any],
    requested_mode: str | None = None,
    requested_provider: str | None = None,
    requested_model: str | None = None,
    prompt_version_id: str | None = None,
    requester: Callable[[str, dict[str, Any]], tuple[dict[str, Any], dict[str, Any], int]] = _post_structured,
) -> dict[str, Any]:
    runtime = _runtime(requested_provider, requested_model)
    configured = _configured(requested_provider, requested_model)
    prompt = get_prompt_version(prompt_version_id)
    stage_prompts = dict(prompt["stagePrompts"])
    prompt_version = (
        AGENT_PROMPT_VERSION
        if prompt["builtin"]
        else f"{prompt['templateKey']}:v{prompt['version']}"
    )
    effective_requester = requester
    if requester is _post_structured:
        effective_requester = lambda system, payload: _post_structured(system, payload, runtime=runtime)
    requested = str(requested_mode or ASHARE_TECH_AGENT_MODE or "hybrid_multi_agent").strip().lower()
    if requested not in {"auto", "hybrid_multi_agent", "deterministic"}:
        requested = "hybrid_multi_agent"
    resolved_mode = "hybrid_multi_agent" if requested == "auto" and configured else "deterministic" if requested == "auto" else requested
    context = build_fact_context(report)
    input_fingerprint = hashlib.sha256(json_dump(context).encode("utf-8")).hexdigest()
    run_id = str(uuid.uuid4())
    now = utc_now()
    status = "running" if resolved_mode == "hybrid_multi_agent" and configured else "deterministic"
    fallback_reason = None
    if resolved_mode == "hybrid_multi_agent" and not configured:
        status = "degraded"
        fallback_reason = "LLM is not configured; deterministic report retained."
    with db() as connection:
        connection.execute(
            """
            insert into ashare_tech_agent_runs
                (id,report_id,task_id,requested_date,analysis_date,analysis_mode,status,provider,
                 requested_model,prompt_version,input_fingerprint,stage_summary_json,usage_json,
                 fallback_reason,created_at,started_at,updated_at,prompt_version_id,prompt_snapshot_json,
                 prompt_fingerprint)
            values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id, report_id, task_id, str(report.get("requestedDate")), str(report.get("analysisDate")),
                resolved_mode, status, runtime.get("provider"), runtime.get("model"),
                prompt_version, input_fingerprint, "[]", "{}", fallback_reason, now, now, now,
                prompt["id"], json_dump(stage_prompts), prompt["fingerprint"],
            ),
        )
        connection.execute(
            """
            update ashare_tech_reports
            set active_agent_run_id=?,analysis_mode=?,llm_status=?,context_json=?,
                requested_provider=?,requested_model=?,prompt_version_id=?,updated_at=?
            where id=?
            """,
            (
                run_id, resolved_mode, status, json_dump(context), runtime.get("provider"),
                runtime.get("model"), prompt["id"], now, report_id,
            ),
        )
    if resolved_mode == "deterministic" or not configured:
        _create_skipped_stages(
            run_id, fallback_reason or "Deterministic mode selected.",
            runtime=runtime, prompt_version=prompt_version, prompt_version_id=prompt["id"],
            stage_prompts=stage_prompts,
        )
        technical = _fallback_technical(report)
        risk = _fallback_risk(report, context)
        signals = _persist_candidate_signals(
            run_id=run_id, report_id=report_id, report=report, technical=technical, risk=risk,
            runtime=runtime, prompt_version=prompt_version, source_type="deterministic",
        )
        summary = {
            "runId": run_id,
            "analysisMode": resolved_mode,
            "status": status,
            "provider": runtime.get("provider"),
            "model": runtime.get("model"),
            "promptVersion": prompt_version,
            "promptVersionId": prompt["id"],
            "stages": _stage_summary(run_id),
            "topSelections": [],
            "fallbackReason": fallback_reason,
            "candidateSignalCount": len(signals),
        }
        with db() as connection:
            connection.execute(
                """
                update ashare_tech_agent_runs set stage_summary_json=?,finished_at=?,updated_at=? where id=?
                """,
                (json_dump(summary["stages"]), utc_now(), utc_now(), run_id),
            )
        return summary

    append_log(task_id, f"Starting A-share six-agent run {run_id} with {runtime['provider']}/{runtime['model']}.")
    technical_fallback = lambda: _fallback_technical(report)
    fundamental_fallback = lambda: _fallback_fundamental(context)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="ashare-agent") as pool:
        technical_future = pool.submit(
            _run_stage, run_id, "technical", context, _stage_payload(context),
            lambda value: _validate_technical(value, context), technical_fallback, effective_requester,
            runtime, prompt_version, prompt["id"], stage_prompts,
        )
        fundamental_future = pool.submit(
            _run_stage, run_id, "fundamental", context, _stage_payload(context),
            lambda value: _validate_stock_scores(value, context, "fundamental"), fundamental_fallback, effective_requester,
            runtime, prompt_version, prompt["id"], stage_prompts,
        )
        technical, technical_status = technical_future.result()
        fundamental, fundamental_status = fundamental_future.result()

    debate_input = _stage_payload(context, technical=technical, fundamental=fundamental)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="ashare-debate") as pool:
        bull_future = pool.submit(
            _run_stage, run_id, "bull", context, debate_input,
            lambda value: _validate_stock_scores(value, context, "bull"),
            lambda: _fallback_debate(context, technical, bullish=True), effective_requester,
            runtime, prompt_version, prompt["id"], stage_prompts,
        )
        bear_future = pool.submit(
            _run_stage, run_id, "bear", context, debate_input,
            lambda value: _validate_stock_scores(value, context, "bear"),
            lambda: _fallback_debate(context, technical, bullish=False), effective_requester,
            runtime, prompt_version, prompt["id"], stage_prompts,
        )
        bull, bull_status = bull_future.result()
        bear, bear_status = bear_future.result()

    risk_input = _stage_payload(
        context, technical=technical, fundamental=fundamental, bull=bull, bear=bear,
        hardVetoes=_hard_vetoes(report),
    )
    risk, risk_status = _run_stage(
        run_id, "risk", context, risk_input,
        lambda value: _validate_risk(value, context),
        lambda: _fallback_risk(report, context), effective_requester,
        runtime, prompt_version, prompt["id"], stage_prompts,
    )
    # Server-side gates always win, even if the model risk reviewer missed them.
    vetoes = _hard_vetoes(report)
    for item in risk["stocks"]:
        if item["symbol"] in vetoes:
            item["status"] = "veto"
            item["risks"] = sorted(set((item.get("risks") or []) + vetoes[item["symbol"]]))
    final_input = _stage_payload(
        context, technical=technical, fundamental=fundamental, bull=bull, bear=bear, risk=risk,
    )
    final, final_status = _run_stage(
        run_id, "final", context, final_input,
        lambda value: _validate_final(value, context, vetoes),
        lambda: _fallback_final(report, context, technical, risk), effective_requester,
        runtime, prompt_version, prompt["id"], stage_prompts,
    )
    # Apply the same guard to fallback and persisted output.
    final = _validate_final(final, context, vetoes)
    # Only model-produced trend probabilities enter the historical scorecard.
    # A deterministic technical fallback remains visible in the report, but
    # recording it under the configured model would contaminate model metrics.
    predictions = (
        _persist_predictions(run_id, report_id, report, technical, final, runtime, prompt_version)
        if technical_status == "success"
        else []
    )
    signals = _persist_candidate_signals(
        run_id=run_id, report_id=report_id, report=report, technical=technical, risk=risk,
        runtime=runtime, prompt_version=prompt_version,
        source_type="model" if technical_status == "success" else "deterministic",
    )
    stage_statuses = [technical_status, fundamental_status, bull_status, bear_status, risk_status, final_status]
    run_status = "success" if all(item == "success" for item in stage_statuses) else "degraded"
    fallback_reason = None if run_status == "success" else "One or more Agent stages used a deterministic fallback."
    stages = _stage_summary(run_id)
    usage: dict[str, float] = {}
    for stage in stages:
        for key, value in (stage.get("usage") or {}).items():
            if isinstance(value, (int, float)):
                usage[key] = usage.get(key, 0) + value
    finished_at = utc_now()
    with db() as connection:
        connection.execute(
            """
            update ashare_tech_agent_runs
            set status=?,stage_summary_json=?,usage_json=?,fallback_reason=?,finished_at=?,updated_at=?
            where id=?
            """,
            (run_status, json_dump(stages), json_dump(usage), fallback_reason, finished_at, finished_at, run_id),
        )
    append_log(task_id, f"Completed A-share Agent run {run_id}; status={run_status}; predictions={len(predictions)}.")
    return {
        "runId": run_id,
        "analysisMode": resolved_mode,
        "status": run_status,
        "provider": runtime["provider"],
        "model": runtime["model"],
        "promptVersion": prompt_version,
        "promptVersionId": prompt["id"],
        "stages": stages,
        "topSelections": final.get("selections") or [],
        "marketRegime": final.get("marketRegime"),
        "summary": final.get("summary"),
        "predictionCount": len(predictions),
        "candidateSignalCount": len(signals),
        "fallbackReason": fallback_reason,
        "usage": usage,
    }


def list_agent_runs(report_id: str) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from ashare_tech_agent_runs where report_id=? order by created_at desc",
            (report_id,),
        ).fetchall()
    return rows_to_dicts(rows)


def get_agent_run(run_id: str) -> dict[str, Any]:
    with db() as connection:
        run = row_to_dict(connection.execute("select * from ashare_tech_agent_runs where id=?", (run_id,)).fetchone())
        if not run:
            raise KeyError("A-share technology Agent run not found.")
        stages = rows_to_dicts(connection.execute(
            "select * from ashare_tech_agent_stages where run_id=? order by sequence_no", (run_id,),
        ).fetchall())
        predictions = rows_to_dicts(connection.execute(
            "select * from ashare_tech_predictions where run_id=? order by selection_rank is null,selection_rank,symbol,horizon_days",
            (run_id,),
        ).fetchall())
        signals = rows_to_dicts(connection.execute(
            "select * from ashare_tech_candidate_signals where run_id=? order by symbol",
            (run_id,),
        ).fetchall())
        report_row = row_to_dict(connection.execute(
            "select report_json,context_json from ashare_tech_reports where id=?",
            (run["report_id"],),
        ).fetchone())
    report_payload = (report_row or {}).get("report") or {}
    context = (report_row or {}).get("context") or {}
    stock_rows = {str(item["code"]): item for item in report_payload.get("fullPool") or []}
    stage_by_key = {str(item["stage_key"]): item.get("output") or {} for item in stages}
    per_stage: dict[str, dict[str, dict[str, Any]]] = {}
    for stage_key in ("technical", "fundamental", "bull", "bear", "risk"):
        per_stage[stage_key] = {
            str(item.get("symbol")): item
            for item in (stage_by_key.get(stage_key) or {}).get("stocks") or []
        }
    final_output = stage_by_key.get("final") or {}
    selections = {str(item.get("symbol")): item for item in final_output.get("selections") or []}
    signals_by_symbol = {str(item["symbol"]): item for item in signals}
    predictions_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for prediction in predictions:
        predictions_by_symbol.setdefault(str(prediction["symbol"]), []).append(prediction)
    symbols = list(context.get("symbols") or stock_rows)
    stock_insights = [{
        "symbol": symbol,
        "name": (stock_rows.get(symbol) or {}).get("name") or symbol,
        "metrics": stock_rows.get(symbol) or {},
        "technical": per_stage["technical"].get(symbol),
        "fundamental": per_stage["fundamental"].get(symbol),
        "bull": per_stage["bull"].get(symbol),
        "bear": per_stage["bear"].get(symbol),
        "risk": per_stage["risk"].get(symbol),
        "selection": selections.get(symbol),
        "predictions": predictions_by_symbol.get(symbol) or [],
        "signal": signals_by_symbol.get(symbol),
    } for symbol in symbols]
    return {
        **run,
        "stages": stages,
        "predictions": predictions,
        "candidateSignals": signals,
        "facts": context.get("facts") or [],
        "stockInsights": stock_insights,
    }


def delete_agent_data(report_id: str) -> None:
    with db() as connection:
        run_rows = connection.execute(
            "select id from ashare_tech_agent_runs where report_id=?", (report_id,),
        ).fetchall()
        run_ids = [str(row["id"]) for row in run_rows]
        connection.execute("delete from ashare_tech_prediction_evaluations where report_id=?", (report_id,))
        connection.execute("delete from ashare_tech_candidate_signals where report_id=?", (report_id,))
        connection.execute("delete from ashare_tech_predictions where report_id=?", (report_id,))
        for run_id in run_ids:
            connection.execute("delete from ashare_tech_agent_stages where run_id=?", (run_id,))
        connection.execute("delete from ashare_tech_agent_runs where report_id=?", (report_id,))


def _realized_direction(return_pct: float, band_pct: float) -> str:
    if return_pct > band_pct:
        return "bullish"
    if return_pct < -band_pct:
        return "bearish"
    return "neutral"


def _brier(probabilities: dict[str, Any], realized: str) -> float:
    return sum((float(probabilities[key]) - (1.0 if key == realized else 0.0)) ** 2 for key in DIRECTIONS)


def refresh_evaluations(
    *,
    adapter: TushareAdapter | None = None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    adapter = adapter or TushareAdapter()
    as_of_date = as_of_date or date.today().isoformat()
    with db() as connection:
        predictions = rows_to_dicts(connection.execute(
            """
            select p.* from ashare_tech_predictions p
            left join ashare_tech_prediction_evaluations e on e.prediction_id=p.id
            where e.id is null or e.status='pending'
            order by p.entry_date,p.symbol,p.horizon_days
            """
        ).fetchall())
    if not predictions:
        return {"evaluated": 0, "pending": 0, "failed": 0}
    calendar_cache: dict[str, list[str]] = {}
    price_cache: dict[tuple[str, str, str], dict[str, float]] = {}
    benchmark_cache: dict[tuple[str, str, str], dict[str, float]] = {}
    targets: dict[str, str | None] = {}
    for prediction in predictions:
        entry_date = str(prediction["entry_date"])
        if entry_date not in calendar_cache:
            calendar = adapter.trade_calendar(entry_date, as_of_date)
            calendar_cache[entry_date] = sorted(
                str(item["trade_date"]) for item in calendar
                if item.get("is_open") and str(item.get("trade_date")) > entry_date
            )
        open_dates = calendar_cache[entry_date]
        horizon = int(prediction["horizon_days"])
        targets[str(prediction["id"])] = open_dates[horizon - 1] if len(open_dates) >= horizon else None
    from .ashare_tech_insights import qfq_rows  # local import avoids circular module initialization

    stats = {"evaluated": 0, "pending": 0, "failed": 0}
    now = utc_now()
    for prediction in predictions:
        prediction_id = str(prediction["id"])
        target = targets[prediction_id]
        status = "pending"
        values: dict[str, Any] = {}
        missing_reason = None
        source_manifest: list[dict[str, Any]] = []
        try:
            if not target:
                missing_reason = "horizon_not_mature"
            else:
                symbol = str(prediction["symbol"])
                entry_date = str(prediction["entry_date"])
                stock_key = (symbol, entry_date, target)
                if stock_key not in price_cache:
                    rows = qfq_rows(adapter.daily_rows(symbol, entry_date, target))
                    price_cache[stock_key] = {
                        str(item["date"]): float(item["close"]) for item in rows if item.get("close") is not None
                    }
                benchmark = str(prediction["benchmark_code"])
                benchmark_key = (benchmark, entry_date, target)
                if benchmark_key not in benchmark_cache:
                    rows = adapter.index_daily_rows(benchmark, entry_date, target)
                    benchmark_cache[benchmark_key] = {
                        str(item.get("date") or item.get("trade_date")): float(item["close"])
                        for item in rows if item.get("close") is not None
                    }
                stock_prices = price_cache[stock_key]
                benchmark_prices = benchmark_cache[benchmark_key]
                stock_entry = stock_prices.get(entry_date)
                stock_exit = stock_prices.get(target)
                benchmark_entry = benchmark_prices.get(entry_date)
                benchmark_exit = benchmark_prices.get(target)
                if not all(value is not None and value > 0 for value in (stock_entry, stock_exit, benchmark_entry, benchmark_exit)):
                    missing_reason = "target_prices_incomplete"
                else:
                    return_pct = (float(stock_exit) / float(stock_entry) - 1) * 100
                    benchmark_return_pct = (float(benchmark_exit) / float(benchmark_entry) - 1) * 100
                    realized = _realized_direction(return_pct, float(prediction["neutral_band_pct"]))
                    probabilities = prediction.get("probabilities") or {}
                    values = {
                        "evaluated_date": target,
                        "entry_close": stock_entry,
                        "exit_close": stock_exit,
                        "benchmark_entry_close": benchmark_entry,
                        "benchmark_exit_close": benchmark_exit,
                        "return_pct": round(return_pct, 6),
                        "benchmark_return_pct": round(benchmark_return_pct, 6),
                        "excess_return_pct": round(return_pct - benchmark_return_pct, 6),
                        "realized_direction": realized,
                        "direction_hit": 1 if realized == prediction["predicted_direction"] else 0,
                        "brier_score": round(_brier(probabilities, realized), 8),
                    }
                    source_manifest = [
                        {"source": "tushare:daily+adj_factor", "symbol": symbol, "from": entry_date, "to": target},
                        {"source": "tushare:index_daily", "symbol": benchmark, "from": entry_date, "to": target},
                    ]
                    status = "evaluated"
            stats[status if status in stats else "pending"] += 1
        except Exception as exc:
            status = "failed"
            missing_reason = _safe_error(exc)
            stats["failed"] += 1
        with db() as connection:
            connection.execute(
                "update ashare_tech_predictions set target_date=? where id=?",
                (target, prediction_id),
            )
            connection.execute(
                """
                insert into ashare_tech_prediction_evaluations
                    (id,prediction_id,run_id,report_id,symbol,horizon_days,status,evaluated_date,
                     entry_close,exit_close,benchmark_code,benchmark_entry_close,benchmark_exit_close,
                     return_pct,benchmark_return_pct,excess_return_pct,realized_direction,direction_hit,
                     brier_score,source_manifest_json,missing_reason,created_at,updated_at)
                values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                on conflict(prediction_id) do update set
                    status=excluded.status,evaluated_date=excluded.evaluated_date,entry_close=excluded.entry_close,
                    exit_close=excluded.exit_close,benchmark_entry_close=excluded.benchmark_entry_close,
                    benchmark_exit_close=excluded.benchmark_exit_close,return_pct=excluded.return_pct,
                    benchmark_return_pct=excluded.benchmark_return_pct,excess_return_pct=excluded.excess_return_pct,
                    realized_direction=excluded.realized_direction,direction_hit=excluded.direction_hit,
                    brier_score=excluded.brier_score,source_manifest_json=excluded.source_manifest_json,
                    missing_reason=excluded.missing_reason,updated_at=excluded.updated_at
                """,
                (
                    str(uuid.uuid4()), prediction_id, prediction["run_id"], prediction["report_id"],
                    prediction["symbol"], prediction["horizon_days"], status, values.get("evaluated_date"),
                    values.get("entry_close") or prediction["entry_close"], values.get("exit_close"),
                    prediction["benchmark_code"], values.get("benchmark_entry_close"),
                    values.get("benchmark_exit_close"), values.get("return_pct"),
                    values.get("benchmark_return_pct"), values.get("excess_return_pct"),
                    values.get("realized_direction"), values.get("direction_hit"), values.get("brier_score"),
                    json_dump(source_manifest), missing_reason, now, now,
                ),
            )
    return stats


def list_evaluations(
    *,
    horizon_days: int | None = None,
    symbol: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    clauses = ["1=1"]
    params: list[Any] = []
    if horizon_days is not None:
        clauses.append("p.horizon_days=?")
        params.append(horizon_days)
    if symbol:
        clauses.append("p.symbol=?")
        params.append(symbol)
    if provider:
        clauses.append("p.provider=?")
        params.append(provider)
    if model:
        clauses.append("p.model=?")
        params.append(model)
    if prompt_version:
        clauses.append("p.prompt_version=?")
        params.append(prompt_version)
    params.append(min(max(limit, 1), 2000))
    with db() as connection:
        rows = connection.execute(
            f"""
            select p.*,e.status as evaluation_status,e.evaluated_date,e.exit_close,
                   e.benchmark_entry_close,e.benchmark_exit_close,e.return_pct,
                   e.benchmark_return_pct,e.excess_return_pct,e.realized_direction,
                   e.direction_hit,e.brier_score,e.missing_reason
            from ashare_tech_predictions p
            left join ashare_tech_prediction_evaluations e on e.prediction_id=p.id
            where {' and '.join(clauses)}
            order by p.entry_date desc,p.selection_rank is null,p.selection_rank,p.symbol,p.horizon_days
            limit ?
            """,
            params,
        ).fetchall()
    items = rows_to_dicts(rows)
    return {"items": items, "count": len(items)}


def evaluation_summary(
    *,
    horizon_days: int | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
) -> dict[str, Any]:
    response = list_evaluations(
        horizon_days=horizon_days, provider=provider, model=model,
        prompt_version=prompt_version, limit=2000,
    )
    matured = [item for item in response["items"] if item.get("evaluation_status") == "evaluated"]
    pending = [item for item in response["items"] if item.get("evaluation_status") in {None, "pending"}]

    def mean(key: str, rows: list[dict[str, Any]]) -> float | None:
        values = [float(item[key]) for item in rows if item.get(key) is not None]
        return round(sum(values) / len(values), 6) if values else None

    selected = [item for item in matured if item.get("selection_rank") is not None]
    top5 = [item for item in matured if item.get("selection_rank") is not None and int(item["selection_rank"]) <= 5]
    by_horizon = []
    for horizon in HORIZONS:
        horizon_rows = [item for item in matured if int(item["horizon_days"]) == horizon]
        horizon_top5 = [item for item in horizon_rows if item.get("selection_rank") is not None and int(item["selection_rank"]) <= 5]
        by_horizon.append({
            "horizonDays": horizon,
            "sampleSize": len(horizon_rows),
            "directionAccuracy": mean("direction_hit", horizon_rows),
            "meanBrier": mean("brier_score", horizon_rows),
            "averageReturnPct": mean("return_pct", horizon_rows),
            "averageExcessReturnPct": mean("excess_return_pct", horizon_rows),
            "top5AverageReturnPct": mean("return_pct", horizon_top5),
            "top5LiftPct": (
                round((mean("return_pct", horizon_top5) or 0) - (mean("return_pct", horizon_rows) or 0), 6)
                if horizon_top5 and horizon_rows else None
            ),
        })
    return {
        "sampleSize": len(matured),
        "pending": len(pending),
        "sampleSufficient": len(matured) >= 20,
        "directionAccuracy": mean("direction_hit", matured),
        "meanBrier": mean("brier_score", matured),
        "averageReturnPct": mean("return_pct", matured),
        "averageExcessReturnPct": mean("excess_return_pct", matured),
        "selectedAverageReturnPct": mean("return_pct", selected),
        "top5AverageReturnPct": mean("return_pct", top5),
        "byHorizon": by_horizon,
        "provider": provider,
        "model": model,
        "promptVersion": prompt_version,
    }
