# API

The backend is FastAPI, mounted from `web/backend/app/main.py`. Runtime API
authentication is enabled by default. Direct clients must send the local Bearer
token from `LEAN_API_TOKEN` or the 0600 runtime token file; the frontend proxy
uses the same protected local session. Disabling authentication is permitted
only in explicitly isolated tests.

Last reviewed: 2026-07-26. The generated OpenAPI document at `GET /openapi.json` and interactive UI at `/docs` are the route-level source of truth; this file is a curated behavioral guide.

## Common Behavior

- JSON request/response by default.
- Expected domain errors return structured JSON with `detail`, `message`, `error_code`, `category`, and one authoritative `retryable`; validation failures also expose the first affected `field`.
- Missing resources return HTTP 404 with `error_code=NOT_FOUND`.
- Redis/Celery dispatch failure returns HTTP 503 with `error_code=SERVICE_UNAVAILABLE` and `retryable=true`.
- Temporary MySQL connection failure returns HTTP 503 with `error_code=DATABASE_UNAVAILABLE` and `retryable=true` after bounded connection retries.
- The primary history lists (`projects`, `backtests`, `tasks`, `reports`,
  `experiment-batches`, `paper`, `optimize`, `research`, and `data-assets`)
  return `{items, count, limit, offset}` and accept bounded `limit`/`offset`.
  During the compatibility period, `paged=false` returns the bounded legacy
  array.
- Write requests may send `Idempotency-Key`. A completed identical request is
  replayed with `Idempotent-Replayed: true`; payload drift or an in-flight
  duplicate returns 409. The Web client adds a key to every write.
- Backtest and task logs accept byte `offset` or `cursor` plus bounded `limit`;
  responses include `nextOffset`, `nextCursor`, `total`, and `hasMore`.
- `X-Trace-ID` and `X-Workflow-ID` propagate through Celery headers into LEAN
  configuration and the run-local `trace-context.json`/artifact manifest.

## Backtests

```text
GET    /api/backtests
POST   /api/backtests
POST   /api/backtests/preflight
GET    /api/backtests/{run_id}
GET    /api/backtests/{run_id}/status
GET    /api/backtests/{run_id}/result
GET    /api/backtests/{run_id}/validation
GET    /api/backtests/{run_id}/versions
POST   /api/backtests/{run_id}/cancel
GET    /api/backtests/{run_id}/logs
GET    /api/backtests/{run_id}/chart-data
GET    /api/backtests/{run_id}/artifacts/{name}
```

`GET /api/backtests/{run_id}/results` is a deprecated, OpenAPI-hidden 308
redirect to the canonical singular `/result` route. New fingerprints expose
camelCase canonical keys; the five former snake_case synonyms are isolated
under `legacyAliases` during the compatibility period.

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
POST   /api/experiment-batches/{batch_id}/restart
GET    /api/experiment-batches/{batch_id}/export.csv
```

The example catalog covers backtest, optimization and research workflows. Preview expands symbols, strategies, parameter grids, rolling windows or PIT-universe instructions and rejects a request that exceeds `maxBatchRuns`. Walk-forward expands train, validation and OOS phases; parameter selection uses validation only. Creation persists the batch and its child specifications; dispatch remains bounded by the batch window and the global scheduler lease limit. Failed-only retry and cancelled-batch restart preserve successful children and survive service restarts.

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

## A-share Technology Insights

A-share Technology Insights combine the closing daily report, six-stage Agent research, per-stock candidate signals, risk guardrails, and forecast evaluation in one workflow. The former generic multi-asset Insight workflow and its stored data are removed.

```text
GET  /api/insights/ashare-tech/capabilities
GET  /api/insights/ashare-tech/prompt-templates
POST /api/insights/ashare-tech/prompt-templates
POST /api/insights/ashare-tech/prompt-templates/{template_key}/versions
GET  /api/insights/ashare-tech/production-profile
PUT  /api/insights/ashare-tech/production-profile
POST /api/insights/ashare-tech/reports
```

Each run selects one configured Provider/model for all six stages and snapshots an immutable Prompt version. DeepSeek `deepseek-v4-flash` and `deepseek-v4-pro` use the same key. The model returns per-stock candidate signals; server-side evidence, data-quality, exposure, price-plan, and risk guardrails own the final advisory signal. Signals are not normalized into a portfolio and never enter Paper or order execution.

Environment variables:

```text
DEEPSEEK_API_KEY=...
ZHIPU_API_KEY=...
KIMI_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...

# Legacy fallback used until a production profile is published in the UI.
LEAN_INSIGHTS_LLM_PROVIDER=deepseek
# Optional provider-default overrides.
LEAN_INSIGHTS_LLM_BASE_URL=
LEAN_INSIGHTS_LLM_MODEL=
LEAN_INSIGHTS_LLM_TIMEOUT_SECONDS=60

