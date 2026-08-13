# Current MySQL Schema Boundary

Last reviewed: 2026-08-13.

MySQL is the platform control plane. It stores configuration, instruments and identifiers, task/sync state, dataset registry and manifests, quality/certification, projects, experiments, backtests, Paper/OMS/Risk state, reports and audit evidence.

Stock time series are intentionally absent. Migration `0051_market_lake_authority` retires:

- `market_daily_bars`, `market_intraday_bars`, `market_trade_status`;
- `adjustment_factors`, `daily_basic_values` and their compatibility views;
- the corresponding v2 daily bar/metric/status tables and selection view.

The authoritative market data is the Parquet hierarchy under `LEAN_MARKET_DATA_DIR` (default `data/`). A fresh database may apply older additive migrations first for migration-history compatibility, but `0051` removes those obsolete relations before startup completes.

Generate a machine-specific control-plane schema report against the running MySQL instance when required:

```bash
web/backend/.venv/bin/python scripts/mysql_storage_maintenance.py \
  schema-report --output web/runtime/audit/mysql-schema-current.md
```

Generated reports belong under `web/runtime/` and must not be treated as a market-data inventory. Use Parquet manifests, the Data page and `/api/data/parquet/datasets` for stock-data coverage.
