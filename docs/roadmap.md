# Roadmap

Last reviewed: 2026-07-26. LEAN remains the only production backtest engine. Historical issues and point-in-time evidence are retained in the [2026-07 platform audit](history/platform-audit-2026-07.md), the [2026-07-22 independent audit](history/independent-audit-2026-07-22.md), the [2026-07-23 remediation tracker](history/independent-audit-remediation-2026-07-23.md), the [2026-07-24 independent re-audit](history/independent-audit-2026-07-24.md), the [2026-07-25 P0 trust release](history/p0-trust-release-2026-07-25.md), and the [history index](history/README.md).

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

Status: FAIL, with the non-browser real-stack execution matrix now PASS. On
2026-07-26 the MySQL/Celery/Docker LEAN audit passed the 3x3 parameter grid,
three rolling folds, train/validation/OOS walk-forward with validation-only
selection, and dynamic PIT execution with CSV evidence. A separate destructive
audit passed three-child failed-only retry and five-child cancel/restart while
preserving the successful child's attempt count. Level 4 remains FAIL because
this audit session exposed no controllable browser instance, four offered
universes still lack immutable launch-to-first-licensed-snapshot history, and
the real catalog has not yet populated or recertified all cross-asset datasets
under the new fail-closed quality rules.
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
- PDF, CSV and versioned JSON report exports from the same canonical payload.
- Cross-batch ranking/comparison, parameter-sensitivity heatmaps and
  Train/Validation/OOS visualizations.
- Dataset-completion quality gates for ETF, convertible-bond, futures and
  options identity, lifecycle, trading terms and daily-market invariants.
- Per-universe launch-aware PIT certification with immutable bundle/digest
  evidence; CSI500, CSI1000, SSE50 and STAR50 licensed histories are imported
  but correctly remain partial where their source begins after launch.
- Weekday incremental Parquet/ClickHouse maintenance with independent
  scope/source watermarks, advisory locking, bounded date-count drift repair
  and visible run history. The 2026-07-26 real maintenance run completed four
  ready scope/layer watermarks through 2026-07-22 with Parquet consistency PASS.
- Searchable in-app documentation.

Remaining work:

- Complete the Level 4 interactive browser matrix when an in-app Browser or
  Chrome control instance is available. The API/worker/LEAN matrix is complete;
  a frontend production build is not a substitute for UI interaction evidence.
- Populate the real ETF, convertible-bond, futures and options datasets and
  recertify their manifests under `cross-asset-quality-v1`. On 2026-07-26 the
  fail-closed ledger correctly reported nine missing datasets and two legacy
  successful manifests without the new asset-quality evidence.
- Close immutable official/licensed launch-date gaps for CSI500
  (`2007-01-15..2007-01-30`), CSI1000
  (`2014-10-17..2015-03-30`), SSE50
  (`2004-01-02..2009-04-29`) and STAR50
  (`2020-07-22..2020-07-30`). Current or later snapshots must not be
  substituted to manufacture a pass.

### Current verification path

- Run:

  `web/backend/.venv/bin/python scripts/run_level4_audit.py --cases parameter_grid,rolling,walk_forward,dynamic_pit --project-id <project-id> --execute --require-csv --base-url <api-url>`

- Evidence output:

  `web/runtime/audit/level4-real-core-20260726.json`,
  `web/runtime/audit/level4-real-dynamic-pit-20260726.json`,
  `web/runtime/audit/level4-real-recovery-20260726.json`, and
  `web/runtime/audit/level4-derived-maintenance-20260726.json`.

## Level 5: Paper and Operational Safety

Status: **LEVEL5_FAIL** — see the [2026-07-26 platform system
review](audit/level5-platform-system-review-2026-07-26.md) and its
[remediation checklist](audit/level5-remediation-checklist-2026-07-26.md).
The prior “local production-like Paper interruption acceptance PASS” statement
is withdrawn: it reused prior evidence and cannot establish current canonical
state correctness. Level 5 remains blocked by untrusted Paper valuation and
benchmark accounting, mutable ledger handling, unverified recovery, failed
notification delivery, absent backup evidence, and restricted-runner gaps.

Current verification path is implemented in:

- `web/backend/.venv/bin/python scripts/run_level5_audit.py --project-id <project-id>`

  Add `--with-fault` to include the service-restart matrix, and `--constraints`
  for policy-reject evidence.

可以省略 `--source-backtest-id`，脚本会自动从 `/api/paper/accounts/candidates` 选择该项目的首个可信 backtest 作为 source；若存在跨版本/多结果场景，建议显式传入期望的
`--source-backtest-id <backtest-id>` 锁定复现目标。

