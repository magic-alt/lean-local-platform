from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from ..db import db, json_dump, row_to_dict, rows_to_dicts, utc_now
from ..domain.data_scope import DataScope
from . import ashare_swing_screen, daily_gap_analysis, data_gateway, ml_research, object_store, qlib_import_v2, qlib_promotion, research_analysis


QLIB_TEMPLATE_KEY = "qlib-cross-sectional-v1"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_qlib_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("schemaVersion") or "") == "2.0":
        return qlib_import_v2.validate_payload(payload)
    required = {"schemaVersion", "externalRunId", "runKind", "dataset", "model", "execution", "metrics", "latestTargets"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"Qlib import missing fields: {missing}")
    if str(payload["schemaVersion"]) != "1.0":
        raise ValueError("Unsupported Qlib import schemaVersion")
    dataset = payload["dataset"] if isinstance(payload["dataset"], dict) else {}
    model = payload["model"] if isinstance(payload["model"], dict) else {}
    if not str(dataset.get("fingerprint") or "").strip():
        raise ValueError("dataset.fingerprint is required")
    if not str(model.get("fingerprint") or "").strip():
        raise ValueError("model.fingerprint is required")
    latest = payload["latestTargets"] if isinstance(payload["latestTargets"], dict) else {}
    signal_date = str(latest.get("signalDate") or "")
    trade_date = str(latest.get("tradeDate") or "")
    if not signal_date or not trade_date or trade_date <= signal_date:
        raise ValueError("latestTargets.tradeDate must be after signalDate")
    targets = latest.get("targets") if isinstance(latest.get("targets"), list) else []
    if not targets:
        raise ValueError("latestTargets.targets must not be empty")
    seen: set[str] = set()
    gross = 0.0
    normalized: list[dict[str, Any]] = []
    for target in targets:
        instrument = str(target.get("instrument") or "").strip().upper()
        if len(instrument) != 8 or instrument[:2] not in {"SH", "SZ", "BJ"} or not instrument[2:].isdigit():
            raise ValueError(f"Invalid Qlib instrument: {instrument}")
        if instrument in seen:
            raise ValueError(f"Duplicate Qlib instrument: {instrument}")
        seen.add(instrument)
        weight = float(target.get("targetWeight"))
        if weight < 0 or weight > 1:
            raise ValueError(f"Invalid target weight for {instrument}")
        gross += weight
        normalized.append({"instrument": instrument, "targetWeight": weight, "score": target.get("score")})
    if gross > 1.000001:
        raise ValueError("Gross target exposure exceeds 1.0")
    normalized.sort(key=lambda item: item["instrument"])
    return {
        "datasetFingerprint": str(dataset["fingerprint"]),
        "modelFingerprint": str(model["fingerprint"]),
        "signalDate": signal_date,
        "tradeDate": trade_date,
        "targets": normalized,
        "targetsSha256": hashlib.sha256(_canonical_json(normalized).encode()).hexdigest(),
        "grossExposure": gross,
    }


