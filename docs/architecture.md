# Architecture

Last reviewed: 2026-07-25.

This is a local QuantConnect/LEAN research, backtesting and paper-replay platform. LEAN is the only production backtest engine. MySQL is the runtime fact store; SQLite is allowed only as an isolated test backend.

## Current Level

The main chains are implemented. The 2026-07-25 local evidence accepts Level 3,
Level 3+, the 21-day Paper v2 baseline, and the six-checkpoint interruption
chain. Overall operational release remains not ready because production-scale
restore, credential and supply-chain gates are separate. Historical failures
remain preserved:

- Web -> FastAPI -> Celery -> LEAN Docker -> raw artifacts -> parser -> report/UI is operational.
- A-share preflight checks data coverage, benchmark coverage, QA gates and trading-rule metadata before dispatch.
- Strategy, dataset and experiment versions plus run fingerprints are persisted for reproducibility.
- Backtests, optimization and research expose an example catalog and database-backed experiment batches.
- Data synchronization is resumable and auditable through sync runs, checkpoints, heartbeats, watermarks, validation results and quarantined rows.
- Paper Account adds isolated opening ledgers, frozen deployments, idempotent
  daily cycles and rebuildable projections on top of the existing Paper v2
  intent/order/fill/ledger chain. Legacy sessions remain separate.

## Component Map

```text
Browser
  -> React/Vite frontend
       pages, API client, charts, Docs, dataset previews, batch workbench
  -> FastAPI
       API schemas and request validation
  -> Domain services and repositories
       backtests, data sync, experiments, reports, paper, research
  -> MySQL runtime fact store
       metadata, canonical market data, PIT data, results, stored objects
  -> Celery / Redis
       default, data, data-demand and backtest queues; beat coordination
  -> restricted lean-runner
       structure-only jobs, pinned images and allowlisted mount roots
  -> LEAN / Research Docker containers
       digest allowlists, bounded resources, reduced mounts and isolated runs

Derived and optional stores
  MySQL -> LEAN Data cache
  MySQL -> Parquet -> DuckDB
  MySQL -> optional ClickHouse mirror
  run workspace <-> stored_objects archive
```

## Directory Responsibilities

```text
web/frontend/src/
  React UI, API types, charts, batch workflows, previews and searchable docs.

web/backend/app/api/
  FastAPI route layer. HTTP validation and delegation only.

web/backend/app/services/
  Business logic for backtests, validation, data sync, batches, reports and paper.

web/backend/app/repositories/
  Database persistence helpers.

web/backend/app/runners/ and web/backend/app/lean_engine/
  LEAN configuration, isolated workspaces and Docker execution.

web/backend/app/reporting/
  Canonical HTML report renderer shared by live runs and report regeneration.

web/backend/app/tasks/
  Celery task definitions, recovery and batch coordination.

web/backend/app/migrations/versions/
  Ordered MySQL schema migrations. The current latest migration is 0032; every
  migration has a compensating or explicit irreversible recovery policy in
  `migrations/rollback_policy.json`. Applied SQL files remain checksum-immutable.

web/backend/tests/
  Unit and opt-in Docker/LEAN integration tests.

web/runtime/
  Rebuildable or archived runtime cache: projects, runs, reports and uploads.

LEAN_DATA_DIR (default: workspace parent/Data)
  LEAN execution cache and derived Parquet datasets; not the metadata fact store.

docs/help/
  Articles served by the in-app Docs page.
```

## Main Backtest Chain

```text
Project/template selection (projectId required)
  -> POST /api/backtests/preflight
  -> POST /api/backtests
  -> validate persisted source certification, data, benchmark, QA and reference gates
  -> persist task, run and version metadata
  -> acquire database scheduler lease
  -> Celery run_backtest_task -> repeat the fail-closed gates
  -> propagate trace/workflow context to the restricted runner and LEAN
  -> prepare isolated web/runtime/runs/<run_id>
  -> restore or rebuild required LEAN cache from MySQL/object archive
  -> run pinned LEAN Docker image
  -> preserve stdout, result JSON, summary and order events
  -> parse metrics/charts and create artifact manifest
  -> archive artifacts in stored_objects/stored_object_chunks
  -> persist result, fingerprint, validation and experiment snapshots
  -> expose result, logs, objects, structured report and export APIs
```

## Paper Account Chain

```text
Celery Beat (60-second coordinator)
  -> due active deployments for active accounts
  -> exchange calendar and certified data/QA/PIT/reference/benchmark gates
  -> unique deployment + trading-date execution cycle and account checkpoint
  -> global LEAN scheduler lease and restricted runner
  -> LEAN close-derived signal evidence
  -> existing immutable intent + 13-state transition + constraint pipeline
  -> certified next-session matching
  -> immutable fill + shared ledger
  -> six digest-protected checkpoints
  -> rebuildable account/position projection and daily report
  -> durable notification outbox
```

