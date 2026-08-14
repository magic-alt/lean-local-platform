from __future__ import annotations

import math
import statistics
from typing import Any

from ..db import db, rows_to_dicts
from ..research import factors
from . import ashare_swing_screen, cbond, daily_gap_analysis, data_gateway, futures
from .pit_data import index_members_as_of_payload


TEMPLATES = [
    {
        "key": "market-eda",
        "name": "市场探索",
        "description": "价格、收益率、波动率、回撤与相关性诊断。",
        "category": "market",
        "parameterSchema": {},
    },
    {
        "key": "data-quality",
        "name": "数据质量",
        "description": "覆盖区间、缺口、来源与认证状态。",
        "category": "data",
        "parameterSchema": {},
    },
    {
        "key": "universe-pit",
        "name": "PIT 股票池",
        "description": "按当时可知信息还原指数成份，避免未来数据。",
        "category": "universe",
        "parameterSchema": {"universeCode": "CSI300", "tradable": False},
    },
    {
        "key": "factor-evaluation",
        "name": "因子评价",
        "description": "IC、分位数组合与稳定性评价，不模拟交易订单。",
        "category": "factor",
        "parameterSchema": {"factorNames": [], "forwardDays": 5, "quantiles": 5, "engine": "python"},
    },
    {
        "key": ashare_swing_screen.TEMPLATE_KEY,
        "name": "全A有序回调候选",
        "description": "按PIT盈利、流动性、下跌速度、回调修复、波动和趋势筛选A股研究候选。",
        "category": "idea-generation",
        "execution": "async",
        "parameterSchema": ashare_swing_screen.default_parameters(),
    },
    {
        "key": daily_gap_analysis.TEMPLATE_KEY,
        "name": "日K低开修复与高开回吐",
        "description": "按证券代码分别统计标准化缺口、日内修复/回吐、OHLC路径边界及事后量比。",
        "category": "event-study",
        "parameterSchema": daily_gap_analysis.default_parameters(),
    },
    {
        "key": "ml-cross-sectional-ranker",
        "name": "CSI300 横截面机器学习",
        "description": "已冻结的历史兼容模板；新的模型训练与 walk-forward 由 qlib-platform 执行。",
        "category": "machine-learning",
        "legacy": True,
        "parameterSchema": {
            "universeCode": "CSI300", "startDate": "2015-01-01",
            "endDate": "latest", "horizonTradingDays": 5,
        },
    },
    {
        "key": "cbond-double-low",
        "name": "可转债双低筛选",
        "description": "按估值与强赎风险筛选可转债。",
        "category": "cbond",
        "parameterSchema": {"maxDoubleLow": 130, "excludeCallRisk": True},
    },
    {
        "key": "futures-continuous",
        "name": "期货连续合约",
        "description": "主力映射、连续价格、换月价差与展期收益研究。",
        "category": "futures",
        "parameterSchema": {"product": "RB", "exchange": "SHFE", "adjustment": "backward_ratio"},
    },
]


def template(key: str) -> dict[str, Any]:
    item = next((value for value in TEMPLATES if value["key"] == key), None)
    if item is None:
        raise ValueError(f"unknown_research_template:{key}")
    return item


def public_templates() -> list[dict[str, Any]]:
    """Control-center templates; legacy ML runs remain readable but cannot be created."""
    return [item for item in TEMPLATES if not item.get("legacy")]


def is_async_template(key: str) -> bool:
    return str(template(key).get("execution") or "sync") == "async"


def _table(name: str, columns: list[str], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"name": name, "columns": columns, "rows": rows[:1000], "truncated": len(rows) > 1000}


