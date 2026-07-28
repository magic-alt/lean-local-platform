# Data Pipeline

Last reviewed: 2026-07-21.

MySQL is the runtime source of truth for market/reference data and synchronization state. LEAN files, Parquet and ClickHouse are generated or mirrored layers and must remain rebuildable. SQLite is used only by isolated tests.

## Data Layers

```text
Provider / CSV
  -> normalize, validate, deduplicate, quarantine
  -> MySQL canonical tables and import metadata
  -> LEAN cache for execution
  -> Parquet/DuckDB for analytical scans
  -> optional ClickHouse mirror
```

Key canonical domains include instruments and identifiers, A-share/reference tables, daily bars, trade status, adjustment factors, trading calendars, PIT memberships, futures/options contracts and import/quality metadata.

## One-Click Build and Incremental Update

The Data page exposes exactly 10 bulk datasets:

| Dataset | Purpose |
| --- | --- |
| `stock_basic` | A-share security master and listing state |
| `trade_cal` | Exchange trading calendar |
| `daily` | A-share daily OHLCV |
| `adj_factor` | Adjustment factors and LEAN factor inputs |
| `suspend_d` | Suspension history |
| `stk_limit` | Daily limit-up/limit-down prices |
| `index_basic` | Index master data |
| `index_daily` | Index daily bars and benchmarks |
| `fut_basic` | Futures contract master data |
| `opt_basic` | Options contract master data |

If no successful full build is recorded, the UI says “一键全量更新”. After a successful build, persisted sync metadata makes the same action “一键增量更新”. A restart does not reset this decision.

Sync runs are idempotent, cancellable and resumable. They persist per-dataset progress, true provider call counts, checkpoints, heartbeats, watermarks, validation totals, empty-result counts and quarantined rows. `daily`, `suspend_d` and `stk_limit` use bounded concurrent fetch plus a single batched writer for initial history; everyday sparse-status updates use one market-wide request per trade date. A governed daily rebuild validates and archives every response, compares deterministic database fingerprints, reads exact rows only for mismatching symbols, and writes only missing/provider-corrected dates. `adj_factor` and `stk_limit` likewise skip unchanged canonical rows. Long `daily` requests use safe 22-year windows, while `index_daily` uses capped 2,500-day windows so provider row limits cannot silently truncate history.

The small reference catalogs are fetched across every supported scope: index markets (`MSCI`, `CSI`, `SSE`, `SZSE`, `CICC`, `SW`, `OTH`), futures exchanges (`CFFEX`, `DCE`, `CZCE`, `SHFE`, `INE`, `GFEX`) and option exchanges (`SSE`, `SZSE`, `CFFEX`, `DCE`, `CZCE`, `SHFE`).

## On-Demand Datasets

All registry entries outside the 10 bulk datasets use `sync_policy=on_demand`. They do not participate in one-click update. The user starts them explicitly, chooses an approved host-visible storage target, and may select a database or file/Parquet-oriented result according to the dataset workflow.

The 50 GiB default limit (`LEAN_MYSQL_ON_DEMAND_MAX_DATABASE_GB`) bounds each
on-demand MySQL write estimate. It is not compared with the aggregate MySQL
instance size, which also includes governed bulk-sync data, and it does not cap
one-click construction. Aggregate growth remains subject to the physical disk
reserve.

## Correctness and Audit Chain

Every provider batch is checked in stages:

1. Verify endpoint permission, request scope and response schema.
2. Normalize identifiers, dates, numbers and nulls.
3. Validate required fields, primary keys, date ranges and OHLC relationships.
4. Deduplicate within the response and upsert using canonical keys.
5. Resolve trade-status source precedence in memory or per batch.
6. Quarantine invalid rows with reason and source metadata.
7. Persist manifest counts, request/payload hashes, validation results and watermarks.
8. Compare database counts/date bounds and, where configured, cross-source or Parquet consistency.

“Processed” is not equivalent to “inserted”: idempotent replays can process valid rows while updating or skipping existing keys. A zero-row result may be legitimate for a symbol/date scope, but is recorded separately for coverage analysis.

## Raw Provider Retention

`provider_raw_records` is a lightweight key/date/hash index. It does not store a complete JSON document for every canonical row.

