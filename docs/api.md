# API

The backend is FastAPI, mounted from `web/backend/app/main.py`. All routes are local and unauthenticated in the current personal platform version.

Last reviewed: 2026-07-21. The generated OpenAPI document at `GET /openapi.json` and interactive UI at `/docs` are the route-level source of truth; this file is a curated behavioral guide.

## Common Behavior

- JSON request/response by default.
- Expected domain errors return structured JSON with `detail`, `message`, `error_code`, `category`, and `retryable`.
- Missing resources return HTTP 404 with `error_code=NOT_FOUND`.
- Redis/Celery dispatch failure returns HTTP 503 with `error_code=SERVICE_UNAVAILABLE` and `retryable=true`.
- Temporary MySQL connection failure returns HTTP 503 with `error_code=DATABASE_UNAVAILABLE` and `retryable=true` after bounded connection retries.
- Some list endpoints return arrays directly; newer endpoints may return `{items, count, limit, offset}`.
- Backtest logs currently return the latest tail, not a cursor-based stream.

## Backtests

```text
GET    /api/backtests
POST   /api/backtests
POST   /api/backtests/preflight
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
  "projectId": "my-strategy-20260721153000",
  "parameters": {
    "benchmarkSymbol": "000300"
  }
}
```

`projectId` is required for both create and preflight requests. Missing values return 422; unknown projects return 404. The worker executes the immutable project snapshot and has no default demo-algorithm fallback. Historical runs with `project_id=null` remain readable.

For China equity, the service injects A-share trading config and blocks runs with missing benchmark or critical QA gates.

`POST /api/backtests/preflight` validates the proposed project, parameters, data scope, benchmark and quality gates without dispatching a LEAN container. Batch preview uses the same contracts before expansion.

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

## Examples and Experiment Batches

```text
GET    /api/examples
GET    /api/examples/{kind}/{key}
POST   /api/examples/{kind}/{key}/instantiate

POST   /api/experiment-batches/preview
GET    /api/experiment-batches
POST   /api/experiment-batches
GET    /api/experiment-batches/{batch_id}
POST   /api/experiment-batches/{batch_id}/cancel
POST   /api/experiment-batches/{batch_id}/retry-failed
GET    /api/experiment-batches/{batch_id}/export.csv
```

The example catalog covers backtest, optimization and research workflows. Preview expands symbols, strategies, parameter grids, rolling windows or PIT-universe instructions and rejects a request that exceeds `maxBatchRuns`. Creation persists the batch and its child specifications; dispatch remains bounded by the batch window and the global scheduler lease limit. Cancellation and retry update persisted child state and survive service restarts.

## Tasks

```text
GET    /api/tasks
GET    /api/tasks/{task_id}
GET    /api/tasks/{task_id}/logs
POST   /api/tasks/{task_id}/cancel
```

Task cancellation is centralized in `services/tasks.py`.

- `kind=backtest`: delegates to `cancel_backtest()`, revokes Celery when possible, and stops the named LEAN container.
- `kind=optimization`: revokes the optimization task, cancels the optimization row, marks non-terminal child `backtest_runs` as `cancelled`, and stops child LEAN containers with known `container_name`.
- `kind=research`: revokes the task and stops the recorded research container.
- `kind=report` and data tasks: revoke the task when a Celery id exists and persist `cancelled`.
- `kind=insight`: revokes the model task and marks the linked insight report `cancelled`.

## Insights

Insights create structured, model-assisted research reports from LEAN-owned daily market data. They support DeepSeek, Zhipu, Kimi, OpenAI, and Anthropic, and remain opt-in until a supported API key is configured for both API and worker.

```text
GET    /api/insights/capabilities
GET    /api/insights
POST   /api/insights
GET    /api/insights/{report_id}
DELETE /api/insights/{report_id}
POST   /api/insights/{report_id}/paper-signals
```

`POST /api/insights` accepts `equity`, `crypto`, `crypto_future`, and `future`, currently at daily resolution. The optional `backtestRunId` must be a successful run for the same symbol, asset class, and venue. The response is HTTP 202 with the report and task identifiers.

