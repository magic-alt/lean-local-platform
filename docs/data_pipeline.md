# Data Pipeline

The data layer supports research tables, A-share reference data, LEAN cache generation, Parquet export, object storage, and quality gates. The current trusted chain focuses on A-share daily data and benchmark coverage for LEAN backtests.

## Layering

```text
Raw source data
  -> import scripts or API adapters
  -> normalized database tables
  -> data quality reports and reference tables
  -> LEAN cache files under Data/
  -> object store archive
  -> optional Parquet datasets
  -> backtest fingerprint and validation metadata
```

## Storage Roles

### Raw

Raw data is fetched by scripts and service adapters:

- `scripts/import_ashare_free_sample.py`
- `scripts/import_csi300_benchmark.py`
- `scripts/import_ashare_reference_public.py`
- `scripts/import_tqsdk_futures.py`
- `web/backend/app/services/ashare_source_adapters.py`
- `web/backend/app/services/tushare_adapter.py`

Raw provider payloads are not yet consistently archived as immutable snapshots. For production research this should become a required step.

### Normalized Database

`web/backend/app/db.py` defines the canonical schema. Key tables:

- `instruments`
- `market_daily_bars`
- `market_trade_status`
- `ashare_daily_bars`
- `ashare_trade_status`
- `trade_calendar`
- `securities`
- `adjustment_factors`
- `corporate_actions`
- `universe_membership`
- `index_membership_events`
- `financial_statements`
- `financial_facts`
- `factor_values`
- `parquet_datasets`
- `parquet_files`
- `data_quality_reports`
- `stored_objects`

MySQL is the default database through `LEAN_DATABASE_URL`. SQLite remains useful for tests and small local runs.

### LEAN Cache

LEAN reads from `Data/`, mounted into Docker as `/Lean/Data:ro`.

For A-share daily equity data, the cache includes:

```text
Data/equity/china/daily/<symbol>.zip
Data/equity/china/factor_files/<symbol>.csv
Data/equity/china/map_files/<symbol>.csv
```

`ensure_ashare_lean_cache()` restores or rebuilds cache files before Docker execution. Cache file hashes are recorded in the run fingerprint.

### Parquet

Parquet support is under `web/backend/app/services/parquet_lake.py` and API routes under `/api/data/parquet/*`.

Parquet is intended for fast research scans and factor analysis. It should not replace the canonical database or LEAN data folder in the production backtest chain.

### Object Store

`stored_objects` and `stored_object_chunks` archive:

- LEAN raw outputs.
- LEAN cache files.
- Reports and generated artifacts.
- Other binary/text objects through `/api/object-store`.

The object store can live in MySQL chunks or local runtime storage depending on configuration.

## Data Quality

Current quality checks include:

- duplicate dates
- invalid OHLC price shape
- abnormal or zero volume
- missing/incomplete A-share bars
- missing trade status
- critical multi-source discrepancy reports
- benchmark row coverage

Important services:

- `data_quality.py`: row normalization and QA.
- `ashare_multisource.py`: source comparison and critical gate.
- `ashare_repository.py`: A-share coverage, status, reference data, universe APIs.
- `backtest_validation.py`: per-run validation summary.

## A-Share Rules Affecting Backtests

The trusted A-share backtest path records and enforces:

- T+1 sell restriction through `AShareExecutionHelper`.
- suspended day buy/sell block through `ashare_trade_status`.
- limit-up buy block.
- limit-down sell block.
- lot size, default 100 shares.
- commission rate.
- minimum commission.
- sell stamp tax.
- transfer fee.
- constant bps slippage.
- explicit benchmark requirement.

Known limitations:

- Matching is still constrained by what LEAN and the helper implement; this is not yet a full exchange simulator.
- Intraday auction rules are not fully modeled.
- Board-specific limit rules depend on the quality of imported trade status and reference data.
- ETF, convertible bond, and futures rules exist partially and need separate acceptance gates.

## Versioning and Fingerprints

Each backtest stores:

- `fingerprint`: git state, parameters hash, data row counts, batch id, cache hashes, Docker image digest.
- `validation`: A-share rules, data gates, benchmark gates.
- `experiment`: strategy, parameters, data, environment, and validation summary.
- `strategy_versions`: strategy path, source hash, git commit, git dirty state.
- `dataset_versions`: data scope, row counts, trade status counts, benchmark rows, cache hashes.
- `experiments`: run-to-version linkage plus full fingerprint/validation snapshots.

The first three fields live on `backtest_runs` as JSON columns. The version records live in normalized tables.

## Upgrade Path

P1 requirements that are still incomplete or partial:

- immutable raw provider snapshots
- richer version browsing and comparison UI
- full data quality reports for ETF, convertible bonds, futures, and factors
- PIT data coverage report for every research universe
- board-specific A-share limit rules as first-class metadata
