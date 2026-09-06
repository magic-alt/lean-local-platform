"""Read-only facade for imported qlib-platform research bundles.

Research computation is intentionally external. This module only projects persisted
Artifact Contract v2 imports into UI/API-safe previews and never mutates research
state.
"""

from __future__ import annotations

import json
from typing import Any

from ..db import db, row_to_dict, rows_to_dicts


def _json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _signal_preview(connection, import_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """select * from qlib_signal_snapshots
           where import_id=? order by created_at desc limit 1""",
        (import_id,),
    ).fetchone()
    item = row_to_dict(row)
    if not item:
        return None
    targets = _json(item.get("targets_json"), [])
    preview_targets = sorted(
        [dict(target) for target in targets if isinstance(target, dict)],
        key=lambda target: float(target.get("targetWeight") or target.get("target_weight") or 0),
        reverse=True,
    )[:10]
    return {
        "id": item.get("id"),
        "signalDate": item.get("signal_date"),
        "tradeDate": item.get("trade_date"),
        "targetArtifactId": item.get("target_artifact_id"),
        "targetsSha256": item.get("targets_sha256"),
        "targetCount": int(item.get("target_count") or len(targets)),
        "grossExposure": item.get("gross_exposure"),
        "previewTargets": preview_targets,
    }


def _validation_preview(connection, research_run_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """select * from qlib_lean_validations
           where research_run_id=? order by created_at desc limit 1""",
        (research_run_id,),
    ).fetchone()
    item = row_to_dict(row)
    if not item:
        return None
    return {
        "id": item.get("id"),
        "status": item.get("status"),
        "leanBacktestRunId": item.get("lean_backtest_run_id"),
        "validationArtifactId": item.get("validation_artifact_id"),
        "createdAt": item.get("created_at"),
    }


def _project_import(connection, raw: dict[str, Any], *, include_manifest: bool) -> dict[str, Any]:
    run_id = str(raw.get("research_run_id") or "")
    run_row = connection.execute(
        "select name,status,scope_json,summary_json from research_runs where id=?",
        (run_id,),
    ).fetchone()
    run = row_to_dict(run_row) or {}
    scope = _json(run.get("scope_json"), {})
    manifest = _json(raw.get("manifest_json"), {})
    artifacts = manifest.get("artifacts") if isinstance(manifest, dict) else []
    artifact_summary = [
        {
            "artifactId": item.get("artifactId"),
            "artifactType": item.get("artifactType"),
            "promotionStatus": item.get("promotionStatus"),
            "payloadSha256": item.get("payloadSha256"),
        }
        for item in artifacts or []
        if isinstance(item, dict)
    ]
    item = {
        "id": raw.get("id"),
        "researchRunId": run_id,
        "externalRunId": raw.get("external_run_id"),
        "name": run.get("name"),
        "status": run.get("status"),
        "market": scope.get("market") or "china",
        "schemaVersion": raw.get("schema_version"),
        "runKind": raw.get("run_kind"),
        "dataReleaseId": raw.get("data_release_id") or raw.get("dataset_fingerprint"),
        "modelReleaseId": raw.get("model_fingerprint"),
        "manifestSha256": raw.get("manifest_sha256"),
        "rootArtifactIds": _json(raw.get("root_artifact_ids_json"), []),
        "summary": _json(run.get("summary_json"), {}),
        "artifactSummary": artifact_summary,
        "latestSignal": _signal_preview(connection, str(raw.get("id") or "")),
        "leanValidation": _validation_preview(connection, run_id),
        "createdAt": raw.get("created_at"),
    }
    if include_manifest:
        item["manifest"] = manifest
    return item


def list_imports(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    bounded_limit = min(max(int(limit), 1), 100)
    bounded_offset = max(int(offset), 0)
    with db() as connection:
        rows = connection.execute(
            "select * from qlib_research_imports order by created_at desc limit ? offset ?",
            (bounded_limit, bounded_offset),
        ).fetchall()
        count_row = connection.execute("select count(*) as count from qlib_research_imports").fetchone()
        raw_items = rows_to_dicts(rows)
        items = [_project_import(connection, raw, include_manifest=False) for raw in raw_items]
    return {
        "items": items,
        "count": int(count_row["count"] if count_row else len(items)),
        "limit": bounded_limit,
        "offset": bounded_offset,
    }


def get_import(import_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from qlib_research_imports where id=?", (import_id,)).fetchone()
        raw = row_to_dict(row)
        if not raw:
            raise KeyError(f"Qlib research import not found: {import_id}")
        return _project_import(connection, raw, include_manifest=True)
