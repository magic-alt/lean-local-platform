# Backend

The backend is the FastAPI/Celery control plane for LEAN Local Platform. The current runtime uses **PostgreSQL + RabbitMQ + Celery**; MySQL and Redis are legacy dependencies and are not part of the supported runtime topology.

For the canonical architecture and support boundary, see [`../../docs/current-state.md`](../../docs/current-state.md), [`../../docs/architecture.md`](../../docs/architecture.md), and [`../../docs/deployment.md`](../../docs/deployment.md).

## Runtime Dependencies

| Concern | Current component |
| --- | --- |
| API | FastAPI / Uvicorn |
| Control-plane database | PostgreSQL 17, `lean_platform` |
| Celery broker | RabbitMQ 4.3.5, vhost `lean` |
| Celery result backend | PostgreSQL `lean_celery` |
| MLflow metadata | PostgreSQL `lean_mlflow` |
| Market time-series authority | Parquet under `$LEAN_DATA_DIR` |
| Parquet query engine | DuckDB |
| Backtest / execution validation | Restricted runner + QuantConnect LEAN |

`lean_celery` is disposable workflow/result metadata and is not a source of business truth. PostgreSQL `lean_platform` stores control-plane facts, while market quote time series remain in Parquet. SQLite is permitted only for isolated tests.

Strict runtime v2 rejects legacy `LEAN_MYSQL_*` and `REDIS_URL` variables instead of translating them silently.

## Install

From the repository root, copy and configure the environment template first:

```bash
cp .env.example .env
```

At minimum, assign unique values to:

```text
LEAN_POSTGRES_ADMIN_PASSWORD
LEAN_POSTGRES_APP_PASSWORD
LEAN_POSTGRES_CELERY_PASSWORD
LEAN_POSTGRES_MLFLOW_PASSWORD
LEAN_RABBITMQ_PASSWORD
```

Then install the backend:

```bash
cd web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The backend loads the repository-root `.env` automatically. Do not commit populated credentials.

## Start Supporting Services

For development, start PostgreSQL, RabbitMQ, database initialization, and the platform migration from the repository root:

```bash
docker compose --profile app up -d postgres rabbitmq postgres-init migration
```

For the supported full-stack path, prefer the platform launcher:

```bash
python scripts/platformctl.py --mode docker --profile full doctor
python scripts/platformctl.py --mode docker --profile full start
python scripts/platformctl.py --mode docker --profile full status
```

## Run the API

```bash
cd web/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The primary health endpoint is:

```text
GET http://127.0.0.1:8000/api/health
```

Prometheus metrics are exposed at `/metrics`.

## Run a Development Worker

A single worker is sufficient for focused local task development:

```bash
cd web/backend
source .venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

Production-style Compose uses dedicated queue workers, including `default`, `data-bulk`, `data-lineage`, `data-demand`, `backtest`, and `ml`, plus Celery Beat. Use the full Docker profile when validating queue routing, worker isolation, or scheduled workflows.

## Current Connection Variables

Use `.env.example` as the source template. The relevant host-side URL shapes are:

```text
LEAN_DATABASE_URL=postgresql+psycopg://lean_app:<password>@127.0.0.1:5432/lean_platform
CELERY_BROKER_URL=amqp://lean_worker:<password>@127.0.0.1:5672/lean
CELERY_RESULT_BACKEND=db+postgresql+psycopg://lean_celery:<password>@127.0.0.1:5432/lean_celery
LEAN_MLFLOW_DATABASE_URL=postgresql+psycopg://lean_mlflow:<password>@127.0.0.1:5432/lean_mlflow
```

The default LEAN/research images are digest-pinned in backend configuration and `.env.example`. Prefer the repository defaults or an explicitly allowlisted digest rather than an unpinned `latest` tag.

## Database Initialization and Migrations

Fresh PostgreSQL deployments use the PostgreSQL baseline and ordered migrations under:

```text
app/migrations/postgres/
```

The legacy migration lineage under `app/migrations/versions/` is retained for auditability and is not replayed into a fresh PostgreSQL database. Only the migration service applies production migrations; API and workers verify migration state read-only at startup.

For native deployments:

```bash
python scripts/platformctl.py --mode native db init
python scripts/platformctl.py --mode native db migrate
```

## Main Modules

- `app/api/` — HTTP routers and request validation.
- `app/services/` — domain orchestration for projects, backtests, data, experiments, reports, Paper, and research imports.
- `app/repositories/` — PostgreSQL persistence boundaries.
- `app/tasks/` — Celery tasks, queue coordination, reconciliation, and scheduled work.
- `app/runners/` and `app/lean_engine/` — restricted LEAN execution and runtime preparation.
- `app/reporting/` — canonical report generation.
- `app/migrations/postgres/` — current PostgreSQL baseline and migrations.
- `tests/` — unit and opt-in integration tests.

## Data Ownership Rules

The backend deliberately separates market facts from control-plane facts:

- Parquet is authoritative for market time-series data.
- DuckDB queries the Parquet lake directly.
- PostgreSQL stores manifests, lineage, dataset/control metadata, task state, accounts, reports, audit facts, and related control-plane state.
- RabbitMQ transports tasks; queue contents are not recovery authority.
- ClickHouse is an optional analytical mirror only.
- Stored binary/provider payloads live in the configured filesystem/object-store root; PostgreSQL stores their metadata and hashes.

Application guards fail closed if market quote time series are routed into the PostgreSQL control plane.

## Useful Data Maintenance Tasks

Validate/register the canonical Parquet lake through the API:

```bash
curl -X POST http://127.0.0.1:8000/api/data/parquet/consistency \
  -H 'Content-Type: application/json' \
  -d '{"assetClass":"equity","market":"china","source":"tushare"}'
```

Generate an A-share multi-source QA acceptance report from already ingested provider data:

```bash
.venv/bin/python ../../scripts/compare_ashare_sources_batch.py \
  --symbols 600519,000001 \
  --sources tushare,akshare,baostock \
  --start-date 2026-01-01 \
  --end-date 2026-07-03
```

Backtest and Paper A-share defaults share `app/services/trading_config.py`, including fees, slippage, calendar, benchmark, max positions, max weight, cash floor, blacklist, and watchlist settings.

## Validation

Backend unit tests:

```bash
cd web/backend
.venv/bin/python -m pytest -q
```

Real PostgreSQL integration is opt-in and documented in [`../../docs/deployment.md`](../../docs/deployment.md) and [`../../docs/testing.md`](../../docs/testing.md).
