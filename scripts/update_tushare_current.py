from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
SPECIAL_DATASETS = frozenset({"extended_daily", "dividend"})


def _resolve_data_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def _apply_data_dir_override(value: str | None) -> Path | None:
    """Apply an explicit data root before backend configuration is imported.

    With no override the backend remains authoritative: it reads ``LEAN_DATA_DIR``
    from the process/.env and otherwise defaults to ``<repo>/data``.  An explicit
    CLI path intentionally moves the whole local lake together so market, host,
    Parquet and sync-spool paths cannot drift across volumes.
    """
    if not value:
        return None
    root = _resolve_data_dir(value)
    parquet = root / "output" / "parquet"
    overrides = {
        "LEAN_DATA_DIR": root,
        "LEAN_HOST_DATA_DIR": root,
        "LEAN_MARKET_DATA_DIR": root,
        "LEAN_PARQUET_DIR": parquet,
        "LEAN_HOST_PARQUET_DIR": parquet,
        "LEAN_DATA_SYNC_SPOOL_DIR": root / ".sync-spool",
    }
    for name, path in overrides.items():
        os.environ[name] = str(path)
    return root


def _run_once(
    data_sync: Any,
    datasets: list[str],
    request_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
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


def complete_special_datasets(
    data_sync: Any,
    *,
    include: set[str] | frozenset[str] = SPECIAL_DATASETS,
    initial_result: dict[str, Any] | None = None,
    symbol_batch_size: int = 1000,
    max_extended_cycles: int = 12,
    max_dividend_retries: int = 3,
) -> dict[str, Any]:
    """Drive bounded extended/dividend incremental recovery to completion."""
    selected = set(include) & set(SPECIAL_DATASETS)
    if not selected:
        return {"status": "skipped", "datasets": [], "extendedCycles": 0}
    if not 1 <= symbol_batch_size <= 1000:
        raise ValueError("symbol_batch_size must be between 1 and 1000")
    if max_extended_cycles < 1:
        raise ValueError("max_extended_cycles must be positive")
    if max_dividend_retries < 1:
        raise ValueError("max_dividend_retries must be positive")

    os.environ["LEAN_DATA_EXTENDED_SYMBOLS_PER_RUN"] = str(symbol_batch_size)
    seed_result = initial_result
    if seed_result is None or not selected <= set((seed_result.get("datasets") or {}).keys()):
        seed_result = _run_once(data_sync, sorted(selected))

    extended_result = seed_result
    dividend_result: dict[str, Any] | None = seed_result if "dividend" in selected else None
    cycle = 1 if "extended_daily" in selected else 0
    while "extended_daily" in selected and _dataset_metric(
        extended_result, "extended_daily", "deferredSymbolTasks"
    ):
        if cycle >= max_extended_cycles:
            raise RuntimeError("extended_daily did not complete within the configured cycle limit")
        cycle += 1
        extended_result = _run_once(data_sync, ["extended_daily"])

    if "dividend" in selected and dividend_result and _dataset_metric(
        dividend_result, "dividend", "failed"
    ):
        for _ in range(max_dividend_retries):
            dividend_result = _run_once(
                data_sync,
                ["dividend"],
                {"retryFailedOnlyDatasets": ["dividend"]},
            )
            if not _dataset_metric(dividend_result, "dividend", "failed"):
                break
        if _dataset_metric(dividend_result, "dividend", "failed"):
            raise RuntimeError("dividend failures remain after the configured retry limit")

    extended_failures = (
        _dataset_metric(extended_result, "extended_daily", "partitionFailures")
        if "extended_daily" in selected
        else 0
    )
    if extended_failures:
        print(
            f"WARNING: {extended_failures} extended partitions still failed after retries.",
            file=sys.stderr,
        )

    return {
        "status": "success",
        "datasets": sorted(selected),
        "extendedCycles": cycle,
        "extendedPartitionFailures": extended_failures,
        "dividendFailures": (
            _dataset_metric(dividend_result or {}, "dividend", "failed")
            if "dividend" in selected
            else 0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh TuShare extended_daily and dividend Bronze data to completion. "
            "The data root defaults to LEAN_DATA_DIR from the environment/.env, "
            "then <repo>/data."
        )
    )
    parser.add_argument(
        "--data-dir",
        help="Override the local data root; relative paths are resolved from the repository root.",
    )
    parser.add_argument("--symbol-batch-size", type=int, default=1000)
    parser.add_argument("--max-extended-cycles", type=int, default=12)
    parser.add_argument("--max-dividend-retries", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.symbol_batch_size <= 1000:
        parser.error("--symbol-batch-size must be between 1 and 1000")

    _apply_data_dir_override(args.data_dir)
    os.environ["LEAN_TUSHARE_LINEAGE_ASYNC"] = "0"
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    from app.core.config import DATA_DIR
    from app.services import data_sync

    data_root = DATA_DIR.expanduser().resolve()
    spool = Path(os.environ.get("LEAN_DATA_SYNC_SPOOL_DIR", data_root / ".sync-spool"))
    if not spool.is_absolute():
        spool = (REPO_ROOT / spool).resolve()
    os.environ["LEAN_DATA_SYNC_SPOOL_DIR"] = str(spool)
    spool.mkdir(parents=True, exist_ok=True)

    result = complete_special_datasets(
        data_sync,
        symbol_batch_size=args.symbol_batch_size,
        max_extended_cycles=args.max_extended_cycles,
        max_dividend_retries=args.max_dividend_retries,
    )
    print(
        json.dumps(
            {
                **result,
                "dataRoot": str(data_root),
                "portableDataRoot": True,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
