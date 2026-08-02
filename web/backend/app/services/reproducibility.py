from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..repositories.backtest_repository import get_backtest
from .db_object_store import put_bytes
from .run_paths import run_file


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_manifest(result_path: Path) -> list[dict[str, Any]]:
    root = result_path.parent
    return [
        {
            "path": str(path.relative_to(root)),
            "size": path.stat().st_size,
            "sha256": _file_sha256(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _orders(payload: dict[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("orders") or payload.get("Orders") or {}
    items = list(value.values()) if isinstance(value, dict) else list(value) if isinstance(value, list) else []
    return sorted(items, key=lambda item: str(item.get("id") or item.get("Id") or ""))


def _fills(result_path: Path, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    path = result_path.parent / f"{result_path.stem}-order-events.json"
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = []
        return value if isinstance(value, list) else []
    return [
        item for item in orders
        if str(item.get("status") or item.get("Status") or "").lower() in {"2", "3", "filled"}
    ]


def _equity(payload: dict[str, Any]) -> Any:
    charts = payload.get("charts") or payload.get("Charts") or {}
    strategy = charts.get("Strategy Equity") or charts.get("strategy equity") or {}
    series = strategy.get("series") or strategy.get("Series") or {}
    equity = series.get("Equity") or series.get("equity") or {}
    return equity.get("values") or equity.get("Values") or []


def issue_certificate(run_id: str) -> dict[str, Any]:
    run = get_backtest(run_id)
    if not run:
        raise KeyError("Backtest run not found.")
    fingerprint = run.get("fingerprint") or {}
    release_id = run.get("dataset_release_id") or fingerprint.get("datasetReleaseId")
    if not release_id:
        raise ValueError("certified_dataset_release_required")
    with db() as connection:
        release = connection.execute(
            "select id,status,is_production,is_certified from dataset_releases where id=?",
            (release_id,),
        ).fetchone()
    if not release or release["status"] != "active" or not release["is_production"] or not release["is_certified"]:
        raise ValueError("active_certified_dataset_release_required")
    result_path = run_file(run_id, run.get("result_json_path"), f"results/{run_id}.json")
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    orders = _orders(payload)
    fills = _fills(result_path, orders)
    equity = _equity(payload)
    artifact_manifest = _artifact_manifest(result_path)
    components = {
        "dockerImageDigest": fingerprint.get("docker_image_digest") or (fingerprint.get("docker") or {}).get("digest"),
        "projectSnapshot": {
            "strategyFileSha256": fingerprint.get("strategyFileHash"),
            "gitCommit": fingerprint.get("git_commit"),
            "gitStatusHash": fingerprint.get("git_status_hash"),
        },
        "datasetReleaseId": release_id,
        "leanCache": {
            "zipSha256": fingerprint.get("lean_zip_sha256"),
            "factorSha256": fingerprint.get("factor_file_sha256"),
            "manifestSha256": fingerprint.get("leanCacheManifestSha256") or (
                _hash(
                    {
                        "zipSha256": fingerprint.get("lean_zip_sha256"),
                        "factorSha256": fingerprint.get("factor_file_sha256"),
                    }
                )
                if fingerprint.get("lean_zip_sha256") or fingerprint.get("factor_file_sha256")
                else None
            ),
        },
        "configSha256": fingerprint.get("configFileHash"),
        "canonicalResultSha256": fingerprint.get("canonicalResultSha256") or _hash(payload),
        "ordersSha256": _hash(orders),
        "fillsSha256": _hash(fills),
        "equitySha256": _hash(equity),
        "artifactManifestSha256": _hash(artifact_manifest),
    }
    required = (
        components.get("dockerImageDigest"),
        (components.get("projectSnapshot") or {}).get("strategyFileSha256"),
        (components.get("leanCache") or {}).get("manifestSha256"),
        components.get("configSha256"),
        components.get("canonicalResultSha256"),
        components.get("ordersSha256"),
        components.get("fillsSha256"),
        components.get("equitySha256"),
        components.get("artifactManifestSha256"),
    )
    if any(not value for value in required):
        raise ValueError("reproducibility_component_digest_missing")
    input_fingerprint = str(fingerprint.get("inputFingerprint") or "")
    if not input_fingerprint:
        raise ValueError("input_fingerprint_missing")
    equivalence_digest = _hash(
        {
            "inputFingerprint": input_fingerprint,
            "datasetReleaseId": release_id,
            "canonicalResultSha256": components["canonicalResultSha256"],
            "ordersSha256": components["ordersSha256"],
            "fillsSha256": components["fillsSha256"],
            "equitySha256": components["equitySha256"],
        }
    )
    certificate_id = f"repro:{uuid.uuid4()}"
    created_at = utc_now()
    certificate = {
        "schemaVersion": 1,
        "id": certificate_id,
        "runId": run_id,
        "createdAt": created_at,
        "inputFingerprint": input_fingerprint,
        "equivalenceDigest": equivalence_digest,
        "components": components,
        "artifacts": artifact_manifest,
    }
    certificate_sha256 = _hash(certificate)
    stored = put_bytes(
        "reproducibility-certificates",
        f"{run_id}/{certificate_sha256}.json",
        json.dumps(certificate, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        content_type="application/json",
        metadata={"runId": run_id, "certificateSha256": certificate_sha256},
    )
    with db() as connection:
        connection.execute(
            """
            insert into reproducibility_certificates
                (id,run_id,dataset_release_id,input_fingerprint,equivalence_digest,
                 certificate_sha256,canonical_result_sha256,orders_sha256,fills_sha256,
                 equity_sha256,artifact_manifest_sha256,stored_object_id,status,
                 certificate_json,created_at)
            values (?,?,?,?,?,?,?,?,?,?,?,?, 'valid',?,?)
            on conflict(run_id) do update set
                dataset_release_id=excluded.dataset_release_id,
                input_fingerprint=excluded.input_fingerprint,
                equivalence_digest=excluded.equivalence_digest,
                certificate_sha256=excluded.certificate_sha256,
                canonical_result_sha256=excluded.canonical_result_sha256,
                orders_sha256=excluded.orders_sha256,
                fills_sha256=excluded.fills_sha256,
                equity_sha256=excluded.equity_sha256,
                artifact_manifest_sha256=excluded.artifact_manifest_sha256,
                stored_object_id=excluded.stored_object_id,
                status=excluded.status,
                certificate_json=excluded.certificate_json,
                created_at=excluded.created_at
            """,
            (
                certificate_id, run_id, release_id, input_fingerprint, equivalence_digest,
                certificate_sha256, components["canonicalResultSha256"], components["ordersSha256"],
                components["fillsSha256"], components["equitySha256"],
                components["artifactManifestSha256"], stored.get("id"), json_dump(certificate), created_at,
            ),
        )
        row = connection.execute(
            "select * from reproducibility_certificates where run_id=?",
            (run_id,),
        ).fetchone()
        persisted_id = str(row["id"])
        connection.execute(
            "update backtest_runs set reproducibility_certificate_id=? where id=?",
            (persisted_id, run_id),
        )
    return certificate_for_run(run_id) or {}


def certificate_for_run(run_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from reproducibility_certificates where run_id=?",
            (run_id,),
        ).fetchone()
        if not row:
            return None
        matches = connection.execute(
            """
            select run_id from reproducibility_certificates
            where input_fingerprint=? and equivalence_digest=? and status='valid'
            order by created_at
            """,
            (row["input_fingerprint"], row["equivalence_digest"]),
        ).fetchall()
    item = row_to_dict(row) or {}
    item["matchingRunIds"] = [str(match["run_id"]) for match in matches]
    item["goldenPair"] = len(matches) >= 2
    return item


def golden_pairs(limit: int = 100) -> dict[str, Any]:
    bounded = max(1, min(int(limit), 200))
    with db() as connection:
        rows = connection.execute(
            """
            select input_fingerprint,equivalence_digest,count(*) as run_count,
                   min(created_at) as first_created_at,max(created_at) as last_created_at
            from reproducibility_certificates where status='valid'
            group by input_fingerprint,equivalence_digest having count(*)>=2
            order by last_created_at desc limit ?
            """,
            (bounded,),
        ).fetchall()
    items = rows_to_dicts(rows)
    return {"items": items, "count": len(items), "limit": bounded, "offset": 0}
