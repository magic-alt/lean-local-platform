# Market Data Lake

`$LEAN_DATA_DIR` (default: `<repository>/data`) is the sole authority for market time series. PostgreSQL remains the control-plane database for instruments, universes, jobs, runs, accounts, orders, risk, and audit metadata; it does not store stock bars, trade status, adjustment factors, or daily-basic time series.

The runtime reads the existing hierarchy directly:

```text
data/
├── bronze/tushare/current/
│   ├── daily/
│   ├── adj_factor/
│   ├── daily_basic/
│   ├── stk_limit/
│   └── suspend_d/
├── bronze/tushare/revisions/
├── silver/daily/current/trade_date=YYYYMMDD/data.parquet
├── gold/qlib_staging/
└── qlib/versions/
```

Daily equity reads use `silver/daily/current`. Adjustment and daily-basic reads use the corresponding bronze current partitions. The CSI300 benchmark may be read from its gold staging file. Qlib files and versions are never mutated by the LEAN platform.

Incremental writes merge the affected date partition, write a temporary Parquet file, retain the previous file in `bronze/tushare/revisions/lean_*`, and atomically replace the current file and manifest. Consumers therefore never observe a partially written partition.

Configuration defaults are:

```text
LEAN_DATA_DIR=<repository>/data
LEAN_MARKET_DATA_DIR=<repository>/data
LEAN_PARQUET_DIR=<repository>/data/output/parquet
```

`GET/POST /api/data/query` accepts Parquet as the local source. The removed `mysql`, `database`, and `local` source aliases fail closed. The former database-to-Parquet export and rebuild endpoints are retired because Parquet is no longer a derived copy of SQL market tables.