- Losslessly represented canonical datasets retain standard-table rows plus request, key and payload hashes.
- Responses that cannot be mapped losslessly are serialized once per batch, gzip-compressed, content-addressed and cataloged by `provider_raw_archives` in the MySQL object store.
- This removes the former third copy of large payloads while preserving source/batch auditability.

Historical row JSON can be cleaned with:

```bash
cd web/backend
.venv/bin/python ../../scripts/cleanup_provider_raw_json.py --help
```

The script validates the target, clears JSON in resumable key ranges and preserves record hashes/metadata. Do not truncate `provider_raw_records`. Physical disk space usually is not returned until a separate low-traffic InnoDB table-space rebuild, which needs temporary free space and a backup.

## CSV Import

Download a schema-specific template from `GET /api/data/import-csv/template` before importing. The backend validates required columns and data types before converting supported equity, crypto and futures daily files into canonical/LEAN formats. Invalid CSV input is rejected with actionable field errors rather than partially imported silently.

## Dataset Preview

`GET /api/data/dataset-preview/{dataset}` supplies data-aware previews:

- stocks: profile, daily bars, adjustment factors, suspension and limit history;
- trading calendar: market/date sessions;
- indexes: index master and daily bars;
- futures/options: contract master data.

Preview values are JSON-safe and formatted defensively so an unfamiliar Provider field cannot blank the full application.

## Derived Layers

### LEAN cache

LEAN consumes files from `LEAN_DATA_DIR`. Before a run, required files can be restored from `stored_objects` or rebuilt from MySQL canonical data. Their identifiers and hashes are included in the run fingerprint.

### Parquet and DuckDB

`parquet_datasets` and `parquet_files` track scope, row counts, date ranges, hashes and schema versions. Consistency jobs compare MySQL counts/date ranges, file hashes and DuckDB reads. Parquet is not a metadata database.

### ClickHouse

ClickHouse is optional and mirrors committed MySQL data. Health/table checks should occur at task/batch scope, writes should be accumulated, and mirror failure must have an independent retry/watermark rather than rolling back authoritative MySQL data.

Weekday post-close maintenance incrementally rewrites only affected Parquet
years and mirrors ClickHouse from its own last successful boundary. The two
layers persist independent scope/source watermarks and run history; one layer
can fail or lag without promoting the other or changing MySQL.
When an existing ClickHouse scope has no persisted watermark, bootstrap compares
deduplicated row counts by trading date and replays only deficient dates. It
refuses to hide surplus derived rows behind a successful watermark; those
require an explicit governed rebuild.

## Disk Safety and Size Reporting

- One-click sync has no database-size ceiling.
- It stops before free disk would fall below `max(500 GiB, 50% of total capacity)`.
- API and workers use the same read-only MySQL data-directory observer mount so the catalog and live task report the same physical allocated size.
- Logical table size, InnoDB allocated size and host free disk are different metrics; documentation and UI label the physical value explicitly.
- Bulk loader sessions disable binlog for rebuildable provider data. Business metadata retains normal durability; binlogs use minimal row images and expire by configuration.

## A-Share Backtest Contract

Trusted China-equity runs require canonical daily bars, a real benchmark, trading calendar and applicable execution status. The helper enforces T+1 selling, suspension and limit blocks, lot rounding, cash buffer, fees and slippage. The run stores fingerprint, validation and experiment snapshots plus normalized strategy/dataset version links.

Known limitations remain: intraday auction mechanics are incomplete and
board-specific rules depend on imported reference quality. Dataset completion
now runs asset-specific ETF, convertible-bond, futures and options gates for
identity, lifecycle, trading terms, OHLC, settlement and open interest.

## Remaining Data Work

- Maintain the immutable CSI300 bundle and record any official corrections
  without substituting the `CSI300_TUSHARE` shadow universe.
- Close the certified launch-date gaps for CSI500, CSI1000, SSE50 and STAR50
  using immutable official/licensed evidence; partial TuShare snapshots remain
  queryable but cannot be promoted as complete.
- Extend cross-asset gates to factor inputs and exchange-specific microstructure.
- Cross-asset adjustment, continuous-contract and corporate-action acceptance.
