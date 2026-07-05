from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..core.config import REPO_ROOT
from ..db import db, rows_to_dicts, utc_now


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
            cwd=REPO_ROOT,
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


def git_state() -> dict[str, Any]:
    status = _run_git(["status", "--porcelain"]) or ""
    return {
        "commit": _run_git(["rev-parse", "HEAD"]),
        "branch": _run_git(["branch", "--show-current"]),
        "dirty": bool(status),
        "statusHash": hashlib.sha256(status.encode("utf-8")).hexdigest() if status else None,
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
            cwd=REPO_ROOT,
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
    return {
        "symbol": str(parameters.get("ticker") or parameters.get("symbol") or "").upper(),
        "assetClass": parameters.get("assetClass") or "equity",
        "market": parameters.get("market") or parameters.get("venue") or "usa",
        "venue": parameters.get("venue") or parameters.get("market") or "usa",
        "resolution": parameters.get("resolution") or "daily",
        "dataType": parameters.get("dataType") or "trade",
        "adjust": parameters.get("adjust") or "raw",
        "source": parameters.get("source") or parameters.get("provider") or "akshare",
        "start": parameters.get("start"),
        "end": parameters.get("end"),
    }


def data_fingerprint(parameters: dict[str, Any]) -> dict[str, Any]:
    scope = market_data_scope(parameters)
    symbol = scope["symbol"]
    rows: list[dict[str, Any]] = []
    parquet_files: list[dict[str, Any]] = []
    if symbol:
        with db() as connection:
            data_row = connection.execute(
                """
                select count(*) as row_count,
                       min(trade_date) as first_date,
                       max(trade_date) as last_date,
                       min(batch_id) as first_batch_id,
                       max(batch_id) as last_batch_id
                from market_daily_bars
                where symbol = ? and asset_class = ? and market = ? and venue = ?
                  and resolution = ? and data_type = ? and adjust = ?
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
                    scope["start"],
                    scope["end"],
                ),
            ).fetchone()
            parquet_files = rows_to_dicts(
                connection.execute(
                    """
                    select f.dataset_id, f.file_path, f.row_count, f.sha256, f.first_timestamp, f.last_timestamp
                    from parquet_files f
                    join parquet_datasets d on d.id = f.dataset_id
                    where d.asset_class = ? and d.market = ? and d.venue = ?
                      and d.resolution = ? and d.data_type = ? and d.adjust = ?
                    order by f.file_path
                    """,
                    (
                        str(scope["assetClass"]).lower(),
                        str(scope["market"]).lower(),
                        str(scope["venue"]).lower(),
                        str(scope["resolution"]).lower(),
                        str(scope["dataType"]).lower(),
                        scope["adjust"],
                    ),
                ).fetchall()
            )
        rows = [dict(data_row)] if data_row else []
    return {"scope": scope, "marketDailyBars": rows[0] if rows else {}, "parquetFiles": parquet_files}


def build_run_fingerprint(
    *,
    run_id: str,
    parameters: dict[str, Any],
    docker_image: str | None,
    lean_cache: dict[str, Any] | None = None,
    strategy_path: str | Path | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "runId": run_id,
        "createdAt": utc_now(),
        "git": git_state(),
        "parametersHash": _json_hash(parameters),
        "parameters": parameters,
        "strategyFileHash": _file_hash(strategy_path),
        "configFileHash": _file_hash(config_path),
        "data": data_fingerprint(parameters),
        "leanCache": lean_cache or {},
        "docker": docker_image_digest(docker_image),
    }
