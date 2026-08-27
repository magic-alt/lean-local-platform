# Current State

Last reviewed: 2026-08-27. Baseline: `e84383243627340ab18f2fd5452ada99f5889628`.

This document is the single current architecture and support snapshot. Dated audits and documents under `docs/history/` are evidence for their original baseline, not current operating instructions.

## Runtime facts

| Concern | Current authority |
| --- | --- |
| Market time-series facts | Parquet under `$LEAN_DATA_DIR` |
| Control plane | PostgreSQL 17 (`lean_platform`) |
| Task broker | RabbitMQ 4.3.5, vhost `lean` |
| Celery result metadata | PostgreSQL `lean_celery`; disposable, not a business authority |
| MLflow metadata | PostgreSQL `lean_mlflow` |
| Parquet query engine | DuckDB |
| Backtest/execution validation | Platform and LEAN |
| Research execution | External `qlib-platform` |
| Optional analytical mirror | ClickHouse; disabled by default and never authoritative |

PostgreSQL must not contain market quote time series. RabbitMQ transports work and is not a source of business truth. SQLite is allowed only in isolated tests.

## Research and execution boundary

```text
platform: immutable DataRelease publication
  -> qlib-platform: features, factors, training, selection, walk-forward research
  -> Artifact Contract v2 + content-addressed TARGET_PORTFOLIO
  -> platform: fail-closed import, LEAN validation, backtest, Paper, OMS and execution
```

The boundary preserves `artifactId`, `DataReleaseId`, target-weight SHA-256, lineage and lifecycle state. Platform must not silently repair an invalid imported artifact or grow a second model-training system.

## Deployment matrix

| Mode | Manager | Intended use |
| --- | --- | --- |
| Docker | Compose through `platformctl` | Normal local and production-like deployment |
| Windows Native Local | User processes | Dockerless development; default for `start_windows_native.ps1` |
| Windows Native SCM | Windows services | Explicit certified deployment with `LEAN_NATIVE_MANAGER=windows-scm` or production mode |

Use `python scripts/platformctl.py --mode docker --profile full start` for Docker. The dependency order is PostgreSQL -> database initialization -> migration -> API/workers, with RabbitMQ healthy before task consumers start.

## Supported boundaries

- LEAN is the authoritative execution validator.
- P9/live activation is disabled. No production transition or broker-write API is part of the current release.
- One-click datasets are defined by `BULK_DATASET_KEYS`; documentation must not hand-maintain a numeric claim without checking that constant.
- Backtest containers accept only configured digest-pinned allowlisted images. API examples should omit `dockerImage` unless an approved digest is required explicitly.
- `/openapi.json` and generated `docs/help/api-reference.md` own the current endpoint list. Narrative guides must not hard-code route counts.

## Recovery set

A complete recovery set contains the PostgreSQL `lean_platform` and `lean_mlflow` logical backups, the complete `$LEAN_DATA_DIR` lake/object store, and auditable project/strategy sources. `lean_celery` is reconstructed by reconciliation. RabbitMQ queues are transport state, not the recovery authority.

See [Deployment](deployment.md), [Research boundary](help/research.md), [Data pipeline](data_pipeline.md), and [Release status](release-status.md).
