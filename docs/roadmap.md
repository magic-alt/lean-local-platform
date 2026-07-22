# Roadmap

Last reviewed: 2026-07-22. LEAN remains the only production backtest engine. Historical issues and point-in-time evidence are retained in the [2026-07 platform audit](history/platform-audit-2026-07.md), the [2026-07-22 independent audit](history/independent-audit-2026-07-22.md), and the [history index](history/README.md).

## Level 3: Reliable Backtest Chain

Status: remediation candidate, not passed. The 2026-07-22 independent audit
reported `LEVEL3_FAIL`. Source/QA/reference gates, canonical fingerprints,
archive integrity and container admission have since been hardened, but a new
independent production-like re-audit is required before changing this status.

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

Status: failed in the 2026-07-22 independent audit. The workflows exist, but
complete rolling/walk-forward/dynamic-PIT execution evidence, portable CSI300
source evidence and production-scale consistency acceptance remain incomplete.

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

Status: replay blocked and operationally not ready. `signal_simulation`
acceptance is not evidence for a real 21-day LEAN walk-forward. Unattended
operation, notification/escalation and full failure-recovery acceptance remain
required.

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

1. Re-run the independent Source/QA/reference gate matrix against certified production data.
2. Retain or make fetchable the immutable official CSI300 source bundle; fill and verify 2005-2017 PIT membership without current-constituent substitution.
3. Prove canonical fingerprint/result digest repeatability with release golden runs.
4. Reconcile all archive references and complete ten-dataset manifest/watermark/archive evidence.

### P1: Stability and operation

1. Run scheduled production-scale MySQL backup/restore and stored-object recovery drills.
2. Complete five-job concurrency, phase cancellation and Redis/MySQL/worker fault injection.
3. Complete a real 21-day LEAN Paper chain with interruption/idempotency evidence.
4. Add notification/escalation, resource-pressure alerts and an operational runbook.

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
