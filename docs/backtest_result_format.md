# Backtest Result Format

This document describes the output layers from LEAN raw files to parsed API/UI payloads.

## Raw LEAN Artifacts

Typical files in `web/runtime/runs/<run_id>/results`:

```text
<run_id>.json
<run_id>-summary.json
<run_id>-order-events.json
<run_id>-log.txt
log.txt
report.html
artifact-manifest.json
data-monitor-report-*.json
succeeded-data-requests-*.txt
failed-data-requests-*.txt
```

Inputs in the run workspace:

```text
config.json
ashare_execution.py
ashare_trade_status.json
```

All important raw artifacts are archived to `stored_objects` under namespace `backtest-results`.

## Parsed Result Row

Parsed results are stored in `backtest_results`:

```text
id
job_id
summary_metrics_json
equity_curve_json
drawdown_curve_json
orders_json
trades_json
holdings_json
statistics_json
performance_json
raw_result_path
raw_result_object_id
summary_object_id
created_at
```

`row_to_dict()` exposes JSON columns as public keys such as `summary_metrics`, `equity_curve`, and `performance`.

## Parser Entry Points

- `parse_result_payload(result_json, summary_json, run)`
- `performance_analytics(statistics, chart_data, order_events, data)`
- `persist_result(job_id, result_json, summary_json, run)`
- `extract_chart_data()` and `extract_statistics()` in `lean.py`

## API Payload

`GET /api/backtests/<run_id>/result` returns:

```json
{
  "job": {},
  "result": {
    "summary_metrics": {},
    "statistics": {},
    "performance": {},
    "equity_curve": [],
    "drawdown_curve": [],
    "orders": [],
    "trades": [],
    "holdings": [],
    "raw_result_path": "...",
    "raw_result_object_id": "...",
    "summary_object_id": "..."
  }
}
```

`GET /api/backtests/<run_id>/validation` returns:

```json
{
  "job_id": "...",
  "validation": {},
  "experiment": {},
  "fingerprint": {}
}
```

## Metrics

The parser preserves LEAN statistics and computes or exposes:

- total return through equity curve.
- annual return from LEAN statistics.
- drawdown from LEAN chart/statistics.
- Sharpe Ratio from LEAN statistics.
- Sortino Ratio from LEAN statistics.
- Calmar Ratio computed when annual return and drawdown exist.
- monthly returns.
- yearly returns.
- strategy return.
- benchmark return.
- excess return.
- computed alpha and beta from aligned chart returns.
- trade PnL pairs.
- trade PnL summary.
- single trade returns.
- industry exposure when security metadata exists.

## Orders and Trades

Raw order events are normalized by `_filled_events()`. Trade pairs are reconstructed FIFO by `_trade_pairs()`:

```json
{
  "symbol": "600519",
  "entry_time": "...",
  "exit_time": "...",
  "quantity": 100,
  "entry_price": 100.0,
  "exit_price": 105.0,
  "gross_pnl": 500.0,
  "fees": 12.0,
  "net_pnl": 488.0,
  "return": 0.0488,
  "holding_days": 5
}
```

Known limitation: trade reconstruction depends on available LEAN order event fields and is not yet a broker-grade execution ledger.

## Holdings

Holdings are taken from LEAN result fields when present. If LEAN output shape changes or holdings are missing, the parser keeps an empty list rather than failing the whole result.

## Validation Snapshot

P1 stores `validation` and `experiment` inside `performance` as a result-time snapshot. This keeps trust metadata attached to the parsed result even if `backtest_runs` changes later.

