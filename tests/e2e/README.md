# Web E2E Tests

This suite validates the React Web UI against the current FastAPI, PostgreSQL,
RabbitMQ/Celery and LEAN platform topology.  The normal suite owns isolated
control-plane services and deterministic fixture data; the real-local-data
case mounts an operator-owned data lake read-only from the test harness point
of view and never seeds or deletes it.

## Layout

- `specs/`: Playwright test cases.
- `pages/`: Page Object Model wrappers.
- `utils/`: API helpers, isolated E2E topology, backtest waiters and reports.
- `fixtures/seed_e2e_data.py`: cleans only `E2E_` control-plane records and
  seeds isolated SPY / A-share 510300 fixture data.
- `reports/`: HTML/JSON reports, environment evidence, screenshots, traces and videos.

## Default isolated ports

- API: `18080`
- Frontend: `15173`
- PostgreSQL: `15432`
- RabbitMQ AMQP: `15673`
- RabbitMQ management: `15674`

Override them with `E2E_API_PORT`, `E2E_FRONTEND_PORT`,
`E2E_POSTGRES_PORT`, `E2E_RABBITMQ_PORT`, and
`E2E_RABBITMQ_MANAGEMENT_PORT`.

The E2E harness supplies its own non-production database/broker credentials.
It does not reuse `LEAN_DATABASE_URL` or `CELERY_BROKER_URL` from the operator
environment, which prevents a test run from attaching to a production control
plane accidentally.

## Normal fixture-backed runs

Run from `web/frontend`:

```bash
npm run test:e2e:smoke
npm run test:e2e:backtest
npm run test:e2e
npm run test:e2e:compat
npm run test:e2e:ui-audit
npm run test:e2e:report
```

In the default local-backend mode, global setup starts only PostgreSQL and
RabbitMQ with Docker Compose, initializes the dedicated PostgreSQL roles and
databases, applies current migrations, then starts FastAPI and a Celery worker
from `web/backend/.venv`.  Vite is managed by Playwright.

To exercise the application services themselves through Compose:

```bash
E2E_BACKEND_MODE=compose npm run test:e2e
```

To reuse an already running backend:

```bash
E2E_START_STACK=0 E2E_API_URL=http://127.0.0.1:8000 npm run test:e2e
```

Set `E2E_STOP_STACK=1` when the isolated PostgreSQL/RabbitMQ containers should
be removed after the run.

## Real local data

The real-data UI case is intentionally opt-in:

```bash
E2E_REAL_LOCAL_DATA=1 \
E2E_SKIP_SEED=1 \
E2E_LEAN_DATA_DIR=/absolute/path/to/data \
npx playwright test 20-data-preview-local.spec.ts --project=chromium
```

`E2E_SKIP_SEED=1` is mandatory when `E2E_REAL_LOCAL_DATA=1`; global setup
fails closed otherwise.  This case verifies the actual Parquet-backed equity,
`daily_basic` and CSI300 preview paths without creating fixture market data.

For the complete local-data acceptance, use the repository-level verifier
instead of invoking Playwright directly:

```bash
python scripts/system_verify.py --profile local-data --data-dir ./data
```

That command also runs `scripts/local_data_certification.py`, including
canonical Parquet integrity checks and a real Parquet -> isolated LEAN Data ->
pinned LEAN Docker smoke backtest.  Source Parquet files are never rewritten.

## Browser matrix

The mandatory PR smoke lane uses Chromium.  Responsive audits cover desktop,
tablet and mobile Chromium viewports. Firefox and WebKit remain outside the
current required compatibility matrix.

## Reports

- HTML report: `tests/e2e/reports/html/index.html`
- Playwright artifacts: `tests/e2e/reports/artifacts`
- Environment report: `tests/e2e/reports/environment.json`
- Data source report: `tests/e2e/reports/data-source.json`
- Case result summary: `tests/e2e/reports/e2e-case-results.json`
