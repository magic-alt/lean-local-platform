#!/usr/bin/env python3
import argparse
import html
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


COLORS = ["#2563eb", "#dc2626", "#059669", "#7c3aed", "#d97706", "#0891b2"]
REPORT_LAYOUT_VERSION = "report-layout-v2"
SCREENING_REPORT_NAME = "screening-report.json"


def load_json(path):
    with Path(path).open() as file:
        return json.load(file)


def load_screening(source_path):
    path = Path(source_path).parent / SCREENING_REPORT_NAME
    if not path.is_file():
        return {}
    try:
        payload = load_json(path)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def unix_to_date(value):
    return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime("%Y-%m-%d")


def iso_to_date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")


def series_points(chart, series_name, *, ignore_zero_values=False):
    series = (chart.get("series") or {}).get(series_name) or {}
    points = []
    for row in series.get("values", []):
        if len(row) < 2:
            continue
        timestamp = float(row[0])
        y_value = float(row[-1])
        if (
            math.isfinite(timestamp)
            and math.isfinite(y_value)
            and (not ignore_zero_values or y_value != 0)
        ):
            points.append((timestamp, y_value))
    return points


def get_chart(data, name):
    return (data.get("charts") or {}).get(name) or {}


def interpolate_y(points, timestamp):
    if not points:
        return None
    return min(points, key=lambda point: abs(point[0] - timestamp))[1]


def nice_number(value):
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def make_svg(title, series_map, y_unit="", markers=None, height=330):
    width = 1080
    left = 70
    right = 28
    top = 36
    bottom = 54
    plot_width = width - left - right
    plot_height = height - top - bottom

    all_points = [point for points in series_map.values() for point in points]
    if not all_points:
        return f"<section><h2>{html.escape(title)}</h2><p>No data.</p></section>"

    min_x = min(point[0] for point in all_points)
    max_x = max(point[0] for point in all_points)
    min_y = min(point[1] for point in all_points)
    max_y = max(point[1] for point in all_points)
    if min_x == max_x:
        max_x += 1
    if min_y == max_y:
        min_y -= 1
        max_y += 1

    y_padding = (max_y - min_y) * 0.08
    min_y -= y_padding
    max_y += y_padding

    def x_scale(x_value):
        return left + (x_value - min_x) / (max_x - min_x) * plot_width

    def y_scale(y_value):
        return top + (max_y - y_value) / (max_y - min_y) * plot_height

    parts = [
        f'<section class="chart-card"><h2>{html.escape(title)}</h2>',
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">',
        f'<rect x="0" y="0" width="{width}" height="{height}" rx="6" fill="#ffffff"/>',
    ]

    for i in range(5):
        ratio = i / 4
        y = top + ratio * plot_height
        value = max_y - ratio * (max_y - min_y)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        parts.append(
            f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" font-size="12" fill="#475569">'
            f'{html.escape(nice_number(value))}{html.escape(y_unit)}</text>'
        )

    for i in range(5):
        ratio = i / 4
        x = left + ratio * plot_width
        value = min_x + ratio * (max_x - min_x)
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height-bottom}" stroke="#f1f5f9"/>')
        parts.append(
            f'<text x="{x:.1f}" y="{height-22}" text-anchor="middle" font-size="12" fill="#475569">'
            f'{unix_to_date(value)}</text>'
        )

    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#94a3b8"/>')
    parts.append(f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#94a3b8"/>')

    for index, (name, points) in enumerate(series_map.items()):
        color = COLORS[index % len(COLORS)]
        polyline = " ".join(f"{x_scale(x):.2f},{y_scale(y):.2f}" for x, y in points)
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2.4" '
            f'stroke-linejoin="round" stroke-linecap="round" points="{polyline}"/>'
        )

    if markers:
        base_points = next(iter(series_map.values()))
        for marker in markers:
            timestamp = marker["timestamp"]
            if timestamp < min_x or timestamp > max_x:
                continue
            y_value = interpolate_y(base_points, timestamp)
            if y_value is None:
                continue
            x = x_scale(timestamp)
            y = y_scale(y_value)
            color = "#16a34a" if marker["side"] == "BUY" else "#dc2626"
            parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height-bottom}" stroke="{color}" stroke-dasharray="4 5" opacity="0.55"/>')
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="{color}"/>')
            parts.append(
                f'<text x="{x+7:.1f}" y="{max(top+13, y-8):.1f}" font-size="12" fill="{color}" font-weight="700">'
                f'{html.escape(marker["side"])}</text>'
            )

    legend_x = left
    legend_y = 18
    for index, name in enumerate(series_map):
        color = COLORS[index % len(COLORS)]
        x = legend_x + index * 150
        parts.append(f'<line x1="{x}" y1="{legend_y}" x2="{x+24}" y2="{legend_y}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{x+31}" y="{legend_y+4}" font-size="13" fill="#1f2937">{html.escape(name)}</text>')

    parts.append("</svg></section>")
    return "\n".join(parts)


