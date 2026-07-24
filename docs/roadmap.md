# Roadmap

Last reviewed: 2026-07-24. LEAN remains the only production backtest engine. Historical issues and point-in-time evidence are retained in the [2026-07 platform audit](history/platform-audit-2026-07.md), the [2026-07-22 independent audit](history/independent-audit-2026-07-22.md), the [2026-07-23 remediation tracker](history/independent-audit-remediation-2026-07-23.md), the [2026-07-24 independent re-audit](history/independent-audit-2026-07-24.md), and the [history index](history/README.md).

## Level 3: Reliable Backtest Chain

Status: PASS (with open caveats outside Level 3 scope). A fresh independent
production-like re-audit completed on 2026-07-24 returned `LEVEL3_PASS` and
`LEVEL3_PLUS_PASS`:

- Source/QA/reference gates and certification checks are now enforced in
  production-like create/worker paths.
- Daily shadow pipeline and canonical lineage checks passed.
- 1) real LEAN smoke backtest, 2) paper replay, and 3) paper constraints
  acceptance were executed with explicit evidence.

Level 3 remains candidate-bound by remaining open operational and Level 5 work; it
is not automatically elevated above “research production” without the pending
unattended-run and fault-injection evidence.

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

Status: FAIL. The 2026-07-24 production-like execution completed 17 real LEAN
children (9 parameter-grid, 3 rolling, 4 legacy walk-forward and 1 dynamic PIT),
but the strict validator correctly rejected the then-current train/test-only
walk-forward. The code now expands train/validation/OOS with stable lineage and
adds failed-only retry plus cancelled-batch restart; this does not change the
status until the production-like matrix is independently rerun.
The scripted closure path exists via:

- `web/backend/.venv/bin/python scripts/run_level4_audit.py`

The default probe covers a real 3×3 parameter grid plus rolling, walk-forward,
and dynamic PIT. Preview-only proves expansion contracts only; it is never
Level 4 acceptance. Use `--execute --require-csv` and retain the resulting
database rows and artifacts for an acceptance attempt.

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
- Walk-forward train/validation/OOS isolation, validation-only parameter
  selection, and fold/phase anti-leakage fingerprints.
- Failed-only batch retry and cancelled-batch restart that preserve successful
  child runs.
- Structured HTML reports, Markdown export and archived report objects.
- Searchable in-app documentation.

Remaining work:

- Independently execute the new train/validation/OOS, failed-child retry,
  cancel/restart recovery and complete Level 4 browser matrix against real
  MySQL/Celery/Docker LEAN.
- PDF, CSV and JSON report export formats; Markdown is already implemented.
- Richer cross-batch ranking, sensitivity heatmaps and comparison dashboards.
- Complete ETF, convertible-bond, futures and options data-quality gates.
- Full historical PIT coverage for every offered universe, especially CSI300 before 2017-12-08.
- Scheduled incremental Parquet/ClickHouse maintenance with visible independent watermarks.

### Current verification path

- Run:

  `web/backend/.venv/bin/python scripts/run_level4_audit.py --cases parameter_grid,rolling,walk_forward,dynamic_pit --project-id <project-id> --execute --require-csv --base-url <api-url>`

- Evidence output:

  `web/runtime/audit/level4-*.json`

## Level 5: Paper and Operational Safety

Status: replay blocked and operationally not ready. `signal_simulation`
acceptance is not evidence for a real 21-day LEAN walk-forward. Unattended
operation, notification/escalation and full failure-recovery acceptance remain
required.

Current verification path is implemented in:

- `web/backend/.venv/bin/python scripts/run_level5_audit.py --project-id <project-id>`

  Add `--with-fault` to include the service-restart matrix, and `--constraints`
  for policy-reject evidence.

可以省略 `--source-backtest-id`，脚本会自动从 `/api/paper/candidates` 选择该项目的首个可信 backtest 作为 source；若存在跨版本/多结果场景，建议显式传入期望的
`--source-backtest-id <backtest-id>` 锁定复现目标。

The script performs 21-day LEAN Paper, duplicate-call idempotency, optional
service-fault matrix and constraint coverage checks.

Implemented:

- Paper sessions sourced from a successful, validated, frozen backtest project.
- Daily LEAN walk-forward execution, signals, orders, positions, snapshots and daily reports.
- Feature-gated `lean_walkforward_v2` with immutable LEAN-sourced intents,
  legal 13-state transitions, the shared A-share/portfolio constraint layer,
  idempotent fills and ledger entries, ledger-derived cash/position read models,
  and six digest-protected checkpoints.
- A-share T+1, suspension, limit, lot, fee and portfolio constraints in both
  signal simulation and the v2 LEAN intent path.
- Monitoring endpoints, Prometheus/Grafana stack and database-backed task recovery.
- Persistent operational alerts with Webhook delivery, delivery audit records,
  cooldown deduplication and repeated Paper scheduling failure escalation.
- Digest-pinned runtime/base images and a version-pinned Grafana datasource plugin.

Remaining work:

- Run a new compliant 21-day v2 session with both real strategy intents that
  fill and intents that policy rejects; then prove all six recovery phases
  against a no-fault digest without ledger drift.
- Keep v2 disabled outside isolated remediation until that evidence passes;
  legacy sessions remain unchanged.
- Complete unattended daily orchestration and multi-day notification/escalation acceptance evidence.
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
