from __future__ import annotations

import hashlib
import json
import math
import statistics
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..core.config import (
    INSIGHTS_LLM_API_KEY,
    INSIGHTS_LLM_BASE_URL,
    INSIGHTS_LLM_MODEL,
    INSIGHTS_LLM_PROVIDER,
    INSIGHTS_LLM_TIMEOUT_SECONDS,
)
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..domain.assets import ASSET_CLASSES, asset_request
from .market_data import query_database_bars
from .tasks import append_log, update_task


PROMPT_VERSION = "lean-insights-v1"
SPOT_ASSET_CLASSES = {"equity", "crypto"}
EVIDENCE_SOURCES = {"price", "technical", "data_quality", "backtest"}
SIGNAL_HORIZONS = {"intraday", "1d", "3d", "5d", "10d", "swing", "long"}


class InsightError(ValueError):
    pass


class InsightConfigurationError(InsightError):
    pass


class InsightDeleteConflict(InsightError):
    pass


def capabilities() -> dict[str, Any]:
    configured = bool(INSIGHTS_LLM_BASE_URL and INSIGHTS_LLM_API_KEY and INSIGHTS_LLM_MODEL)
    return {
        "configured": configured,
        "provider": INSIGHTS_LLM_PROVIDER or None,
        "model": INSIGHTS_LLM_MODEL or None,
        "assetClasses": sorted(ASSET_CLASSES),
        "resolutions": ["daily"],
        "paperHandoffAssetClasses": sorted(SPOT_ASSET_CLASSES),
        "promptVersion": PROMPT_VERSION,
    }


