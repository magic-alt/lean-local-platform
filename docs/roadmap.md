# Roadmap

The roadmap follows the platform levels and the P0/P1/P2/P3 implementation plan. LEAN remains the only production backtest engine.

## Level 3 Acceptance

Required:

- Web can create backtest tasks.
- Backend generates LEAN config.
- Docker runs LEAN reliably.
- Each task has an isolated workspace.
- Raw results are saved.
- Results are parsed.
- Frontend displays equity, drawdown, trades/orders, logs.
- Failed tasks show clear errors.
- At least 3 standard strategies run reliably.
- Unit and integration tests cover the core chain.

Current status:

- Mostly implemented.
- Raw artifacts and manifests are archived.
- Frontend shows validation metadata.
- Docker integration test is opt-in and should be run in release validation.

## Level 4 Acceptance

Required:

- standardized data layer.
- data quality validation.
- strategy template library.
- experiment version management.
- parameter optimization.
- strategy comparison.
- out-of-sample testing.
- report export.
- A-share trading rule handling.
- reproducible results.

Current status:

- A-share daily data, benchmark gate, QA gate, LEAN cache, run fingerprint, validation, and experiment metadata are implemented.
- Scheduler leases enforce `maxConcurrentJobs` before LEAN container startup.
- StrategyVersion, DatasetVersion, and Experiment rows are persisted for each backtest run.
- Strategy templates include standard P1 set.
- Result analytics include key metrics and benchmark comparison.
- Optimization/research APIs exist but need stronger acceptance.
- Report export exists as HTML generation; PDF/Markdown/CSV/JSON export is not complete.

## Level 5 Acceptance

Required:

- paper trading.
- real-time data adapter.
- order status tracking.
- risk module.
- run monitoring.
- alerts.
- path from backtest strategy to paper/live strategy.
- architecture isolation for QMT/broker integration.

Current status:

- A-share daily LEAN Paper runs frozen Project snapshots through the standard worker and reconciles historical orders.
- Legacy fixed-signal replay sessions are retained read-only; intraday live data is not enabled.
- Broker/QMT integration should remain isolated behind adapters.

## P0: Main Chain Stability

Completed:

- backtest status lifecycle.
- LEAN Docker Runner.
- isolated result directories.
- artifact manifest.
- raw artifact archive.
- parser and result persistence.
- cancellation route integration.
- minimal UI result visibility.
- tests for runner, parser, reports, A-share benchmark hard failure.

## P1: Trusted Backtest

Completed or partially completed:

- A-share fee model.
- T+1 helper.
- limit/suspension status helper.
- benchmark hard requirement.
- data QA gate.
- run fingerprint.
- validation/experiment JSON.
- scheduler lease/slot enforcement.
- strategy/dataset/experiment version entities.
- UI validation tab.
- standard strategy templates.
- benchmark return, excess return, alpha/beta, Calmar, monthly/yearly returns.

Remaining:

- immutable raw provider snapshots.
- richer version browsing/filtering UI.
- complete report export formats.
- golden standard backtest suite with deterministic expected values.
- broader ETF/convertible/futures validation gates.

## P2: Research and Analysis

Targets:

- batch backtests.
- parameter optimization.
- parameter sensitivity heatmaps.
- strategy comparison UI.
- out-of-sample split.
- rolling window tests.
- walk-forward analysis.
- strategy ranking by return, drawdown, Sharpe, Calmar, stability, trades, OOS performance.

Current partials:

- optimization API.
- factor research APIs.
- performance analytics.
- some P2 tests.

## P3: Paper Trading and Pre-Live

Targets:

- simulated account.
- real-time data adapter.
- order lifecycle.
- risk checks.
- daily replay.
- monitoring and alerts.
- backtest-to-paper consistency report.
- broker adapter boundary for QMT or similar.

Current partials:

- paper sessions, signals, orders, positions, snapshots, daily reports.
- replay acceptance tests.

## Data Boundary

Trusted P1 boundary is A-share daily equity and CSI300-like benchmark data where:

- bars exist for the period.
- trade status exists for the period.
- latest import batch QA passed.
- no critical multi-source QA report blocks the symbol.
- benchmark bars cover the period.
- LEAN cache can be restored or rebuilt.

Everything outside this boundary must be labelled research or partial until it has equivalent gates.
