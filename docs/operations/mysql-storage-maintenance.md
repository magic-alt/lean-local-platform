# MySQL Storage Maintenance

This runbook reduces MySQL allocation without silently deleting market data.
All mutating commands require `--confirm`; run the matching read-only command
first. Stop API/worker writes during `OPTIMIZE` and A-share cutover operations.

## 1. Remove duplicate indexes

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py report
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py index-status
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py hide-indexes --confirm
```

Run one daily sync, a representative A-share screen, and a standard backtest.
Compare returned row counts and result hashes with the baseline. If any query
regresses, restore the indexes with `restore-indexes --confirm`. Otherwise,
after the observation period, run `drop-indexes --confirm`; schedule
`optimize --tables factor_values,market_daily_bars,ashare_daily_bars,ashare_trade_status --confirm`
only when free disk can hold the largest target table plus 30%.

## 2. Retire covered legacy daily_basic EAV rows

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py eav-audit
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  delete-equivalent-eav --batch-size 10000 --confirm
```

Only records whose same-source wide-column value is present and equal are
deleted. Uncovered, unknown, null-wide, and mismatched values remain readable
through the compatibility view. Repeat `eav-audit`, then rebuild
`factor_values` in a maintenance window if physical space must be returned.

## 3. Move binary objects outside MySQL

Compose defaults new objects to filesystem mode under
`$LEAN_DATA_DIR/object-store`; this directory must be backed up with `Data/`.
Migrate old chunk-backed objects in restart-safe batches:

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  migrate-objects --limit 1000 --confirm
```

Each object is copied atomically, checked by SHA-256, marked `filesystem`, and
only then has its MySQL chunks removed. `provider-raw`, PIT evidence, and
reproducibility certificates are retained. Only `backtest-results`,
`lean-data-files`, and `pipeline-artifacts` older than 180 days are eligible
for removal:

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  prune-artifacts --retention-days 180 --confirm
```

After migration, online raw-record keys older than 180 days can be pruned only
when an archive for their original batch remains checksum-readable:

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  prune-raw-records --retention-days 180 --limit 10000 --confirm
```

## 4. A-share canonical-table cutover

Deploy the release, set `LEAN_ASHARE_CANONICAL_WRITES=1` for API and workers,
then pause writes and run:

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py prepare-ashare --confirm
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py ashare-coverage
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py cutover-ashare --confirm
```

Cutover refuses to run if any A-share row lacks its same-source canonical
market-table counterpart. It renames the old tables to `legacy_*` and creates
read-compatible `ashare_*` views over `market_*`. Keep the legacy tables for
14 days and validate a sync, screen, and backtest. Only then run
`drop-ashare-legacy --confirm`; reverting consists of restoring the legacy
tables/views while writes are paused.

## 5. Direct rebuild of regenerable market data (no backup)

This is the intentionally destructive option for a full redownload. It does
not touch projects, settings, backtest rows, Paper records, task history, or
strategy metadata. It does clear all shared provider/canonical market data
(including non-A-share data), financial facts, raw dedupe records and their
provider-raw objects. Financial data is deliberately **not** added to the
post-reset bulk download selection.

The command first refuses to run if active task, sync, pipeline, or derived
maintenance rows exist. It truncates MySQL base tables (returning their
InnoDB table space), removes the physical duplicate A-share tables, creates
read-compatible views, invalidates Parquet/Dataset Release certificates
without deleting backtest references, clears the enabled ClickHouse mirror,
and removes only `$LEAN_PARQUET_DIR` contents plus the external
`provider-raw` object namespace. When provider-raw chunks were still stored
in MySQL, it also rebuilds the remaining `stored_object_chunks` table to
return those deleted pages. It writes an audit JSON under
`web/runtime/maintenance-audits/`.

Before the window, deploy this release (Compose defaults
`LEAN_ASHARE_CANONICAL_WRITES=1` and filesystem object storage), then enable
the API write gate and stop all writers:

```bash
export LEAN_MAINTENANCE_READ_ONLY=1
docker compose up -d api
docker compose stop worker data-worker data-demand-worker backtest-worker beat lean-runner
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py market-reset-plan
```

`market-reset-plan` reports approximate InnoDB row counts and the preserved
table groups without scanning large fact tables. The live reset requires all
three acknowledgement flags because this installation explicitly chose no
backup and no shadow-table rollback:

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  direct-market-reset --confirm --no-backup --direct-reset
```

After the command succeeds, restart writers with the same
`LEAN_MAINTENANCE_READ_ONLY=1` setting, then create a **selected** A-share
download with the `postResetBulkDatasets` list reported by `market-reset-plan`
(it deliberately omits `dividend` and all financial datasets). Validate
source/date/row coverage, then remove the gate and restart API/workers
normally. Do not use the Data page's old “full rebuild” button to reclaim
existing `.ibd` files: it refreshes data but does not perform this controlled
physical-table reset.

## 6. Purge all backtests and MySQL-resident generated artifacts

For an intentionally clean execution history, inspect the scope and then run:

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py backtest-purge-plan
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py purge-backtests --confirm
```

This deletes backtest/result/task rows, experiment and Walk-forward output,
optimization and Qlib intermediates, generated dataset-version snapshots, and
the `backtest-results`, `lean-data-files`, `pipeline-artifacts`,
`reproducibility-certificates`, and current Qlib `object-store` namespaces.
It preserves projects, settings, strategy versions, Paper records, provider
state, and `universe-pit` evidence. The command is foreign-key aware and
rebuilds the residual object tables after deletion.

Generate a current, content-free local schema reference with exact row counts:

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  schema-report --output docs/operations/mysql-schema-current.md
```
