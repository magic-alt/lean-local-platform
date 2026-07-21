# LEAN Local Web Platform

This platform wraps the open-source `quantconnect/lean` Docker image with a local browser UI. It does not use Lean CLI and does not require a QuantConnect paid account for local Docker backtests.

## Architecture

- Backend: FastAPI, MySQL, Redis, Celery.
- Optional infra: ClickHouse, Prometheus, Grafana through root `docker-compose.yml`.
- Frontend: React, Vite, TypeScript, Ant Design, ECharts, Monaco Editor.
- Runtime state: `web/runtime/`.
- LEAN data: `LEAN_DATA_DIR` (by default the workspace parent `Data/` directory).
- Docker execution: local `quantconnect/lean` image with mounted project, data, config, results, and object store.

MySQL stores searchable metadata, market data, PIT memberships, sync/batch lifecycle, backtest results, and binary stored objects. SQLite is an isolated test backend only, not a runtime fallback. Original LEAN JSON, logs, and HTML reports still have filesystem cache copies under `runtime/`, and are archived into MySQL `stored_objects/stored_object_chunks`.
LEAN-format zip files remain the LEAN engine input cache. When ClickHouse is available, imported OHLCV rows can also be mirrored into `lean_market.market_bars` for query acceleration, but MySQL is the runtime source of truth.

## Run Locally

Start Redis in one terminal:

```bash
redis-server --port 6379
```

If you prefer Docker for Redis:

```bash
docker run --rm -p 6379:6379 redis:7-alpine
```

Or start the full local infrastructure stack from the repository root:

```bash
docker compose up -d mysql redis clickhouse prometheus grafana
```

Start the backend API:

```bash
cd /Users/kaermax/lean-platform/web/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the Celery worker in another backend terminal:

```bash
cd /Users/kaermax/lean-platform/web/backend
source .venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

Start the frontend:

```bash
cd /Users/kaermax/lean-platform/web/frontend
npm install
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

Do not allow the frontend to auto-fallback to another port.

```bash
# strict bind required: backend must be available on 127.0.0.1:8000 first
pkill -f "uvicorn app.main:app --reload --host 127.0.0.1 --port 8000" || true
pkill -f "vite --host 127.0.0.1 --port 5173 --strictPort" || true
```

Then start:

```bash
cd /Users/kaermax/lean-platform/web/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd /Users/kaermax/lean-platform/web/frontend
npm run dev
```

If port `8000` is already in use, stop the old process and restart the backend on `127.0.0.1:8000` to keep frontend/API pairing consistent.

## Production-Style Local Build

```bash
cd /Users/kaermax/lean-platform/web/frontend
npm run build

cd ../backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

When `frontend/dist` exists, FastAPI serves it at `/`; API routes remain under `/api`.

## Web Features

- Single-user project workspace with overview, code, data, backtest, results, and logs tabs.
- Project creation, deletion, strategy-template selection, and Monaco-based project editing.
- Example gallery and database-backed batches for backtests, optimization, and research.
- Current Dow Jones Industrial Average component universe, as of 2026-06-29, with local-data readiness flags.
- CSV import plus Yahoo Finance, Stooq, Alpha Vantage, Sina Finance, EastMoney, AKShare, and TongHuaShun daily data import into LEAN zip format.
- US, China A-share, and Hong Kong daily equity data workflows.
- Docker backtests with persisted logs, artifacts, charts, structured HTML reports and Markdown export.
- Equity and asset-price charts with order time markers.
- Settings page for default market, provider, strategy, Docker images, cash, and date ranges.
- Local grid optimization through Celery tasks.
- Multi-symbol/multi-strategy/rolling/PIT-universe batches with cancellation, failed retry and CSV export.
- Research examples, batch research and detached container launcher.
- Local Object Store file upload/download/delete.
- Task queue and logs.
- Dependency health at `/api/health/dependencies`.
- Prometheus metrics at `/metrics`.
- Monitoring page with Grafana and Prometheus links.
- ClickHouse bar preview from the Data Library when the mirror is available.
- Ten-dataset first-full/then-incremental TuShare build, explicit on-demand storage selection, CSV templates and data-aware previews.
- Searchable in-app Docs backed by `docs/help`.

## Data Providers

The web UI writes imported daily bars into `LEAN_DATA_DIR` in LEAN's expected zip format. The backtest engine then reads the same files through the mounted Docker volume.

- `Yahoo Finance`: US equities, no API key, useful for demos, but the chart endpoint can rate-limit shared networks.
- `Stooq`: US equities, no API key, useful when CSV downloads are allowed, but it can return browser-verification pages from some networks.
- `Alpha Vantage`: US equities, requires an API key and is rate-limited.
- `EastMoney`: A-share and Hong Kong daily bars through the direct public K-line endpoint.
- `Sina Finance`: US, A-share, and Hong Kong daily bars through AKShare adapters.
- `AKShare`: US, A-share, and Hong Kong daily bars; install backend requirements first.
- `TongHuaShun`: A-share daily workflow only in v1.

For a reliable DJIA workflow, open `Workspace` or `Data`, select `Alpha Vantage`, enter an API key or set `ALPHAVANTAGE_API_KEY`, choose missing symbols, then fetch. After local data exists, use `Workspace -> Backtest` to run a real symbol such as `AAPL`, `MSFT`, or `GOOGL`.
