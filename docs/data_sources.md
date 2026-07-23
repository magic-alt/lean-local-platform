# Data Sources and Governance

Last reviewed: 2026-07-23.

LEAN is the execution engine; this repository remains responsible for provider
access, licensing, normalization, quality checks and local storage. Downloaded
market data and provider source files are runtime data and must not be committed
to Git.

## Provider roles

| Provider | Role | Persistence policy |
| --- | --- | --- |
| TuShare Pro | Only eligible China production provider; eligibility still requires persisted certification | Canonical MySQL, verified batch lineage, compressed archives and certified Parquet evidence |
| AKShare | Public reference, selected China/Hong Kong fallback and preview support | Research/reference rows only; explicit `allowResearchSource=true` required |
| JQData / RQData | Licensed research and PIT coverage where configured | Research rows only; imported with local credentials and entitlement checks |
| TQSDK | Futures contract and market-data workflows | Imported on demand with provider attribution |
| CSV | User-supplied portable import | Validated against the downloadable templates before canonical write |
| Binance and other public adapters | Non-China research workflows | Subject to current availability, rate limits and source certification |

Provider availability does not imply permission to redistribute data. Operators
must comply with each provider's account terms, exchange rules and retention
requirements. Credentials belong in `.env` or the runtime secret directory and
must never appear in source-controlled files.

## TuShare full-library contract

The Data page manages ten core datasets in the one-click build/update workflow:
`stock_basic`, `trade_cal`, `daily`, `adj_factor`, `suspend_d`, `stk_limit`,
`index_basic`, `index_daily`, `fut_basic` and `opt_basic`. `daily_basic` is an
on-demand canonical dataset and is not part of the ten-dataset one-click scope.

- Before the first successful library build, the UI exposes a full update.
- After the build marker and dataset watermarks exist, the same workflow is an
  incremental update.
- Datasets marked on-demand are downloaded separately and allow the operator to
  choose an approved storage target.
- Provider calls, processed rows, inserted rows, validation, quarantine,
  checkpoint and heartbeat state are persisted independently.

See [Data Pipeline](data_pipeline.md) for normalization, validation, recovery
and archive details.

## Storage boundaries

```text
TuShare / other providers
        -> validation and normalization
        -> MySQL canonical tables
        -> compressed provider batch archives and metadata
        -> rebuildable LEAN cache under LEAN_DATA_DIR
        -> optional Parquet / ClickHouse derived copies
```

- MySQL is the canonical runtime fact store.
- `web/runtime/` contains local runs, projects, reports, uploads, source caches
  and object-store files. It is excluded from Git.
- `LEAN_DATA_DIR` defaults to the workspace-level `Data` directory outside this
  repository. LEAN zip, factor and map files are rebuildable caches.
- `LEAN_PARQUET_DIR` defaults to `LEAN_DATA_DIR/parquet`; DuckDB only queries
  those derived exports.
- Portable source manifests live in `config/data-sources/`. They may contain
  logical source names, hashes and manual corrections, but never local absolute
  paths or downloaded documents.

## Correctness and verification

Every import must retain provider identity, batch or archive identity and its
coverage window. Validation includes schema/type normalization, primary-key
deduplication, OHLC bounds, positive prices and adjustment factors, trade-date
coverage, source-priority rules and dataset-specific checks. Invalid records are
quarantined rather than silently accepted.

For production research, verify:

1. Dataset sync state is successful and its watermark covers the requested end date.
2. Validation has no critical report or unresolved quarantine.
3. Symbol, exchange, market and provider identifiers resolve to one canonical instrument.
4. Benchmark, trade status, adjustment and PIT universe data cover the full backtest window.
5. The run fingerprint records dataset versions, hashes, source certification and LEAN cache state.

The platform must not substitute current constituents for missing historical
PIT membership or silently mix providers with different adjustment semantics.
Provider name is never sufficient certification. Any canonical write revokes
the affected derived certification; promotion requires a successful TuShare
batch lineage plus a persisted MySQL/Parquet/DuckDB/file-hash consistency
report. Synthetic and `environment=research` batches cannot be promoted.

## Portable CSI300 evidence

`config/data-sources/csi300_pit_sources.json` records the verified official
source hashes, coverage boundary and manual events. Referenced XLS/PDF files are
resolved below `web/runtime/source-cache/csi300-official/` or an explicit
`--cache-dir`; the manifest itself is machine-independent.

The production manifest references an operator-retained offline official-source
bundle and intentionally fails validation if an attachment is absent or its
hash differs. To test the portable parser without that bundle, use the tracked
example manifest:

```bash
web/backend/.venv/bin/python scripts/import_csi300_pit_public.py \
  --manifest config/data-sources/csi300_pit_sources.example.json \
  --dry-run --validate
```

The current verified official-cache reconstruction starts at 2017-12-08. The
earlier CSI300 history remains an explicit coverage gap in the living roadmap.

TuShare Pro also exposes monthly `index_weight` snapshots. They are useful as
an independent historical cross-check, but are not CSIndex official source
attachments and cannot silently replace the official `CSI300` universe. The
governed importer therefore writes only the `CSI300_TUSHARE` shadow universe:

```bash
# Strict read-only validation; any incomplete snapshot fails.
web/backend/.venv/bin/python scripts/import_tushare_csi300_pit.py \
  --start-date 2005-01-01 --end-date 2026-07-22 --dry-run

# Explicitly quarantine incomplete snapshots while validating the remaining
# shadow series. Remove --dry-run only after reviewing the generated report.
web/backend/.venv/bin/python scripts/import_tushare_csi300_pit.py \
  --start-date 2005-01-01 --end-date 2026-07-22 \
  --dry-run --quarantine-incomplete \
  --report-out web/runtime/audit/csi300-tushare-dry-run.json
```

The importer requires 300 distinct members per usable snapshot, a weight sum
within tolerance, bounded snapshot gaps and no duplicate constituent/date key.
It stores a deterministic compressed provider archive, lightweight row hashes,
canonical weights and no-lookahead snapshot intervals only when `--dry-run` is
removed. Incomplete snapshots remain visible in the report and are never
filled with current constituents. Promotion remains blocked until the shadow
series is reconciled against the official announcement bundle.

The 2026-07-23 governed run fetched 76,498 TuShare rows, accepted 254 complete
monthly snapshots (76,200 no-lookahead membership intervals) covering
2005-04-29 through 2026-06-30, and quarantined the incomplete 298-member
snapshot dated 2009-12-31. This closes the TuShare shadow coverage gap only.
`CSI300` production PIT remains unavailable before the verified official
2017-12-08 boundary; `CSI300_TUSHARE` is never considered an official-source
replacement.
