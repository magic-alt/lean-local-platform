from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ..core.config import BACKEND_DIR, GIT_ROOT
from ..db import db, rows_to_dicts, utc_now
from ..lean_engine import data_paths
from ..lean_engine.symbols import normalize_symbol, symbol_key
from .source_gate import source_certification


def _json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_hash(path: Path | str | None) -> str | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return None
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_git(args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=GIT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


_RUNTIME_UNTRACKED_PREFIXES = (
    ".pytest_cache/",
    ".ruff_cache/",
    ".mypy_cache/",
    "runtime/",
    "web/backend/runtime/",
    "web/frontend/dist/",
)


def _is_runtime_untracked(line: str) -> bool:
    if not line.startswith("?? "):
        return False
    path = line[3:]
    if "__pycache__/" in path or path.endswith((".pyc", ".pyo")):
        return True
    return path == ".DS_Store" or any(path.startswith(prefix) for prefix in _RUNTIME_UNTRACKED_PREFIXES)


def git_state() -> dict[str, Any]:
    tracked_status = _run_git(["status", "--porcelain", "--untracked-files=no"]) or ""
    raw_status = _run_git(["status", "--porcelain"]) or ""
    meaningful_untracked = [
        line for line in raw_status.splitlines() if line.startswith("?? ") and not _is_runtime_untracked(line)
    ]
    ignored_untracked = [line for line in raw_status.splitlines() if _is_runtime_untracked(line)]
    status = "\n".join([line for line in [tracked_status, *meaningful_untracked] if line])
    return {
        "commit": _run_git(["rev-parse", "HEAD"]),
        "branch": _run_git(["branch", "--show-current"]),
        "dirty": bool(status),
        "statusHash": hashlib.sha256(status.encode("utf-8")).hexdigest() if status else None,
        "statusMode": "tracked_plus_non_runtime_untracked",
        "meaningfulUntrackedCount": len(meaningful_untracked),
        "ignoredUntrackedCount": len(ignored_untracked),
        "rawDirty": bool(raw_status),
        "rawStatusHash": hashlib.sha256(raw_status.encode("utf-8")).hexdigest() if raw_status else None,
    }


def docker_image_digest(image: str | None) -> dict[str, Any]:
    if not image:
        return {"image": None, "digest": None, "error": "docker_image_missing"}
    docker = shutil.which("docker")
    if not docker:
        return {"image": image, "digest": None, "error": "docker_not_found"}
    try:
        completed = subprocess.run(
            [docker, "image", "inspect", image, "--format", "{{json .RepoDigests}}"],
            cwd=GIT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return {"image": image, "digest": None, "error": str(exc)}
    if completed.returncode != 0:
        return {"image": image, "digest": None, "error": completed.stderr.strip() or completed.stdout.strip()}
    try:
        digests = json.loads(completed.stdout.strip() or "[]")
    except json.JSONDecodeError:
        digests = []
    return {"image": image, "digest": digests[0] if digests else None, "repoDigests": digests}


def market_data_scope(parameters: dict[str, Any]) -> dict[str, Any]:
    source = parameters.get("source") or parameters.get("provider")
    return {
        "symbol": str(parameters.get("ticker") or parameters.get("symbol") or "").upper(),
        "assetClass": parameters.get("assetClass") or "equity",
        "market": parameters.get("market") or parameters.get("venue") or "usa",
        "venue": parameters.get("venue") or parameters.get("market") or "usa",
        "resolution": parameters.get("resolution") or "daily",
        "dataType": parameters.get("dataType") or "trade",
        "adjust": parameters.get("adjust") or "raw",
        "source": source,
        "start": parameters.get("start"),
        "end": parameters.get("end"),
    }


def data_fingerprint(parameters: dict[str, Any]) -> dict[str, Any]:
    scope = market_data_scope(parameters)
    symbol = scope["symbol"]
    rows: list[dict[str, Any]] = []
    trade_status: dict[str, Any] = {}
    benchmark: dict[str, Any] = {}
    parquet_files: list[dict[str, Any]] = []
    if symbol:
        source_clause = "and source = ?" if scope["source"] else ""
        source_params = [scope["source"]] if scope["source"] else []
        with db() as connection:
            data_row = connection.execute(
                f"""
                select count(*) as row_count,
                       min(trade_date) as first_date,
                       max(trade_date) as last_date,
                       min(batch_id) as first_batch_id,
                       max(batch_id) as last_batch_id
                from market_daily_bars
                where symbol = ? and asset_class = ? and market = ? and venue = ?
                  and resolution = ? and data_type = ? and adjust = ?
                  {source_clause}
                  and trade_date between ? and ?
                """,
                (
                    symbol,
                    str(scope["assetClass"]).lower(),
                    str(scope["market"]).lower(),
                    str(scope["venue"]).lower(),
                    str(scope["resolution"]).lower(),
                    str(scope["dataType"]).lower(),
                    scope["adjust"],
                    *source_params,
                    scope["start"],
                    scope["end"],
                ),
            ).fetchone()
            trade_status_row = connection.execute(
                """
                select count(distinct trade_date) as row_count,
                       min(trade_date) as first_date,
                       max(trade_date) as last_date
                from market_trade_status
                where symbol = ? and trade_date between ? and ?
                """,
                (symbol, scope["start"], scope["end"]),
            ).fetchone()
            benchmark_symbol = str(parameters.get("benchmarkSymbol") or parameters.get("benchmark_symbol") or "").upper()
            if benchmark_symbol:
                benchmark_row = connection.execute(
                    f"""
                    select count(*) as row_count,
                           min(trade_date) as first_date,
                           max(trade_date) as last_date
                    from market_daily_bars
                    where symbol = ? and asset_class = ? and market = ? and venue = ?
                      and resolution = ? and data_type = ? and adjust = ?
                      {source_clause}
                      and trade_date between ? and ?
                    """,
                    (
                        benchmark_symbol,
                        str(scope["assetClass"]).lower(),
                        str(scope["market"]).lower(),
                        str(scope["venue"]).lower(),
                        str(scope["resolution"]).lower(),
                        str(scope["dataType"]).lower(),
                        scope["adjust"],
                        *source_params,
                        scope["start"],
                        scope["end"],
                    ),
                ).fetchone()
                benchmark = {"symbol": benchmark_symbol, **(dict(benchmark_row) if benchmark_row else {})}
            parquet_files = rows_to_dicts(
                connection.execute(
                    f"""
                    select f.dataset_id, f.file_path, f.row_count, f.sha256, f.first_timestamp, f.last_timestamp
                    from parquet_files f
                    join parquet_datasets d on d.id = f.dataset_id
                    where d.asset_class = ? and d.market = ? and d.venue = ?
                      and d.resolution = ? and d.data_type = ? and d.adjust = ?
                      {source_clause.replace('source = ?', 'd.source = ?')}
                    order by f.file_path
                    """,
                    (
                        str(scope["assetClass"]).lower(),
                        str(scope["market"]).lower(),
                        str(scope["venue"]).lower(),
                        str(scope["resolution"]).lower(),
                        str(scope["dataType"]).lower(),
                        scope["adjust"],
                        *source_params,
                    ),
                ).fetchall()
            )
        rows = [dict(data_row)] if data_row else []
        trade_status = dict(trade_status_row) if trade_status_row else {}
    return {
        "scope": scope,
        "marketDailyBars": rows[0] if rows else {},
        "tradeStatus": trade_status,
        "benchmark": benchmark,
        "parquetFiles": parquet_files,
    }


def _first_cache_file(lean_cache: dict[str, Any] | None, name: str) -> dict[str, Any]:
    if not lean_cache:
        return {}
    if "files" in lean_cache:
        return dict((lean_cache.get("files") or {}).get(name) or {})
    symbol_cache = lean_cache.get("symbol") if isinstance(lean_cache, dict) else None
    if isinstance(symbol_cache, dict):
        return dict((symbol_cache.get("files") or {}).get(name) or {})
    return {}


def _local_cache_file(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists() and path.is_file(),
        "sha256": _file_hash(path),
        "source": "local_lean_data",
    }


def _local_ashare_cache(parameters: dict[str, Any]) -> dict[str, Any]:
    asset_class = str(parameters.get("assetClass") or "equity").lower()
    market = str(parameters.get("market") or parameters.get("venue") or "china").lower()
    venue = str(parameters.get("venue") or parameters.get("market") or "china").lower()
    if asset_class != "equity" or (market != "china" and venue != "china"):
        return {}
    raw_symbol = str(parameters.get("ticker") or parameters.get("symbol") or "").strip()
    if not raw_symbol:
        return {}
    source = parameters.get("source") or parameters.get("provider") or "jqdata"
    adjust = parameters.get("adjust") or "raw"

    def files_for(symbol: str) -> dict[str, Any]:
        normalized = normalize_symbol(symbol, "china")
        ticker = symbol_key(normalized)
        data_dir = data_paths.DATA_DIR / "equity" / "china"
        return {
            "symbol": normalized,
            "files": {
                "daily": _local_cache_file(data_dir / "daily" / f"{ticker}.zip"),
                "factor": _local_cache_file(data_dir / "factor_files" / f"{ticker}.csv"),
                "map": _local_cache_file(data_dir / "map_files" / f"{ticker}.csv"),
            },
        }

    primary = files_for(raw_symbol)
    result = {
        "symbol": primary["symbol"],
        "source": source,
        "adjust": adjust,
        "files": primary["files"],
    }
    benchmark_symbol = str(parameters.get("benchmarkSymbol") or parameters.get("benchmark_symbol") or "").strip()
    if benchmark_symbol:
        result["benchmark"] = files_for(benchmark_symbol)
    return result


def _requirements_hash() -> str | None:
    return _file_hash(BACKEND_DIR / "requirements.txt")


def build_run_fingerprint(
    *,
    run_id: str,
    parameters: dict[str, Any],
    docker_image: str | None,
    lean_cache: dict[str, Any] | None = None,
    strategy_path: str | Path | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    created_at = utc_now()
    git = git_state()
    data = data_fingerprint(parameters)
    certification = source_certification(
        (data.get("scope") or {}).get("source"),
        asset_class=str((data.get("scope") or {}).get("assetClass") or "equity"),
        market=str((data.get("scope") or {}).get("market") or "china"),
        venue=str((data.get("scope") or {}).get("venue") or "china"),
    )
    docker = docker_image_digest(docker_image)
    if lean_cache is None:
        lean_cache = _local_ashare_cache(parameters)
    daily_cache = _first_cache_file(lean_cache, "daily")
    factor_cache = _first_cache_file(lean_cache, "factor")
    parquet_files = data.get("parquetFiles") or []
    first_parquet = parquet_files[0] if parquet_files else {}
    market_daily = data.get("marketDailyBars") or {}
    trade_status = data.get("tradeStatus") or {}
    benchmark = data.get("benchmark") or {}
    return {
        "schemaVersion": 1,
        "runId": run_id,
        "createdAt": created_at,
        "run_start_time": created_at,
        "timezone": os.environ.get("TZ") or time.tzname[0],
        "python_version": sys.version,
        "requirements_hash": _requirements_hash(),
        "git": git,
        "git_commit": git.get("commit"),
        "git_branch": git.get("branch"),
        "git_dirty": git.get("dirty"),
        "git_status_hash": git.get("statusHash"),
        "parametersHash": _json_hash(parameters),
        "parameters_sha256": _json_hash(parameters),
        "parameters": parameters,
        "strategyFileHash": _file_hash(strategy_path),
        "strategy_file_sha256": _file_hash(strategy_path),
        "configFileHash": _file_hash(config_path),
        "config_file_sha256": _file_hash(config_path),
        "data": data,
        "source": certification.get("source"),
        "datasetVersion": certification.get("datasetVersion"),
        "datasetCertification": certification,
        "dataset_version": certification.get("datasetVersion"),
        "dataset_is_certified": certification.get("isCertified"),
        "dataset_qa_report_id": certification.get("qaReportId"),
        "data_batch_id": market_daily.get("last_batch_id"),
        "market_daily_bars_count": market_daily.get("row_count"),
        "trade_status_count": trade_status.get("row_count"),
        "benchmark_symbol": benchmark.get("symbol") or parameters.get("benchmarkSymbol"),
        "benchmark_rows": benchmark.get("row_count"),
        "parquet_dataset_id": first_parquet.get("dataset_id"),
        "parquet_file_sha256": first_parquet.get("sha256"),
        "lean_zip_sha256": daily_cache.get("sha256"),
        "factor_file_sha256": factor_cache.get("sha256"),
        "leanCache": lean_cache or {},
        "docker": docker,
        "docker_image": docker.get("image"),
        "docker_image_digest": docker.get("digest"),
    }
