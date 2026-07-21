# Testing

Tests live under `web/backend/tests`. The frontend currently relies on TypeScript build verification.

## Unit Tests

Run all backend tests:

```bash
cd web/backend
.venv/bin/python -m pytest -q
```

Important unit-level coverage:

- config generation: `tests/test_lean_runner.py`
- status model: `tests/test_backtest_status.py`
- result parser and artifact archive: `tests/test_result_service.py`
- data quality: `tests/test_ashare_p0.py`, `tests/test_ashare_multisource.py`
- A-share repository/reference data: `tests/test_ashare_reference_public.py`, `tests/test_pit_data.py`
- Parquet lake: `tests/test_parquet_lake.py`
- API smoke: `tests/test_api_smoke.py`
- data sync lifecycle/archive: `tests/test_data_sync*.py`
- examples and experiment batches: `tests/test_experiment_examples.py`, `tests/test_experiment_batches.py`
- report generation/export: `tests/test_plot_results.py`, report API/service tests
- transient MySQL failure handling: database and middleware/task recovery tests

## Integration Tests

Docker/LEAN integration is intentionally opt-in:

```bash
cd web/backend
RUN_LEAN_DOCKER_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_ashare_lean_integration.py
```

This requires Docker access and local LEAN data fixtures.

## Frontend Verification

```bash
cd web/frontend
npm run build
```

This runs `tsc -b` and Vite build.

Validate the in-app documentation sources, links, screenshots and generated API endpoint inventory with:

```bash
web/backend/.venv/bin/python scripts/check_help_docs.py
web/backend/.venv/bin/python scripts/generate_help_api_reference.py --check
```

The Docs Playwright case verifies GFM tables, relative article links, reload-safe deep links, search and page overflow. Screenshots are deliberately opt-in because they update tracked assets:

```bash
cd web/frontend
npm run docs:screenshots
```

## Current Acceptance Commands

After P0/P1 changes:

```bash
cd web/backend
.venv/bin/python -m pytest -q

cd ../frontend
npm run build
```

Optional:

```bash
cd web/backend
RUN_LEAN_DOCKER_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_ashare_lean_integration.py
```

## Standard Backtest Problems

### 1. Buy and Hold

- Data: one equity symbol with complete daily bars.
- Period: at least 30 trading days.
- Cash: 100000.
- Rule: buy once after first bar and hold.
- Verify: one buy order, equity curve exists, benchmark curve exists for A-share, result archived.
- Pass: run status success, result JSON, summary JSON, order events, manifest, parsed equity curve.

### 2. SMA Cross

- Data: one symbol with at least 120 daily bars.
- Period: covers several moving-average windows.
- Cash: 100000.
- Rule: fast SMA crosses above slow SMA to enter; exit on reverse.
- Verify: indicator warmup, orders, drawdown curve, Sharpe metric.
- Pass: no parser errors; metrics table populated.

### 3. ETF Momentum Rotation

- Data: multiple ETF symbols.
- Period: at least 1 year daily bars.
- Cash: 100000.
- Rule: rank by lookback momentum, rebalance every N days.
- Verify: multiple subscriptions, switching orders, benchmark comparison.
- Pass: no missing data errors; holdings change over time.

### 4. A-Share T+1 and Limit Test

- Data: A-share symbol with `ashare_trade_status` including suspended, limit-up, limit-down dates.
- Period: includes the blocked dates.
- Cash: 100000 CNY.
- Rule: strategy attempts buy/sell around blocked dates.
- Verify: T+1 prevents same-day sell, limit-up blocks buy, limit-down blocks sell, suspended blocks both.
- Pass: helper logs blocked trades; validation gates pass; no constant benchmark fallback.

### 5. Fees and Slippage

- Data: one equity symbol with simple price path.
- Period: enough to produce at least one round trip.
- Cash: 100000.
- Rule: buy then sell.
- Verify: commission, min commission, stamp tax sell, transfer fee, slippage assumptions.
- Pass: order events contain fees; parsed trade PnL deducts fees.

### Optional 6. Convertible Bond Double Low

- Data: convertible bond daily bars, terms, call risk.
- Rule: select by double-low score.
- Verify: call-risk exclusion, bond/stock metadata.
- Pass: pool API and strategy candidate list match expected fixture.

### Optional 7. Futures Trend

- Data: futures contracts, main mapping, daily bars.
- Rule: trend following on main contract.
- Verify: contract roll mapping, multiplier/margin metadata.
- Pass: no contract lookup gaps; orders use expected contract.

## Test Gaps

- The repository has a browser E2E area, but coverage is not yet a required full release gate for every page.
- No frontend component tests yet.
- No formal benchmark golden files for all templates yet.
- No full exchange-grade A-share matching acceptance test yet.
- No resource-pressure/OOM recovery test representative of the complete Docker Desktop stack yet.
