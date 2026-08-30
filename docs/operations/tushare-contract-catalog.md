# TuShare Contract Catalog

Last reviewed: 2026-08-27.

This document describes the current storage and governance boundary. The retired MySQL typed-source design is preserved as [historical evidence](../history/tushare-commercial-schema-mysql-era-2026-08-12.md).

```text
TuShare contract catalog
  -> Provider raw / Bronze Parquet with immutable revisions
  -> normalized Silver canonical Parquet
  -> PostgreSQL metadata, lineage, watermarks, quality and certification
  -> LEAN / external Qlib / optional ClickHouse consumers
```

The versioned catalog describes structural coverage independently from account permission and local data readiness. A registered contract does not prove that the current credential can fetch it or that a certified local partition exists.

## Storage rules

- Market time series and provider payload facts are Parquet-owned.
- PostgreSQL stores contract identity, run/partition metadata, watermarks, hashes, quality and certification; it must not receive quote time-series tables.
- Bronze current/revisions preserve source evidence; Silver publishes provider-neutral canonical partitions atomically.
- Optional ClickHouse is a rebuildable mirror. DuckDB queries Parquet directly.
- Every published partition records schema version, row count, time/scope coverage and content hash.

## Bulk scope

The Data page one-click scope is the `BULK_DATASET_KEYS` constant in `web/backend/app/services/data_sync.py`. Documentation and UI summaries must derive from that source rather than maintaining a fixed number manually.

## Validation

Contract validation must distinguish structural coverage, provider permission, archive existence, Parquet readability, canonical quality and source certification. Invalid imports fail closed; no operator or documentation workflow may silently reinterpret a contract or manufacture missing PIT history.
