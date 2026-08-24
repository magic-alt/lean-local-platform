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
from .source_gate import DEFAULT_PRODUCTION_SOURCE, source_certification
from . import market_lake


def _json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


_NON_IDENTITY_PARAMETER_KEYS = {
    "dockerImage",
    "preflight",
    "strategySnapshotDir",
    "strategySnapshotMainFile",
    "strategySnapshotAlgorithmClass",
    "strategySnapshotLanguage",
}


def canonical_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Return strategy inputs without run-local paths or duplicated operational metadata."""
    result = {
        key: value
        for key, value in parameters.items()
        if key not in _NON_IDENTITY_PARAMETER_KEYS
    }
    if "initial_cash" in result and "initialCash" not in result:
        result["initialCash"] = result.pop("initial_cash")
    return result


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


def canonical_config_hash(path: Path | str | None) -> str | None:
    if not path:
        return None
    config_path = Path(path)
    if not config_path.is_file():
        return None
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    canonical = dict(payload)
    replacements = {
        "data-folder": "<LEAN_DATA>",
        "results-destination-folder": "<LEAN_RESULTS>",
        "object-store-root": "<LEAN_STORAGE>",
    }
    canonical.update(replacements)
    algorithm = str(canonical.get("algorithm-location") or "")
    canonical["algorithm-location"] = f"<LEAN_PROJECT>/{Path(algorithm).name}" if algorithm else None
    python_paths = canonical.get("python-additional-paths") or []
    canonical["python-additional-paths"] = ["<LEAN_SUPPORT>"] if python_paths else []
    return _json_hash(canonical)


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
    if "@sha256:" in image:
        return {"image": image, "digest": image.split("@", 1)[1], "repoDigests": [image]}
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
    market_summary: dict[str, Any] = {}
    trade_status: dict[str, Any] = {}
    benchmark: dict[str, Any] = {}
    parquet_files: list[dict[str, Any]] = []
    if symbol:
        common = {
            "market": str(scope["market"]).lower(),
            "venue": str(scope["venue"]).lower(),
            "resolution": str(scope["resolution"]).lower(),
            "data_type": str(scope["dataType"]).lower(),
            "adjust": str(scope["adjust"]).lower(),
            "source": scope["source"],
        }
        predicates = ("symbol = ?", "trade_date between ? and ?")
        values = (symbol, scope["start"], scope["end"])
        bar_content_rows = market_lake.query_matching(
            kind="bars", asset_class=str(scope["assetClass"]).lower(), **common,
            predicates=predicates, parameters=values, order_by="trade_date,source",
        )
        dates = sorted(str(row["trade_date"])[:10] for row in bar_content_rows)
        batches = sorted(str(row["batch_id"]) for row in bar_content_rows if row.get("batch_id"))
        market_summary = {
            "row_count": len(bar_content_rows),
            "first_date": dates[0] if dates else None,
            "last_date": dates[-1] if dates else None,
            "first_batch_id": batches[0] if batches else None,
            "last_batch_id": batches[-1] if batches else None,
            "content_sha256": _json_hash(bar_content_rows),
        }
        status_rows = market_lake.query_matching(
            kind="trade_status", asset_class=str(scope["assetClass"]).lower(),
            market=str(scope["market"]).lower(), venue=str(scope["venue"]).lower(),
            predicates=predicates, parameters=values, order_by="trade_date,source",
        )
        status_dates = sorted({str(row["trade_date"])[:10] for row in status_rows})
        trade_status = {
            "row_count": len(status_dates),
            "first_date": status_dates[0] if status_dates else None,
            "last_date": status_dates[-1] if status_dates else None,
            "content_sha256": _json_hash(status_rows),
        }
        benchmark_symbol = str(parameters.get("benchmarkSymbol") or parameters.get("benchmark_symbol") or "").upper()
        if benchmark_symbol:
            benchmark_rows: list[dict[str, Any]] = []
            for candidate_class in dict.fromkeys((str(scope["assetClass"]).lower(), "index")):
                benchmark_rows.extend(
                    market_lake.query_matching(
                        kind="bars", asset_class=candidate_class, **common,
                        predicates=predicates,
                        parameters=(benchmark_symbol, scope["start"], scope["end"]),
                        order_by="trade_date,source",
                    )
                )
            benchmark_dates = sorted({str(row["trade_date"])[:10] for row in benchmark_rows})
            benchmark = {
                "symbol": benchmark_symbol,
                "row_count": len(benchmark_dates),
                "first_date": benchmark_dates[0] if benchmark_dates else None,
                "last_date": benchmark_dates[-1] if benchmark_dates else None,
                "content_sha256": _json_hash(benchmark_rows),
            }
        for lake_scope in market_lake.matching_scopes(
            kind="bars", asset_class=str(scope["assetClass"]).lower(), **common,
        ):
            manifest = market_lake.load_manifest(**lake_scope)
            for item in manifest.get("files") or []:
                parquet_files.append(
                    {
                        "dataset_id": manifest.get("datasetKey"),
                        "dataset_version": manifest.get("datasetVersion"),
                        "file_path": item.get("path"),
                        "row_count": item.get("rowCount"),
                        "sha256": item.get("sha256"),
                        "first_timestamp": item.get("firstTimestamp"),
                        "last_timestamp": item.get("lastTimestamp"),
                    }
                )
    return {
        "scope": scope,
        "marketDailyBars": market_summary,
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
    source = parameters.get("source") or parameters.get("provider") or DEFAULT_PRODUCTION_SOURCE
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


def _lean_cache_manifest_hash(lean_cache: dict[str, Any] | None) -> str | None:
    files: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("sha256"):
                files.append({"path": value.get("path"), "sha256": value.get("sha256")})
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(lean_cache or {})
    return _json_hash(sorted(files, key=lambda item: str(item.get("path") or item["sha256"]))) if files else None


def build_run_fingerprint(
    *,
    run_id: str,
    parameters: dict[str, Any],
    docker_image: str | None,
    lean_cache: dict[str, Any] | None = None,
    strategy_path: str | Path | None = None,
    config_path: str | Path | None = None,
    execution_backend: str = "docker",
    runtime_identity: dict[str, Any] | None = None,
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
    if runtime_identity is None and execution_backend == "docker":
        raw_digest = str(docker.get("digest") or "")
        runtime_identity = {
            "backend": "docker",
            "runtimeId": docker.get("image"),
            "artifactSha256": raw_digest.removeprefix("sha256:"),
            "dockerImage": docker.get("image"),
        }
    if lean_cache is None:
        lean_cache = _local_ashare_cache(parameters)
    daily_cache = _first_cache_file(lean_cache, "daily")
    factor_cache = _first_cache_file(lean_cache, "factor")
    lean_cache_manifest_sha256 = _lean_cache_manifest_hash(lean_cache)
    parquet_files = data.get("parquetFiles") or []
    first_parquet = parquet_files[0] if parquet_files else {}
    market_daily = data.get("marketDailyBars") or {}
    trade_status = data.get("tradeStatus") or {}
    benchmark = data.get("benchmark") or {}
    canonical_params = canonical_parameters(parameters)
    strategy_sha256 = _file_hash(strategy_path)
    requirements_sha256 = _requirements_hash()
    canonical_config_sha256 = canonical_config_hash(config_path)
    logical_identity = {
        "schemaVersion": 2,
        "parameters": canonical_params,
        "strategyFileSha256": strategy_sha256,
        "gitCommit": git.get("commit"),
        "gitStatusHash": git.get("statusHash"),
        "requirementsSha256": requirements_sha256,
        "data": {
            "scope": data.get("scope") or {},
            "marketDailyBars": {
                key: market_daily.get(key)
                for key in ("row_count", "first_date", "last_date", "content_sha256")
            },
            "tradeStatus": {
                key: trade_status.get(key)
                for key in ("row_count", "first_date", "last_date", "content_sha256")
            },
            "benchmark": {
                key: benchmark.get(key)
                for key in ("symbol", "row_count", "first_date", "last_date", "content_sha256")
            },
            "parquetFiles": [
                {
                    key: item.get(key)
                    for key in ("dataset_id", "row_count", "sha256", "first_timestamp", "last_timestamp")
                }
                for item in data.get("parquetFiles") or []
            ],
        },
        "datasetCertification": {
            key: certification.get(key)
            for key in (
                "source",
                "datasetVersion",
                "datasetReleaseId",
                "datasetId",
                "fileManifestSha256",
                "qaStatus",
                "isProduction",
                "isCertified",
            )
        },
        "leanCache": {
            "dailySha256": daily_cache.get("sha256"),
            "factorSha256": factor_cache.get("sha256"),
            "manifestSha256": lean_cache_manifest_sha256,
        },
        "canonicalConfigSha256": canonical_config_sha256,
    }
    logical_input_fingerprint = _json_hash(logical_identity)
    parameters_hash = _json_hash(canonical_params)
    config_file_hash = _file_hash(config_path)
    execution_identity = {
        "schemaVersion": 1,
        "logicalInputFingerprint": logical_input_fingerprint,
        "executionBackend": execution_backend,
        "runtimeIdentity": runtime_identity,
        "configFileSha256": config_file_hash,
    }
    execution_fingerprint = _json_hash(execution_identity)
    dataset_version = certification.get("datasetVersion")
    return {
        "schemaVersion": 3,
        "runId": run_id,
        "createdAt": created_at,
        "run_start_time": created_at,
        "timezone": os.environ.get("TZ") or time.tzname[0],
        "python_version": sys.version,
        "requirements_hash": requirements_sha256,
        "git": git,
        "git_commit": git.get("commit"),
        "git_branch": git.get("branch"),
        "git_dirty": git.get("dirty"),
        "git_status_hash": git.get("statusHash"),
        "parametersHash": parameters_hash,
        "parameters": parameters,
        "canonicalParameters": canonical_params,
        "logicalInputFingerprint": logical_input_fingerprint,
        "executionFingerprint": execution_fingerprint,
        "inputFingerprint": execution_fingerprint,
        "inputIdentity": execution_identity,
        "logicalInputIdentity": logical_identity,
        "executionBackend": execution_backend,
        "runtimeIdentity": runtime_identity,
        "strategyFileHash": strategy_sha256,
        "configFileHash": config_file_hash,
        "canonicalConfigSha256": canonical_config_sha256,
        "data": data,
        "source": certification.get("source"),
        "datasetVersion": dataset_version,
        "datasetReleaseId": certification.get("datasetReleaseId"),
        "datasetCertification": certification,
        "legacyAliases": {
            "parameters_sha256": parameters_hash,
            "input_fingerprint": execution_fingerprint,
            "strategy_file_sha256": strategy_sha256,
            "config_file_sha256": config_file_hash,
            "dataset_version": dataset_version,
        },
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
        "leanCacheManifestSha256": lean_cache_manifest_sha256,
        "leanCache": lean_cache or {},
        "docker": docker,
        "docker_image": docker.get("image"),
        "docker_image_digest": docker.get("digest"),
    }
