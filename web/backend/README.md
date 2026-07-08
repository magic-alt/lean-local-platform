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

Compose startup with MySQL, Redis, API, and worker:

```bash
cd /Users/kaermax/lean-platform
docker compose --profile app up -d --build mysql redis api worker
```

If a host port is already in use:

```bash
LEAN_REDIS_PORT=6380 LEAN_API_PORT=8002 docker compose --profile app up -d --build mysql redis api worker
```

Useful environment variables:

```bash
export REDIS_URL=redis://127.0.0.1:6379/0
export LEAN_DATABASE_URL=mysql+pymysql://lean:lean@127.0.0.1:3306/lean_market
export LEAN_DOCKER_IMAGE=quantconnect/lean:latest
export LEAN_RESEARCH_IMAGE=quantconnect/research:latest
```

Main modules:

- `app/api/`: HTTP routers.
- `app/services/`: project, task, and object-store domain services.
- `app/tasks/`: Celery app and worker jobs.
- `app/lean.py`: LEAN Docker command construction, data conversion helpers, and result parsing.

Useful data maintenance tasks:

```bash
# Rebuild derived Parquet datasets from MySQL market_daily_bars and persist a consistency report.
.venv/bin/python ../../scripts/rebuild_market_parquet.py \
  --asset-class equity --market china --venue china --resolution daily --data-type trade --adjust raw

# Generate a batch A-share multisource QA acceptance report from already ingested provider data.
.venv/bin/python ../../scripts/compare_ashare_sources_batch.py \
  --symbols 600519,000001 --sources tushare,akshare,baostock --start-date 2026-01-01 --end-date 2026-07-03
```

Backtest and Paper A-share defaults share `app/services/trading_config.py`, including fees, slippage, calendar, benchmark, max positions, max weight, cash floor, blacklist, and watchlist settings.
