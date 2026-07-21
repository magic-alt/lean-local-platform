# Roadmap

Last reviewed: 2026-07-21. LEAN remains the only production backtest engine. Historical issues and point-in-time evidence are retained in the [2026-07 platform audit](history/platform-audit-2026-07.md) and [history index](history/README.md).

## Level 3: Reliable Backtest Chain

Status: implemented; Docker/LEAN integration remains an opt-in release acceptance test.

Implemented:

- Web creation, preflight, task lifecycle, cancellation and failure details.
- Isolated run workspace and pinned LEAN Docker execution.
- Raw artifacts, manifests, parsed results, charts, logs and object archives.
- Scheduler leases enforcing `maxConcurrentJobs` before container startup.
- A-share benchmark, data coverage, QA and execution-rule validation.
- Strategy/dataset/experiment versions and reproducibility fingerprint.

Remaining acceptance work:

- Maintain release-specific golden runs for all production templates.
- Extend exchange-grade matching acceptance beyond the current A-share daily helper.

## Level 4: Data, Experiments and Reproducibility

Status: main workflows implemented; cross-asset breadth is partial.

Implemented:

- MySQL-only runtime fact store, schema migrations and stored-object archive.
- Ten-dataset first full/then incremental TuShare build with checkpoints, heartbeats, watermarks, validation and quarantine.
- On-demand dataset download with selectable storage target and CSV templates.
- Stock, calendar, index, futures and options dataset previews.
- Canonical-row deduplication, lightweight raw index and compressed batch archives.
- Parquet/DuckDB derived layer, consistency reports and optional ClickHouse mirror.
- Strategy template and example catalog for backtests, optimization and research.
- Database-backed experiment batches with bounded dispatch, cancellation, failed-child retry and CSV export.
- Multi-symbol, multi-strategy, independent matrix, parameter grid, rolling-window, dynamic PIT universe and walk-forward workflows.
- Structured HTML reports, Markdown export and archived report objects.
- Searchable in-app documentation.

Remaining work:

- PDF, CSV and JSON report export formats; Markdown is already implemented.
- Richer cross-batch ranking, sensitivity heatmaps and comparison dashboards.
- Complete ETF, convertible-bond, futures and options data-quality gates.
- Full historical PIT coverage for every offered universe, especially CSI300 before 2017-12-08.
- Scheduled incremental Parquet/ClickHouse maintenance with visible independent watermarks.

## Level 5: Paper and Operational Safety

Status: controlled Paper Replay is implemented; unattended production operation remains partial.

Implemented:

- Paper sessions sourced from a successful, validated, frozen backtest project.
- Daily LEAN walk-forward execution, signals, orders, positions, snapshots and daily reports.
- A-share T+1, suspension, limit, lot, fee, slippage and portfolio constraints.
- Monitoring endpoints, Prometheus/Grafana stack and database-backed task recovery.

Remaining work:

- Unattended daily orchestration with notification/escalation and multi-day acceptance evidence.
- Broker integration, reconciliation and secrets hardening before any live trading.
- Industry/capacity risk limits, circuit breakers and cross-asset paper acceptance.
- Restore drills, resource budgets and alert thresholds for MySQL, Redis and Docker.

## Priority Work

### P0: Trust and data coverage

1. Fill and verify CSI300 2005-2017 official PIT membership; never substitute current constituents.
2. Make per-universe PIT coverage visible before batch expansion.
3. Extend explicit adjustment and benchmark contracts to every supported asset class.
4. Keep production dataset permissions, coverage, quarantines and validation results observable.

### P1: Stability and operation

1. Run scheduled MySQL backup/restore and stored-object recovery drills.
2. Add resource-pressure alerts and validate MySQL OOM recovery under Docker memory limits.
3. Complete unattended Paper daily-chain acceptance and notification delivery.
4. Add browser E2E coverage for Data Preview, batch workflows, reports and Docs.

### P2: Research productivity

1. Add ranking and side-by-side comparison across experiment batches.
2. Add parameter sensitivity heatmaps and train/test/OOS visualization.
3. Expand factor normalization, neutralization, portfolio construction and robustness templates.
4. Add complete futures continuous-contract, margin, fee and roll attribution support.

## Definition of Done for New Capabilities

A capability is not complete merely because an endpoint exists. It must have:

- persisted lifecycle and restart behavior;
- explicit data scope, PIT and adjustment semantics;
- structured failure and retry behavior;
- unit tests plus proportional integration/UI validation;
- user-facing documentation and an example where appropriate;
- migration and rollback/compatibility notes for schema changes;
- no deletion of the historical issue that motivated the change.