The script performs 21-day LEAN Paper, duplicate-call idempotency, optional
service-fault matrix and constraint coverage checks. Evidence reuse is reported
as `revalidated_from_prior_evidence`, never as a passing certification.

Implemented:

- Paper multi-account brokerage workspace with isolated account generations,
  immutable opening balances, Decimal ledger bridges and rebuildable projections.
- Frozen/versioned strategy deployments sourced only from trusted
  `/api/paper/accounts/candidates`, with one active `paper_execute` primary per account
  and optional `signal_only` deployments.
- Unique daily execution cycles, 60-second due coordination, explicit
  queued/running/waiting-data states, duplicate Beat/Run-now idempotency,
  orphan recovery and a durable notification outbox.
- Paginated account overview, positions, orders, trades, signals, performance,
  cycles, reports and audit APIs plus 2–10 account comparison.
- Paper sessions sourced from a successful, validated, frozen backtest project.
- Daily LEAN walk-forward execution, signals, orders, positions, snapshots and daily reports.
- Default-enabled `lean_walkforward_v2` with immutable LEAN-sourced intents,
  legal 13-state transitions, the shared A-share/portfolio constraint layer,
  idempotent fills and ledger entries, ledger-derived cash/position read models,
  and six digest-protected checkpoints.

The new account layer is implemented but is not marked operationally ready
until `scripts/run_paper_accounts_acceptance.py` produces
`PAPER_ACCOUNTS_PASS` against a real trusted candidate, MySQL, Redis, Celery and
restricted LEAN Docker lane. The 2026-07-25 development database currently has
no `/api/paper/accounts/candidates` result suitable for that new acceptance, so this
release gate remains explicit rather than inferred from unit tests.
- A-share T+1, suspension, limit, lot, fee and portfolio constraints in both
  signal simulation and the v2 LEAN intent path.
- Monitoring endpoints, Prometheus/Grafana stack and database-backed task recovery.
- Persistent operational alerts with Webhook delivery, delivery audit records,
  cooldown deduplication and repeated Paper scheduling failure escalation.
- External 2xx-gated Paper outbox state, fail-closed alert-channel readiness and
  automatic backfill of open alerts after channel recovery.
- Independent primary/escalation Webhooks, forced recovery notifications, and
  disk/memory/CPU/Celery-queue pressure alerts with automatic resolution.
- Five accepted LEAN jobs under a two-active/three-queued budget, queued and
  running cancellation, and worker/Redis/MySQL restart invariants.
- Durable Paper finalization recovery after worker SIGKILL, lightweight
  checkpoint/run probes, and terminal state only after all six v2 checkpoints.
- Operational runbook for alert ownership, resource pressure, fault drills,
  recovery order, and release blocking.
- Digest-pinned runtime/base images, exact hash-locked Python dependencies,
  locally generated/scanned SBOMs and signed vulnerability-policy evidence.
- Daily retained MySQL backups and an isolated restore-drill runner that records
  measured RPO/RTO, sampled table row-count differences and checksums.

Remaining work:

- Complete extended unattended multi-day notification delivery acceptance
  against production on-call endpoints; local dual-channel lifecycle tests pass.
- Broker integration, reconciliation and secrets hardening before any live trading.
- Industry/capacity risk limits, circuit breakers and cross-asset paper acceptance.
- Stored-object/filesystem recovery on an independent host; the full-size local
  MySQL restore drill is now automated and evidence-producing.

## Priority Work

### P0: Trust and data coverage

Status: COMPLETE on 2026-07-25. Machine-readable evidence and checksums are in
`audit-output/p0-trust-2026-07-25/`.

1. Independent certified-production Source/QA/reference matrix: passed all
   positive and fail-closed cases.
2. Official CSI300 immutable bundle and 2005-2017 PIT without
   current-constituent substitution: passed.
3. Two real LEAN release golden runs with equal canonical input/result digests:
   passed.
4. Ten-dataset manifest/watermark/archive evidence and all historical archive
   references: passed; 37 retained issues reconciled, 0 open.

### P1: Stability and operation

1. COMPLETE for scheduled full-size MySQL backup/isolated restore; independent
   stored-object/filesystem recovery remains required.
2. COMPLETE — five-job concurrency, phase cancellation and Redis/MySQL/worker
   fault injection: `web/runtime/audit/p1-stability-2026-07-25.json`.
3. COMPLETE — real 21-day LEAN Paper chain with interruption/idempotency:
   `web/runtime/audit/level5-p1-2026-07-25/level5-audit.json`.
4. COMPLETE — independent notification/escalation, resource-pressure alerts
   and `docs/operations/level5-runbook.md`.

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
