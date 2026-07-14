from __future__ import annotations

import hashlib
import html
import json
import math
import re
import statistics
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Callable
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from ..core.config import (
    ASHARE_TECH_CLOSE_TOLERANCE_PCT,
    INSIGHTS_LLM_API_KEY,
    INSIGHTS_LLM_BASE_URL,
    INSIGHTS_LLM_MODEL,
    INSIGHTS_LLM_TIMEOUT_SECONDS,
)
from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from .tasks import append_log, update_task
from .tushare_adapter import TushareAdapter, to_tushare_stock_code


PROMPT_VERSION = "ashare-tech-gpt56-v1"
ALLOWED_LABELS = ("重点观察", "低吸观察", "小仓试错前置", "观察", "继续等待", "不追高", "风险较高")
GROUP_DEFINITIONS = (
    {"key": "core", "name": "核心科技股"},
    {"key": "semiconductor_storage", "name": "半导体/存储"},
    {"key": "ai_compute", "name": "AI算力/CPO/PCB/服务器"},
)
GROUP_NAMES = {item["key"]: item["name"] for item in GROUP_DEFINITIONS}
DEFAULT_STOCKS = (
    ("002475", "立讯精密", "core"), ("300124", "汇川技术", "core"),
    ("603501", "豪威集团/韦尔股份", "core"), ("688012", "中微公司", "core"),
    ("300408", "三环集团", "core"), ("002415", "海康威视", "core"),
    ("603986", "兆易创新", "semiconductor_storage"), ("600460", "士兰微", "semiconductor_storage"),
    ("688008", "澜起科技", "semiconductor_storage"), ("301308", "江波龙", "semiconductor_storage"),
    ("688525", "佰维存储", "semiconductor_storage"), ("300223", "北京君正", "semiconductor_storage"),
    ("688110", "东芯股份", "semiconductor_storage"), ("688766", "普冉股份", "semiconductor_storage"),
    ("688123", "聚辰股份", "semiconductor_storage"), ("000021", "深科技", "semiconductor_storage"),
    ("688256", "寒武纪", "ai_compute"), ("688041", "海光信息", "ai_compute"),
    ("601138", "工业富联", "ai_compute"), ("000977", "浪潮信息", "ai_compute"),
    ("300308", "中际旭创", "ai_compute"), ("300502", "新易盛", "ai_compute"),
    ("300394", "天孚通信", "ai_compute"), ("002463", "沪电股份", "ai_compute"),
    ("300476", "胜宏科技", "ai_compute"), ("600183", "生益科技", "ai_compute"),
)
STRONG_AI = {"300308", "300502", "300394", "688256", "688041", "601138", "002463", "300476"}
STORAGE = {"603986", "688008", "301308", "688525", "300223", "688110", "688766", "688123"}
STOCK_POOL = tuple({
    "code": code, "name": name, "groupKey": group_key, "group": GROUP_NAMES[group_key],
    "enabled": True,
    "ruleTags": (["strong_ai"] if code in STRONG_AI else []) + (["storage"] if code in STORAGE else []),
} for code, name, group_key in DEFAULT_STOCKS)
STOCK_GROUPS = tuple((group["name"], tuple((item["code"], item["name"]) for item in STOCK_POOL if item["groupKey"] == group["key"])) for group in GROUP_DEFINITIONS)
MAX_WATCHLIST_SIZE = 60
INDEX_POOL = (
    ("000001", "上证指数"), ("399001", "深证成指"), ("399006", "创业板指"), ("000688", "科创50"),
)
SECTOR_KEYWORDS = ["半导体", "存储", "CPO", "PCB", "AI服务器"]
POLICY_PAGES = (
    ("工业和信息化部", "https://www.miit.gov.cn/zwgk/zcwj/wjfb/index.html"),
    ("中国证监会", "https://www.csrc.gov.cn/csrc/c100028/common_list.shtml"),
    ("中国政府网", "https://www.gov.cn/zhengce/zuixin/"),
)
RISK_KEYWORDS = ("减持", "解禁", "问询", "监管", "诉讼", "停产", "停牌", "处罚", "立案", "亏损", "下修", "终止")


class AshareTechReportError(ValueError):
    pass


class ReportDataNotReady(AshareTechReportError):
    pass


def _pool_fingerprint(items: list[dict[str, Any]]) -> str:
    canonical = [{
        "code": item["code"], "name": item["name"], "groupKey": item["groupKey"],
        "enabled": bool(item.get("enabled", True)), "ruleTags": sorted(item.get("ruleTags") or []),
    } for item in sorted(items, key=lambda row: row["code"])]
    return hashlib.sha256(json_dump(canonical).encode("utf-8")).hexdigest()


def _default_watchlist_items() -> list[dict[str, Any]]:
    return [dict(item) for item in STOCK_POOL]


