# Architecture

This platform is a local QuantConnect/LEAN based research and backtesting system. LEAN is the only production backtest engine. Other engines, if ever added, must stay outside the production chain as research comparison tools.

## Current Level

Current implementation is between Level 3 and early Level 4:

- Level 3 main chain is available: Web -> Backend -> Celery task -> LEAN Docker -> raw artifacts -> parser -> UI.
- P0 has hardened the LEAN run chain with artifact manifests and raw artifact archiving.
- P1 has added trusted backtest validation metadata for A-share rules, data coverage, benchmark coverage, QA gates, experiment fingerprint, and UI visibility.
- P1 also has database-backed scheduler leases for `maxConcurrentJobs` and version rows for strategy, dataset, and experiment records.
- P2/P3 features exist only partially. Optimization, factors, paper replay, convertible bonds, futures, ClickHouse, Prometheus, and Grafana have code or infrastructure, but they are not yet the primary acceptance chain.

## Module Map

```text
Browser
  -> web/frontend/src
      App.tsx, api.ts, components.tsx
  -> FastAPI backend
      web/backend/app/main.py
      web/backend/app/api/*
  -> Services
      backtest_service.py
      backtest_validation.py
      result_service.py
      strategies.py
      scheduler.py, experiments.py
      data.py, ashare_repository.py, lean_cache.py
  -> Task layer
      tasks/worker.py
      tasks/celery_app.py
      Redis broker
  -> Runner layer
      runners/lean_runner.py
      runners/docker_runner.py
      lean.py config/mount helpers
  -> LEAN Docker container
      quantconnect/lean:latest by default
  -> Storage
      MySQL or SQLite via db.py
      stored_objects/stored_object_chunks
      web/runtime/runs/<run_id>
      Data/ LEAN cache
      parquet datasets
```

## Directory Responsibilities

```text
web/frontend/
  React/Vite UI. Owns pages, API client types, charts, status and validation display.

web/backend/app/api/
  FastAPI route layer. Routes should validate HTTP shape and delegate to services.

web/backend/app/services/
  Business logic. Backtest creation, validation, result parsing, data import, A-share rules, object storage.

web/backend/app/runners/
  Execution adapters. LeanRunner prepares workspaces and DockerRunner runs/stops containers.

web/backend/app/tasks/
  Celery tasks for async backtests, data fetch, optimization, reports.

web/backend/app/repositories/
  Database persistence helpers for backtests and results.

web/backend/app/domain/
  Shared domain constants and small domain helpers such as backtest status normalization.

web/backend/tests/
  Unit and integration tests. Docker/LEAN tests are gated by RUN_LEAN_DOCKER_INTEGRATION=1.

web/runtime/
  Runtime state: runs, projects, uploads, reports, object-store, local SQLite if used.

Data/
  LEAN data cache. Mounted read-only into LEAN containers.

scripts/
  Data import, migration, comparison, and replay scripts.

docs/
  Architecture and operating documentation.
```

## Main Backtest Chain

```text
Strategy selection or project upload
  -> parameter form
  -> POST /api/backtests
  -> create_backtest_job()
  -> validate_backtest_parameters()
  -> A-share preflight, QA gate, benchmark gate when market=china
  -> create task and backtest_runs row
  -> acquire scheduler lease before LEAN execution
  -> Celery run_backtest_task()
  -> LeanRunner.run_backtest()
  -> create web/runtime/runs/<run_id>
  -> write config.json and optional A-share helper files
  -> docker run quantconnect/lean
  -> tee Docker/LEAN console output to results/stdout.log and task log
  -> write raw LEAN results
  -> write artifact-manifest.json
  -> parse result JSON and order events
  -> archive raw artifacts into stored_objects
  -> save parsed backtest_results row
  -> GET /api/backtests/<id>/result, /validation, /logs, /chart-data
  -> UI details, charts, validation tab, reports
```

## Runtime Dependencies

- Python backend: FastAPI, Celery, Redis client, PyMySQL, Pandas-like data tooling as listed in `web/backend/requirements.txt`.
- Frontend: Vite, React, Ant Design, ECharts.
- Docker: required for LEAN backtest execution.
- Redis: required for async task dispatch.
- MySQL: default database via `LEAN_DATABASE_URL`; SQLite is still supported in tests and local fallback paths.
- Data folder: `LEAN_DATA_DIR`, defaulting to `../Data` relative to the platform workspace.
- Optional services: ClickHouse, Prometheus, Grafana.

## Architectural Rules

- LEAN remains the only production backtest executor.
- API routes should not grow Docker or filesystem orchestration logic; that belongs in services/runners.
- Each run must have an isolated `web/runtime/runs/<run_id>` workspace.
- Raw outputs must be preserved before and after parsing.
- Task cancellation must go through the service layer so Celery revoke, LEAN container stop, child run status, and related task state stay consistent.
- API errors must retain `detail` for compatibility and also expose `error_code`, `category`, and `retryable` for UI handling.
- Every trusted backtest should carry `fingerprint`, `validation`, and `experiment` metadata.
- Every trusted backtest should persist linked `strategy_versions`, `dataset_versions`, and `experiments` rows.
- A-share backtests must use explicit benchmark data and must not fall back to constant benchmark curves.