def _dedupe_bars(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_timestamp: dict[str, dict[str, Any]] = {}
    for item in items:
        by_timestamp[str(item.get("timestamp") or "")] = item
    return [by_timestamp[key] for key in sorted(by_timestamp) if key]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _mean(values: list[float]) -> float | None:
    return round(statistics.fmean(values), 6) if values else None


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) <= period:
        return None
    changes = [closes[index] - closes[index - 1] for index in range(len(closes) - period, len(closes))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    average_loss = statistics.fmean(losses)
    if average_loss == 0:
        return 100.0
    relative_strength = statistics.fmean(gains) / average_loss
    return round(100 - (100 / (1 + relative_strength)), 4)


def _technical_context(bars: list[dict[str, Any]], asset_class: str) -> dict[str, Any]:
    closes = [_finite(item.get("close")) for item in bars]
    close_values = [item for item in closes if item is not None]
    volumes = [_finite(item.get("volume")) for item in bars]
    volume_values = [item for item in volumes if item is not None]
    returns = [
        (close_values[index] / close_values[index - 1]) - 1
        for index in range(1, len(close_values))
        if close_values[index - 1] != 0
    ]
    highs = [item for item in (_finite(row.get("high")) for row in bars[-20:]) if item is not None]
    lows = [item for item in (_finite(row.get("low")) for row in bars[-20:]) if item is not None]
    latest = bars[-1] if bars else {}
    return {
        "latestClose": _finite(latest.get("close")),
        "latestVolume": _finite(latest.get("volume")),
        "sma20": _mean(close_values[-20:]),
        "sma50": _mean(close_values[-50:]),
        "rsi14": _rsi(close_values),
        "return5dPct": round(((close_values[-1] / close_values[-6]) - 1) * 100, 4) if len(close_values) >= 6 and close_values[-6] else None,
        "return20dPct": round(((close_values[-1] / close_values[-21]) - 1) * 100, 4) if len(close_values) >= 21 and close_values[-21] else None,
        "realizedVolatility20dPct": round(
            statistics.pstdev(returns[-20:]) * math.sqrt(365 if asset_class in {"crypto", "crypto_future"} else 252) * 100,
            4,
        ) if len(returns) >= 2 else None,
        "high20": max(highs) if highs else None,
        "low20": min(lows) if lows else None,
        "averageVolume20": _mean(volume_values[-20:]),
    }


def _derivative_context(request_asset: Any, as_of_date: str | None) -> dict[str, Any] | None:
    if request_asset.asset_class not in {"future", "crypto_future"}:
        return None
    predicates = ["symbol = ?", "asset_class = ?", "venue = ?"]
    values: list[Any] = [request_asset.symbol, request_asset.asset_class, request_asset.venue]
    if as_of_date:
        predicates.append("trade_date <= ?")
        values.append(as_of_date)
    with db() as connection:
        bar = connection.execute(
            f"""
            select trade_date, settle, open_interest, source
            from market_daily_bars
            where {' and '.join(predicates)}
            order by trade_date desc
            limit 1
            """,
            values,
        ).fetchone()
        instrument = connection.execute(
            """
            select underlying_symbol, expiry_date, contract_multiplier, margin_rate, currency,
                   base_currency, quote_currency, source
            from instruments
            where symbol = ? and asset_class = ? and venue = ?
            order by updated_at desc
            limit 1
            """,
            (request_asset.symbol, request_asset.asset_class, request_asset.venue),
        ).fetchone()
    return {
        "latest": dict(bar) if bar else None,
        "contract": dict(instrument) if instrument else None,
    }


def _backtest_context(run_id: str | None, request_asset: Any) -> dict[str, Any] | None:
    if not run_id:
        return None
    with db() as connection:
        run_row = connection.execute("select * from backtest_runs where id = ?", (run_id,)).fetchone()
        result_row = connection.execute("select * from backtest_results where job_id = ?", (run_id,)).fetchone()
    run = row_to_dict(run_row)
    if not run:
        raise InsightError("Backtest run not found.")
    if run.get("status") != "success":
        raise InsightError("Backtest run must be successful.")
    if str(run.get("symbol") or "").upper() != request_asset.symbol:
        raise InsightError("Backtest run symbol does not match the insight request.")
    if str(run.get("asset_class") or "equity") != request_asset.asset_class:
        raise InsightError("Backtest run asset class does not match the insight request.")
    if str(run.get("venue") or "") != request_asset.venue:
        raise InsightError("Backtest run venue does not match the insight request.")
    result = row_to_dict(result_row) or {}
    return {
        "runId": run_id,
        "finishedAt": run.get("finished_at"),
        "summaryMetrics": result.get("summary_metrics") or {},
        "validation": run.get("validation") or (result.get("performance") or {}).get("validation"),
        "fingerprint": run.get("fingerprint"),
    }


def build_context(parameters: dict[str, Any]) -> dict[str, Any]:
    request_asset = asset_request(
        parameters["symbol"],
        parameters.get("assetClass"),
        parameters.get("venue"),
        parameters.get("market"),
        "daily",
        parameters.get("dataType") or "trade",
    )
    lookback = max(60, min(int(parameters.get("lookbackBars") or 120), 500))
    payload = query_database_bars(
        asset_class=request_asset.asset_class,
        symbol=request_asset.symbol,
        market=parameters.get("market"),
        venue=request_asset.venue,
        resolution="daily",
        data_type=request_asset.data_type,
        end_date=parameters.get("asOfDate"),
        limit=5000,
    )
    bars = _dedupe_bars(payload.get("items") or [])[-lookback:]
    sources = sorted({str(item.get("source")) for item in bars if item.get("source")})
    warnings: list[str] = []
    if len(bars) < 60:
        warnings.append(f"insufficient_daily_bars:{len(bars)}/60")
    if not bars:
        warnings.append("daily_bars_missing")
    as_of_date = str(bars[-1].get("timestamp"))[:10] if bars else parameters.get("asOfDate")
    return {
        "instrument": {
            "symbol": request_asset.symbol,
            "assetClass": request_asset.asset_class,
            "market": parameters.get("market"),
            "venue": request_asset.venue,
            "resolution": "daily",
            "dataType": request_asset.data_type,
        },
        "asOfDate": as_of_date,
        "price": {
            "barCount": len(bars),
            "firstDate": str(bars[0].get("timestamp"))[:10] if bars else None,
            "lastDate": as_of_date,
            "latest": bars[-1] if bars else None,
            "recentBars": bars[-30:],
        },
        "technical": _technical_context(bars, request_asset.asset_class),
        "derivative": _derivative_context(request_asset, as_of_date),
        "dataQuality": {
            "level": "ok" if not warnings else "degraded",
            "sources": sources,
            "warnings": warnings,
        },
        "backtest": _backtest_context(parameters.get("backtestRunId"), request_asset),
    }


def _llm_endpoint() -> str:
    base = INSIGHTS_LLM_BASE_URL.rstrip("/")
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def _post_json(payload: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        _llm_endpoint(),
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {INSIGHTS_LLM_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=INSIGHTS_LLM_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _extract_content(response: dict[str, Any]) -> dict[str, Any]:
    choices = response.get("choices") or []
    if not choices:
        raise InsightError("LLM response did not contain choices.")
    content = ((choices[0].get("message") or {}).get("content"))
    if isinstance(content, dict):
        return content
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise InsightError("LLM response must be a JSON object.")
    return parsed


def _validate_analysis_response(value: dict[str, Any]) -> dict[str, Any]:
    required_sections = {"summary", "technical", "risks", "catalysts", "evidence", "signal"}
    missing_sections = sorted(required_sections - set(value))
    if missing_sections:
        raise InsightError(f"LLM response missing sections: {', '.join(missing_sections)}")
    if not isinstance(value.get("summary"), dict) or not isinstance(value.get("technical"), dict):
        raise InsightError("LLM summary and technical sections must be objects.")
    for key in ("risks", "catalysts", "evidence"):
        if not isinstance(value.get(key), list):
            raise InsightError(f"LLM {key} section must be an array.")
    signal = value.get("signal")
    if not isinstance(signal, dict):
        raise InsightError("LLM signal section must be an object.")
    required_signal = {"stance", "direction", "intent", "targetExposure", "confidence", "score", "horizon", "reason"}
    missing_signal = sorted(required_signal - set(signal))
    if missing_signal:
        raise InsightError(f"LLM signal missing fields: {', '.join(missing_signal)}")
    return value


def request_analysis(context: dict[str, Any]) -> dict[str, Any]:
    if not capabilities()["configured"]:
        raise InsightConfigurationError(
            "Configure DEEPSEEK_API_KEY, ZHIPU_API_KEY, KIMI_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY to enable Insights."
        )
    system = (
        "You are a quantitative research assistant. Use only facts in CONTEXT. "
        "No news or sentiment claims are allowed. Return JSON only with keys summary, technical, risks, catalysts, evidence, signal. "
        "evidence items must be {fact, sourceKey} where sourceKey is price, technical, data_quality, or backtest. "
        "signal must include stance, direction, intent, targetExposure, confidence, score, horizon, entryLow, entryHigh, stopLoss, targetPrice, invalidation, reason."
    )
    payload = {
        "model": INSIGHTS_LLM_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "CONTEXT:\n" + json.dumps(context, ensure_ascii=False)},
        ],
    }
    if INSIGHTS_LLM_PROVIDER == "kimi":
        payload["thinking"] = {"type": "disabled"}
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            return _validate_analysis_response(_extract_content(_post_json(payload)))
        except HTTPError as exc:
            last_error = exc
            if exc.code < 500 and exc.code != 429:
                break
        except (URLError, TimeoutError, json.JSONDecodeError, InsightError) as exc:
            last_error = exc
        if attempt == 0:
            time.sleep(0.2)
    raise InsightError(f"LLM analysis failed after two attempts: {last_error}")


def _clean_evidence(value: Any) -> list[dict[str, str]]:
    items = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        source_key = str(item.get("sourceKey") or "").strip().lower()
        fact = str(item.get("fact") or "").strip()
        if fact and source_key in EVIDENCE_SOURCES:
            items.append({"fact": fact, "sourceKey": source_key})
    return items[:12]


def normalize_report(response: dict[str, Any]) -> dict[str, Any]:
    summary = response.get("summary") if isinstance(response.get("summary"), dict) else {}
    technical = response.get("technical") if isinstance(response.get("technical"), dict) else {}
    return {
        "summary": {
            "headline": str(summary.get("headline") or "Quantitative insight"),
            "thesis": str(summary.get("thesis") or ""),
            "score": max(0, min(int(_finite(summary.get("score")) or 0), 100)),
        },
        "technical": technical,
        "risks": [str(item) for item in response.get("risks", []) if str(item).strip()][:10],
        "catalysts": [str(item) for item in response.get("catalysts", []) if str(item).strip()][:10],
        "evidence": _clean_evidence(response.get("evidence")),
        "disclaimer": "Research use only; not investment advice.",
    }


def guard_signal(raw: Any, context: dict[str, Any], evidence: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, Any]]:
    signal = raw if isinstance(raw, dict) else {}
    violations: list[str] = []
    stance = str(signal.get("stance") or "neutral").lower()
    direction = str(signal.get("direction") or "flat").lower()
    intent = str(signal.get("intent") or "hold").lower()
    if stance not in {"bullish", "neutral", "bearish"}:
        stance, violations = "neutral", ["invalid_stance"]
    if direction not in {"long", "flat", "short"}:
        direction, violations = "flat", [*violations, "invalid_direction"]
    if intent not in {"enter", "add", "hold", "reduce", "exit"}:
        intent, violations = "hold", [*violations, "invalid_intent"]
    exposure = _finite(signal.get("targetExposure"))
    exposure = max(-1.0, min(exposure if exposure is not None else 0.0, 1.0))
    asset_class = context["instrument"]["assetClass"]
    if asset_class in SPOT_ASSET_CLASSES and (exposure < 0 or direction == "short"):
        exposure, direction = 0.0, "flat"
        intent = "exit" if intent in {"enter", "add"} else intent
        violations.append("spot_short_exposure_blocked")
    confidence = max(0.0, min(_finite(signal.get("confidence")) or 0.0, 1.0))
    score = max(0, min(int(_finite(signal.get("score")) or 0), 100))
    horizon = str(signal.get("horizon") or "swing").lower()
    if horizon not in SIGNAL_HORIZONS:
        horizon = "swing"
        violations.append("invalid_horizon")
    levels = {key: _finite(signal.get(key)) for key in ("entryLow", "entryHigh", "stopLoss", "targetPrice")}
    if direction == "long" and all(levels.values()):
        if not (levels["stopLoss"] < levels["entryLow"] <= levels["entryHigh"] < levels["targetPrice"]):
            violations.append("invalid_long_price_plan")
    if direction == "short" and all(levels.values()):
        if not (levels["targetPrice"] < levels["entryLow"] <= levels["entryHigh"] < levels["stopLoss"]):
            violations.append("invalid_short_price_plan")
    actionable = True
    if context["dataQuality"]["warnings"]:
        actionable = False
        violations.append("data_quality_degraded")
    if not evidence:
        actionable = False
        violations.append("evidence_missing")
    if any(item.startswith("invalid_") for item in violations):
        actionable = False
    if not actionable:
        direction, intent, exposure = "flat", "hold", 0.0
    final = {
        "stance": stance,
        "direction": direction,
        "intent": intent,
        "targetExposure": round(exposure, 4),
        "confidence": round(confidence, 4),
        "score": score,
        "horizon": horizon,
        **levels,
        "invalidation": str(signal.get("invalidation") or ""),
        "reason": str(signal.get("reason") or ""),
        "actionable": actionable,
    }
    return final, {"passed": not violations, "adjusted": bool(violations), "violations": violations}


