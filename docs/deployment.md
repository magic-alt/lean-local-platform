# Deployment

Last reviewed: 2026-08-27. See [Current State](current-state.md).

The production runtime is PostgreSQL 17, RabbitMQ 4.3.5, Celery 5.6, Parquet,
DuckDB and LEAN. Docker Compose and native hosts are deployment adapters for
the same application architecture. SQLite is permitted only in isolated unit
tests. ClickHouse is an optional asynchronous mirror and is disabled by
default.

## Storage boundary

- `lean_platform`: authoritative control plane, DataRelease/PIT metadata,
  Paper/OMS state, task facts, scheduler leases, audit and object metadata.
- `lean_celery`: disposable Celery workflow/result metadata. It is not a
  business source of truth and is not part of core disaster recovery.
- `lean_mlflow`: MLflow-owned schema and metadata.
- `data/` Parquet: authoritative market time series. DuckDB queries these files
  directly; quote bars, minute data and ticks must not be written to PostgreSQL.

The PostgreSQL baseline does not create forbidden quote relations. Application
guards and the startup schema scan fail closed if a typed market-time-series
source attempts a control-plane write or a forbidden relation appears.

## Docker Compose

Copy `.env.example` to `.env` and set unique PostgreSQL, RabbitMQ, API and
runner secrets. Then run:

```bash
python scripts/platformctl.py --mode docker --profile full doctor
python scripts/platformctl.py --mode docker --profile full start
```

The dependency gates are:

```text
PostgreSQL healthy -> postgres-init -> migration complete -> API/workers/beat/runner
RabbitMQ healthy ------------------------------------------> API/workers/beat
MLflow database upgrade complete --------------------------> MLflow
```

Only the dedicated `migration` service applies platform migrations. API and
workers verify the applied baseline read-only at startup. MLflow upgrades its
own database separately.

Compose uses exact `postgres:17.11` and `rabbitmq:4.3.5-management` tags. Before
a production release, resolve and record the approved registry digests in the
release evidence; an unreviewed tag update is not a certified upgrade.

RabbitMQ queues are durable classic queues on the single-host topology, with
persistent delivery, publisher confirms, manual late acknowledgements,
heartbeat, startup retry and prefetch 1. Quorum queues are reserved for a real
three-node broker deployment.

## Native and Windows

See [Native deployment](native-deployment.md) and the
[Windows deployment matrix](current-state.md#deployment-matrix). Windows Dockerless
development defaults to user processes managed by `platformctl`.
`LEAN_NATIVE_MANAGER=windows-scm` selects `LeanPlatformSupervisor` and
`LeanRestrictedRunner` services explicitly. Production mode requires SCM and
a current host-bound certification before startup.

## Database initialization and migration

```bash
python scripts/platformctl.py --mode native db init
python scripts/platformctl.py --mode native db migrate
```

Fresh PostgreSQL uses `P0001_postgresql_baseline.sql`; legacy migrations and
their checksums remain immutable lineage evidence and are never replayed into
the new database. JSON and date/time application contracts remain text in the
baseline. JSONB/TIMESTAMPTZ conversion is a later, independent migration.

## Backup and isolated restore

Create a logical backup:

```bash
python scripts/platformctl.py --mode native backup
```

The backup service writes `.partial` files, runs `pg_dump -Fc` for
`lean_platform` and `lean_mlflow`, verifies hashes, writes `manifest.json`,
atomically publishes the directory and adds `COMPLETE`. `lean_celery` is
excluded intentionally; reconciliation redispatches non-terminal authoritative
tasks after recovery.

Restore only to a new `lean_restore_*` namespace:

```bash
python scripts/platformctl.py --mode native restore \
  --backup web/runtime/backups/postgres/<backup-id> \
  --target-prefix lean_restore_drill

python scripts/run_restore_drill.py \
  --backup web/runtime/backups/postgres/<backup-id> \
  --target-prefix lean_restore_drill \
  --confirm RESTORE_ISOLATED_DATABASE
```

The drill compares exact row counts and deterministic row digests for critical
tables. It never overwrites a live database.

## Health and operations

`GET /api/health` reports runtime-neutral blocks for `database`, `broker`,
`execution` and `storage`. `platformctl doctor`, `status`, `logs`, `backup`,
`restore` and `runtime` work through the selected deployment adapter.

Legacy `LEAN_MYSQL_*` and `REDIS_URL` variables are rejected in strict runtime
v2. They are not silently translated. Broker loss, result cleanup or worker
restart must be recoverable from `lean_platform` plus the Parquet/object store.

## Verification lanes

Unit tests use SQLite in an isolated temporary directory. Real PostgreSQL is
opt-in:

```bash
cd web/backend
RUN_POSTGRES_INTEGRATION=1 .venv/bin/python -m pytest -q \
  -m integration_postgres tests/test_postgres_integration_lane.py
```

LEAN Docker integration remains opt-in. Windows production additionally needs
the fault matrix and soak evidence described by
`config/runtime/windows-celery-certification.json`.
