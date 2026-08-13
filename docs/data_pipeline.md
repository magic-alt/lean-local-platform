# Data Pipeline

Last reviewed: 2026-08-13.

Parquet under `data/` is the source of truth for market time series. MySQL is the control-plane store for synchronization state, manifests, watermarks, quality, certification and business/runtime records. SQLite is used only by isolated tests.

## Data layers

```text
Provider / CSV
  -> normalize, validate, deduplicate, quarantine
  -> Bronze Parquet + immutable revisions
  -> Silver normalized Parquet
  -> Gold PIT / adjusted / feature views
  -> LEAN cache and read-only Qlib consumers
  -> optional ClickHouse serving mirror

MySQL
  <- task, manifest, lineage, watermark, QA and certification metadata
```

The default root is `data/`. A-share daily reads use `silver/daily/current/trade_date=YYYYMMDD/data.parquet`; adjustment factors and daily-basic facts use their Bronze current partitions. No pipeline stage writes stock bars, status, adjustment factors or daily-basic time series to MySQL.

## One-click build and incremental update

The Data page bulk scope is defined by `BULK_DATASET_KEYS` and currently includes security/trading-calendar reference data plus daily bars, adjustment, status, index, futures and options basics. The checked-in TuShare contract catalog also exposes on-demand datasets independently of the bulk scope.

Before the first successful build, the UI offers a full update. After manifests and watermarks exist, it offers an incremental update. Restarts do not reset this state.

Daily market writes follow this contract:

1. Check endpoint permission and bounded request scope.
2. Normalize identifiers, dates, numbers and nulls.
3. Validate schema, unique keys, OHLC bounds and coverage.
4. Write a temporary Bronze Parquet partition.
5. Archive an existing partition and manifest under `bronze/tushare/revisions/`.
6. Atomically publish Bronze current and normalized Silver current.
7. Persist batch, checkpoint, watermark, row counts, hashes and quality state in MySQL.
8. Revoke affected certification until file and DuckDB checks pass again.

Sync runs remain cancellable and resumable. Provider call count, processed/landed/quarantined row count, checkpoint and heartbeat are independent. Idempotent replay may process rows without changing the published partition.

## On-demand data

Datasets outside the bulk scope are started explicitly. Market facts use an approved Parquet/file target; there is no MySQL market-table target or MySQL-size gate. Every target must be host-visible to the worker, remain inside an allowlisted data/export root and pass free-space checks.

Provider-native reference contracts may use compatibility typed-source tables only when `LEAN_TUSHARE_TYPED_SOURCE_WRITES=1`. The default is off, and this option must never recreate removed market time-series tables.

## Raw retention and revisions

Losslessly normalized TuShare daily data is retained in Bronze with provider-shaped fields and a per-partition `manifest.json`. When a current date is corrected, the old `data.parquet` and manifest are copied to a content-hash revision directory before publication.

Responses that do not map losslessly to a governed dataset can be stored once as gzip-compressed, content-addressed raw archives. `provider_raw_records` is only a lightweight key/date/hash index, not another market-data copy.

## Reading and Preview

Backend services read through `app.services.market_lake`. DuckDB queries current Parquet partitions with projection and filter pushdown. The API accepts `source=parquet` or `source=duckdb`; removed `mysql`, `database` and `local` aliases fail closed.

Dataset Preview reads local Parquet or governed archives and never calls a Provider just because a page is opened. Supported views include securities, daily bars, adjustment factors, suspension/limit history, calendars, indexes and derivative reference records.

## Derived layers

### LEAN

LEAN files are generated/restored from Silver/Gold and included in run fingerprints. They are caches: deleting them must not remove canonical Parquet data.

### Qlib

`data/qlib` and `gold/qlib_staging` are external, read-only materializations. lean-platform may consume them, but never modifies the Qlib repository or publishes into those directories.

### Registry and DuckDB

`parquet_datasets` and `parquet_files` catalog paths, scope, coverage, versions and hashes in MySQL. Registering a dataset discovers existing files; it is not a database-to-Parquet export. DuckDB is a query engine, not a metadata database.

### ClickHouse

ClickHouse is optional and mirrors Parquet facts for serving. It has an independent health/watermark boundary and can lag or fail without changing the authoritative lake.

## CSV import

Download a schema-specific template from `GET /api/data/import-csv/template`. Supported rows are validated, normalized and written through the same market-lake contract. Invalid input is rejected before publication rather than partially inserted.

## Disk safety and backup

Data download checks the filesystem holding `LEAN_MARKET_DATA_DIR`. UI and monitoring must report that filesystem separately from MySQL allocation. Backups must include the complete `data/` lake and an independent MySQL control-plane dump; neither alone is a complete recovery set.

## A-share research/backtest gate

Trusted China-equity runs require Parquet coverage for the requested bars, a real benchmark, trading calendar, adjustment/status rules and PIT universe inputs. Each run records dataset version, partition hashes, certification and LEAN cache state. Current constituents may not substitute for missing historical PIT membership, and provider labels alone never grant production trust.

See [Market Data Lake](market_data_lake.md) and [Data help](help/data.md) for concrete paths and API examples.