def create_report(parameters: dict[str, Any]) -> dict[str, Any]:
    if not capabilities()["configured"]:
        raise InsightConfigurationError("Insights LLM is not configured.")
    request_asset = asset_request(
        parameters["symbol"], parameters.get("assetClass"), parameters.get("venue"), parameters.get("market"), "daily", parameters.get("dataType")
    )
    report_id = str(uuid.uuid4())
    now = utc_now()
    with db() as connection:
        connection.execute(
            """
            insert into insight_reports
                (id, symbol, asset_class, market, venue, resolution, data_type, as_of_date,
                 lookback_bars, backtest_run_id, status, model, prompt_version, created_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id, request_asset.symbol, request_asset.asset_class, parameters.get("market"), request_asset.venue,
                "daily", request_asset.data_type, parameters.get("asOfDate"), int(parameters.get("lookbackBars") or 120),
                parameters.get("backtestRunId"), "queued", INSIGHTS_LLM_MODEL, PROMPT_VERSION, now,
            ),
        )
    return get_report(report_id)


def attach_task(report_id: str, task_id: str) -> None:
    with db() as connection:
        connection.execute("update insight_reports set task_id = ? where id = ?", (task_id, report_id))


def fail_report(report_id: str, error: str) -> None:
    with db() as connection:
        connection.execute(
            "update insight_reports set status = ?, error = ?, finished_at = ? where id = ?",
            ("failed", error, utc_now(), report_id),
        )


def get_report(report_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from insight_reports where id = ?", (report_id,)).fetchone()
        signal_row = connection.execute("select * from decision_signals where insight_report_id = ?", (report_id,)).fetchone()
    item = row_to_dict(row)
    if item is None:
        raise KeyError("Insight report not found.")
    item["signal"] = row_to_dict(signal_row)
    return item


def list_reports(*, asset_class: str | None = None, symbol: str | None = None, status: str | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    clauses: list[str] = []
    values: list[Any] = []
    for column, value in (("asset_class", asset_class), ("symbol", symbol.upper() if symbol else None), ("status", status)):
        if value:
            clauses.append(f"{column} = ?")
            values.append(value)
    where = f"where {' and '.join(clauses)}" if clauses else ""
    bounded_limit = max(1, min(int(limit), 500))
    bounded_offset = max(0, int(offset))
    with db() as connection:
        count = connection.execute(f"select count(*) as count from insight_reports {where}", values).fetchone()["count"]
        rows = connection.execute(
            f"select * from insight_reports {where} order by created_at desc limit ? offset ?",
            [*values, bounded_limit, bounded_offset],
        ).fetchall()
    return {"items": rows_to_dicts(rows), "count": count, "limit": bounded_limit, "offset": bounded_offset}


def delete_report(report_id: str) -> dict[str, Any]:
    with db() as connection:
        report_row = connection.execute("select * from insight_reports where id = ?", (report_id,)).fetchone()
        task_rows = connection.execute("select id, status, log_path from tasks where related_id = ?", (report_id,)).fetchall()
        signal_row = connection.execute(
            "select paper_session_id, paper_signal_id from decision_signals where insight_report_id = ?",
            (report_id,),
        ).fetchone()
    report = row_to_dict(report_row)
    if not report:
        raise KeyError("Insight report not found.")
    tasks = rows_to_dicts(task_rows)
    active_statuses = {"created", "queued", "running", "interrupted"}
    if str(report.get("status")) in active_statuses or any(str(item.get("status")) in active_statuses for item in tasks):
        raise InsightDeleteConflict("Cancel or wait for the Insight report to finish before deleting it.")
    with db() as connection:
        connection.execute("delete from decision_signals where insight_report_id = ?", (report_id,))
        connection.execute("delete from insight_reports where id = ?", (report_id,))
        connection.execute("delete from tasks where related_id = ?", (report_id,))
    for task in tasks:
        try:
            Path(str(task.get("log_path") or "")).unlink(missing_ok=True)
        except OSError:
            pass
    signal = row_to_dict(signal_row)
    return {
        "deleted": True,
        "id": report_id,
        "deletedTasks": len(tasks),
        "deletedDecisionSignal": bool(signal_row),
        "paperAuditPreserved": bool(signal and signal.get("paper_signal_id")),
    }


def run_report(task_id: str, report_id: str) -> dict[str, Any]:
    report = get_report(report_id)
    update_task(task_id, status="running", started_at=utc_now(), error=None)
    with db() as connection:
        connection.execute("update insight_reports set status = ?, started_at = ? where id = ?", ("running", utc_now(), report_id))
    append_log(task_id, f"Building daily context for {report['asset_class']}/{report['venue']}/{report['symbol']}.")
    parameters = {
        "symbol": report["symbol"], "assetClass": report["asset_class"], "market": report.get("market"),
        "venue": report["venue"], "dataType": report["data_type"], "asOfDate": report.get("as_of_date"),
        "lookbackBars": report["lookback_bars"], "backtestRunId": report.get("backtest_run_id"),
    }
    try:
        context = build_context(parameters)
        fingerprint = hashlib.sha256(json_dump(context).encode("utf-8")).hexdigest()
        append_log(task_id, f"Requesting structured analysis from {INSIGHTS_LLM_MODEL}.")
        raw_response = request_analysis(context)
        normalized = normalize_report(raw_response)
        raw_signal = raw_response.get("signal") if isinstance(raw_response.get("signal"), dict) else {}
        final_signal, guardrail = guard_signal(raw_signal, context, normalized["evidence"])
        normalized["dataQuality"] = context["dataQuality"]
        normalized["model"] = {"name": INSIGHTS_LLM_MODEL, "promptVersion": PROMPT_VERSION}
        now = utc_now()
        signal_id = str(uuid.uuid4())
        signal_status = "active" if final_signal["actionable"] else "observation"
        with db() as connection:
            connection.execute(
                """
                update insight_reports set status = ?, as_of_date = ?, input_fingerprint = ?, context_json = ?,
                    raw_response_json = ?, report_json = ?, error = null, finished_at = ? where id = ?
                """,
                ("success", context.get("asOfDate"), fingerprint, json_dump(context), json_dump(raw_response), json_dump(normalized), now, report_id),
            )
            connection.execute(
                """
                insert into decision_signals
                    (id, insight_report_id, symbol, asset_class, venue, as_of_date, raw_signal_json,
                     final_signal_json, guardrail_json, status, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (signal_id, report_id, report["symbol"], report["asset_class"], report["venue"], context.get("asOfDate"),
                 json_dump(raw_signal), json_dump(final_signal), json_dump(guardrail), signal_status, now, now),
            )
        update_task(task_id, status="success", finished_at=now, artifacts_json=[f"insight:{report_id}"])
        append_log(task_id, f"Insight completed; actionable={final_signal['actionable']}.")
        return get_report(report_id)
    except Exception as exc:
        now = utc_now()
        safe_error = str(exc).replace(INSIGHTS_LLM_API_KEY, "[REDACTED]") if INSIGHTS_LLM_API_KEY else str(exc)
        with db() as connection:
            connection.execute("update insight_reports set status = ?, error = ?, finished_at = ? where id = ?", ("failed", safe_error, now, report_id))
        update_task(task_id, status="failed", error=safe_error, finished_at=now)
        append_log(task_id, f"Insight failed: {safe_error}")
        raise


def handoff_to_paper(report_id: str, session_id: str, target_percent: float | None) -> dict[str, Any]:
    from . import paper as paper_service

    report = get_report(report_id)
    signal = report.get("signal") or {}
    final = signal.get("finalSignal") or {}
    if not final.get("actionable"):
        raise InsightError("Only actionable signals can be handed to Paper.")
    if report["asset_class"] not in SPOT_ASSET_CLASSES:
        raise InsightError("Paper handoff currently supports equity and spot crypto only.")
    session = paper_service.get_session(session_id)
    if not session:
        raise KeyError("Paper session not found.")
    if session.get("asset_class") != report["asset_class"] or session.get("venue") != report["venue"]:
        raise InsightError("Paper session asset class or venue does not match the insight.")
    session_symbols = (session.get("parameters") or {}).get("symbols") or [session.get("symbol")]
    if report["symbol"] not in {str(item).upper() for item in session_symbols}:
        raise InsightError("Paper session does not contain the insight symbol.")
    direction = final.get("direction")
    intent = final.get("intent")
    if direction == "long" and intent in {"enter", "add", "hold"}:
        side = "buy" if intent in {"enter", "add"} else "hold"
        if side == "buy" and (target_percent is None or not 0 < float(target_percent) <= 1):
            raise InsightError("A buy handoff requires targetPercent in (0, 1].")
    elif intent in {"reduce", "exit"}:
        side, target_percent = "sell", 0.0
    else:
        side, target_percent = "hold", None
    if signal.get("paper_signal_id"):
        return {"created": False, "paperSignalId": signal["paper_signal_id"], "report": report}
    paper_signal = paper_service.create_signal(
        session_id,
        trade_date=report.get("as_of_date") or date.today().isoformat(),
        side=side,
        symbol=report["symbol"],
        target_percent=target_percent,
        strength=final.get("confidence"),
        reason=str(final.get("reason") or (report.get("report") or {}).get("summary", {}).get("thesis") or "Insight signal"),
        source=f"insight:{report_id}",
    )
    with db() as connection:
        connection.execute(
            "update decision_signals set status = ?, paper_session_id = ?, paper_signal_id = ?, updated_at = ? where insight_report_id = ?",
            ("handed_off", session_id, paper_signal["id"], utc_now(), report_id),
        )
    return {"created": True, "paperSignal": paper_signal, "report": get_report(report_id)}