# A-share technology daily report: hybrid_multi_agent or deterministic.
LEAN_ASHARE_TECH_AGENT_MODE=hybrid_multi_agent
# Matured 1/5/20-trading-day forecast evaluation schedule.
LEAN_ASHARE_TECH_EVALUATION_HOUR=18
LEAN_ASHARE_TECH_EVALUATION_MINUTE=45
```

Configure one or more provider keys. The model catalog exposes both `deepseek-v4-flash` and `deepseek-v4-pro`, plus the configured Zhipu, Kimi, OpenAI, and Anthropic choices. `ZAI_API_KEY` and `MOONSHOT_API_KEY` are accepted as aliases for `ZHIPU_API_KEY` and `KIMI_API_KEY`. API keys are never returned by capabilities, stored in settings, or persisted with reports.

## Reports

```text
GET    /api/reports
POST   /api/reports
GET    /api/reports/{report_id}
GET    /api/reports/{report_id}/objects
GET    /api/reports/{report_id}/objects/{object_id}
GET    /api/reports/{report_id}/file
GET    /api/reports/{report_id}/export?format=html|markdown|pdf|csv|json
```

Backtest reports are synthesized from `backtest_runs`, `backtest_results`, and `stored_objects`. They include `fingerprint`, `validation`, `experiment`, and all archived backtest artifacts when available.

Report file responses use `Cache-Control: no-store`. HTML, Markdown, PDF, CSV
and JSON exports are generated from the same canonical report payload. A
persisted `report_path` is served only when its resolved file is beneath
`RUNS_DIR` or `REPORTS_DIR`; paths outside those roots fail with
`REPORT_PATH_FORBIDDEN`.

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
GET    /api/data/quality/cross-asset
GET    /api/data/quality/reports
GET    /api/data/derived/watermarks
POST   /api/data/derived/maintenance
GET    /api/pit/universes/coverage
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
POST   /api/optimizations/preview
GET    /api/optimizations
POST   /api/optimizations
GET    /api/optimizations/{optimization_id}
POST   /api/optimizations/{optimization_id}/cancel
POST   /api/optimizations/{optimization_id}/retry-failed
POST   /api/optimizations/{optimization_id}/archive
POST   /api/optimizations/compare

GET    /api/portfolio-optimizations/candidates
POST   /api/portfolio-optimizations/preview
GET    /api/portfolio-optimizations
POST   /api/portfolio-optimizations

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
GET    /api/paper/accounts
POST   /api/paper/accounts
GET    /api/paper/accounts/candidates?projectId={project_id}
GET    /api/paper/accounts/{account_id}/overview
GET    /api/paper/accounts/{account_id}/performance
GET    /api/paper/accounts/{account_id}/audit
GET    /api/paper/accounts/{account_id}/deployments
POST   /api/paper/accounts/{account_id}/deployments
POST   /api/paper/deployments/{deployment_id}/run-now
```

Creating a deployment requires `projectId` and `sourceBacktestId`. The source run
must belong to the project, have passed execution validation, contain complete
certified data, and retain its frozen strategy snapshot. The account workflow
records immutable intents, legal transitions, fills and ledger entries, then
rebuilds projections with point-in-time Source Gate prices and exact benchmark
dates. Legacy session and replay endpoints are retired.

## A-share Technology Daily Report

```text
GET    /api/insights/ashare-tech/capabilities
GET    /api/insights/ashare-tech/prompt-templates
GET    /api/insights/ashare-tech/prompt-templates/{template_key}/versions
POST   /api/insights/ashare-tech/prompt-templates
POST   /api/insights/ashare-tech/prompt-templates/{template_key}/versions
GET    /api/insights/ashare-tech/production-profile
PUT    /api/insights/ashare-tech/production-profile
GET    /api/insights/ashare-tech/reports
POST   /api/insights/ashare-tech/reports
GET    /api/insights/ashare-tech/reports/{report_id}
DELETE /api/insights/ashare-tech/reports/{report_id}
POST   /api/insights/ashare-tech/model-diagnostics
GET    /api/insights/ashare-tech/reports/{report_id}/agent-runs
GET    /api/insights/ashare-tech/agent-runs/{run_id}
GET    /api/insights/ashare-tech/evaluations
GET    /api/insights/ashare-tech/evaluations/summary
POST   /api/insights/ashare-tech/evaluations/refresh
GET    /api/insights/ashare-tech/watchlist
POST   /api/insights/ashare-tech/watchlist/items
PATCH  /api/insights/ashare-tech/watchlist/items/{code}
DELETE /api/insights/ashare-tech/watchlist/items/{code}
POST   /api/insights/ashare-tech/watchlist/reset
```

The former `/api/ashare-tech-insights/*` namespace remains as an
OpenAPI-hidden 308 redirect during the compatibility period.

The specialized A-share report starts with a 26-stock default pool and persists
an editable add/delete/enable configuration. New symbols must pass TuShare
`stock_basic` validation, while each report stores an immutable pool snapshot. It
uses TuShare Pro for individual indicators and Eastmoney only to cross-check the
latest close. DC/THS sector indexes are
preferred; Eastmoney sector K-lines are a marked fallback. It runs at 17:30
Asia/Shanghai on weekdays and retries at 18:00 and 18:30 when the full-pool
close is incomplete. Exchange announcements and official government policy
pages are checked over the latest seven calendar days.

When a provider is configured, the default hybrid workflow runs structured
technical, PIT-fundamental, bull, bear, risk, and final-selection stages. It
stores stage status, input fingerprint, fact IDs, prompt/model versions, output,
latency and usage, but never chain-of-thought or API keys. Technical forecasts
cover 1, 5 and 20 actual trading days; the 18:45 weekday evaluator records
direction accuracy, three-class Brier score, stock/benchmark return, excess
return and Top-5 lift. Deterministic fallbacks stay visible but are excluded
from model prediction metrics. Server-side risk gates always override model
output. It also emits an auditable candidate signal for every stock with an
independent target exposure, entry/exit plan, evidence IDs, and server-side
guardrail result. Prompt templates are editable as immutable six-stage versions;
the published Provider/model/Prompt profile controls the scheduled 17:30 run.
This workspace never creates Paper signals or orders.

## Health and Observability

```text
GET /api/health
GET /api/health/dependencies
GET /api/health/database
GET /metrics
```

`/metrics` requires the API Bearer token. Prometheus supplies it through its
Docker secret credentials file.

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
