from __future__ import annotations

from typing import Any


REPORT_LAYOUT_VERSION = "report-layout-v2"


def report_payload(item: dict[str, Any]) -> dict[str, Any]:
    result = item.get("result") or {}
    parameters = item.get("parameters") or {}
    symbol = item.get("symbol") or parameters.get("ticker") or parameters.get("symbol")
    asset_class = item.get("asset_class") or parameters.get("assetClass") or "equity"
    title = parameters.get("name") or (f"Local {asset_class} {symbol} Backtest" if symbol else "LEAN Backtest Report")
    return {
        "id": item.get("id"),
        "runId": item.get("run_id"),
        "source": item.get("source"),
        "status": item.get("status"),
        "createdAt": item.get("created_at"),
        "finishedAt": item.get("finished_at"),
        "error": item.get("error"),
        "title": title,
        "symbol": symbol,
        "market": item.get("venue") or parameters.get("market") or parameters.get("venue"),
        "provider": parameters.get("providerSource") or parameters.get("source"),
        "startDate": parameters.get("start"),
        "endDate": parameters.get("end"),
        "initialCash": parameters.get("initialCash") or parameters.get("initial_cash") or parameters.get("cash"),
        "metrics": result.get("summary_metrics") or result.get("statistics") or {},
        "performance": result.get("performance") or {},
        "orders": result.get("orders") or [],
        "trades": result.get("trades") or [],
        "holdings": result.get("holdings") or [],
        "validation": item.get("validation") or (result.get("performance") or {}).get("validation"),
        "experiment": item.get("experiment") or (result.get("performance") or {}).get("experiment"),
        "storedObjects": item.get("storedObjects") or [],
        "rawResultObjectId": item.get("raw_result_object_id"),
        "summaryObjectId": item.get("summary_object_id"),
    }


def markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        f"<!-- {REPORT_LAYOUT_VERSION} -->",
        "",
        f"# {payload.get('title') or 'LEAN Backtest Report'}",
        "",
        f"> QUANTCONNECT LEAN · 回测分析 · 运行编号 `{payload.get('runId') or payload.get('id')}`",
        "",
        "## Summary",
        "",
        f"- Symbol: {payload.get('symbol') or '-'}",
        f"- Market: {payload.get('market') or '-'}",
        f"- Period: {payload.get('startDate') or '-'} to {payload.get('endDate') or '-'}",
        f"- Provider: {payload.get('provider') or '-'}",
        f"- Initial Cash: {payload.get('initialCash') or '-'}",
        f"- Status: {payload.get('status') or '-'}",
        f"- Created: {payload.get('createdAt') or '-'}",
        f"- Finished: {payload.get('finishedAt') or '-'}",
        f"- Error: {payload.get('error') or '-'}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    metrics = payload.get("metrics") or {}
    if metrics:
        lines.extend(f"| {key} | {value} |" for key, value in metrics.items())
    else:
        lines.append("| - | - |")
    validation = payload.get("validation") or {}
    if validation:
        lines.extend(
            [
                "",
                "## Validation",
                "",
                f"- Passed: {validation.get('passed')}",
                f"- Severity: {validation.get('severity')}",
                f"- Gates: {len(validation.get('gates') or [])}",
            ]
        )
    experiment = payload.get("experiment") or {}
    if experiment:
        lines.extend(
            [
                "",
                "## Experiment",
                "",
                f"- Strategy SHA256: {((experiment.get('strategy') or {}).get('sha256')) or '-'}",
                f"- Parameters SHA256: {((experiment.get('parameters') or {}).get('sha256')) or '-'}",
                f"- Docker Image: {((experiment.get('environment') or {}).get('dockerImage')) or '-'}",
            ]
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "| Key | SHA256 | Size |",
            "| --- | --- | --- |",
        ]
    )
    objects = payload.get("storedObjects") or []
    if objects:
        lines.extend(f"| {item.get('object_key') or item.get('key') or '-'} | {item.get('sha256') or '-'} | {item.get('size') or '-'} |" for item in objects)
    else:
        lines.append("| - | - | - |")
    return "\n".join(lines) + "\n"