The model returns a candidate signal, but server-side guardrails own the final signal. Missing data, unsupported spot short exposure, invalid price plans, or missing evidence make the signal non-actionable. Nothing is sent to Paper automatically. The paper handoff endpoint is an explicit user action and currently supports equity and spot crypto sessions only.

Environment variables:

```text
DEEPSEEK_API_KEY=...
ZHIPU_API_KEY=...
KIMI_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...

# Optional provider selection; otherwise the first configured key in the listed order is used.
LEAN_INSIGHTS_LLM_PROVIDER=deepseek
# Optional provider-default overrides.
LEAN_INSIGHTS_LLM_BASE_URL=
LEAN_INSIGHTS_LLM_MODEL=
LEAN_INSIGHTS_LLM_TIMEOUT_SECONDS=60
```

Configure only the key for the provider you want to use. Provider defaults are `deepseek-v4-flash`, `glm-5.2`, `kimi-k2.6`, `gpt-5-mini`, and `claude-sonnet-4-6`, respectively. `ZAI_API_KEY` and `MOONSHOT_API_KEY` are accepted as aliases for `ZHIPU_API_KEY` and `KIMI_API_KEY`. API keys are never returned by capabilities, stored in settings, or persisted with the report.

## Reports

```text
GET    /api/reports
POST   /api/reports
GET    /api/reports/{report_id}
GET    /api/reports/{report_id}/objects
GET    /api/reports/{report_id}/objects/{object_id}
GET    /api/reports/{report_id}/file
GET    /api/reports/{report_id}/export?format=html|markdown
```

Backtest reports are synthesized from `backtest_runs`, `backtest_results`, and `stored_objects`. They include `fingerprint`, `validation`, `experiment`, and all archived backtest artifacts when available.

Report file responses use `Cache-Control: no-store`. HTML and Markdown export are implemented; PDF, CSV and JSON report exports are not yet supported.

## Data

```text
GET    /api/symbols
GET    /api/securities/search
GET    /api/data-assets
GET    /api/data/providers
GET    /api/data/providers/availability
GET    /api/data/catalog
GET    /api/data/dataset-preview/{dataset}
GET    /api/data/on-demand/storage-targets
POST   /api/data/on-demand/downloads
GET    /api/asset-classes
GET    /api/data/files
GET    /api/data/query
POST   /api/data/fetch
POST   /api/data/fetch-batch
GET    /api/data/import-csv/template
POST   /api/data/import-csv
POST   /api/data/fetch-alpha-vantage
POST   /api/data/free/ashare/daily/import-sample
POST   /api/data/intraday/import
```

Dataset preview is data-aware for stocks, calendars, indexes, futures and options. The on-demand routes only accept datasets marked `sync_policy=on_demand` and an approved selectable storage target. CSV clients should download the matching template before import.

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

GET    /api/data/catalog
GET    /api/data/sync-runs
POST   /api/data/sync-runs
GET    /api/data/sync-runs/{run_id}
GET    /api/data/sync-runs/{run_id}/validation
POST   /api/data/sync-runs/{run_id}/cancel
POST   /api/data/sync-runs/{run_id}/resume
```

The Data page full-update workflow probes the configured TuShare Pro token at
runtime. The local entitlement hint is 5,000 points, while successful endpoint
probes remain authoritative because some datasets require separate grants. The
sync boundary is low-frequency research data; real-time, minute, Tick, and news
streams are excluded. The first successful one-click build is full; subsequent
one-click runs are incremental. Runs are idempotent, cancellable, and resumable
from per-dataset checkpoints. Only the 10 bulk datasets documented in
`docs/data_pipeline.md` participate; other catalog entries are on-demand.

## Research, Optimization, Factors

```text
GET    /api/optimize
POST   /api/optimize
GET    /api/optimize/{optimization_id}