def _insert_watchlist_item(connection: Any, item: dict[str, Any], now: str) -> None:
    connection.execute(
        """
        insert into ashare_tech_watchlist_items
            (code, name, group_key, enabled, rule_tags_json, source, created_at, updated_at)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(code) do update set
            name = excluded.name,
            group_key = excluded.group_key,
            enabled = excluded.enabled,
            rule_tags_json = excluded.rule_tags_json,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (
            item["code"], item["name"], item["groupKey"], 1 if item.get("enabled", True) else 0,
            json_dump(sorted(set(item.get("ruleTags") or []))), item.get("source") or "default",
            item.get("created_at") or now, now,
        ),
    )


def _ensure_default_watchlist() -> None:
    with db() as connection:
        count = int(connection.execute("select count(*) from ashare_tech_watchlist_items").fetchone()[0])
        if count:
            return
        now = utc_now()
        for item in _default_watchlist_items():
            _insert_watchlist_item(connection, {**item, "source": "default"}, now)


def _watchlist_rows() -> list[dict[str, Any]]:
    _ensure_default_watchlist()
    with db() as connection:
        rows = connection.execute(
            "select * from ashare_tech_watchlist_items order by group_key, code"
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows_to_dicts(rows):
        group_key = str(row.pop("group_key"))
        items.append({
            **row, "code": str(row["code"]), "groupKey": group_key,
            "group": GROUP_NAMES.get(group_key, group_key), "enabled": bool(row.get("enabled")),
            "ruleTags": sorted(set(row.get("ruleTags") or [])),
        })
    return items


def get_watchlist() -> dict[str, Any]:
    items = _watchlist_rows()
    return {
        "items": items, "count": len(items), "enabledCount": sum(1 for item in items if item["enabled"]),
        "maxSize": MAX_WATCHLIST_SIZE, "groups": list(GROUP_DEFINITIONS), "fingerprint": _pool_fingerprint(items),
    }


def watchlist_snapshot() -> dict[str, Any]:
    watchlist = get_watchlist()
    enabled = [item for item in watchlist["items"] if item["enabled"]]
    return {
        "items": enabled, "count": len(enabled), "totalCount": watchlist["count"],
        "fingerprint": _pool_fingerprint(enabled), "capturedAt": utc_now(),
    }


def _validate_group_and_tags(group_key: str, rule_tags: list[str] | None) -> list[str]:
    if group_key not in GROUP_NAMES:
        raise AshareTechReportError(f"Unknown groupKey: {group_key}.")
    tags = sorted(set(rule_tags or []))
    unknown = sorted(set(tags) - {"strong_ai", "storage"})
    if unknown:
        raise AshareTechReportError(f"Unknown rule tags: {', '.join(unknown)}.")
    return tags


def add_watchlist_item(
    code: str, group_key: str, rule_tags: list[str] | None = None, *, adapter: TushareAdapter | None = None,
) -> dict[str, Any]:
    code = str(code).strip()
    if not re.fullmatch(r"\d{6}", code):
        raise AshareTechReportError("股票代码必须是6位数字。")
    tags = _validate_group_and_tags(group_key, rule_tags)
    watchlist = get_watchlist()
    if any(item["code"] == code for item in watchlist["items"]):
        raise AshareTechReportError(f"股票 {code} 已在观察池中。")
    if watchlist["count"] >= MAX_WATCHLIST_SIZE:
        raise AshareTechReportError(f"观察池最多允许 {MAX_WATCHLIST_SIZE} 只股票。")
    try:
        adapter = adapter or TushareAdapter()
        security = adapter.stock_by_code(code)
    except Exception as exc:
        raise AshareTechReportError(f"TuShare 无法验证 {code}：{exc}") from exc
    if not security or security.get("status") != "listed":
        raise AshareTechReportError(f"TuShare 未确认 {code} 为在市A股，未保存。")
    item = {
        "code": code, "name": str(security.get("name") or code), "groupKey": group_key,
        "enabled": True, "ruleTags": tags, "source": "tushare:stock_basic",
    }
    now = utc_now()
    with db() as connection:
        _insert_watchlist_item(connection, item, now)
    return next(row for row in get_watchlist()["items"] if row["code"] == code)


def update_watchlist_item(code: str, *, enabled: bool | None = None, rule_tags: list[str] | None = None) -> dict[str, Any]:
    watchlist = get_watchlist()
    current = next((item for item in watchlist["items"] if item["code"] == code), None)
    if not current:
        raise KeyError("Watchlist item not found.")
    tags = current["ruleTags"] if rule_tags is None else _validate_group_and_tags(current["groupKey"], rule_tags)
    next_enabled = current["enabled"] if enabled is None else bool(enabled)
    if current["enabled"] and not next_enabled and watchlist["enabledCount"] <= 1:
        raise AshareTechReportError("观察池至少需要保留1只启用股票。")
    with db() as connection:
        connection.execute(
            "update ashare_tech_watchlist_items set enabled = ?, rule_tags_json = ?, updated_at = ? where code = ?",
            (1 if next_enabled else 0, json_dump(tags), utc_now(), code),
        )
    return next(row for row in get_watchlist()["items"] if row["code"] == code)


def delete_watchlist_item(code: str) -> dict[str, Any]:
    watchlist = get_watchlist()
    current = next((item for item in watchlist["items"] if item["code"] == code), None)
    if not current:
        raise KeyError("Watchlist item not found.")
    if current["enabled"] and watchlist["enabledCount"] <= 1:
        raise AshareTechReportError("不能删除最后1只启用股票。")
    with db() as connection:
        connection.execute("delete from ashare_tech_watchlist_items where code = ?", (code,))
    return {"deleted": True, "code": code, "watchlist": get_watchlist()}


def reset_watchlist() -> dict[str, Any]:
    now = utc_now()
    with db() as connection:
        connection.execute("delete from ashare_tech_watchlist_items")
        for item in _default_watchlist_items():
            _insert_watchlist_item(connection, {**item, "source": "default"}, now)
    return get_watchlist()


def capabilities() -> dict[str, Any]:
    watchlist = get_watchlist()
    return {
        "poolSize": watchlist["enabledCount"],
        "totalPoolSize": watchlist["count"],
        "defaultPoolSize": len(STOCK_POOL),
        "groups": [{**group, "count": sum(1 for item in watchlist["items"] if item["groupKey"] == group["key"])} for group in GROUP_DEFINITIONS],
        "primarySource": "TuShare Pro",
        "crossCheckSource": "东方财富",
        "promptVersion": PROMPT_VERSION,
        "model": INSIGHTS_LLM_MODEL or None,
        "llmOptional": True,
        "paperHandoff": False,
        "schedule": "A股工作日 17:30 Asia/Shanghai；数据未齐时 18:00、18:30 重试",
        "labels": list(ALLOWED_LABELS),
    }


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _round(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None and math.isfinite(value) else None


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return (numerator / denominator - 1) * 100


def qfq_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply TuShare's forward-adjust formula without touching volume or amount."""
    ordered = sorted((dict(item) for item in rows if item.get("date")), key=lambda item: str(item["date"]))
    valid_factors = [_finite(item.get("adj_factor")) for item in ordered]
    valid_factors = [item for item in valid_factors if item and item > 0]
    if not ordered or not valid_factors:
        return []
    latest_factor = valid_factors[-1]
    result: list[dict[str, Any]] = []
    for item in ordered:
        factor = _finite(item.get("adj_factor"))
        if not factor or factor <= 0:
            continue
        adjusted = dict(item)
        for key in ("open", "high", "low", "close", "prev_close"):
            raw = _finite(item.get(key))
            adjusted[key] = raw * factor / latest_factor if raw is not None else None
        adjusted["raw_close"] = _finite(item.get("close"))
        adjusted["adjust"] = "qfq"
        result.append(adjusted)
    return result


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    output = [values[0]]
    for value in values[1:]:
        output.append(alpha * value + (1 - alpha) * output[-1])
    return output


def _moving_average(values: list[float], period: int) -> float | None:
    return _mean(values[-period:]) if len(values) >= period else None


def _ma_direction(closes: list[float], period: int) -> str | None:
    if len(closes) < period + 5:
        return None
    current = _moving_average(closes, period)
    prior = _mean(closes[-period - 5:-5])
    change = _pct(current, prior)
    if change is None:
        return None
    return "向上" if change > 0.2 else "向下" if change < -0.2 else "走平"


def calculate_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = sorted(rows, key=lambda item: str(item.get("date") or ""))
    usable = [item for item in rows if all(_finite(item.get(key)) is not None for key in ("open", "high", "low", "close"))]
    if not usable:
        return {"sampleCount": 0, "dataComplete": False, "missing": ["OHLC"]}
    closes = [_finite(item["close"]) or 0.0 for item in usable]
    highs = [_finite(item["high"]) or 0.0 for item in usable]
    lows = [_finite(item["low"]) or 0.0 for item in usable]
    volumes = [_finite(item.get("volume")) or 0.0 for item in usable]
    amounts = [_finite(item.get("amount")) or 0.0 for item in usable]
    latest = usable[-1]
    close = closes[-1]
    mas = {period: _moving_average(closes, period) for period in (5, 10, 20, 60, 120)}
    volume_mas = {period: _moving_average(volumes, period) for period in (5, 10, 20)}
    amount_mas = {period: _moving_average(amounts, period) for period in (5, 20)}
    ema12, ema26 = _ema(closes, 12), _ema(closes, 26)
    diffs = [left - right for left, right in zip(ema12, ema26)]
    dea = _ema(diffs, 9)
    hist = [2 * (left - right) for left, right in zip(diffs, dea)]
    high20 = max(highs[-20:]) if len(highs) >= 20 else None
    low20 = min(lows[-20:]) if len(lows) >= 20 else None
    high60 = max(highs[-60:]) if len(highs) >= 60 else None
    low60 = min(lows[-60:]) if len(lows) >= 60 else None
    prior_close = _finite(latest.get("prev_close")) or (closes[-2] if len(closes) >= 2 else None)
    missing: list[str] = []
    if len(usable) < 120:
        missing.append(f"仅{len(usable)}个交易日，MA120不可用")
    if len(usable) < 60:
        missing.append("MA60不可用")
    if len(usable) < 20:
        missing.append("不足20日，禁止低吸筛选")
    if not any(amounts[-20:]):
        missing.append("成交额缺失")
    if not all(bool(item.get("adj_factor_verified", True)) for item in usable[-120:]):
        missing.append("复权因子未完整核验")
    if len(usable) >= 20 and not all(bool(item.get("turnover_history_complete")) for item in usable[-20:]):
        missing.append("近20日换手率序列不完整")
    if _finite(latest.get("turnover_rate")) is None:
        missing.append("换手率缺失")
    result = {
        "date": str(latest["date"]), "sampleCount": len(usable), "open": _round(_finite(latest.get("open"))),
        "high": _round(_finite(latest.get("high"))), "low": _round(_finite(latest.get("low"))),
        "close": _round(close), "rawClose": _round(_finite(latest.get("raw_close")) or close),
        "changePct": _round(_pct(close, prior_close)), "volume": _round(volumes[-1], 0),
        "amount": _round(amounts[-1], 0), "turnoverRate": _round(_finite(latest.get("turnover_rate"))),
        "ma5": _round(mas[5]), "ma10": _round(mas[10]), "ma20": _round(mas[20]),
        "ma60": _round(mas[60]), "ma120": _round(mas[120]),
        "volumeMa5": _round(volume_mas[5], 0), "volumeMa10": _round(volume_mas[10], 0),
        "volumeMa20": _round(volume_mas[20], 0), "amountMa5": _round(amount_mas[5], 0),
        "amountMa20": _round(amount_mas[20], 0),
        "volumeRatio20": _round(volumes[-1] / volume_mas[20] if volume_mas[20] else None),
        "amountRatio20": _round(amounts[-1] / amount_mas[20] if amount_mas[20] else None),
        "high20": _round(high20), "low20": _round(low20), "high60": _round(high60), "low60": _round(low60),
        "ma20DeviationPct": _round(_pct(close, mas[20])), "ma60DeviationPct": _round(_pct(close, mas[60])),
        "drawdown20Pct": _round(_pct(close, high20)),
        "return5Pct": _round(_pct(close, closes[-6] if len(closes) >= 6 else None)),
        "return10Pct": _round(_pct(close, closes[-11] if len(closes) >= 11 else None)),
        "ma20Direction": _ma_direction(closes, 20), "ma60Direction": _ma_direction(closes, 60),
        "ma120Direction": _ma_direction(closes, 120), "dif": _round(diffs[-1]), "dea": _round(dea[-1]),
        "macdHistogram": _round(hist[-1]), "macdHistogramPrior": _round(hist[-2] if len(hist) >= 2 else None),
        "macdAxis": "零轴上" if diffs[-1] >= 0 else "零轴下",
        "macdCross": "金叉" if len(diffs) >= 2 and diffs[-2] <= dea[-2] and diffs[-1] > dea[-1] else
                     "死叉" if len(diffs) >= 2 and diffs[-2] >= dea[-2] and diffs[-1] < dea[-1] else "无新交叉",
        "missing": missing, "dataComplete": len(usable) >= 120 and not missing,
    }
    result["ma20Position"] = "上方" if mas[20] is not None and close >= mas[20] else "下方" if mas[20] is not None else "数据不足"
    result["ma60Position"] = "上方" if mas[60] is not None and close >= mas[60] else "下方" if mas[60] is not None else "数据不足"
    result["movingAverageDirection"] = f"MA20{result['ma20Direction'] or '未知'} / MA60{result['ma60Direction'] or '未知'}"
    histogram_change = "扩张" if len(hist) >= 2 and abs(hist[-1]) > abs(hist[-2]) else "收缩"
    result["macdStatus"] = f"{result['macdAxis']}；{result['macdCross']}；柱体{histogram_change}"
    return result


def _price_structure(rows: list[dict[str, Any]], metrics: dict[str, Any]) -> str:
    if metrics.get("sampleCount", 0) < 20:
        return "数据不足"
    close = metrics["close"]
    volume_ratio = metrics.get("volumeRatio20") or 0
    amount_ratio = metrics.get("amountRatio20") or 0
    prior20 = rows[-21:-1]
    prior_high = max((_finite(item.get("high")) or -math.inf) for item in prior20) if prior20 else None
    if prior_high and close > prior_high and max(volume_ratio, amount_ratio) >= 1.5:
        return "平台突破"
    if metrics.get("ma60") and close < metrics["ma60"] and max(volume_ratio, amount_ratio) >= 1.5:
        return "放量破位"
    if metrics.get("drawdown20Pct") is not None and metrics["drawdown20Pct"] > -3 and max(volume_ratio, amount_ratio) >= 1.5:
        return "高位分歧"
    if metrics.get("ma20Direction") == "向上" and metrics.get("ma60Direction") == "向上" and close >= (metrics.get("ma20") or close):
        return "上升"
    if metrics.get("ma20Direction") == "向下" and close < (metrics.get("ma20") or close + 1):
        return "下降"
    if metrics.get("ma20") and metrics.get("ma60") and close >= metrics["ma20"] >= metrics["ma60"]:
        return "反抽修复"
    return "震荡"


def _volume_price_state(metrics: dict[str, Any]) -> str:
    rising = (metrics.get("changePct") or 0) >= 0
    ratio = max(metrics.get("volumeRatio20") or 0, metrics.get("amountRatio20") or 0)
    volume = "明显放量" if ratio >= 1.5 else "明显缩量" if ratio <= 0.7 else "量能平稳"
    return f"价{'涨' if rising else '跌'}；{volume}"


def classify_stock(
    rows: list[dict[str, Any]], metrics: dict[str, Any], *, code: str = "", negative_announcement: bool = False,
    storage_sector_pullback_days: int = 0, source_conflict: bool = False, rule_tags: list[str] | None = None,
) -> dict[str, Any]:
    tags = set(rule_tags or [])
    structure = _price_structure(rows, metrics)
    close = metrics.get("close")
    ma5, ma10, ma20, ma60 = (metrics.get(key) for key in ("ma5", "ma10", "ma20", "ma60"))
    volume_ratio = metrics.get("volumeRatio20")
    amount_ratio = metrics.get("amountRatio20")
    ratio = max(volume_ratio or 0, amount_ratio or 0)
    drawdown = metrics.get("drawdown20Pct")
    near_support = any(
        support and close and abs(close / support - 1) <= 0.03 for support in (ma20, ma60, metrics.get("low20"))
    )
    shrinking = volume_ratio is not None and amount_ratio is not None and max(volume_ratio, amount_ratio) <= 1.0
    stopped_falling = len(rows) >= 3 and _finite(rows[-1].get("low")) is not None and _finite(rows[-2].get("low")) is not None and (
        (_finite(rows[-1].get("low")) or 0) >= (_finite(rows[-2].get("low")) or 0)
    )
    re_stood = close is not None and ma5 is not None and ma10 is not None and close >= ma5 and close >= ma10
    blocked = bool(metrics.get("sampleCount", 0) < 20 or metrics.get("missing") or source_conflict or negative_announcement)
    high_risk = structure == "放量破位" or negative_announcement or (ma60 and close and close < ma60 and ratio >= 1.5)
    high_position = drawdown is not None and drawdown > -8
    label = "观察"
    trigger = structure
    if high_risk:
        label = "风险较高"
    elif "strong_ai" in tags and high_position:
        label, trigger = "不追高", "强势热门股距20日高点回撤不足8%"
    elif structure == "高位分歧" or (drawdown is not None and drawdown > -3):
        label, trigger = "不追高", "接近20日高位或高位分歧"
    elif not blocked and near_support and shrinking and stopped_falling and structure != "下降":
        label, trigger = "低吸观察", "缩量回踩并初步止跌"
        if re_stood:
            label, trigger = "小仓试错前置", "站回MA5/MA10且具备次日右侧确认条件"
    elif structure == "上升":
        label, trigger = "重点观察", "强趋势延续"
    elif structure in {"下降", "数据不足"}:
        label, trigger = "继续等待", "弱势或数据不足"
    if "storage" in tags and label in {"低吸观察", "小仓试错前置"} and storage_sector_pullback_days < 2:
        label, trigger = "继续等待", "存储板块尚未连续回调2—3日"
    if blocked and label in {"低吸观察", "小仓试错前置"}:
        label, trigger = "继续等待", "关键数据、来源核验或公告检查不完整"
    support_values = [value for value in (ma20, ma60, metrics.get("low20")) if value and close and value <= close * 1.03]
    support = max(support_values) if support_values else metrics.get("low20")
    observation = [_round(support * 0.98), _round(support * 1.02)] if support else None
    invalidation = _round(support * 0.97) if support else None
    next_condition = None
    if ma10 and metrics.get("high"):
        next_condition = f"收盘站稳{max(ma10, metrics['high']):.2f}且额比20不高于1.2"
    return {
        "priceStructure": structure, "volumePriceState": _volume_price_state(metrics), "triggerType": trigger,
        "direction": "风险" if label == "风险较高" else "不追高" if label == "不追高" else "修复/趋势观察",
        "keySupport": _round(support), "observationZone": observation, "invalidation": invalidation,
        "nextDayCondition": next_condition, "conclusion": label,
    }


def _merge_daily_basic(daily: list[dict[str, Any]], basics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date = {str(item.get("trade_date")): item.get("factors") or {} for item in basics}
    result = []
    for item in daily:
        row = dict(item)
        factors = by_date.get(str(row.get("date")), {})
        row["turnover_rate"] = factors.get("turnover_rate")
        row["turnover_history_complete"] = factors.get("turnover_rate") is not None
        result.append(row)
    return result


def _eastmoney_latest(code: str) -> dict[str, Any] | None:
    secid = f"1.{code}" if code.startswith(("5", "6", "9")) else f"0.{code}"
    query = urlencode({"secid": secid, "fields": "f57,f58,f43,f170,f124"})
    request = Request(f"https://push2.eastmoney.com/api/qt/stock/get?{query}", headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=10) as response:  # noqa: S310 - fixed official market-data host
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data") or {}
    raw_close = _finite(data.get("f43"))
    timestamp = _finite(data.get("f124"))
    if raw_close is None:
        return None
    return {
        "close": raw_close / 100, "changePct": (_finite(data.get("f170")) or 0) / 100,
        "timestamp": datetime.fromtimestamp(timestamp).isoformat() if timestamp else None,
        "source": "eastmoney:push2",
    }


def _official_announcements(code: str, start_date: str, end_date: str) -> list[dict[str, Any]]:
    if code.startswith(("6", "9")):
        params = {
            "isPagination": "true", "pageHelp.pageSize": "50", "pageHelp.pageNo": "1",
            "pageHelp.cacheSize": "1", "START_DATE": start_date, "END_DATE": end_date,
            "SECURITY_CODE": code, "TITLE": "", "BULLETIN_TYPE": "", "stockType": "1",
        }
        request = Request(
            "https://query.sse.com.cn/security/stock/queryCompanyBulletinNew.do?" + urlencode(params),
            headers={"Referer": "https://www.sse.com.cn/disclosure/listedinfo/announcement/", "User-Agent": "Mozilla/5.0"},
        )
        with urlopen(request, timeout=15) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        items = payload.get("result") or []
        return [{
            "date": str(item.get("SSEDATE") or item.get("BULLETIN_DATE") or "")[:10],
            "title": item.get("TITLE") or item.get("BULLETIN_TITLE"),
            "url": "https://www.sse.com.cn" + str(item.get("URL") or item.get("BULLETIN_URL") or ""),
            "source": "上海证券交易所",
        } for item in items]
    body = json.dumps({
        "pageSize": 50, "pageNum": 1, "stock": [code], "channelCode": ["listedNotice_disc"],
        "seDate": [start_date, end_date],
    }).encode("utf-8")
    request = Request(
        "https://www.szse.cn/api/disc/announcement/annList", data=body, method="POST",
        headers={"Content-Type": "application/json", "Referer": "https://www.szse.cn/disclosure/listed/notice/", "User-Agent": "Mozilla/5.0"},
    )
    with urlopen(request, timeout=15) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    items = payload.get("data") or payload.get("announceList") or []
    return [{
        "date": str(item.get("publishTime") or "")[:10], "title": item.get("title"),
        "url": "https://disc.static.szse.cn" + str(item.get("attachPath") or ""), "source": "深圳证券交易所",
    } for item in items]


def _official_policy_evidence(start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Read official policy listing pages; only dated, linked titles become evidence facts."""
    output: list[dict[str, Any]] = []
    relevant = ("科技", "集成电路", "半导体", "人工智能", "算力", "服务器", "数据", "电子信息")
    for source, page_url in POLICY_PAGES:
        request = Request(page_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed government domains
            content = response.read().decode("utf-8", errors="ignore")
        for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', content, re.I | re.S):
            title = re.sub(r"<[^>]+>", " ", match.group(2))
            title = html.unescape(re.sub(r"\s+", " ", title)).strip()
            if not title or not any(word in title for word in relevant):
                continue
            nearby = content[max(0, match.start() - 180):min(len(content), match.end() + 180)]
            date_match = re.search(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})", nearby)
            if not date_match:
                continue
            item_date = f"{int(date_match.group(1)):04d}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
            if start_date <= item_date <= end_date:
                output.append({"date": item_date, "title": title, "url": urljoin(page_url, match.group(1)), "source": source})
    unique = {(item["date"], item["url"]): item for item in output}
    return sorted(unique.values(), key=lambda item: (item["date"], item["source"]), reverse=True)


def _eastmoney_sector_rows(keywords: list[str], start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Website fallback used only when TuShare DC/THS sector permissions are unavailable."""
    list_query = urlencode({
        "pn": 1, "pz": 500, "po": 1, "np": 1, "fltt": 2, "invt": 2,
        "fs": "m:90+t:2", "fields": "f12,f14",
    })
    request = Request(f"https://push2.eastmoney.com/api/qt/clist/get?{list_query}", headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed Eastmoney host
        catalogue_payload = json.loads(response.read().decode("utf-8"))
    catalogue = ((catalogue_payload.get("data") or {}).get("diff") or [])
    output: list[dict[str, Any]] = []
    for keyword in keywords:
        match = next((item for item in catalogue if keyword.lower() in str(item.get("f14") or "").lower()), None)
        if not match:
            continue
        code = str(match.get("f12") or "")
        query = urlencode({
            "secid": f"90.{code}", "klt": 101, "fqt": 0,
            "beg": start_date.replace("-", ""), "end": end_date.replace("-", ""),
            "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        })
        bars_request = Request(f"https://push2his.eastmoney.com/api/qt/stock/kline/get?{query}", headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(bars_request, timeout=15) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        rows = []
        for line in ((payload.get("data") or {}).get("klines") or []):
            fields = str(line).split(",")
            if len(fields) < 11:
                continue
            rows.append({
                "date": fields[0], "open": _finite(fields[1]), "close": _finite(fields[2]),
                "high": _finite(fields[3]), "low": _finite(fields[4]), "volume": _finite(fields[5]),
                "amount": _finite(fields[6]), "turnover_rate": _finite(fields[10]), "adj_factor": 1.0,
            })
        if rows:
            output.append({
                "keyword": keyword, "code": code, "name": match.get("f14") or keyword,
                "source": "eastmoney:sector_kline_fallback", "rows": rows,
            })
    return output


def _market_environment(adapter: TushareAdapter, start_date: str, end_date: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for code, name in INDEX_POOL:
        try:
            rows = adapter.index_daily_rows(code, start_date, end_date)
            qfq = qfq_rows(rows) or rows
            metrics = calculate_metrics(qfq)
            result.append({"code": code, "name": name, **{key: metrics.get(key) for key in ("date", "close", "changePct", "volumeRatio20", "amountRatio20")}, "source": "tushare:index_daily"})
        except Exception as exc:
            result.append({"code": code, "name": name, "error": str(exc), "source": "tushare:index_daily"})
    try:
        sector_items = adapter.sector_daily_rows(SECTOR_KEYWORDS, start_date, end_date)
    except Exception:
        sector_items = []
    if not sector_items and hasattr(adapter, "sector_daily_rows"):
        try:
            sector_items = _eastmoney_sector_rows(SECTOR_KEYWORDS, start_date, end_date)
        except Exception:
            sector_items = []
    for item in sector_items:
        metrics = calculate_metrics(item["rows"])
        closes = [_finite(row.get("close")) for row in item["rows"]]
        closes = [value for value in closes if value is not None]
        pullback_days = 0
        for index in range(len(closes) - 1, 0, -1):
            if closes[index] < closes[index - 1]:
                pullback_days += 1
            else:
                break
        result.append({
            "code": item["code"], "name": item["name"], "category": "sector", "keyword": item["keyword"],
            **{key: metrics.get(key) for key in ("date", "close", "changePct", "volumeRatio20", "amountRatio20", "turnoverRate")},
            "source": item["source"],
            "pullbackDays": pullback_days,
        })
    return result


def _group_summaries(stocks: list[dict[str, Any]], market: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    for definition in GROUP_DEFINITIONS:
        group = definition["name"]
        items = [item for item in stocks if item["groupKey"] == definition["key"]]
        if not items:
            continue
        changes = [item["metrics"].get("changePct") for item in items if item["metrics"].get("changePct") is not None]
        amounts = [item["metrics"].get("amount") for item in items if item["metrics"].get("amount") is not None]
        summaries.append({
            "group": group, "source": "观察池等权代理（非官方行业指数）", "averageChangePct": _round(_mean(changes)),
            "totalAmount": _round(sum(amounts), 0) if amounts else None,
            "advancers": sum(1 for value in changes if value > 0), "decliners": sum(1 for value in changes if value < 0),
            "interpretation": "用于说明观察池内部环境；不替代申万、东财或同花顺正式板块指数。",
        })
    return summaries


def _previous_changes(previous: dict[str, Any] | None, stocks: list[dict[str, Any]]) -> dict[str, list[str] | str]:
    if not previous or not previous.get("report"):
        return {"status": "无法读取上一期报告", "新增": [], "升级": [], "降级": [], "移出观察": []}
    old_items = previous["report"].get("fullPool") or []
    old = {item.get("code"): item.get("conclusion") for item in old_items}
    ranks = {label: index for index, label in enumerate(("风险较高", "继续等待", "不追高", "观察", "重点观察", "低吸观察", "小仓试错前置"))}
    output: dict[str, Any] = {"status": "已比较", "新增": [], "升级": [], "降级": [], "移出观察": []}
    for item in stocks:
        code, label = item["code"], item["classification"]["conclusion"]
        if code not in old:
            output["新增"].append(code)
        elif ranks.get(label, 0) > ranks.get(old[code], 0):
            output["升级"].append(f"{code} {old[code]}→{label}")
        elif ranks.get(label, 0) < ranks.get(old[code], 0):
            output["降级"].append(f"{code} {old[code]}→{label}")
    output["移出观察"] = [code for code in old if code not in {item["code"] for item in stocks}]
    return output


def build_report(
    *, requested_date: str, analysis_date: str, market_status: str, stocks: list[dict[str, Any]],
    market: list[dict[str, Any]], source_conflicts: list[dict[str, Any]], previous: dict[str, Any] | None,
    cutoff_at: str, non_trading: bool = False, policy_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    title = f"A股科技股量价及均线分析｜{analysis_date}"
    if non_trading:
        return {
            "title": title, "requestedDate": requested_date, "analysisDate": analysis_date,
            "marketStatus": market_status, "dataCutoffAt": cutoff_at,
            "summary": "非交易日：仅展示最近可核验交易日状态，不生成或虚构当日行情。",
            "marketEnvironment": market, "nextTradingDayWatch": ["等待下一交易日收盘数据完整后重新计算全部指标。"],
            "policyEvidence": policy_evidence or [],
            "disclaimer": "仅用于研究、复盘和风险识别，不构成投资建议，不自动下单，不承诺收益。",
        }
    full_pool = []
    for item in stocks:
        metrics, classification = item["metrics"], item["classification"]
        full_pool.append({
            "code": item["code"], "name": item["name"], "groupKey": item.get("groupKey"),
            "group": item["group"], "ruleTags": item.get("ruleTags") or [],
            **metrics, **classification, "announcementRisk": item.get("announcementRisk") or "未发现重大负面",
            "announcements": item.get("announcements") or [], "dataCompleteness": item.get("dataCompleteness"),
        })
    focus_labels = {"低吸观察", "小仓试错前置", "重点观察", "风险较高"}
    focus = [item for item in full_pool if item["conclusion"] in focus_labels]
    no_chase = [item for item in full_pool if item["conclusion"] in {"不追高", "风险较高"}]
    low_buy = [item for item in full_pool if item["conclusion"] == "低吸观察"]
    trial = [item for item in full_pool if item["conclusion"] == "小仓试错前置"]
    watch = []
    for item in (focus + no_chase)[:10]:
        if item.get("nextDayCondition"):
            watch.append({"code": item["code"], "name": item["name"], "condition": item["nextDayCondition"], "invalidation": item.get("invalidation")})
    changes = _previous_changes(previous, stocks)
    facts = []
    for index, item in enumerate(full_pool, 1):
        facts.append({"id": f"STOCK-{index:02d}", "code": item["code"], "close": item.get("close"), "changePct": item.get("changePct"), "conclusion": item["conclusion"]})
    for index, item in enumerate(market, 1):
        facts.append({"id": f"MARKET-{index:02d}", "name": item.get("name"), "changePct": item.get("changePct"), "volumeRatio20": item.get("volumeRatio20"), "source": item.get("source")})
    for index, item in enumerate(policy_evidence or [], 1):
        facts.append({"id": f"POLICY-{index:02d}", **item})
    return {
        "title": title, "requestedDate": requested_date, "analysisDate": analysis_date, "marketStatus": market_status,
        "dataCutoffAt": cutoff_at, "primarySource": "TuShare Pro（日线/复权因子/daily_basic）",
        "crossCheckSource": "东方财富仅核验最新收盘价", "sourceConflicts": source_conflicts,
        "conclusionFirst": {
            "lowBuy": [f"{item['code']} {item['name']}" for item in low_buy] or ["今日无"],
            "smallPositionTrial": [f"{item['code']} {item['name']}" for item in trial] or ["今日无"],
            "importantChanges": [f"{item['code']} {item['name']}：{item['triggerType']}（{item['conclusion']}）" for item in focus[:5]],
            "highRisk": [f"{item['code']} {item['name']}：{item['triggerType']}" for item in no_chase[:8]],
            "versusPrevious": changes,
        },
        "focus": focus, "fullPool": full_pool, "groupSummary": _group_summaries(stocks, market),
        "marketEnvironment": market, "doNotChase": no_chase, "nextTradingDayWatch": watch,
        "policyEvidence": policy_evidence or [],
        "finalThreeLines": {
            "mostWorthTracking": "、".join(f"{item['code']} {item['name']}" for item in focus[:3]) or "今日无",
            "avoidChasingOrBreakdown": "、".join(f"{item['code']} {item['name']}" for item in no_chase[:3]) or "今日无",
            "overallStage": "高位分歧" if no_chase else "趋势延续" if any(item["priceStructure"] == "上升" for item in full_pool) else "修复确认",
        },
        "facts": facts, "disclaimer": "仅用于研究、复盘和风险识别，不构成投资建议，不自动下单，不承诺收益。",
    }


def _maybe_add_llm_narrative(report: dict[str, Any]) -> dict[str, Any] | None:
    """Add prose only. Numeric facts, labels, supports and invalidations stay rule-owned."""
    if not (INSIGHTS_LLM_BASE_URL and INSIGHTS_LLM_API_KEY and INSIGHTS_LLM_MODEL):
        report["narrativeStatus"] = "deterministic-template"
        return None
    facts = report.get("facts") or []
    allowed_ids = {str(item.get("id")) for item in facts if item.get("id")}
    endpoint = INSIGHTS_LLM_BASE_URL.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    payload = {
        "model": INSIGHTS_LLM_MODEL, "temperature": 0.1, "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": (
                "你只负责润色A股科技股收盘复盘，不得修改或新增数字、结论等级、支撑位、观察区或失效位。"
                "只能使用FACTS中的事实。返回JSON对象，键为headline、marketSummary、groupSummary、riskSummary；"
                "每个事实句末必须附一个或多个[FACT-ID]。不得给出买卖指令或收益承诺。"
            )},
            {"role": "user", "content": json.dumps({"FACTS": facts, "ruleConclusions": report.get("conclusionFirst")}, ensure_ascii=False)},
        ],
    }
    try:
        request = Request(
            endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {INSIGHTS_LLM_API_KEY}", "Content-Type": "application/json"},
        )
        with urlopen(request, timeout=INSIGHTS_LLM_TIMEOUT_SECONDS) as response:  # noqa: S310 - operator-configured endpoint
            raw = json.loads(response.read().decode("utf-8"))
        content = (((raw.get("choices") or [{}])[0].get("message") or {}).get("content"))
        narrative = content if isinstance(content, dict) else json.loads(str(content or "{}").strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(narrative, dict) or not narrative:
            raise ValueError("empty narrative")
        references = set(re.findall(r"\[([A-Z]+-\d+)\]", json.dumps(narrative, ensure_ascii=False)))
        if not references or not references <= allowed_ids:
            raise ValueError("narrative contains missing or unknown fact IDs")
        report["modelNarrative"] = narrative
        report["narrativeStatus"] = "model-generated-from-facts"
        return raw
    except Exception as exc:
        safe_error = str(exc).replace(INSIGHTS_LLM_API_KEY, "[REDACTED]")
        report["narrativeStatus"] = "deterministic-fallback"
        report["narrativeWarning"] = safe_error
        return None


def create_report(requested_date: str | None = None, *, force: bool = False) -> dict[str, Any]:
    requested_date = requested_date or datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    try:
        date.fromisoformat(requested_date)
    except ValueError as exc:
        raise AshareTechReportError("requestedDate must be YYYY-MM-DD.") from exc
    with db() as connection:
        existing = connection.execute("select * from ashare_tech_reports where requested_date = ?", (requested_date,)).fetchone()
    if existing and not force:
        return row_to_dict(existing) or {}
    snapshot = watchlist_snapshot()
    if not snapshot["items"]:
        raise AshareTechReportError("观察池没有启用股票，无法创建报告。")
    now, report_id = utc_now(), str(uuid.uuid4())
    if existing:
        report_id = str(existing["id"])
        with db() as connection:
            connection.execute(
                """
                update ashare_tech_reports
                set status = ?, error = null, report_json = null, pool_snapshot_json = ?,
                    pool_fingerprint = ?, updated_at = ?
                where id = ?
                """,
                ("queued", json_dump(snapshot), snapshot["fingerprint"], now, report_id),
            )
    else:
        with db() as connection:
            connection.execute(
                """
                insert into ashare_tech_reports
                    (id, requested_date, market_status, status, data_completeness_json, source_conflicts_json,
                     source_manifest_json, pool_snapshot_json, pool_fingerprint, prompt_version, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (report_id, requested_date, "pending", "queued", "{}", "[]", "[]", json_dump(snapshot),
                 snapshot["fingerprint"], PROMPT_VERSION, now, now),
            )
    return get_report(report_id)


def attach_task(report_id: str, task_id: str) -> None:
    with db() as connection:
        connection.execute("update ashare_tech_reports set task_id = ?, updated_at = ? where id = ?", (task_id, utc_now(), report_id))


def get_report(report_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from ashare_tech_reports where id = ?", (report_id,)).fetchone()
    result = row_to_dict(row)
    if not result:
        raise KeyError("A-share technology report not found.")
    return result


def list_reports(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit, offset = min(max(limit, 1), 200), max(offset, 0)
    with db() as connection:
        rows = connection.execute("select * from ashare_tech_reports order by requested_date desc limit ? offset ?", (limit, offset)).fetchall()
        count = connection.execute("select count(*) from ashare_tech_reports").fetchone()[0]
    return {"items": rows_to_dicts(rows), "count": count, "limit": limit, "offset": offset}


def fail_report(report_id: str, error: str) -> None:
    with db() as connection:
        connection.execute(
            "update ashare_tech_reports set status = ?, error = ?, finished_at = ?, updated_at = ? where id = ?",
            ("failed", error, utc_now(), utc_now(), report_id),
        )


def _previous_report(analysis_date: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from ashare_tech_reports where status = 'success' and analysis_date < ? order by analysis_date desc limit 1",
            (analysis_date,),
        ).fetchone()
    return row_to_dict(row)


def run_report(
    task_id: str, report_id: str, *, attempt: int = 0, adapter: TushareAdapter | None = None,
    cross_checker: Callable[[str], dict[str, Any] | None] = _eastmoney_latest,
    announcement_fetcher: Callable[[str, str, str], list[dict[str, Any]]] = _official_announcements,
    policy_fetcher: Callable[[str, str], list[dict[str, Any]]] = _official_policy_evidence,
) -> dict[str, Any]:
    record = get_report(report_id)
    requested_date = str(record["requested_date"])
    snapshot = record.get("poolSnapshot") or watchlist_snapshot()
    pool_items = [dict(item) for item in snapshot.get("items") or [] if item.get("enabled", True)]
    if not pool_items:
        raise AshareTechReportError("报告观察池快照为空，无法生成报告。")
    if not record.get("poolSnapshot"):
        with db() as connection:
            connection.execute(
                "update ashare_tech_reports set pool_snapshot_json = ?, pool_fingerprint = ?, updated_at = ? where id = ?",
                (json_dump(snapshot), snapshot["fingerprint"], utc_now(), report_id),
            )
    expected_pool_size = len(pool_items)
    adapter = adapter or TushareAdapter()
    now = utc_now()
    update_task(task_id, status="running", started_at=now, error=None)
    append_log(task_id, f"A-share technology report attempt {attempt + 1}; requested date {requested_date}.")
    with db() as connection:
        connection.execute(
            "update ashare_tech_reports set status = ?, attempt_count = ?, started_at = coalesce(started_at, ?), updated_at = ? where id = ?",
            ("running", attempt + 1, now, now, report_id),
        )
    start_calendar = (date.fromisoformat(requested_date) - timedelta(days=14)).isoformat()
    calendar = adapter.trade_calendar(start_calendar, requested_date)
    open_dates = sorted(str(item["trade_date"]) for item in calendar if item.get("is_open") and item.get("trade_date"))
    is_trading = requested_date in open_dates
    latest_trade_date = open_dates[-1] if open_dates else None
    if not latest_trade_date:
        raise AshareTechReportError("TuShare trade calendar returned no verifiable trading date.")
    history_start = (date.fromisoformat(latest_trade_date) - timedelta(days=260)).isoformat()
    announcements_start = (date.fromisoformat(latest_trade_date) - timedelta(days=7)).isoformat()
    market = _market_environment(adapter, history_start, latest_trade_date)
    storage_pullback_days = max(
        (int(item.get("pullbackDays") or 0) for item in market if item.get("category") == "sector" and item.get("keyword") == "存储"),
        default=0,
    )
    policy_error = None
    try:
        policy_evidence = policy_fetcher(announcements_start, latest_trade_date)
    except Exception as exc:
        policy_evidence, policy_error = [], str(exc)
        append_log(task_id, f"Official policy check unavailable: {exc}")
    if not is_trading:
        report = build_report(
            requested_date=requested_date, analysis_date=latest_trade_date, market_status="非交易日",
            stocks=[], market=market, source_conflicts=[], previous=_previous_report(latest_trade_date), cutoff_at=utc_now(), non_trading=True,
            policy_evidence=policy_evidence,
        )
        report["poolFingerprint"] = snapshot.get("fingerprint")
        report["poolSnapshot"] = pool_items
        completion = {"complete": True, "mode": "non-trading-status", "poolSize": expected_pool_size}
        return _finish_report(task_id, report_id, report, completion, [], [{"source": "tushare:trade_cal"}, {"source": "official-policy-pages", "error": policy_error}], latest_trade_date, "非交易日")

    stocks: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    manifest: list[dict[str, Any]] = [{"source": "tushare:trade_cal", "date": requested_date}]
    available_date_sets: list[set[str]] = []
    for pool_item in pool_items:
        code = pool_item["code"]
        append_log(task_id, f"Fetching TuShare OHLCV/amount/turnover/adj_factor for {code}.")
        try:
            raw = adapter.daily_rows(code, history_start, latest_trade_date)
            basics = adapter.daily_basic_rows(code, history_start, latest_trade_date)
            rows = qfq_rows(_merge_daily_basic(raw, basics))
        except Exception as exc:
            rows = []
            append_log(task_id, f"TuShare failed for {code}: {exc}")
        metrics = calculate_metrics(rows)
        available_date_sets.append({str(row.get("date")) for row in rows if row.get("date")})
        try:
            cross = cross_checker(code)
        except Exception as exc:
            cross = None
            append_log(task_id, f"Eastmoney cross-check unavailable for {code}: {exc}")
        raw_close = metrics.get("rawClose")
        source_conflict = False
        cross_date = str(cross.get("timestamp") or "")[:10] if cross else ""
        if cross and raw_close and cross_date == str(metrics.get("date") or ""):
            difference = abs((float(cross["close"]) / float(raw_close) - 1) * 100)
            if difference > ASHARE_TECH_CLOSE_TOLERANCE_PCT:
                source_conflict = True
                conflicts.append({"code": code, "date": cross_date, "tushareClose": raw_close, "eastmoneyClose": cross["close"], "differencePct": _round(difference), "resolution": "采用TuShare；降低结论等级并标需复核"})
        announcement_error = None
        try:
            announcements = announcement_fetcher(code, announcements_start, latest_trade_date)
        except Exception as exc:
            announcements, announcement_error = [], str(exc)
            append_log(task_id, f"Official announcement check unavailable for {code}: {exc}")
        try:
            tushare_announcement_directory = adapter.announcement_directory_rows(code, announcements_start, latest_trade_date)
        except Exception:
            tushare_announcement_directory = []
        negative = any(any(keyword in str(item.get("title") or "") for keyword in RISK_KEYWORDS) for item in announcements)
        if announcement_error:
            metrics.setdefault("missing", []).append("最近7日官方公告检查不完整")
        classification = classify_stock(
            rows, metrics, code=code, negative_announcement=negative,
            storage_sector_pullback_days=storage_pullback_days, source_conflict=source_conflict,
            rule_tags=pool_item.get("ruleTags") or [],
        )
        stocks.append({
            **pool_item, "rows": rows, "metrics": metrics, "classification": classification,
            "announcementRisk": "存在重大负面关键词，否决低吸" if negative else "公告检查失败，需复核" if announcement_error else "未发现重大负面",
            "announcements": announcements, "dataCompleteness": {"sampleCount": metrics.get("sampleCount"), "missing": metrics.get("missing"), "latestDate": metrics.get("date")},
        })
        manifest.extend((
            {"source": "tushare:daily+adj_factor", "code": code, "latestDate": metrics.get("date")},
            {"source": "tushare:daily_basic", "code": code, "latestDate": metrics.get("date")},
            {"source": "SSE/SZSE official announcements", "code": code, "from": announcements_start, "to": latest_trade_date, "error": announcement_error},
            {"source": "tushare:anns_d", "code": code, "directoryCount": len(tushare_announcement_directory), "role": "目录交叉核验，非事实唯一来源"},
        ))
    common_dates = set.intersection(*available_date_sets) if len(available_date_sets) == expected_pool_size and all(available_date_sets) else set()
    common_date = max((item for item in common_dates if item <= latest_trade_date), default=None)
    if common_date != latest_trade_date and attempt < 2:
        message = f"Full-pool close is not ready: expected {latest_trade_date}, common latest {common_date or 'missing'}."
        append_log(task_id, message)
        with db() as connection:
            connection.execute("update ashare_tech_reports set status = ?, error = ?, updated_at = ? where id = ?", ("waiting_data", message, utc_now(), report_id))
        raise ReportDataNotReady(message)
    if common_date is None:
        raise AshareTechReportError(f"重试后仍无法构造{expected_pool_size}只股票的同一完整收盘日；报告已停止，未混用或伪造行情。")
    analysis_date = common_date
    if analysis_date != latest_trade_date:
        # Recalculate a coherent full-pool snapshot instead of mixing report dates.
        for item in stocks:
            coherent_rows = [row for row in item["rows"] if str(row.get("date")) <= analysis_date]
            item["rows"] = coherent_rows
            item["metrics"] = calculate_metrics(coherent_rows)
            item["classification"] = classify_stock(
                coherent_rows, item["metrics"], code=item["code"],
                negative_announcement=item["announcementRisk"].startswith("存在"),
                storage_sector_pullback_days=storage_pullback_days,
                source_conflict=any(conflict["code"] == item["code"] for conflict in conflicts),
                rule_tags=item.get("ruleTags") or [],
            )
    report = build_report(
        requested_date=requested_date, analysis_date=analysis_date, market_status="交易日" if analysis_date == requested_date else "交易日（使用最近完整共同收盘日）",
        stocks=stocks, market=market, source_conflicts=conflicts, previous=_previous_report(analysis_date), cutoff_at=utc_now(),
        policy_evidence=policy_evidence,
    )
    report["poolFingerprint"] = snapshot.get("fingerprint")
    report["poolSnapshot"] = pool_items
    manifest.append({"source": "official-policy-pages", "from": announcements_start, "to": latest_trade_date, "items": len(policy_evidence), "error": policy_error})
    incomplete = [item["code"] for item in stocks if item["metrics"].get("missing")]
    completion = {
        "complete": not incomplete and analysis_date == requested_date, "poolSize": expected_pool_size, "covered": len(stocks),
        "analysisDate": analysis_date, "requestedDate": requested_date, "incompleteSymbols": incomplete,
        "fullPoolDateAligned": bool(common_date),
    }
    return _finish_report(task_id, report_id, report, completion, conflicts, manifest, analysis_date, report["marketStatus"])


def _finish_report(
    task_id: str, report_id: str, report: dict[str, Any], completion: dict[str, Any], conflicts: list[dict[str, Any]],
    manifest: list[dict[str, Any]], analysis_date: str, market_status: str,
) -> dict[str, Any]:
    now = utc_now()
    raw_response = _maybe_add_llm_narrative(report) if report.get("facts") else None
    fingerprint = hashlib.sha256(json_dump({"report": report, "promptVersion": PROMPT_VERSION}).encode("utf-8")).hexdigest()
    sector_sources = sorted({
        str(item.get("source")) for item in report.get("marketEnvironment", [])
        if item.get("category") == "sector" and item.get("source")
    })
    sector_source = ",".join(sector_sources) if sector_sources else "观察池等权代理（正式板块数据缺失）"
    with db() as connection:
        connection.execute(
            """
            update ashare_tech_reports
            set analysis_date = ?, market_status = ?, status = 'success', data_cutoff_at = ?, sector_source = ?,
                data_completeness_json = ?, source_conflicts_json = ?, source_manifest_json = ?,
                raw_response_json = ?, report_json = ?, model = ?, input_fingerprint = ?, error = null, finished_at = ?, updated_at = ?
            where id = ?
            """,
            (analysis_date, market_status, now, sector_source, json_dump(completion), json_dump(conflicts), json_dump(manifest),
             json_dump(raw_response) if raw_response else None, json_dump(report),
             INSIGHTS_LLM_MODEL if report.get("narrativeStatus") == "model-generated-from-facts" else None,
             fingerprint, now, now, report_id),
        )
    update_task(task_id, status="success", artifacts_json=[f"ashare-tech-report:{report_id}"], finished_at=now, error=None)
    append_log(task_id, f"Completed A-share technology report for {analysis_date}; {completion.get('covered', 0)} stocks.")
    return get_report(report_id)