def order_markers(data):
    markers = []
    for order in (data.get("orders") or {}).values():
        quantity = float(order.get("quantity", 0))
        time_value = order.get("lastFillTime") or order.get("time")
        if not time_value:
            continue
        timestamp = datetime.fromisoformat(time_value.replace("Z", "+00:00")).timestamp()
        markers.append({
            "timestamp": timestamp,
            "side": "BUY" if quantity > 0 else "SELL",
            "symbol": ((order.get("symbol") or {}).get("value") or ""),
            "quantity": quantity,
            "price": float(order.get("price") or 0),
            "date": iso_to_date(time_value),
        })
    return sorted(markers, key=lambda item: item["timestamp"])


def period_returns(points, period):
    grouped = {}
    for timestamp, value in points:
        date_key = unix_to_date(timestamp)
        key = date_key[:7] if period == "month" else date_key[:4]
        item = grouped.setdefault(key, {"period": key, "start": value, "end": value})
        item["end"] = value
    rows = []
    for key in sorted(grouped):
        item = grouped[key]
        start = item["start"]
        end = item["end"]
        rows.append({"period": key, "return": (end / start - 1) if start else 0, "start": start, "end": end})
    return rows


def profit_loss_rows(data):
    rows = []
    for time_value, value in sorted((data.get("profitLoss") or {}).items()):
        try:
            date_value = iso_to_date(time_value)
        except Exception:
            date_value = str(time_value)[:10]
        rows.append({"date": date_value, "pnl": float(value)})
    return rows


def pct(value):
    return f"{value * 100:.2f}%"


def returns_table(title, rows):
    if not rows:
        return f'<section class="orders"><h2>{html.escape(title)}</h2><p>No data.</p></section>'
    body = "".join(
        "<tr>"
        f"<td>{html.escape(row['period'])}</td>"
        f"<td>{pct(row['return'])}</td>"
        f"<td>{row['start']:.2f}</td>"
        f"<td>{row['end']:.2f}</td>"
        "</tr>"
        for row in rows
    )
    return (
        f'<section class="orders"><h2>{html.escape(title)}</h2>'
        "<table><thead><tr><th>Period</th><th>Return</th><th>Start Equity</th><th>End Equity</th></tr></thead>"
        f"<tbody>{body}</tbody></table></section>"
    )


def pnl_table(rows):
    if not rows:
        return '<section class="orders"><h2>Closed Trade P&L</h2><p>No closed trades.</p></section>'
    body = "".join(
        "<tr>"
        f"<td>{html.escape(row['date'])}</td>"
        f"<td>{row['pnl']:.2f}</td>"
        "</tr>"
        for row in rows
    )
    return (
        '<section class="orders"><h2>Closed Trade P&L</h2>'
        "<table><thead><tr><th>Date</th><th>P&L</th></tr></thead>"
        f"<tbody>{body}</tbody></table></section>"
    )