GET    /api/research
POST   /api/research
GET    /api/research/{session_id}
POST   /api/research/{session_id}/stop
POST   /api/research/{session_id}/restart
GET    /api/research/{session_id}/logs
DELETE /api/research/{session_id}

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
GET    /api/paper/candidates?projectId={project_id}
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
GET    /api/paper/{session_id}/runs
```

Creating a LEAN Paper session requires `projectId` and `sourceBacktestId`. The source run must belong to the project, have passed execution validation, contain complete data, and retain its strategy snapshot. Each A-share trading day runs that frozen project through the standard LEAN backtest worker and reconciles historical order fingerprints before the Paper ledger advances. Legacy replay sessions remain readable but cannot be resumed.

## Insights and A-share Technology Daily Report

```text
GET  /api/insights/capabilities
GET  /api/insights
POST /api/insights
GET  /api/insights/{report_id}
DELETE /api/insights/{report_id}
POST /api/insights/{report_id}/paper-signals

GET    /api/ashare-tech-insights/capabilities
GET    /api/ashare-tech-insights/reports
POST   /api/ashare-tech-insights/reports
GET    /api/ashare-tech-insights/reports/{report_id}
DELETE /api/ashare-tech-insights/reports/{report_id}
GET    /api/ashare-tech-insights/watchlist
POST   /api/ashare-tech-insights/watchlist/items
PATCH  /api/ashare-tech-insights/watchlist/items/{code}
DELETE /api/ashare-tech-insights/watchlist/items/{code}
POST   /api/ashare-tech-insights/watchlist/reset
```

The specialized A-share report starts with a 26-stock default pool and persists
an editable add/delete/enable configuration. New symbols must pass TuShare
`stock_basic` validation, while each report stores an immutable pool snapshot. It
uses TuShare Pro for individual indicators and Eastmoney only to cross-check the
latest close. DC/THS sector indexes are
preferred; Eastmoney sector K-lines are a marked fallback. It runs at 17:30
Asia/Shanghai on weekdays and retries at 18:00 and 18:30 when the full-pool
close is incomplete. Exchange announcements and official government policy
pages are checked over the latest seven calendar days. The rule engine owns all
metrics, classifications and risk gates; an optional LLM may only add prose
that cites report fact IDs. This workspace never creates Paper signals or orders.

## Health and Observability

```text
GET /api/health
GET /api/health/dependencies
GET /api/health/database
GET /metrics
```

## Help Articles

```text
GET /api/help/articles
GET /api/help/articles/{slug}
```

Help articles are registered by `docs/help/catalog.json` and power the searchable in-app Docs page. Catalog sources are restricted to Markdown under `docs/`; slugs must be lowercase and URL-safe. List items retain `slug`, `title`, `order` and `snippet`, and also expose `group`, `category`, `summary` and `status` so the frontend can distinguish tutorials, references and historical snapshots.

Search matches titles, summaries, headings, body text, configuration keys and API paths. The frontend route `/#/docs/{slug}?section={heading}` provides reload-safe article and section deep links. Screenshot assets are served by an internal allowlisted help route and only accept PNG, JPEG and WebP under `docs/help/assets`.

`docs/help/api-reference.md` is generated from OpenAPI and checked with:

```bash
web/backend/.venv/bin/python scripts/generate_help_api_reference.py --check
```

## Object Store

```text
GET    /api/object-store
GET    /api/object-store/_stored-objects
POST   /api/object-store/{key}
GET    /api/object-store/{key}
DELETE /api/object-store/{key}
```

## Error Codes

Current API errors keep the historical `detail` field and add structured fields:

```json
{
  "detail": "Task not found.",
  "message": "Task not found.",
  "error_code": "NOT_FOUND",
  "category": "not_found",
  "retryable": false
}
```

Currently emitted generic codes:

```text
BAD_REQUEST
UNAUTHORIZED
FORBIDDEN
NOT_FOUND
CONFLICT
VALIDATION_ERROR
RATE_LIMITED
SERVICE_UNAVAILABLE
DATABASE_UNAVAILABLE
INTERNAL_ERROR
HTTP_ERROR
LEAN_WEB_ERROR
```

Recommended domain-specific P1/P2 codes:

```text
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