def _qlib_import_for_run(run_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute("select * from qlib_research_imports where research_run_id=?", (run_id,)).fetchone()
        imported = row_to_dict(row)
        if not imported:
            return None
        signal = connection.execute(
            "select * from qlib_signal_snapshots where research_run_id=? order by created_at desc limit 1",
            (run_id,),
        ).fetchone()
    imported["latestSignal"] = row_to_dict(signal)
    return imported


def import_qlib_run(payload: dict[str, Any]) -> dict[str, Any]:
    if str(payload.get("schemaVersion") or "") == "2.0":
        return qlib_import_v2.import_run(payload)
    validated = _validate_qlib_payload(payload)
    external_run_id = str(payload["externalRunId"]).strip()
    manifest_json = _canonical_json(payload)
    manifest_sha256 = hashlib.sha256(manifest_json.encode()).hexdigest()
    with db() as connection:
        existing = connection.execute(
            "select * from qlib_research_imports where external_run_id=?", (external_run_id,)
        ).fetchone()
    existing_item = row_to_dict(existing)
    if existing_item:
        if str(existing_item["manifest_sha256"]) != manifest_sha256:
            raise ValueError("externalRunId already exists with different content")
        run = get_run(str(existing_item["research_run_id"]))
        return {
            "researchRunId": run["id"], "importId": existing_item["id"],
            "signalSnapshotId": (run.get("qlibImport") or {}).get("latestSignal", {}).get("id"),
            "replayed": True,
        }

    object_keys: list[str] = []
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
    for artifact in artifacts:
        key = str(artifact.get("objectKey") or "").strip()
        expected = str(artifact.get("sha256") or "").strip().lower()
        if not key or len(expected) != 64:
            raise ValueError("Each artifact requires objectKey and sha256")
        path = object_store.get_item_path(key)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Artifact checksum mismatch: {key}")
        object_keys.append(key)

    run_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    import_id = str(uuid.uuid4())
    snapshot_id = str(uuid.uuid4())
    now = utc_now()
    result = {
        "schemaVersion": "1.0",
        "template": QLIB_TEMPLATE_KEY,
        "dataFingerprint": validated["datasetFingerprint"],
        "summary": payload.get("metrics") or {},
        "artifacts": artifacts,
        "latestTargets": payload["latestTargets"],
        "warnings": [],
    }
    scope = {
        "assetClass": "equity", "market": "china", "universe": payload["dataset"].get("universe"),
        "startDate": payload["dataset"].get("startDate"), "endDate": payload["dataset"].get("endDate"),
    }
    with db() as connection:
        connection.execute(
            """insert into research_runs
               (id,template_key,name,status,scope_json,parameters_json,result_json,summary_json,
                data_fingerprint,cancel_requested,created_at,started_at,finished_at)
               values (?,?,?,'success',?,?,?,?,?,0,?,?,?)""",
            (run_id, QLIB_TEMPLATE_KEY, str(payload.get("name") or f"Qlib {external_run_id}"),
             json_dump(scope), json_dump({"externalRunId": external_run_id, "runKind": payload["runKind"]}),
             json_dump(result), json_dump(payload.get("metrics") or {}), validated["datasetFingerprint"], now, now, now),
        )
        connection.execute(
            """insert into research_run_items
               (id,run_id,item_index,item_key,status,parameters_json,result_json,created_at,started_at,finished_at)
               values (?,?,0,?,'success',?,?,?,?,?)""",
            (item_id, run_id, QLIB_TEMPLATE_KEY, json_dump({"externalRunId": external_run_id}), json_dump(result), now, now, now),
        )
        connection.execute(
            """insert into qlib_research_imports
               (id,research_run_id,external_run_id,schema_version,run_kind,dataset_fingerprint,
                model_fingerprint,manifest_sha256,manifest_json,object_keys_json,created_at)
               values (?,?,?,?,?,?,?,?,?,?,?)""",
            (import_id, run_id, external_run_id, payload["schemaVersion"], payload["runKind"],
             validated["datasetFingerprint"], validated["modelFingerprint"], manifest_sha256,
             manifest_json, json_dump(object_keys), now),
        )
        connection.execute(
            """insert into qlib_signal_snapshots
               (id,import_id,research_run_id,model_fingerprint,dataset_fingerprint,signal_date,
                trade_date,targets_sha256,target_count,gross_exposure,targets_json,created_at)
               values (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (snapshot_id, import_id, run_id, validated["modelFingerprint"], validated["datasetFingerprint"],
             validated["signalDate"], validated["tradeDate"], validated["targetsSha256"],
             len(validated["targets"]), validated["grossExposure"], json_dump(validated["targets"]), now),
        )
    return {"researchRunId": run_id, "importId": import_id, "signalSnapshotId": snapshot_id, "replayed": False}


def preview(template_key: str, scope: DataScope | dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
    research_analysis.template(template_key)
    if template_key == ml_research.TEMPLATE_KEY:
        normalized = data_gateway.normalize_scope(scope)
        return ml_research.preview(parameters, scope=normalized)
    if template_key == ashare_swing_screen.TEMPLATE_KEY:
        normalized = data_gateway.normalize_scope(scope)
        resolved = data_gateway.resolve(normalized)
        payload = ashare_swing_screen.preview(normalized, parameters)
        return {
            **resolved,
            **payload,
            "scope": normalized,
            "scopeHash": resolved["scopeHash"],
            "dataFingerprint": resolved["dataFingerprint"],
        }
    if template_key == daily_gap_analysis.TEMPLATE_KEY:
        normalized = data_gateway.normalize_scope(scope)
        resolved = data_gateway.resolve(normalized)
        return {
            **resolved,
            **daily_gap_analysis.preview(normalized, parameters, resolved=resolved),
            "scope": normalized,
            "scopeHash": resolved["scopeHash"],
            "dataFingerprint": resolved["dataFingerprint"],
        }
    resolved = data_gateway.resolve(scope)
    return {
        **resolved,
        "template": template_key,
        "parameters": parameters,
        "blocking": [] if resolved["ready"] or template_key in {"universe-pit", "cbond-double-low", "factor-evaluation", "futures-continuous"} else ["data_unavailable"],
    }


def list_runs(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    with db() as connection:
        rows = connection.execute(
            "select * from research_runs order by created_at desc limit ? offset ?",
            (min(max(limit, 1), 500), max(offset, 0)),
        ).fetchall()
    return rows_to_dicts(rows)


def get_run(run_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute("select * from research_runs where id=?", (run_id,)).fetchone()
    item = row_to_dict(row)
    if item is None:
        raise KeyError("Research run not found.")
    if item.get("template_key") == ml_research.TEMPLATE_KEY:
        item["mlResearch"] = ml_research.training_for_research(run_id)
        if item["mlResearch"]:
            item["mlResearch"] = ml_research.training_detail(str(item["mlResearch"]["id"]))
    if item.get("template_key") == QLIB_TEMPLATE_KEY:
        item["qlibImport"] = _qlib_import_for_run(run_id)
    return item


def create_run(
    *,
    template_key: str,
    name: str | None,
    scope: DataScope | dict[str, Any],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    template = research_analysis.template(template_key)
    if template.get("legacy"):
        raise ValueError("QLIB_OWNS_MODEL_TRAINING: create the model research job in qlib-platform")
    normalized = data_gateway.normalize_scope(scope)
    if template_key == ml_research.TEMPLATE_KEY:
        ml_research.validate_scope(normalized, parameters)
    run_id = str(uuid.uuid4())
    item_id = str(uuid.uuid4())
    now = utc_now()
    run_name = str(name or template["name"]).strip() or template["name"]
    queued = template_key == ml_research.TEMPLATE_KEY or research_analysis.is_async_template(template_key)
    with db() as connection:
        connection.execute(
            """
            insert into research_runs
                (id, template_key, name, status, scope_json, parameters_json,
                 cancel_requested, created_at, started_at)
            values (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (run_id, template_key, run_name, "queued" if queued else "running", json_dump(normalized), json_dump(parameters), now, None if queued else now),
        )
        connection.execute(
            """
            insert into research_run_items
                (id, run_id, item_index, item_key, status, parameters_json, created_at, started_at)
            values (?, ?, 0, ?, ?, ?, ?, ?)
            """,
            (item_id, run_id, template_key, "queued" if queued else "running", json_dump(parameters), now, None if queued else now),
        )
    if template_key == ml_research.TEMPLATE_KEY:
        ml_research.create_training_record(run_id, parameters)
        return get_run(run_id)
    if queued:
        return get_run(run_id)
    try:
        result = research_analysis.analyze(template_key, normalized, parameters)
        finished = utc_now()
        summary = result.get("summary") or {}
        with db() as connection:
            connection.execute(
                """
                update research_runs
                set status='success', result_json=?, summary_json=?, data_fingerprint=?, finished_at=?
                where id=?
                """,
                (json_dump(result), json_dump(summary), result["dataFingerprint"], finished, run_id),
            )
            connection.execute(
                "update research_run_items set status='success', result_json=?, finished_at=? where id=?",
                (json_dump(result), finished, item_id),
            )
    except Exception as exc:
        finished = utc_now()
        with db() as connection:
            connection.execute(
                "update research_runs set status='failed', error=?, finished_at=? where id=?",
                (str(exc), finished, run_id),
            )
            connection.execute(
                "update research_run_items set status='failed', error=?, finished_at=? where id=?",
                (str(exc), finished, item_id),
            )
    return get_run(run_id)


def execute_analysis_run(
    run_id: str,
    *,
    progress=None,
) -> dict[str, Any]:
    item = get_run(run_id)
    if item["status"] in {"success", "failed", "cancelled"}:
        return item
    if not research_analysis.is_async_template(str(item["template_key"])):
        raise ValueError("Research run is not an asynchronous analysis template.")

    def cancelled() -> bool:
        with db() as connection:
            row = connection.execute(
                "select cancel_requested,status from research_runs where id=?",
                (run_id,),
            ).fetchone()
        return bool(row and (row["cancel_requested"] or row["status"] == "cancelled"))

    started = utc_now()
    with db() as connection:
        connection.execute(
            "update research_runs set status='running',started_at=coalesce(started_at,?),owner_heartbeat_at=?,error=null where id=?",
            (started, started, run_id),
        )
        connection.execute(
            "update research_run_items set status='running',started_at=coalesce(started_at,?),error=null where run_id=?",
            (started, run_id),
        )
    try:
        result = research_analysis.analyze(
            str(item["template_key"]),
            item["scope"],
            item["parameters"],
            run_id=run_id,
            cancelled=cancelled,
            progress=progress,
        )
        if cancelled():
            raise RuntimeError("research_run_cancelled")
        finished = utc_now()
        summary = result.get("summary") or {}
        with db() as connection:
            connection.execute(
                """
                update research_runs
                set status='success',result_json=?,summary_json=?,data_fingerprint=?,owner_heartbeat_at=?,finished_at=?
                where id=?
                """,
                (json_dump(result), json_dump(summary), result["dataFingerprint"], finished, finished, run_id),
            )
            connection.execute(
                "update research_run_items set status='success',result_json=?,finished_at=? where run_id=?",
                (json_dump(result), finished, run_id),
            )
    except Exception as exc:
        finished = utc_now()
        cancelled_run = str(exc) == "research_run_cancelled" or cancelled()
        status = "cancelled" if cancelled_run else "failed"
        with db() as connection:
            connection.execute(
                "update research_runs set status=?,error=?,owner_heartbeat_at=?,finished_at=? where id=?",
                (status, None if cancelled_run else str(exc), finished, finished, run_id),
            )
            connection.execute(
                "update research_run_items set status=?,error=?,finished_at=? where run_id=?",
                (status, None if cancelled_run else str(exc), finished, run_id),
            )
        if not cancelled_run:
            raise
    return get_run(run_id)


def cancel_run(run_id: str) -> dict[str, Any]:
    item = get_run(run_id)
    if item["status"] in {"success", "failed", "cancelled"}:
        return item
    with db() as connection:
        connection.execute(
            "update research_runs set status='cancelled', cancel_requested=1, finished_at=? where id=?",
            (utc_now(), run_id),
        )
        connection.execute(
            "update research_run_items set status='cancelled', finished_at=? where run_id=? and status in ('queued','running')",
            (utc_now(), run_id),
        )
    return get_run(run_id)


def retry_run(run_id: str) -> dict[str, Any]:
    item = get_run(run_id)
    return create_run(
        template_key=str(item["template_key"]),
        name=f"{item['name']} · retry",
        scope=item["scope"],
        parameters=item["parameters"],
    )


def delete_run(run_id: str) -> None:
    item = get_run(run_id)
    if item.get("template_key") == ashare_swing_screen.TEMPLATE_KEY:
        ashare_swing_screen.remove_artifacts(run_id)
    with db() as connection:
        connection.execute("delete from qlib_signal_snapshots where research_run_id=?", (run_id,))
        connection.execute("delete from qlib_research_imports where research_run_id=?", (run_id,))
        connection.execute("delete from research_run_items where run_id=?", (run_id,))
        connection.execute("delete from research_runs where id=?", (run_id,))


def artifact_path(run_id: str, artifact_key: str) -> Path:
    item = get_run(run_id)
    if item.get("template_key") == ml_research.TEMPLATE_KEY:
        return ml_research.artifact_path(run_id, artifact_key)
    result = item.get("result") or {}
    artifact = next(
        (entry for entry in result.get("artifacts") or [] if str(entry.get("key")) == artifact_key),
        None,
    )
    if not artifact:
        raise KeyError("Research artifact not found.")
    return ashare_swing_screen.artifact_path(run_id, str(artifact.get("name") or ""))


def backtest_draft(run_id: str) -> dict[str, Any]:
    item = get_run(run_id)
    if item["template_key"] == QLIB_TEMPLATE_KEY:
        imported = item.get("qlibImport") or {}
        signal = imported.get("latestSignal") or {}
        if not signal:
            raise ValueError("Qlib signal snapshot is missing")
        return {
            **qlib_promotion.validation_draft(run_id, data_scope=item["scope"]),
            "dataFingerprint": item.get("data_fingerprint"),
            "signalSource": {
                "kind": "qlib_target_snapshot", "snapshotId": signal["id"],
                "signalDate": signal["signal_date"], "tradeDate": signal["trade_date"],
                "targetsSha256": signal["targets_sha256"],
            },
        }
    if item["template_key"] == ml_research.TEMPLATE_KEY:
        raise ValueError("ML_SIGNAL_EXPORT_NOT_IMPLEMENTED")
    if item["status"] != "success":
        raise ValueError("Only a successful research run can create a backtest draft.")
    resolved = data_gateway.resolve(item["scope"])
    values = list((item["scope"].get("selection") or {}).get("values") or [])
    selection_type = str((item["scope"].get("selection") or {}).get("type") or "symbols")
    target = "backtest" if selection_type in {"symbols", "products"} and len(values) == 1 else "batch"
    return {
        "sourceResearchRunId": run_id,
        "dataScope": item["scope"],
        "scopeHash": resolved["scopeHash"],
        "dataFingerprint": item.get("data_fingerprint") or resolved["dataFingerprint"],
        "target": target,
        "strategyRequired": True,
        "preflightRequired": True,
        "note": "Research data scope is preserved; order, fee, slippage and portfolio assumptions must be configured in Backtest.",
    }
