# API

The backend is FastAPI, mounted from `web/backend/app/main.py`. All routes are local and unauthenticated in the current personal platform version.

## Common Behavior

- JSON request/response by default.
- Expected domain errors generally return HTTP 400 with `detail`.
- Missing resources return HTTP 404.
- Redis/Celery dispatch failure returns HTTP 503.
- Some list endpoints return arrays directly; newer endpoints may return `{items, count, limit, offset}`.
- Backtest logs currently return the latest tail, not a cursor-based stream.

## Backtests

```text
GET    /api/backtests
POST   /api/backtests
GET    /api/backtests/{run_id}
GET    /api/backtests/{run_id}/status
GET    /api/backtests/{run_id}/result
GET    /api/backtests/{run_id}/results
GET    /api/backtests/{run_id}/validation
GET    /api/backtests/{run_id}/versions
POST   /api/backtests/{run_id}/cancel
GET    /api/backtests/{run_id}/logs
GET    /api/backtests/{run_id}/chart-data
GET    /api/backtests/{run_id}/artifacts/{name}
```

`POST /api/backtests` accepts:

```json
{
  "symbol": "600519",
  "assetClass": "equity",
  "market": "china",
  "venue": "china",
  "resolution": "daily",
  "dataType": "trade",
  "start": "2024-01-02",
  "end": "2024-01-04",
  "cash": 100000,
  "dockerImage": "quantconnect/lean:latest",
  "projectId": null,
  "parameters": {
    "benchmarkSymbol": "000300"
  }
}
```

For China equity, the service injects A-share trading config and blocks runs with missing benchmark or critical QA gates.

`GET /api/backtests/{run_id}/versions` returns the normalized version records linked to a run:

```json
{
  "job_id": "...",
  "experiment": {},
  "strategyVersion": {},
  "datasetVersion": {}
}
```

## Strategies and Projects

```text
GET    /api/strategies/templates
GET    /api/strategies
POST   /api/strategies
GET    /api/strategies/{strategy_id}
PUT    /api/strategies/{strategy_id}
DELETE /api/strategies/{strategy_id}

GET    /api/projects
POST   /api/projects
GET    /api/projects/{project_id}
DELETE /api/projects/{project_id}
GET    /api/projects/{project_id}/files
GET    /api/projects/{project_id}/file
PUT    /api/projects/{project_id}/file
```

## Tasks

```text
GET    /api/tasks
GET    /api/tasks/{task_id}
GET    /api/tasks/{task_id}/logs
POST   /api/tasks/{task_id}/cancel
```

Backtest task cancellation delegates to `cancel_backtest()` when `kind=backtest`.

## Reports

```text
GET    /api/reports
POST   /api/reports
GET    /api/reports/{report_id}
GET    /api/reports/{report_id}/file
```

Backtest reports are synthesized from `backtest_runs`, `backtest_results`, and `stored_objects`. They include `fingerprint`, `validation`, `experiment`, and all archived backtest artifacts when available.

## Data

```text
GET    /api/symbols
GET    /api/securities/search
GET    /api/data-assets
GET    /api/data/providers
GET    /api/data/providers/availability
GET    /api/asset-classes
GET    /api/data/files
GET    /api/data/query
POST   /api/data/fetch
POST   /api/data/fetch-batch
POST   /api/data/import-csv
POST   /api/data/fetch-alpha-vantage
POST   /api/data/free/ashare/daily/import-sample
POST   /api/data/intraday/import
```

Parquet and quality routes:

```text
POST   /api/data/parquet/export
GET    /api/data/parquet/datasets
POST   /api/data/parquet/rebuild
POST   /api/data/parquet/consistency
POST   /api/data/quality/ashare/daily/compare
POST   /api/data/quality/ashare/daily/compare-batch
GET    /api/data/quality/reports
```

## A-Share Reference Data

```text
GET    /api/data/batches
GET    /api/data/batches/{batch_id}
GET    /api/data/qa/{batch_id}
POST   /api/ashare/securities/import
POST   /api/ashare/tushare/securities/import
POST   /api/ashare/tushare/trade-calendar/import
POST   /api/ashare/trade-status/import
POST   /api/ashare/adjustment-factors/import
GET    /api/ashare/adjustment-factors/{symbol}
POST   /api/ashare/corporate-actions/import
GET    /api/ashare/corporate-actions/{symbol}
GET    /api/ashare/reference-data/coverage
GET    /api/ashare/universe/{universe_code}
GET    /api/ashare/universe/{universe_code}/tradable
GET    /api/ashare/securities/{symbol}/status
```

## Research, Optimization, Factors

```text
GET    /api/optimize
POST   /api/optimize
GET    /api/optimize/{optimization_id}

GET    /api/research
POST   /api/research
GET    /api/research/{session_id}
POST   /api/research/{session_id}/stop

GET    /api/factors/engines
POST   /api/factors/values
POST   /api/factors/matrix
POST   /api/factors/evaluate
POST   /api/factors/evaluate-batch
GET    /api/factors/evaluations
```

These are useful research APIs but are not yet the core Level 3 acceptance chain.

## Paper Trading

```text
GET    /api/paper
POST   /api/paper
POST   /api/paper/{session_id}/status
GET    /api/paper/{session_id}
GET    /api/paper/{session_id}/signals
POST   /api/paper/{session_id}/signals
GET    /api/paper/{session_id}/orders
GET    /api/paper/{session_id}/positions
GET    /api/paper/{session_id}/snapshots
GET    /api/paper/{session_id}/reports
GET    /api/paper/{session_id}/reports/{trade_date}
POST   /api/paper/{session_id}/run-day
POST   /api/paper/{session_id}/replay
```

Paper trading is P3-oriented. It must stay isolated from backtest execution until consistency validation is complete.

## Health and Observability

```text
GET /api/health
GET /api/health/dependencies
GET /api/health/database
GET /metrics
```

## Object Store

```text
GET    /api/object-store
GET    /api/object-store/_stored-objects
POST   /api/object-store/{key}
GET    /api/object-store/{key}
DELETE /api/object-store/{key}
```

## Error Code Roadmap

Current responses mostly use text. Recommended formal codes:

```text
VALIDATION_ERROR
DATA_MISSING
DATA_QA_BLOCKED
BENCHMARK_MISSING
DOCKER_NOT_FOUND
DOCKER_UNAVAILABLE
LEAN_TIMEOUT
LEAN_RESULT_MISSING
TASK_CANCELLED
REDIS_UNAVAILABLE
RESOURCE_NOT_FOUND
```

## Pagination and Log Cursor Roadmap

Current state:

- Some list endpoints support `limit` and `offset`.
- Backtest and task logs return a bounded tail string.

Recommended P2/P3 change:

```text
GET /api/backtests/{id}/logs?cursor=<byte_offset>&limit=65536
-> {logs, nextCursor, eof}
```
