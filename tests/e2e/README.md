# Web E2E Tests

This suite validates the React Web UI, FastAPI API, Celery worker, Docker, and LEAN backtest path.

## Layout

- `specs/`: Playwright test cases.
- `pages/`: Page Object Model wrappers.
- `utils/`: API helpers, environment paths, backtest waiters, report writers.
- `fixtures/seed_e2e_data.py`: cleans only `E2E_` records and seeds isolated SPY / A-share 510300 data.
- `reports/`: HTML report, JSON result, screenshots, traces, videos, and audit files.

## Default Ports

The suite uses isolated ports by default:

- API: `18080`
- Frontend: `15173`
- MySQL: `13306`
- Redis: `16379`
- ClickHouse HTTP: `18123`

Override with `E2E_API_PORT`, `E2E_FRONTEND_PORT`, `E2E_MYSQL_PORT`, `E2E_REDIS_PORT`, and `E2E_CLICKHOUSE_HTTP_PORT`.

## Commands

Run from `web/frontend`:

```bash
npm run test:e2e:smoke
npm run test:e2e:backtest
npm run test:e2e
npm run test:e2e:compat
npm run test:e2e:ui-audit
npm run test:e2e:report
```

By default global setup starts the Docker infrastructure services `mysql`, `redis`, and `clickhouse`, then starts the FastAPI API and Celery worker locally from `web/backend/.venv`. Vite is started through the Playwright `webServer`.

`test:e2e:compat` runs the responsive and smoke cases at 1920×1080 plus the dedicated
shell audit at 1280×800 and 768×1024. Use `test:e2e:ui-audit` for the two required
audit viewports only; that command isolates API calls with route mocks and does not
start or seed the backend stack. Firefox and WebKit are not part of the current
compatibility matrix.

To force the API and worker to run through the compose app profile:

```bash
E2E_BACKEND_MODE=compose npm run test:e2e
```

To reuse an already running backend:

```bash
E2E_START_STACK=0 E2E_API_URL=http://127.0.0.1:8000 npm run test:e2e
```

To leave the E2E Docker stack running, do nothing. To stop it after tests:

```bash
E2E_STOP_STACK=1 npm run test:e2e
```

## Data Isolation

Only records prefixed with `E2E_` are cleaned. Test market data is written under `web/runtime/e2e-lean-data` unless `E2E_LEAN_DATA_DIR` is provided. User strategy projects, market data, and production settings are not deleted.

SPY data is copied from a local LEAN data directory when available; otherwise deterministic synthetic daily bars are generated. A-share 510300 and benchmark 000300 are deterministic E2E fixtures written to the isolated database and LEAN data directory.

## Reports

- HTML report: `tests/e2e/reports/html/index.html`
- Playwright artifacts: `tests/e2e/reports/artifacts`
- Environment report: `tests/e2e/reports/environment.json`
- Data source report: `tests/e2e/reports/data-source.json`
- Case result summary: `tests/e2e/reports/e2e-case-results.json`
