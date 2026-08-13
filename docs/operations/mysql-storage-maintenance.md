# MySQL Storage Maintenance

MySQL maintenance now applies only to the control plane. Stock bars, intraday bars, trade status, adjustment factors and daily-basic facts live in `data/` Parquet and must never be recreated or reset through MySQL maintenance commands.

All mutating commands require `--confirm`; run the corresponding read-only report first and stop affected API/worker writes during table rebuilds.

## Schema and allocation reports

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py report
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  schema-report --output web/runtime/audit/mysql-schema-current.md
```

MySQL allocation represents control-plane state and object metadata, not the size of the market-data lake. Check `LEAN_MARKET_DATA_DIR` separately for stock-data capacity.

## Legacy daily-basic EAV cleanup

Old `factor_values` rows from `tushare:daily_basic` may be removed only when the same value exists in canonical daily-basic Parquet:

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py eav-audit
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  delete-equivalent-eav --batch-size 10000 --confirm
```

Uncovered, unknown, null and mismatched EAV values remain. This is a compatibility cleanup, not a market-data write path.

## Object migration and retention

New objects default to filesystem mode under `$LEAN_DATA_DIR/object-store`; back up that directory with the full lower-case `data/` lake.

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  migrate-objects --limit 1000 --confirm

web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  prune-artifacts --retention-days 180 --confirm

web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  prune-raw-records --retention-days 180 --limit 10000 --confirm
```

Objects are copied atomically and SHA-256 checked before chunk removal. Provider raw evidence is pruned only when its archived object remains readable.

## Index and table maintenance

Only indexes returned by `index-status` and explicitly allowlisted tables may be changed:

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py index-status
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py optimize \
  --tables factor_values --confirm
```

The former direct market reset and market-reset plan commands are removed. To redownload stock data, use the Data workflow and a reviewed Parquet partition/revision procedure; do not delete the entire `data/` root and do not touch Qlib-owned directories.

## Backup boundary

Before control-plane maintenance, create and verify a MySQL logical backup. Separately back up `data/` including Bronze revisions, Silver, Gold, registry and quality. A MySQL dump cannot restore stock prices, and a Parquet backup cannot restore accounts, tasks or audit state.