def _market_eda(scope: dict[str, Any]) -> tuple[dict, list, list, list]:
    payload = data_gateway.query(scope, limit=1000)
    items = payload["items"]
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        by_symbol.setdefault(str(item["symbol"]), []).append(item)
    metrics = []
    chart_series = []
    for symbol, rows in by_symbol.items():
        closes = [float(row["close"]) for row in rows if row.get("close") not in (None, 0)]
        returns = [(closes[index] / closes[index - 1]) - 1 for index in range(1, len(closes))]
        peak = -math.inf
        max_drawdown = 0.0
        for close in closes:
            peak = max(peak, close)
            max_drawdown = min(max_drawdown, close / peak - 1)
        metrics.append(
            {
                "symbol": symbol,
                "bars": len(closes),
                "return": closes[-1] / closes[0] - 1 if len(closes) > 1 else None,
                "volatility": statistics.pstdev(returns) * math.sqrt(252) if len(returns) > 1 else None,
                "maxDrawdown": max_drawdown if closes else None,
            }
        )
        chart_series.append(
            {
                "name": symbol,
                "data": [{"x": row["trade_date"], "y": row.get("close")} for row in rows if row.get("close") is not None],
            }
        )
    summary = {"symbols": len(by_symbol), "bars": len(items), "metrics": metrics}
    charts = [{"type": "line", "title": "收盘价", "series": chart_series}]
    return summary, charts, [_table("市场概览", ["symbol", "bars", "return", "volatility", "maxDrawdown"], metrics)], []


def _data_quality(scope: dict[str, Any]) -> tuple[dict, list, list, list]:
    resolved = data_gateway.resolve(scope)
    coverage = resolved["coverage"]
    warnings = [] if resolved["ready"] else ["当前范围没有可用数据。"]
    rows = [
        {
            "source": resolved["source"],
            "rows": coverage.get("rows"),
            "symbols": coverage.get("symbols"),
            "firstDate": coverage.get("first_date"),
            "lastDate": coverage.get("last_date"),
            "certified": bool((resolved.get("certification") or {}).get("isCertified")),
        }
    ]
    return {"ready": resolved["ready"], **coverage}, [], [_table("数据覆盖", list(rows[0]), rows)], warnings


def _pit(scope: dict[str, Any], parameters: dict[str, Any]) -> tuple[dict, list, list, list]:
    as_of = scope["time"].get("asOfDate") or scope["time"].get("endDate")
    if not as_of:
        raise ValueError("asOfDate is required for PIT universe research")
    code = str(parameters.get("universeCode") or (scope["selection"]["values"] or ["CSI300"])[0])
    result = index_members_as_of_payload(
        code,
        as_of,
        tradable=bool(parameters.get("tradable")),
        min_listed_days=int(parameters.get("minListedDays") or 0),
        exclude_st=bool(parameters.get("excludeSt", True)),
    )
    return result, [], [_table("PIT 成份", ["symbol", "name", "in_date", "out_date"], result.get("items") or [])], (
        [str(result["message"])] if result.get("message") else []
    )


def _factor(scope: dict[str, Any], parameters: dict[str, Any]) -> tuple[dict, list, list, list]:
    names = [str(value) for value in parameters.get("factorNames") or [] if str(value).strip()]
    if not names:
        raise ValueError("factorNames is required")
    start = scope["time"].get("startDate")
    end = scope["time"].get("endDate")
    if not start or not end:
        raise ValueError("startDate and endDate are required for factor evaluation")
    universe = str(parameters.get("universeCode") or (scope["selection"]["values"] or ["ALL_A"])[0])
    results = [
        factors.evaluate_factor(
            factor_name=name,
            universe_code=universe,
            start_date=start,
            end_date=end,
            forward_days=int(parameters.get("forwardDays") or 5),
            quantiles=int(parameters.get("quantiles") or 5),
            engine=parameters.get("engine"),
            persist=True,
        )
        for name in names
    ]
    rows = [
        {
            "factorName": item.get("factorName") or item.get("factor_name"),
            "icMean": item.get("icMean"),
            "icIr": item.get("icIr"),
            "coverage": item.get("coverage"),
            "engine": item.get("engine"),
        }
        for item in results
    ]
    return {"factors": len(results), "results": results}, [], [_table("因子评价", list(rows[0]) if rows else [], rows)], []


def _cbond(scope: dict[str, Any], parameters: dict[str, Any]) -> tuple[dict, list, list, list]:
    as_of = scope["time"].get("asOfDate") or scope["time"].get("endDate")
    if not as_of:
        raise ValueError("asOfDate is required for convertible-bond research")
    result = cbond.double_low_pool(
        as_of_date=as_of,
        max_double_low=float(parameters.get("maxDoubleLow") or 130),
        exclude_call_risk=bool(parameters.get("excludeCallRisk", True)),
        limit=1000,
    )
    return result, [], [_table("双低候选", ["bond_code", "bond_name", "close", "premium_rate", "double_low", "rating"], result["items"])], []


