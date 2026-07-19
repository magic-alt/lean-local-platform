# Deployment

This project is designed for local or single-host deployment first. Distributed scheduling and broker connectivity are later-stage work.

## Local Development

Backend:

```bash
cd web/backend
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Worker:

```bash
cd web/backend
.venv/bin/celery -A app.tasks.celery_app worker --loglevel=info --pool=solo --queues=default,data,backtest
```

Frontend:

```bash
cd web/frontend
npm run dev
```

Redis:

```bash
redis-server --port 6379
```

Docker Desktop or Docker Engine must be running for LEAN backtests.

## Docker Compose

Infrastructure only:

```bash
docker compose up -d mysql redis
```

Full app profile:

```bash
docker compose --profile app up -d --build mysql redis api worker data-worker backtest-worker
```

Optional observability/data services:

```bash
docker compose up -d clickhouse prometheus grafana
```

Default service ports:

```text
Redis:      6379
MySQL:      3306
API:        8000
ClickHouse: 8123 / 9000
Prometheus: 9090
Grafana:    3000
```

Ports can be changed with:

```text
LEAN_REDIS_PORT
LEAN_MYSQL_PORT
LEAN_API_PORT
LEAN_CLICKHOUSE_HTTP_PORT
LEAN_CLICKHOUSE_NATIVE_PORT
LEAN_PROMETHEUS_PORT
LEAN_GRAFANA_PORT
```

## Environment Variables

Important backend variables:

```text
LEAN_DATABASE_URL
DATABASE_URL
REDIS_URL
LEAN_DATA_DIR
LEAN_HOST_DATA_DIR
LEAN_HOST_PLATFORM_DIR
LEAN_PARQUET_DIR
LEAN_DOCKER_IMAGE
BACKTEST_JOB_TIMEOUT_SECONDS
BACKTEST_MAX_CONCURRENT_JOBS
LEAN_DB_OBJECT_STORE_ENABLED
LEAN_DB_OBJECT_CHUNK_BYTES
TUSHARE_TOKEN
```

`scripts/start_web_single_instance.sh` generates a runtime-only MySQL loader
password and grants that account only the privileges required for rebuildable
market-data batches. Bulk sessions disable their own binlog; API, projects,
backtests and paper-trading metadata continue using the normal database user.

High-throughput TuShare synchronization can be tuned with
`LEAN_TUSHARE_CALLS_PER_MINUTE` (maximum 500 for the 5,000-point account),
`LEAN_TUSHARE_FETCH_CONCURRENCY`, and `LEAN_DATA_SYNC_CHUNK_ROWS`.

The workstation profile treats MySQL as a bounded cache.
`LEAN_MYSQL_MAX_DATABASE_GB` defaults to 50; bulk writes stop before the
estimated tables, indexes, binlog and engine headroom exceed that limit.
One-click refreshes retain only A-share execution data, benchmark indexes,
CFFEX futures references, and SSE option references. Contract bars plus
fundamentals, funds, overseas markets, macro data, and feature lists are fetched
on demand by the workflow that uses them.

MySQL uses the `mysql-data` named volume while `LEAN_MYSQL_DATA_DIR` is blank.
To move it to a mechanical drive, stop the stack completely, copy the named
volume contents to an empty directory on the drive, set for example
`LEAN_MYSQL_DATA_DIR=/Volumes/MarketData/lean-platform/mysql`, and restart.
Never copy a live MySQL data directory. Use a journaled local filesystem and do
not place the directory under cloud synchronization.

Business binlogs use `MINIMAL` row images and expire after seven days. Bulk
provider-cache sessions do not write binlogs, preventing rebuildable history
from consuming storage twice.

`BACKTEST_MAX_CONCURRENT_JOBS` is enforced by database-backed `scheduler_leases` before a LEAN container starts. When no slot is available, the Celery task remains queued and retries instead of launching another container.

Default database URL is MySQL:

```text
mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market
```

DuckDB is used only as a query engine over Parquet exports under `LEAN_PARQUET_DIR`; it is not a runtime metadata database.

## Docker Socket

The `api` and `worker` services mount:

```text
/var/run/docker.sock:/var/run/docker.sock
```

This lets the worker start sibling LEAN containers. Treat this as privileged access. Do not expose this deployment on an untrusted network.

## Data Directories

```text
Data/
  LEAN cache mounted into containers.

web/runtime/runs/
  run workspaces and raw result files.

web/runtime/projects/
  uploaded/generated project files.

web/runtime/object-store/
  local object store fallback.

web/runtime/reports/
  report files.

Data/parquet or LEAN_PARQUET_DIR
  Parquet research datasets.
```

In Docker Compose, `LEAN_HOST_DATA_DIR` must point to the host path that Docker can mount into LEAN containers.

## MySQL Backup

Recommended logical backup:

```bash
docker exec lean-platform-mysql-1 mysqldump -ulean -plean lean_market > lean_market.sql
```

Restore:

```bash
docker exec -i lean-platform-mysql-1 mysql -ulean -plean lean_market < lean_market.sql
```

Also back up:

- `Data/`
- `web/runtime/runs/`
- `web/runtime/projects/`
- `web/runtime/reports/`
- Parquet root

If `stored_objects` contains all critical binaries, database backup covers archived artifacts, but raw filesystem workspaces are still useful for debugging.

## Health Checks

```text
GET /api/health
GET /api/health/dependencies
GET /api/health/database
GET /metrics
```

Use dependency health before running long backtests.

## Production Hardening Checklist

- Restrict API network exposure.
- Protect Docker socket.
- Move credentials to secrets.
- Use persistent volumes and scheduled backups.
- Run Docker integration tests after image upgrades.
- Pin LEAN image digest for reproducible releases.
- Monitor MySQL disk growth from `stored_object_chunks`.
- Archive or prune old `web/runtime/runs` after verifying object-store persistence.
