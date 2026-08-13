# Backend

The backend is a FastAPI API plus Celery worker. Redis is used as the broker/result backend, and MySQL is the runtime database for metadata, market data, PIT memberships, results, and stored objects. SQLite remains available for isolated local test backend only.

Install:

```bash
cd /Users/kaermax/lean-platform/web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run API:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run worker:

```bash
source .venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

Required supporting service:

```bash
redis-server --port 6379
```

Compose startup with the complete application worker split:

```bash
cd /Users/kaermax/lean-platform
docker compose --profile app up -d --build mysql redis api worker data-worker data-demand-worker backtest-worker beat
```

If a host port is already in use:

```bash
LEAN_REDIS_PORT=6380 LEAN_API_PORT=8002 docker compose --profile app up -d --build mysql redis api worker data-worker data-demand-worker backtest-worker beat
```

Useful environment variables:

```bash
export REDIS_URL=redis://127.0.0.1:6379/0
export LEAN_DATABASE_URL=mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market
export LEAN_DOCKER_IMAGE=quantconnect/lean@sha256:19e3633d2da1e8b378dd6af4b999b0ca6cf0660a1bf557a0518a2e43fc270823
export LEAN_RESEARCH_IMAGE=quantconnect/research:latest
```

Main modules:

- `app/api/`: HTTP routers.
- `app/services/`: project, task, and object-store domain services.
- `app/tasks/`: Celery app and worker jobs.
- `app/lean.py`: LEAN Docker command construction, data conversion helpers, and result parsing.
- `app/migrations/versions/`: ordered runtime schema migrations; run status checks before starting workers after upgrades.

The API also serves the example catalog, experiment batches, dataset previews/on-demand downloads and help articles. MySQL connection startup uses bounded transient retries and returns retryable `DATABASE_UNAVAILABLE` rather than a generic 500 when the server is temporarily restarting.

Useful data maintenance tasks:

```bash
# Validate/register the existing canonical Parquet lake through the API.
curl -X POST http://127.0.0.1:8000/api/data/parquet/consistency \
  -H 'Content-Type: application/json' -d '{"assetClass":"equity","market":"china","source":"tushare"}'

# Generate a batch A-share multisource QA acceptance report from already ingested provider data.
.venv/bin/python ../../scripts/compare_ashare_sources_batch.py \
  --symbols 600519,000001 --sources tushare,akshare,baostock --start-date 2026-01-01 --end-date 2026-07-03
```

Backtest and Paper A-share defaults share `app/services/trading_config.py`, including fees, slippage, calendar, benchmark, max positions, max weight, cash floor, blacklist, and watchlist settings.