def _futures(scope: dict[str, Any], parameters: dict[str, Any]) -> tuple[dict, list, list, list]:
    product = str(parameters.get("product") or (scope["selection"]["values"] or [""])[0]).upper()
    exchange = str(parameters.get("exchange") or scope["asset"]["venue"]).upper()
    start, end = scope["time"].get("startDate"), scope["time"].get("endDate")
    if not product or not start or not end:
        raise ValueError("product, startDate and endDate are required for futures research")
    mapping = futures.refresh_main_mapping(product=product, exchange=exchange, start_date=start, end_date=end)
    with db() as connection:
        rows = rows_to_dicts(
            connection.execute(
                """
                select m.trade_date, m.main_symbol, b.close, b.settle, b.volume, b.open_interest
                from futures_main_mapping m
                left join futures_daily_bars b
                  on b.contract_code=m.main_symbol and b.trade_date=m.trade_date
                where m.batch_id=? order by m.trade_date
                """,
                (mapping["batchId"],),
            ).fetchall()
        )
    rolls = []
    previous = None
    for row in rows:
        current = row.get("main_symbol")
        if previous and current != previous:
            rolls.append({"tradeDate": row["trade_date"], "from": previous, "to": current})
        previous = current
    summary = {"product": product, "exchange": exchange, "bars": len(rows), "rolls": len(rolls), "mappingBatchId": mapping["batchId"]}
    charts = [{"type": "line", "title": f"{product} 主力连续价格", "series": [{"name": product, "data": [{"x": row["trade_date"], "y": row.get("close")} for row in rows]}]}]
    return summary, charts, [_table("主力映射", ["trade_date", "main_symbol", "close", "volume", "open_interest"], rows), _table("换月事件", ["tradeDate", "from", "to"], rolls)], []


ANALYZERS = {
    "market-eda": _market_eda,
    "data-quality": _data_quality,
    "universe-pit": _pit,
    "factor-evaluation": _factor,
    daily_gap_analysis.TEMPLATE_KEY: daily_gap_analysis.analyze,
    "cbond-double-low": _cbond,
    "futures-continuous": _futures,
}


def analyze(
    template_key: str,
    scope: dict[str, Any],
    parameters: dict[str, Any],
    *,
    run_id: str | None = None,
    cancelled=None,
    progress=None,
) -> dict[str, Any]:
    template(template_key)
    resolved = data_gateway.resolve(scope)
    normalized = resolved["scope"]
    if template_key == ashare_swing_screen.TEMPLATE_KEY:
        if not run_id:
            raise ValueError("run_id is required for A-share swing screening")
        payload = ashare_swing_screen.analyze(
            normalized,
            parameters,
            run_id=run_id,
            cancelled=cancelled,
            progress=progress,
        )
        return {
            "schemaVersion": "1.0",
            "template": template_key,
            "scope": normalized,
            "scopeHash": resolved["scopeHash"],
            "dataFingerprint": payload["dataFingerprint"],
            "source": resolved["source"],
            "certification": resolved["certification"],
            "coverage": payload["coverage"],
            "summary": payload["summary"],
            "charts": payload["charts"],
            "tables": payload["tables"],
            "warnings": payload["warnings"],
            "artifacts": payload["artifacts"],
            "resolvedParameters": payload["resolvedParameters"],
        }
    analyzer = ANALYZERS[template_key]
    if template_key in {"market-eda", "data-quality"}:
        summary, charts, tables, warnings = analyzer(normalized)
    else:
        summary, charts, tables, warnings = analyzer(normalized, parameters)
    return {
        "schemaVersion": "1.0",
        "template": template_key,
        "scope": normalized,
        "scopeHash": resolved["scopeHash"],
        "dataFingerprint": resolved["dataFingerprint"],
        "source": resolved["source"],
        "certification": resolved["certification"],
        "coverage": resolved["coverage"],
        "summary": summary,
        "charts": charts,
        "tables": tables,
        "warnings": warnings,
        "artifacts": [],
    }
