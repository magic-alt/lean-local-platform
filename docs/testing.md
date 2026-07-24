# Testing

Backend tests live under `web/backend/tests`; browser E2E lives under
`tests/e2e`. Unit tests default to isolated SQLite and therefore do not count as
production-MySQL or real-LEAN acceptance evidence.

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

There is currently no `npm run test` component-test script. The maintained
frontend test entrypoint is Playwright (`npm run test:e2e`); it must not be
silently substituted with the build command.

Focused and full browser suites run against an isolated MySQL/Redis/ClickHouse
stack. Synthetic A-share fixtures are explicitly tagged `environment=research`
and `synthetic=true`; they require `allowResearchSource=true` and can never be
reported as production certification evidence.

```bash
cd web/frontend
npm run test:e2e:smoke
npm run test:e2e
```

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

Real Paper and bounded local-service recovery acceptances are explicit,
resumable and refuse unsafe shortcuts.

### Level 4 / Level 5 Audit Commands

Use the dedicated acceptance scripts before each review cycle:

```bash
# 1) Level 4: 3x3 grid + rolling-window + walk-forward + dynamic PIT evidence
cd web/backend
.venv/bin/python scripts/run_level4_audit.py \
  --project-id PROJECT_ID \
  --base-url http://127.0.0.1:8000 \
  --cases parameter_grid,rolling,walk_forward,dynamic_pit \
  --execute \
  --require-csv \
  --timeout 1800 \
  --poll-seconds 2 \
  --evidence-out web/runtime/audit/level4-reproducibility.json

# Or preview-only to validate expansion, limits and scheduling preconditions
.venv/bin/python scripts/run_level4_audit.py \
  --project-id PROJECT_ID \
  --base-url http://127.0.0.1:8000 \
  --cases rolling \
  --preview-only \
  --evidence-out web/runtime/audit/level4-rolling-preview.json
```

```bash
# 2) Level 5: 21-day real LEAN Paper chain + optional fault matrix
# Enable only on the isolated remediation stack; run_level5_audit requires v2.
export LEAN_PAPER_ORDER_PIPELINE_V2_ENABLED=1
cd web/backend
.venv/bin/python scripts/run_level5_audit.py \
  --project-id PROJECT_ID \
  --start-date 2023-07-03 \
  --days 21 \
  --with-fault \
  --fault-scenarios worker@7:before_queue,redis@14:during_wait,mysql@20:after_wait \
  --constraints \
  --evidence-dir web/runtime/audit \
  --api-url http://127.0.0.1:8000

# If you already know the trusted source id, keep explicit linkage:
.venv/bin/python scripts/run_level5_audit.py \
  --project-id PROJECT_ID \
  --source-backtest-id BACKTEST_ID \
  --start-date 2023-07-03 \
  --days 21 \
  --with-fault \
  --fault-scenarios worker@7:before_queue,redis@14:during_wait,mysql@20:after_wait \
  --constraints \
  --evidence-dir web/runtime/audit \
  --api-url http://127.0.0.1:8000
```

`run_level5_audit.py` is a wrapper around
`run_lean_paper_walkforward_acceptance.py` that captures per-session evidence for:

- full 21+ day LEAN walk-forward completion
- duplicate-call idempotency (`run-day` re-issue must block)
- fills + policy rejects + reject reason presence
- restart recovery points at selected fault phases
- constraints/reject coverage

The strict Level 5 result counts fills and policy rejects from the same v2
session. The optional `--constraints` helper remains supplementary coverage and
cannot substitute for a rejected real LEAN-sourced intent in that session.

For one-shot dry-run before execution:

```bash
web/backend/.venv/bin/python scripts/run_lean_paper_walkforward_acceptance.py \
  --project-id PROJECT_ID \
  --paper-mode lean_walkforward_v2 \
  --start-date 2023-07-03 --days 21 \
  --evidence-out web/runtime/audit/paper-21-day.json \
  --dry-run

# 或者显式指定已验证 source backtest：
web/backend/.venv/bin/python scripts/run_lean_paper_walkforward_acceptance.py \
  --project-id PROJECT_ID --source-backtest-id BACKTEST_ID \
  --start-date 2023-07-03 --days 21 \
  --evidence-out web/runtime/audit/paper-21-day.json \
  --dry-run

# Legacy bounded restart matrix is still kept as a lower-level smoke:
web/backend/.venv/bin/python scripts/run_service_restart_fault_acceptance.py \
  --services worker,redis,mysql --confirm RESTART_LOCAL_SERVICES \
  --output web/runtime/audit/service-restart-matrix.json
```

The wrapper supports `--with-fault` and `--constraints`; both are required
for full Level 5 replay re-evaluation in the current audit process. When
`--with-fault` is omitted, fault scenarios are intentionally skipped.

The Paper command distinguishes a successful 21-day cumulative LEAN chain
from the stricter Level 5 replay gate. Level 5 also requires at least one fill
and one policy-rejected order with a reason in the same session; a run without
that rejection is reported as `partial`, not promoted to PASS.

Generate runtime-image CycloneDX evidence and verify immutable dependency
inputs with:

```bash
scripts/generate_container_sbom.sh web/runtime/audit/sbom
web/backend/.venv/bin/python scripts/check_supply_chain.py \
  --output web/runtime/audit/supply-chain.json
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
- No accepted production-like five-job concurrency/cancellation/fault matrix yet.
- A real 21-trading-day LEAN Paper acceptance is available, but it cannot
  close Level 5 unless the same session contains a filled and a policy-rejected
  order.
- The production CSI300 manifest cannot validate without the operator-retained official attachment bundle.
- Disk exhaustion/OOM and production-scale restore remain isolated-environment
  gates; they must never be injected into the formal workstation data volume.
- SBOM generation exists, but Python transitive hash locking, vulnerability
  policy and trusted image signature verification remain release gates.

## Real MySQL Integration Lane

SQLite remains the fast unit-test backend. MySQL migration, index, unique-key,
transaction and named-lock behavior has a separate disposable lane:

```bash
docker compose --profile test run --build --rm mysql-integration-tests
```

The lane uses a dedicated `lean_integration` database on a tmpfs-backed MySQL
service. Its tests refuse any other database name. It does not mount the
production MySQL volume, repository, Docker socket, or market-data directory.