`paper_accounts` never stores mutable current cash or holdings as facts.
`paper_account_projections` and position/daily projections are caches rebuilt
from account-tagged ledger entries, fills and certified prices. Each account has
an independent shadow v2 session solely to reuse the existing LEAN and order
pipeline; it is not a second ledger. A deployment freezes source Backtest,
project snapshot, strategy, dataset, universe, parameters and risk version.
Changing execution inputs creates a new deployment version.

The v1 production acceptance scope is China A-share daily data in
`Asia/Shanghai`. Trading day T closes and passes certification before the
strategy runs. Signals become orders for the next certified session; same-close
matching is prohibited. A no-signal cycle succeeds with an observed
`no_signal` record. Market, QA, benchmark or reference gaps cause
`waiting_data`, bounded retry, or a structured terminal failure without ledger
mutation.

## Experiment Batch Chain

```text
Example or batch form
  -> POST /api/experiment-batches/preview
  -> validate expansion against maxBatchRuns
  -> POST /api/experiment-batches
  -> persist batch and child specifications
  -> dispatch a bounded window of child work
  -> standard backtest / optimization / research service
  -> reconcile terminal children in a periodic task
  -> aggregate progress and metrics
  -> cancel, retry failed children, restart cancelled work or export CSV
```

Supported batch shapes include independent symbol/strategy matrices, multi-strategy runs, parameter grids, rolling windows, point-in-time universe portfolios, walk-forward optimization and research batches. Walk-forward folds isolate train, validation and OOS; only validation selects parameters. A batch does not bypass the global LEAN scheduler lease limit.

The feature-gated Paper v2 remediation path treats LEAN order output as immutable
intents rather than final portfolio facts. It records accepted fills as
append-only opening-balance, principal, commission and position ledger entries;
cash and positions are reconstructed read models. This path remains unapproved
until the documented production-like 21-day and interruption-recovery evidence
is complete.

## Data Synchronization Chain

```text
TuShare Pro
  -> capability/policy check
  -> concurrent bounded fetch and rate limiting
  -> normalize, validate, deduplicate and quarantine
  -> batched canonical MySQL writes
  -> persist manifest, checkpoint, watermark and validation
  -> update optional ClickHouse mirror / derived cache work
```

The 10 one-click datasets are listed in [data_pipeline.md](data_pipeline.md). Other catalog entries are on-demand. Canonical data is not duplicated as per-row JSON; non-canonical responses use content-addressed gzip batch archives.

## Storage Ownership

- MySQL: authoritative runtime metadata, canonical data, PIT membership, task state, reports and binary archives.
- `stored_objects` / `stored_object_chunks`: durable artifact and cache archive inside MySQL.
- `web/runtime`: local execution/debug cache; safe to prune only after verifying required objects are archived.
- `Data/`: LEAN-readable cache generated or restored from authoritative data.
- Parquet/DuckDB: rebuildable analytical layer.
- ClickHouse: optional mirror with an independent health/watermark boundary; never the source of truth.
- SQLite: tests only. Do not reintroduce it as a local runtime fallback.

## Failure and Recovery Boundaries

- MySQL connection establishment retries transient 1040/2003/2006/2013 errors a bounded number of times.
- API requests return HTTP 503 with `DATABASE_UNAVAILABLE` while MySQL is temporarily unavailable; periodic Celery coordinators retry.
- Sync runs persist heartbeat and checkpoint state. Recovery only takes over orphaned work and replays an idempotent small batch at most.
- Experiment batches are reconciled from database child state after restarts.
- Report and dataset preview failures are contained to their feature area and must not blank the whole application.

## Architectural Rules

- LEAN remains the only production backtest executor.
- MySQL remains the only runtime fact store; derived stores must be rebuildable.
- API routes delegate orchestration to services/runners.
- Every run uses an isolated workspace and preserves raw artifacts before parsing.
- Trusted runs persist fingerprint, validation, experiment and normalized version links.
- A production source is trusted only after persisted batch lineage, QA and MySQL/Parquet/DuckDB/file-hash consistency certification; provider names alone grant no trust.
- A-share runs require real benchmark data and cannot use a constant fallback.
- Cancellation flows through services so Celery state, containers and database state remain consistent.
- Provider data must retain audit hashes and source/batch metadata without duplicating canonical payloads.
- Historical problem records under `docs/history/`, including `platform-audit-2026-07.md`, are append-only evidence.
