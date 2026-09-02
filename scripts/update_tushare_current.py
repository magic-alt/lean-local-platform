from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
DATA_ROOT = (REPO_ROOT / "data").resolve()


def _configure_d_drive() -> None:
    if DATA_ROOT.drive.upper() != "D:":
        raise RuntimeError(f"TuShare current must be on D:, resolved data root is {DATA_ROOT}")
    os.environ["LEAN_DATA_DIR"] = str(DATA_ROOT)
    os.environ["LEAN_HOST_DATA_DIR"] = str(DATA_ROOT)
    os.environ["LEAN_MARKET_DATA_DIR"] = str(DATA_ROOT)
    os.environ["LEAN_PARQUET_DIR"] = str(DATA_ROOT)
    os.environ["LEAN_HOST_PARQUET_DIR"] = str(DATA_ROOT)
    os.environ["LEAN_DATA_SYNC_SPOOL_DIR"] = str(DATA_ROOT / ".sync-spool")
    os.environ["LEAN_TUSHARE_LINEAGE_ASYNC"] = "0"
    (DATA_ROOT / ".sync-spool").mkdir(parents=True, exist_ok=True)


def _run_once(data_sync: Any, datasets: list[str], request_scope: dict[str, Any] | None = None) -> dict[str, Any]:
    run = data_sync.create_sync_run(
        requested=datasets,
        mode="incremental",
        request_scope=request_scope or {},
    )
    result = data_sync.run_sync(run["id"])
    compact = {
        "runId": run["id"],
        "status": result.get("status"),
        "datasets": result.get("datasets"),
    }
    print(json.dumps(compact, ensure_ascii=False, default=str), flush=True)
    return result


def _dataset_metric(result: dict[str, Any], dataset: str, metric: str) -> int:
    return int(((result.get("datasets") or {}).get(dataset) or {}).get(metric) or 0)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh D-drive TuShare extended and dividend Bronze data to completion."
    )
    parser.add_argument("--symbol-batch-size", type=int, default=1000)
    parser.add_argument("--max-extended-cycles", type=int, default=12)
    parser.add_argument("--max-dividend-retries", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.symbol_batch_size <= 1000:
        parser.error("--symbol-batch-size must be between 1 and 1000")

    _configure_d_drive()
    os.environ["LEAN_DATA_EXTENDED_SYMBOLS_PER_RUN"] = str(args.symbol_batch_size)
    sys.path.insert(0, str(BACKEND_DIR))
    from app.services import data_sync

    result = _run_once(data_sync, ["extended_daily", "dividend"])
    cycle = 1
    while _dataset_metric(result, "extended_daily", "deferredSymbolTasks"):
        if cycle >= args.max_extended_cycles:
            raise RuntimeError("extended_daily did not complete within the configured cycle limit")
        cycle += 1
        result = _run_once(data_sync, ["extended_daily"])

    retry_result: dict[str, Any] | None = None
    for _ in range(args.max_dividend_retries):
        retry_result = _run_once(
            data_sync,
            ["dividend"],
            {"retryFailedOnlyDatasets": ["dividend"]},
        )
        if not _dataset_metric(retry_result, "dividend", "failed"):
            break
    if retry_result and _dataset_metric(retry_result, "dividend", "failed"):
        raise RuntimeError("dividend failures remain after the configured retry limit")

    extended_failures = _dataset_metric(result, "extended_daily", "partitionFailures")
    if extended_failures:
        print(f"WARNING: {extended_failures} extended partitions still failed after retries.", file=sys.stderr)

    print(
        json.dumps(
            {
                "status": "success",
                "dataRoot": str(DATA_ROOT),
                "extendedCycles": cycle,
                "cDriveUsedAsCapacityGate": False,
                "extendedPartitionFailures": extended_failures,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())