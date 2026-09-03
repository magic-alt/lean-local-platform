# Local Data Operations CLI

`datactl` is the supported command-line entrypoint for inspecting, synchronizing,
repairing, and validating the local governed market-data lake.

The CLI is intentionally thin: it calls the same backend data-sync, Parquet QA,
archive-evidence, and TuShare contract services used by the application. It does
not create a second data pipeline.

## Data-root resolution

There is no drive-letter requirement. The effective data root is resolved in
this order:

1. `--data-dir <path>` on `datactl` or `update_tushare_current.py`;
2. `LEAN_DATA_DIR` from the process environment or repository `.env`;
3. `<repository>/data`.

Relative CLI paths are resolved from the repository root. When `--data-dir` is
explicitly supplied, the related local paths move together:

```text
LEAN_DATA_DIR              <root>
LEAN_HOST_DATA_DIR         <root>
LEAN_MARKET_DATA_DIR       <root>
LEAN_PARQUET_DIR           <root>/output/parquet
LEAN_HOST_PARQUET_DIR      <root>/output/parquet
LEAN_DATA_SYNC_SPOOL_DIR   <root>/.sync-spool
```

The normal default therefore remains portable on Windows, Linux, and macOS:

```text
lean-local-platform/
├── data/
├── scripts/
├── web/
└── ...
```

An external disk is still supported explicitly, for example:

```powershell
python scripts/datactl.py --data-dir E:\MarketData\lean status
```

or:

```bash
python scripts/datactl.py --data-dir /mnt/market-data/lean status
```

## Status

Show the compact catalog and sync state:

```bash
python scripts/datactl.py status
```

Show the complete catalog payload:

```bash
python scripts/datactl.py status --full
```

## Managed synchronization

Let the platform choose `initial_full` before the first successful build and
`incremental` afterwards:

```bash
python scripts/datactl.py update --mode auto
```

Force the normal incremental path:

```bash
python scripts/datactl.py update --mode incremental
```

Build a new local library for the first time:

```bash
python scripts/datactl.py update --mode initial_full
```

Run explicit full reconciliation/rebuild only when the operator has a reason to
rebuild canonical evidence:

```bash
python scripts/datactl.py update --mode full_rebuild
```

Restrict a run to selected managed datasets:

```bash
python scripts/datactl.py update --mode incremental --datasets daily,adj_factor,daily_basic
```

Omitting `--datasets` selects the current managed bulk set from
`BULK_DATASET_KEYS`; on-demand datasets are not silently added.

## Extended/dividend recovery

`extended_daily` and `dividend` have bounded retry/recovery behavior because
those datasets can finish through deferred symbol partitions or failed-only
retries. The unified entrypoint is:

```bash
python scripts/datactl.py repair-current
```

Optional controls:

```bash
python scripts/datactl.py repair-current \
  --symbol-batch-size 1000 \
  --max-extended-cycles 12 \
  --max-dividend-retries 3
```

The historical compatibility entrypoints remain available:

```powershell
.\scripts\update_tushare_current.cmd
```

```bash
python scripts/update_tushare_current.py
```

They use the same portable data-root resolution and no longer require `D:`.

## Local fail-closed validation

The default validation does not opt into external multi-source QA or live
provider probes. It checks the local A-share daily Parquet consistency,
benchmark coverage, provider-archive completion/integrity evidence, and the
offline TuShare contract:

```bash
python scripts/datactl.py validate
```

Treat warnings as a failed operator gate:

```bash
python scripts/datactl.py validate --fail-on-warning
```

Persist the aggregate JSON report to a file:

```bash
python scripts/datactl.py validate \
  --fail-on-warning \
  --output data/reports/data_validation.json
```

Audit a specific successful sync run during provider-archive reconciliation:

```bash
python scripts/datactl.py validate --run-id <sync-run-id>
```

## Deep multi-source QA

`--deep` is explicit because it can contact configured research/reference data
sources. It adds batched A-share cross-source comparison:

```bash
python scripts/datactl.py validate \
  --deep \
  --symbols 600519,000001 \
  --start-date 2026-08-01 \
  --end-date 2026-09-03 \
  --fail-on-warning
```

Override the configured source priority only when required:

```bash
python scripts/datactl.py validate \
  --deep \
  --qa-sources tushare,baostock,sina
```

## Live TuShare contract smoke test

Live provider calls are also opt-in:

```bash
python scripts/datactl.py validate --live-provider
```

This runs the same bounded read-only live samples as
`validate_tushare_contracts.py`; it is not a full provider download.

## Validation gate

For production-like research/backtest preparation, the expected gate is:

| Check | Required state |
| --- | --- |
| Managed sync | `success` |
| Parquet consistency | no `critical` result |
| CSI300 benchmark coverage | at least one covered trading date in scope |
| Provider archive reconciliation | `passed=true` |
| Offline TuShare contract | `valid=true` |
| Deep QA, when requested | no `critical`; no warning when `--fail-on-warning` |
| Live provider smoke, when requested | `valid=true` |

A failed validation exits non-zero. Do not use a failed data gate as input to a
new production-like backtest, research handoff, or paper-execution workflow.

## Windows wrapper

The repository also includes:

```powershell
.\scripts\datactl.cmd status
.\scripts\datactl.cmd update --mode auto
.\scripts\datactl.cmd validate --fail-on-warning
```

The wrapper uses `web\backend\.venv\Scripts\python.exe`, matching the existing
Windows operational scripts.