def stat_cards(statistics):
    keys = [
        "End Equity",
        "Net Profit",
        "Sharpe Ratio",
        "Sortino Ratio",
        "Drawdown",
        "Total Orders",
        "Total Fees",
        "Portfolio Turnover",
    ]
    cards = []
    for key in keys:
        value = statistics.get(key, "N/A")
        cards.append(
            f'<div class="stat"><div class="stat-label">{html.escape(key)}</div>'
            f'<div class="stat-value">{html.escape(str(value))}</div></div>'
        )
    return "\n".join(cards)


def orders_table(markers):
    if not markers:
        return "<p>No orders.</p>"
    rows = []
    for marker in markers:
        rows.append(
            "<tr>"
            f"<td>{html.escape(marker['date'])}</td>"
            f"<td>{html.escape(marker['side'])}</td>"
            f"<td>{html.escape(marker['symbol'])}</td>"
            f"<td>{marker['quantity']:.0f}</td>"
            f"<td>{marker['price']:.2f}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Date</th><th>Side</th><th>Symbol</th><th>Quantity</th><th>Price</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def screening_section(screening):
    items = screening.get("items") or []
    if not items:
        return ""
    summary = screening.get("summary") or {}
    selected_symbols = {str(value) for value in summary.get("selected") or []}
    counts = {
        "持续上涨": sum(1 for item in items if item.get("trend") == "持续上涨"),
        "持续下跌": sum(1 for item in items if item.get("trend") == "持续下跌"),
        "横盘震荡": sum(1 for item in items if item.get("trend") == "横盘震荡"),
        "合格": sum(1 for item in items if item.get("suitableToBuy")),
        "精选": len(selected_symbols),
    }
    rows = []
    for item in sorted(
        items,
        key=lambda row: (
            not bool(row.get("suitableToBuy")),
            -float(row.get("overallScore") or 0),
            str(row.get("symbol") or ""),
        ),
    ):
        symbol = str(item.get("symbol") or "")
        name = str(item.get("name") or "").strip()
        security_label = " ".join(value for value in (symbol, name) if value)
        suitable = bool(item.get("suitableToBuy"))
        metrics = item.get("fundamentals") or {}
        metric_text = " · ".join(
            f"{key}={float(value):.2f}"
            for key, value in sorted(metrics.items())
            if isinstance(value, (int, float))
        ) or "缺失"
        reasons = "；".join(map(str, item.get("reasons") or [])) or "-"
        risks = "；".join(map(str, item.get("risks") or [])) or "-"
        selection_risks = "；".join(map(str, item.get("selectionRisks") or []))
        selection_text = (
            "达标"
            if item.get("selectionEligible") is True
            else selection_risks or ("未达标" if item.get("selectionEligible") is False else "旧版未记录")
        )
        rows.append(
            "<tr>"
            f"<td><strong>{html.escape(security_label)}</strong></td>"
            f"<td><span class=\"trend-badge\">{html.escape(str(item.get('trend') or '-'))}</span></td>"
            f"<td>{float(item.get('technicalScore') or 0):.1f}</td>"
            f"<td>{float(item.get('fundamentalScore') or 0):.1f}</td>"
            f"<td>{float(item.get('overallScore') or 0):.1f}</td>"
            f"<td>{'是' if suitable else '否'}</td>"
            f"<td>{'Top-N' if symbol in selected_symbols else '-'}</td>"
            f"<td>{html.escape(selection_text)}</td>"
            f"<td>{html.escape(metric_text)}</td>"
            f"<td>{html.escape(reasons)}</td>"
            f"<td>{html.escape(risks)}</td>"
            "</tr>"
        )
    cards = "".join(
        f'<div class="screening-stat"><span>{html.escape(label)}</span><strong>{value}</strong></div>'
        for label, value in counts.items()
    )
    return (
        '<section class="screening-report">'
        "<h2>指数成分股技术面与基本面筛选</h2>"
        f"<p>股票池 {html.escape(str(screening.get('universeCode') or '-'))}，"
        f"评估时点 {html.escape(str(screening.get('asOfDate') or '-'))}。"
        "“适合买入”是本策略规则判断，不构成投资建议；缺失基本面不会自动通过。</p>"
        f'<div class="screening-stats">{cards}</div>'
        '<details open><summary>查看全部逐股评估</summary><div class="screening-table-wrap">'
        "<table><thead><tr><th>股票</th><th>走势</th><th>技术分</th><th>基本面分</th>"
        "<th>综合分</th><th>是否合格</th><th>精选</th><th>精选门槛</th><th>基本面快照</th><th>通过依据</th><th>风险/缺失</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div></details></section>"
    )


def report_header(data, source_path, charts, screening=None):
    configuration = data.get("algorithmConfiguration") or {}
    parameters = configuration.get("parameters") or {}
    source = Path(source_path)
    run_id = source.stem
    report_name = str(configuration.get("name") or "LEAN Backtest Report")
    symbol = str(parameters.get("ticker") or parameters.get("symbol") or "-")
    market = str(parameters.get("market") or parameters.get("venue") or "-")
    provider = str(parameters.get("providerSource") or parameters.get("source") or "-")
    start_date = str(parameters.get("start") or configuration.get("startDate") or "-")[:10]
    end_date = str(parameters.get("end") or configuration.get("endDate") or "-")[:10]
    currency = str(configuration.get("accountCurrency") or "")
    initial_cash = parameters.get("initialCash") or parameters.get("initial_cash") or parameters.get("cash")
    try:
        cash_text = f"{float(initial_cash):,.2f} {currency}".strip()
    except (TypeError, ValueError):
        cash_text = str(initial_cash or "-")
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    chart_names = [str(name) for name in charts]
    chart_chips = "".join(f'<li class="chart-chip">{html.escape(name)}</li>' for name in chart_names)

    is_screening = bool(screening)
    eyebrow = "QUANTCONNECT LEAN · 选股分析" if is_screening else "QUANTCONNECT LEAN · 回测分析"
    subject_label = "分析股票池" if is_screening else "回测标的"
    period_label = "分析区间" if is_screening else "回测区间"
    return f"""
<header class="report-header" data-report-layout="{REPORT_LAYOUT_VERSION}">
  <div class="report-heading">
    <div>
      <p class="eyebrow">{eyebrow}</p>
      <h1>{html.escape(report_name)}</h1>
      <p class="report-subtitle">运行编号 <code>{html.escape(run_id)}</code></p>
    </div>
    <div class="report-badge">已生成报告</div>
  </div>
  <dl class="report-meta">
    <div><dt>{subject_label}</dt><dd>{html.escape(str((screening or {}).get("universeCode") or symbol))}</dd></div>
    <div><dt>市场</dt><dd>{html.escape(market)}</dd></div>
    <div><dt>{period_label}</dt><dd>{html.escape(start_date)} <span>至</span> {html.escape(end_date)}</dd></div>
    <div><dt>数据源</dt><dd>{html.escape(provider)}</dd></div>
    <div><dt>初始资金</dt><dd>{html.escape(cash_text)}</dd></div>
    <div><dt>报告生成时间</dt><dd>{html.escape(generated_at)}</dd></div>
  </dl>
  <section class="chart-index" aria-labelledby="chart-index-title">
    <div class="chart-index-heading">
      <div>
        <h2 id="chart-index-title">可用图表</h2>
        <p>从 LEAN 结果中检测到 {len(chart_names)} 个图表；下方展示核心绩效图表，其余数据保留在结果文件中。</p>
      </div>
      <strong>{len(chart_names)}</strong>
    </div>
    <ul class="chart-chips">{chart_chips or '<li class="chart-chip muted-chip">无图表</li>'}</ul>
  </section>
  <details class="source-details">
    <summary>数据来源详情</summary>
    <dl>
      <div><dt>结果文件</dt><dd><code>{html.escape(source.name)}</code></dd></div>
      <div><dt>运行环境路径</dt><dd><code>{html.escape(str(source))}</code></dd></div>
    </dl>
  </details>
</header>
"""


def build_report(data, source_path):
    charts = data.get("charts") or {}
    statistics = data.get("statistics") or {}
    markers = order_markers(data)
    report_title = str((data.get("algorithmConfiguration") or {}).get("name") or "LEAN Backtest Report")

    equity_chart = get_chart(data, "Strategy Equity")
    drawdown_chart = get_chart(data, "Drawdown")
    ema_chart = get_chart(data, "EMA")
    benchmark_chart = get_chart(data, "Benchmark")
    equity_points = series_points(equity_chart, "Equity")
    benchmark_points = series_points(benchmark_chart, "Benchmark", ignore_zero_values=True)
    pnl_rows = profit_loss_rows(data)
    screening = load_screening(source_path)
    screening_chart = get_chart(data, "Screening")
    screening_chart_html = (
        make_svg(
            "Screening",
            {
                name: series_points(screening_chart, name)
                for name in ("Universe", "Rising", "Falling", "Sideways", "Qualified")
            },
        )
        if screening_chart
        else ""
    )

    body = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<meta name="report-layout" content="{REPORT_LAYOUT_VERSION}">',
        f"<title>{html.escape(report_title)}</title>",
        """
<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8fafc; color: #111827; }
main { max-width: 1160px; margin: 0 auto; padding: 28px 22px 48px; }
h1 { margin: 0 0 6px; font-size: 28px; }
h2 { margin: 0 0 14px; font-size: 18px; }
.muted { color: #64748b; margin: 0 0 22px; }
.report-header { margin-bottom: 18px; overflow: hidden; background: #fff; border: 1px solid #dbe4ef; border-radius: 14px; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06); }
.report-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; padding: 24px 26px 20px; background: linear-gradient(135deg, #f8fbff 0%, #fff 58%, #eef6ff 100%); border-bottom: 1px solid #e5edf6; }
.eyebrow { margin: 0 0 8px; color: #2563eb; font-size: 11px; font-weight: 800; letter-spacing: 0.12em; }
.report-subtitle { margin: 8px 0 0; color: #64748b; font-size: 13px; }
.report-subtitle code { color: #334155; overflow-wrap: anywhere; }
.report-badge { flex: 0 0 auto; padding: 7px 11px; color: #166534; background: #dcfce7; border: 1px solid #bbf7d0; border-radius: 999px; font-size: 12px; font-weight: 700; }
.report-meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin: 0; padding: 6px 26px 18px; }
.report-meta > div { min-width: 0; padding: 14px 16px 10px 0; }
.report-meta dt, .source-details dt { margin-bottom: 5px; color: #64748b; font-size: 11px; font-weight: 700; letter-spacing: 0.04em; }
.report-meta dd, .source-details dd { margin: 0; color: #172033; font-size: 14px; font-weight: 650; overflow-wrap: anywhere; }
.report-meta dd span { color: #94a3b8; font-weight: 400; }
.chart-index { margin: 0 26px 18px; padding: 16px 18px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; }
.chart-index-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.chart-index-heading h2 { margin: 0 0 4px; font-size: 15px; }
.chart-index-heading p { margin: 0; color: #64748b; font-size: 12px; line-height: 1.55; }
.chart-index-heading strong { display: grid; flex: 0 0 34px; height: 34px; place-items: center; color: #1d4ed8; background: #dbeafe; border-radius: 9px; font-size: 14px; }
.chart-chips { display: flex; flex-wrap: wrap; gap: 7px; margin: 13px 0 0; padding: 0; list-style: none; }
.chart-chip { max-width: 100%; padding: 5px 9px; color: #334155; background: #fff; border: 1px solid #dbe4ef; border-radius: 999px; font-size: 12px; overflow-wrap: anywhere; }
.muted-chip { color: #94a3b8; }
.source-details { margin: 0 26px 22px; color: #475569; font-size: 12px; }
.source-details summary { width: fit-content; cursor: pointer; color: #475569; font-weight: 650; }
.source-details dl { display: grid; gap: 10px; margin: 12px 0 0; padding: 13px 15px; background: #f8fafc; border-radius: 8px; }
.source-details code { white-space: normal; overflow-wrap: anywhere; }
.stats { display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 12px; margin-bottom: 18px; }
.stat, .chart-card, .orders { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }
.screening-report { margin-top: 16px; padding: 18px; background: #fff; border: 1px solid #dbe4ef; border-radius: 10px; }
.screening-report > p { color: #475569; line-height: 1.6; }
.screening-stats { display: grid; grid-template-columns: repeat(4, minmax(110px, 1fr)); gap: 10px; margin: 14px 0; }
.screening-stat { padding: 12px; background: #f8fafc; border-radius: 8px; }
.screening-stat span { display: block; color: #64748b; font-size: 12px; }
.screening-stat strong { display: block; margin-top: 5px; font-size: 20px; }
.screening-report summary { cursor: pointer; color: #1d4ed8; font-weight: 700; }
.screening-table-wrap { margin-top: 12px; overflow-x: auto; }
.screening-table-wrap table { min-width: 1320px; font-size: 12px; }
.trend-badge { white-space: nowrap; }
.stat-label { color: #64748b; font-size: 12px; margin-bottom: 6px; }
.stat-value { font-size: 18px; font-weight: 700; }
.chart-card { margin-top: 16px; }
svg { width: 100%; height: auto; display: block; }
.orders { margin-top: 16px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { padding: 10px 8px; border-bottom: 1px solid #e5e7eb; text-align: left; }
th { color: #475569; font-weight: 700; }
@media (max-width: 860px) {
  .stats { grid-template-columns: repeat(2, minmax(120px, 1fr)); }
  .screening-stats { grid-template-columns: repeat(2, minmax(110px, 1fr)); }
  .report-meta { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 560px) {
  main { padding: 14px 10px 32px; }
  .report-heading { padding: 20px 18px 16px; }
  .report-heading { display: block; }
  .report-badge { display: inline-block; margin-top: 14px; }
  .report-meta { grid-template-columns: 1fr; padding: 6px 18px 14px; }
  .chart-index, .source-details { margin-right: 18px; margin-left: 18px; }
}
@media print {
  body { background: #fff; }
  main { max-width: none; padding: 0; }
  .report-header, .stat, .chart-card, .orders { box-shadow: none; break-inside: avoid; }
}
</style>
""",
        "</head><body><main>",
        report_header(data, source_path, charts.keys(), screening=screening),
        "" if screening else f'<section class="stats">{stat_cards(statistics)}</section>',
        screening_section(screening),
        "" if screening else make_svg(
            "Strategy Equity",
            {"Equity": equity_points},
            markers=markers,
        ),
        "" if screening else make_svg(
            "EMA",
            {
                "Fast": series_points(ema_chart, "Fast"),
                "Slow": series_points(ema_chart, "Slow"),
            },
        ),
        "" if screening else make_svg(
            "Drawdown",
            {"Drawdown": series_points(drawdown_chart, "Equity Drawdown")},
            y_unit="%",
        ),
        "" if screening else make_svg(
            "Benchmark",
            {"Benchmark": benchmark_points},
        ),
        screening_chart_html,
        "" if screening else f'<section class="orders"><h2>Orders</h2>{orders_table(markers)}</section>',
        "" if screening else returns_table("Monthly Returns", period_returns(equity_points, "month")),
        "" if screening else returns_table("Yearly Returns", period_returns(equity_points, "year")),
        "" if screening else pnl_table(pnl_rows),
        "</main></body></html>",
    ]
    return "\n".join(body)


def render_report_file(input_path, output_path):
    """Render a LEAN JSON result to an HTML file using an atomic replace."""
    data = load_json(input_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(data, input_path)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(report)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return output


def main():
    parser = argparse.ArgumentParser(description="Render a LEAN backtest JSON file as a standalone HTML report.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = render_report_file(args.input, args.output)
    print(output)


if __name__ == "__main__":
    main()
