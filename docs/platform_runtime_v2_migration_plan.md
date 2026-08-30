# Platform Runtime Architecture v2 migration plan

Status: approved for staged local implementation.

Baseline commit: `ceb3119ff80fc47d6200761e1f96341e1752834a`

## Target architecture

- PostgreSQL 17.11 is the only production relational database. SQLite remains
  available only to isolated unit tests.
- One PostgreSQL instance owns three databases with separate lifecycle and
  least-privilege roles: `lean_platform`, `lean_celery`, and `lean_mlflow`.
- RabbitMQ 4.3.5 is the Celery broker. Single-host deployments use durable
  classic queues, persistent messages, publisher confirms, manual late ACKs,
  heartbeats, and a prefetch multiplier of one.
- Celery 5.6.3 runs with prefork on Linux/Compose. Windows uses one
  `--pool=solo --concurrency=1` process per worker instance under the platform
  supervisor. Windows support is certified and owned by this project because
  Celery upstream does not support Windows.
- Parquet remains the authoritative market-data store and DuckDB remains its
  query engine. ClickHouse is an optional asynchronous mirror and is disabled
  by default.
- Docker Compose and Windows SCM are runtime adapters for the same application
  architecture. Native execution includes both LEAN and Research.

## Persistence boundary

`lean_platform` stores control-plane facts, DataRelease and PIT metadata,
provider lineage, task authority, audit evidence, and Paper/OMS state. It must
not store OHLCV, minute, tick, realtime, adjustment-factor, daily-basic, or
other market time series. The boundary is enforced by application dataset
classification, a PostgreSQL forbidden-relation startup check, and CI schema
inspection.

Published DataRelease identities are immutable. The migration must preserve
`artifactId`, `DataReleaseId`, provider provenance, as-of semantics, target
weight SHA-256, deterministic release checksums, and fail-closed lifecycle
gates.

## Migration policy

The legacy `0001` through `0056` migrations remain immutable audit evidence and
are not replayed on PostgreSQL. PostgreSQL starts from
`P0001_postgresql_baseline.sql`, whose manifest binds the source schema version,
legacy migration-root SHA-256, baseline commit, and generated timestamp. The
SQLite test backend has a separate test baseline.

The engine switch preserves current application-visible JSON and temporal
contracts. Converting text JSON/date-time columns to JSONB, DATE, UUID, or
TIMESTAMPTZ is explicitly deferred to a later project.

There is no MySQL-to-PostgreSQL data migration, no dual-write period, and no
legacy MLflow data migration.

## Local implementation stages

1. PostgreSQL foundation: psycopg 3 adapter and process-local pool, baselines,
   three-database initialization, singleton migration, backup and isolated
   restore.
2. PostgreSQL concurrency: `RETURNING`, transactional state transitions,
   idempotency constraints, row locks, `SKIP LOCKED`, limited deadlock retries,
   and market-data relation guards.
3. RabbitMQ: AMQP routing and reliability settings, PostgreSQL result backend,
   broker-neutral recovery/rate limiting/metrics, and Redis retirement path.
4. Runtime abstraction: complete the existing runtime-neutral LEAN and
   Research interfaces while retaining Docker as the reference backend.
5. Windows Native: SCM supervisor, solo workers, restricted runner, signed
   native runtime, Job Objects, restricted tokens, ACLs, firewall enforcement,
   and native Research isolation.
6. Parity certification and cleanup: 24-hour Windows certification, Compose vs
   native deterministic comparison, backup/restore drills, then removal of all
   MySQL and Redis code, dependencies, configuration, and documentation.

Each stage is a local, independently reviewable change set. No remote branch or
pull request is created by this implementation.

## Required configuration

- `LEAN_DATABASE_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `LEAN_POSTGRES_BIN`
- `LEAN_POSTGRES_BACKUP_DIR`
- `LEAN_POSTGRES_BACKUP_RETENTION_DAYS`
- `LEAN_POSTGRES_BACKUP_MAX_FILES`
- `LEAN_EXECUTION_BACKEND`
- `LEAN_NATIVE_RUNTIME_DIR`
- `LEAN_NATIVE_RUNTIME_ID`
- `LEAN_DEPLOYMENT_MODE`

Legacy `LEAN_MYSQL_*`, `MYSQL_BACKUP_*`, and `REDIS_URL` variables are rejected
rather than silently translated.

## Acceptance gates

- PostgreSQL integration covers the baseline, constraints, transactions,
  pooling, concurrent claims, advisory locks, and backup/restore.
- RabbitMQ integration covers durable delivery, publisher confirmation, worker
  loss, broker restart, duplicate redelivery, and reconciliation.
- Paper tests prove that retries cannot duplicate commands, orders, fills,
  ledger entries, cash movements, positions, or finalizations.
- DataRelease tests prove immutable identity and the absence of relational
  market time-series storage.
- LEAN and Research tests prove runtime identity, path layout, timeout/cancel
  behavior, process-tree cleanup, sandbox fail-closed behavior, and immutable
  evidence.
- Windows certification binds the exact OS, Python, Celery, RabbitMQ,
  PostgreSQL, LEAN runtime, and test-evidence digests. It cannot be enabled by a
  boolean environment variable.
- The final gate runs focused tests, the complete backend suite, repository
  hygiene, frontend production build, relevant Playwright flows, and isolated
  restore drills. Provider calls, broker writes, and live activation are never
  exercised.

## Recovery and rollback

Before final cleanup, rollback is performed by reverting the current stage;
there is no runtime dual-write switch. PostgreSQL recovery uses custom-format
`pg_dump` files, SHA-256 manifests, atomic completion markers, and restore into
an isolated database. Core disaster recovery includes `lean_platform`,
`lean_mlflow`, the Parquet lake, object store, and immutable runtime artifacts;
`lean_celery` is disposable and unfinished work is reconstructed from
authoritative platform state.
