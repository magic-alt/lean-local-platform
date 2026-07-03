#!/usr/bin/env python3
import argparse
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path


COLORS = ["#2563eb", "#dc2626", "#059669", "#7c3aed", "#d97706", "#0891b2"]


def load_json(path):
    with Path(path).open() as file:
        return json.load(file)


def unix_to_date(value):
    return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime("%Y-%m-%d")


def iso_to_date(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")


def series_points(chart, series_name):
    series = (chart.get("series") or {}).get(series_name) or {}
    points = []
    for row in series.get("values", []):
        if len(row) < 2:
            continue
        timestamp = float(row[0])
        y_value = float(row[-1])
        if math.isfinite(timestamp) and math.isfinite(y_value):
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


def stat_cards(statistics):
    keys = [
        "End Equity",
        "Net Profit",
        "Sharpe Ratio",
        "Drawdown",
        "Total Orders",
        "Total Fees",
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


def build_report(data, source_path):
    charts = data.get("charts") or {}
    statistics = data.get("statistics") or {}
    markers = order_markers(data)

    equity_chart = get_chart(data, "Strategy Equity")
    drawdown_chart = get_chart(data, "Drawdown")
    ema_chart = get_chart(data, "EMA")
    benchmark_chart = get_chart(data, "Benchmark")

    body = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>LEAN Docker Demo Backtest Report</title>",
        """
<style>
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f8fafc; color: #111827; }
main { max-width: 1160px; margin: 0 auto; padding: 28px 22px 48px; }
h1 { margin: 0 0 6px; font-size: 28px; }
h2 { margin: 0 0 14px; font-size: 18px; }
.muted { color: #64748b; margin: 0 0 22px; }
.stats { display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 12px; margin-bottom: 18px; }
.stat, .chart-card, .orders { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }
.stat-label { color: #64748b; font-size: 12px; margin-bottom: 6px; }
.stat-value { font-size: 18px; font-weight: 700; }
.chart-card { margin-top: 16px; }
svg { width: 100%; height: auto; display: block; }
.orders { margin-top: 16px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th, td { padding: 10px 8px; border-bottom: 1px solid #e5e7eb; text-align: left; }
th { color: #475569; font-weight: 700; }
@media (max-width: 860px) { .stats { grid-template-columns: repeat(2, minmax(120px, 1fr)); } }
</style>
""",
        "</head><body><main>",
        "<h1>LEAN Docker Demo Backtest Report</h1>",
        f'<p class="muted">Generated from {html.escape(str(source_path))}. Charts available: {html.escape(", ".join(charts.keys()))}</p>',
        f'<section class="stats">{stat_cards(statistics)}</section>',
        make_svg(
            "Strategy Equity",
            {"Equity": series_points(equity_chart, "Equity")},
            markers=markers,
        ),
        make_svg(
            "EMA",
            {
                "Fast": series_points(ema_chart, "Fast"),
                "Slow": series_points(ema_chart, "Slow"),
            },
        ),
        make_svg(
            "Drawdown",
            {"Drawdown": series_points(drawdown_chart, "Equity Drawdown")},
            y_unit="%",
        ),
        make_svg(
            "Benchmark",
            {"Benchmark": series_points(benchmark_chart, "Benchmark")},
        ),
        f'<section class="orders"><h2>Orders</h2>{orders_table(markers)}</section>',
        "</main></body></html>",
    ]
    return "\n".join(body)


def main():
    parser = argparse.ArgumentParser(description="Render a LEAN backtest JSON file as a standalone HTML report.")
    parser.add_argument("--input", default="docker-demo/results/docker-demo-backtest.json")
    parser.add_argument("--output", default="docker-demo/results/report.html")
    args = parser.parse_args()

    data = load_json(args.input)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_report(data, args.input), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
