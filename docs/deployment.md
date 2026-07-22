# Deployment

This project is designed for local or single-host deployment first. Distributed scheduling and broker connectivity are later-stage work.

Last reviewed: 2026-07-22.

## Local API authentication

The supported launcher creates a 256-bit bearer token in
`web/runtime/secrets/api_token` with mode `0600`. The Vite development proxy
adds the token to API requests; the token is never returned by an API or
exposed to frontend JavaScript or local storage. When the production frontend
is served directly by FastAPI, the HTML response establishes a derived,
HttpOnly, SameSite=Strict browser session cookie. Direct API clients must send
`Authorization: Bearer <token>` (or `X-LEAN-API-Key`). `/api/health` and
`/metrics` remain unauthenticated for local health checks and Prometheus.

`LEAN_API_AUTH_REQUIRED=1` is the production default. If authentication is
enabled but `LEAN_API_TOKEN` is empty, business APIs fail closed with HTTP 503.
Only isolated pytest runs should set `LEAN_API_AUTH_REQUIRED=0`.

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
docker compose --profile app up -d --build mysql redis api worker data-worker data-demand-worker backtest-worker beat
```

Use `--build` after Dockerfile, dependency or frontend build-input changes. Ordinary restarts do not need it. For the workstation workflow, `scripts/start_web_single_instance.sh` is preferred because it serializes launchers and protects an active data sync from worker replacement.

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
LEAN_API_AUTH_REQUIRED
LEAN_API_TOKEN
BACKTEST_JOB_TIMEOUT_SECONDS
BACKTEST_MAX_CONCURRENT_JOBS
LEAN_DB_OBJECT_STORE_ENABLED
LEAN_DB_OBJECT_CHUNK_BYTES
LEAN_MYSQL_CONNECT_ATTEMPTS
LEAN_MYSQL_CONNECT_RETRY_DELAY_SECONDS
LEAN_MYSQL_BUFFER_POOL_SIZE
LEAN_MYSQL_REDO_LOG_CAPACITY
TUSHARE_TOKEN
```

`scripts/start_web_single_instance.sh` generates a runtime-only MySQL loader
password and grants that account only the privileges required for rebuildable
market-data batches. Bulk sessions disable their own binlog; API, projects,
backtests and paper-trading metadata continue using the normal database user.
The same launcher creates and reuses the local API token; deleting the token
file intentionally rotates it at the next clean start.

LEAN and Research images must be referenced by immutable SHA-256 digest and
must appear in `LEAN_ALLOWED_DOCKER_IMAGES` or
`LEAN_ALLOWED_RESEARCH_IMAGES`. Backtest containers use no network, a
read-only root, dropped capabilities and per-run storage. Research containers
bind Jupyter only to `127.0.0.1`, drop capabilities, apply CPU/memory/PID
limits, and do not mount the shared object store or a host gateway alias.

High-throughput TuShare synchronization can be tuned with
`LEAN_TUSHARE_CALLS_PER_MINUTE` (maximum 500 for the 5,000-point account),
`LEAN_TUSHARE_FETCH_CONCURRENCY`, `LEAN_STK_LIMIT_FETCH_CONCURRENCY`,
`LEAN_DATA_SYNC_BATCH_UNITS` (8-32 instruments per commit), and
`LEAN_DATA_SYNC_CHUNK_ROWS`. Initial `stk_limit` history uses concurrent
instrument prefetch plus a sequential batch writer; later increments use one
market-wide request per missing trade date.

The workstation profile treats on-demand MySQL writes as a bounded cache.
`LEAN_MYSQL_ON_DEMAND_MAX_DATABASE_GB` defaults to 50 and applies only to on-demand
fetches. One-click bulk synchronization has no database-size ceiling and stops
only when the physical disk reserve would be breached. The reserve is the
larger of 500 GiB and 50% of total disk capacity. The API and workers
read the same MySQL data directory through a read-only observer mount, so the
catalog and live progress both report its physical allocated size.
The legacy `LEAN_MYSQL_MAX_DATABASE_GB` name remains a fallback for existing
installations, but no longer limits one-click synchronization.
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

## MySQL Memory and Recovery

The Compose workstation defaults are intentionally conservative:

```text
LEAN_MYSQL_BUFFER_POOL_SIZE=1G
LEAN_MYSQL_REDO_LOG_CAPACITY=256M
LEAN_MYSQL_CONNECT_ATTEMPTS=5
LEAN_MYSQL_CONNECT_RETRY_DELAY_SECONDS=0.5
```

MySQL uses `restart: unless-stopped`. API/worker connection establishment retries transient MySQL codes 1040, 2003, 2006 and 2013 for a bounded period. If recovery is not complete, API requests return retryable HTTP 503 `DATABASE_UNAVAILABLE`; periodic recovery/reconciliation tasks retry through Celery instead of turning a short outage into a permanent failed coordinator run.

Docker Desktop memory is shared by MySQL, workers, LEAN, Research, ClickHouse and observability containers. A `Lost connection ... (2013)` burst across unrelated endpoints usually indicates a server restart or OOM rather than a bad query in each endpoint. Check:

```bash
docker compose ps mysql
docker inspect lean-platform-mysql-1 --format '{{.State.Status}} {{.State.ExitCode}} {{.State.OOMKilled}}'
docker compose logs --tail=200 mysql
```

If `OOMKilled=true` or exit code is 137, stop unused stacks/LEAN containers, increase Docker's total memory if appropriate, and keep buffer/worker concurrency within the host budget. Do not mask repeated OOM by adding unlimited client retries.

`BACKTEST_MAX_CONCURRENT_JOBS` is enforced by database-backed `scheduler_leases` before a LEAN container starts. When no slot is available, the Celery task remains queued and retries instead of launching another container.

Default database URL is MySQL:

```text
mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market
```

DuckDB is used only as a query engine over Parquet exports under `LEAN_PARQUET_DIR`; it is not a runtime metadata database.

## Docker Socket

Only the dedicated `backtest-worker` mounts:

```text
/var/run/docker.sock:/var/run/docker.sock
```

The API, default worker and data workers do not receive the Docker socket. The
backtest worker remains privileged infrastructure and must stay loopback-only.
The API dependency endpoint verifies the dedicated Celery backtest worker and
reports Docker/LEAN execution as delegated; it does not require local Docker
access inside the API container.
Every LEAN child uses a digest allowlist, a per-run writable object directory,
`network=none`, a read-only root filesystem, dropped capabilities, no-new-privileges,
and bounded CPU, memory and PID settings.

## Data Directories

```text
LEAN_DATA_DIR (default workspace parent/Data)
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
./scripts/backup_mysql.sh
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
- Monitor MySQL restarts/OOM state and Docker total memory, not only query latency.
- Archive or prune old `web/runtime/runs` after verifying object-store persistence.
