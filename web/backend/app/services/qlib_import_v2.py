from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Mapping

from ..db import db, json_dump, row_to_dict, utc_now
from . import artifact_registry, object_store


SCHEMA_VERSION = "2.0"
IMPORT_TYPE = "QLIB_RESEARCH_BUNDLE"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _required_string(item: Mapping[str, Any], key: str, *, owner: str) -> str:
    value = str(item.get(key) or "").strip()
    if not value:
        raise ValueError(f"{owner}.{key} is required")
    return value


def _normalize_targets(payload: object) -> list[dict[str, Any]]:
    envelope = payload if isinstance(payload, Mapping) else {}
    raw_targets = envelope.get("targets") if isinstance(envelope.get("targets"), list) else []
    if not raw_targets:
        raise ValueError("TARGET_PORTFOLIO payload must contain targets")
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    gross = 0.0
    for raw in raw_targets:
        item = raw if isinstance(raw, Mapping) else {}
        instrument = str(item.get("instrument") or "").strip().upper()
        if len(instrument) != 8 or instrument[:2] not in {"SH", "SZ", "BJ"} or not instrument[2:].isdigit():
            raise ValueError(f"Invalid Qlib instrument: {instrument}")
        if instrument in seen:
            raise ValueError(f"Duplicate Qlib instrument: {instrument}")
        seen.add(instrument)
        raw_weight = item.get("targetWeight", item.get("target_weight"))
        weight = float(raw_weight)
        if weight < 0 or weight > 1:
            raise ValueError(f"Invalid target weight for {instrument}")
        gross += weight
        result.append({"instrument": instrument, "targetWeight": weight, "score": item.get("score")})
    if gross > 1.000001:
        raise ValueError("Gross target exposure exceeds 1.0")
    return sorted(result, key=lambda item: item["instrument"])


def validate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if str(payload.get("schemaVersion") or "") != SCHEMA_VERSION:
        raise ValueError("Unsupported Qlib import schemaVersion")
    if str(payload.get("importType") or "") != IMPORT_TYPE:
        raise ValueError("Unsupported Qlib v2 importType")
    external_run_id = _required_string(payload, "externalRunId", owner="bundle")
    run_kind = _required_string(payload, "runKind", owner="bundle")
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
    roots = payload.get("rootArtifactIds") if isinstance(payload.get("rootArtifactIds"), list) else []
    if not artifacts or not roots:
        raise ValueError("Qlib v2 import requires artifacts and rootArtifactIds")
    ids: set[str] = set()
    data_release_ids: set[str] = set()
    model_artifacts: list[dict[str, Any]] = []
    normalized: list[dict[str, Any]] = []
    for raw in artifacts:
        if not isinstance(raw, Mapping):
            raise ValueError("Each Qlib v2 artifact must be an object")
        item = dict(raw)
        artifact_id = _required_string(item, "artifactId", owner="artifact")
        if artifact_id in ids:
            raise ValueError(f"Duplicate artifactId: {artifact_id}")
        ids.add(artifact_id)
        if str(item.get("schemaVersion") or "") != SCHEMA_VERSION:
            raise ValueError(f"Unsupported artifact schemaVersion: {artifact_id}")
        artifact_type = _required_string(item, "artifactType", owner=artifact_id)
        status = _required_string(item, "promotionStatus", owner=artifact_id)
        if artifact_type not in artifact_registry.QLIB_TYPES:
            raise ValueError(f"Qlib cannot publish artifact type: {artifact_type}")
        if status not in artifact_registry.QLIB_STATUSES:
            raise ValueError(f"Qlib cannot publish promotion status: {status}")
        data_release_id = _required_string(item, "dataReleaseId", owner=artifact_id)
        if not data_release_id.startswith("ds_") or len(data_release_id) != 67:
            raise ValueError(f"Invalid dataReleaseId: {data_release_id}")
        data_release_ids.add(data_release_id)
        for field in ("gitCommit", "containerDigest", "asOfTime", "timezone", "currency", "payloadSha256"):
            _required_string(item, field, owner=artifact_id)
        payload_ref = item.get("payloadRef") if isinstance(item.get("payloadRef"), Mapping) else {}
        object_key = _required_string(payload_ref, "objectKey", owner=f"{artifact_id}.payloadRef")
        ref_sha = _required_string(payload_ref, "sha256", owner=f"{artifact_id}.payloadRef").lower()
        if len(ref_sha) != 64 or ref_sha != str(item["payloadSha256"]).lower():
            raise ValueError(f"Artifact payload hash mismatch: {artifact_id}")
        _required_string(payload_ref, "mediaType", owner=f"{artifact_id}.payloadRef")
        item["payloadRef"] = {**payload_ref, "objectKey": object_key, "sha256": ref_sha}
        parents = item.get("parentArtifactIds") if isinstance(item.get("parentArtifactIds"), list) else []
        if len(parents) != len(set(map(str, parents))):
            raise ValueError(f"Duplicate artifact parent: {artifact_id}")
        item["parentArtifactIds"] = [str(parent) for parent in parents]
        item["metadata"] = dict(item.get("metadata") or {})
        if artifact_type in {"SIGNAL_SNAPSHOT", "TARGET_PORTFOLIO"}:
            signal_date = _required_string(item, "signalDate", owner=artifact_id)
            trade_date = _required_string(item, "tradeDate", owner=artifact_id)
            if trade_date <= signal_date:
                raise ValueError(f"{artifact_type}.tradeDate must be after signalDate")
        if artifact_type == "MODEL_RELEASE":
            model_artifacts.append(item)
            if item.get("modelReleaseId") not in {None, "", artifact_id}:
                raise ValueError("MODEL_RELEASE modelReleaseId must equal artifactId when supplied")
            item["modelReleaseId"] = artifact_id
        normalized.append(item)
    if len(data_release_ids) != 1:
        raise ValueError("All Qlib v2 artifacts must reference one DataRelease")
    if len(model_artifacts) != 1:
        raise ValueError("Qlib v2 import requires exactly one MODEL_RELEASE")
    unknown_roots = sorted(set(map(str, roots)) - ids)
    if unknown_roots:
        raise ValueError(f"Unknown rootArtifactIds: {unknown_roots}")
    unknown_parents = sorted(
        {parent for item in normalized for parent in item["parentArtifactIds"] if parent not in ids}
    )
    if unknown_parents:
        raise ValueError(f"Artifact parents must be included in the import bundle: {unknown_parents}")
    model_release_id = str(model_artifacts[0]["artifactId"])
    for item in normalized:
        if item["artifactType"] not in {"MODEL_RELEASE", "STRATEGY_POLICY"}:
            if str(item.get("modelReleaseId") or "") != model_release_id:
                raise ValueError(f"Artifact modelReleaseId mismatch: {item['artifactId']}")
    return {
        "externalRunId": external_run_id,
        "runKind": run_kind,
        "dataReleaseId": next(iter(data_release_ids)),
        "modelReleaseId": model_release_id,
        "rootArtifactIds": [str(item) for item in roots],
        "artifacts": normalized,
    }


def _verified_payloads(artifacts: list[dict[str, Any]]) -> tuple[dict[str, object], list[str]]:
    payloads: dict[str, object] = {}
    object_keys: list[str] = []
    for item in artifacts:
        payload_ref = item["payloadRef"]
        key = str(payload_ref["objectKey"])
        path = object_store.get_item_path(key)
        raw = path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != payload_ref["sha256"]:
            raise ValueError(f"Artifact checksum mismatch: {key}")
        object_keys.append(key)
        if item["artifactType"] in {"TARGET_PORTFOLIO", "VALIDATION_RESULT"}:
            try:
                payloads[item["artifactId"]] = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Artifact payload must be JSON: {key}") from exc
    return payloads, object_keys


def import_run(payload: Mapping[str, Any]) -> dict[str, Any]:
    validated = validate_payload(payload)
    manifest_json = _canonical_json(payload)
    manifest_sha = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
    with db() as connection:
        existing = connection.execute(
            "select * from qlib_research_imports where external_run_id=?",
            (validated["externalRunId"],),
        ).fetchone()
        release = connection.execute(
            "select id,status from data_releases where id=?", (validated["dataReleaseId"],)
        ).fetchone()
    existing_item = row_to_dict(existing)
    if existing_item:
        if str(existing_item["manifest_sha256"]) != manifest_sha:
            raise ValueError("externalRunId already exists with different content")
        with db() as connection:
            signal = connection.execute(
                "select id from qlib_signal_snapshots where research_run_id=? order by created_at desc limit 1",
                (existing_item["research_run_id"],),
            ).fetchone()
        return {
            "researchRunId": existing_item["research_run_id"],
            "importId": existing_item["id"],
            "signalSnapshotId": signal["id"] if signal else None,
            "replayed": True,
            "schemaVersion": SCHEMA_VERSION,
            "warnings": [],
        }
    if not release or str(release["status"]) != "active":
        raise ValueError("Qlib v2 import requires an active registered DataRelease")

    artifacts = validated["artifacts"]
    payloads, object_keys = _verified_payloads(artifacts)
    target_items = [item for item in artifacts if item["artifactType"] == "TARGET_PORTFOLIO"]
    target_projections: list[tuple[dict[str, Any], list[dict[str, Any]], str, float]] = []
    for item in target_items:
        targets = _normalize_targets(payloads[item["artifactId"]])
        targets_sha = hashlib.sha256(_canonical_json(targets).encode("utf-8")).hexdigest()
        expected = str(item["metadata"].get("targetsSha256") or "")
        if expected and expected != targets_sha:
            raise ValueError(f"TARGET_PORTFOLIO targets hash mismatch: {item['artifactId']}")
        target_projections.append((item, targets, targets_sha, sum(float(row["targetWeight"]) for row in targets)))
    target_projections.sort(key=lambda value: str(value[0].get("tradeDate") or ""))
    latest = target_projections[-1] if target_projections else None
    validation_items = [item for item in artifacts if item["artifactType"] == "VALIDATION_RESULT"]
    metrics = {}
    if validation_items:
        raw_validation = payloads.get(validation_items[-1]["artifactId"])
        if isinstance(raw_validation, Mapping):
            metrics = dict(raw_validation.get("metrics") or {})

    run_id, item_id, import_id = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    now = utc_now()
    result = {
        "schemaVersion": SCHEMA_VERSION,
        "template": "qlib-cross-sectional-v1",
        "dataReleaseId": validated["dataReleaseId"],
        "dataFingerprint": validated["dataReleaseId"],
        "summary": metrics,
        "rootArtifactIds": validated["rootArtifactIds"],
        "warnings": [],
    }
    scope = {"assetClass": "equity", "market": "china", "universe": payload.get("universe")}
    snapshot_id: str | None = None
    with db() as connection:
        connection.execute(
            """insert into research_runs
               (id,template_key,name,status,scope_json,parameters_json,result_json,summary_json,
                data_fingerprint,cancel_requested,created_at,started_at,finished_at)
               values (?,? ,?,'success',?,?,?,?,?,0,?,?,?)""",
            (
                run_id,
                "qlib-cross-sectional-v1",
                str(payload.get("name") or f"Qlib {validated['externalRunId']}"),
                json_dump(scope),
                json_dump({"externalRunId": validated["externalRunId"], "runKind": validated["runKind"]}),
                json_dump(result),
                json_dump(metrics),
                validated["dataReleaseId"],
                now,
                now,
                now,
            ),
        )
        connection.execute(
            """insert into research_run_items
               (id,run_id,item_index,item_key,status,parameters_json,result_json,created_at,started_at,finished_at)
               values (?,?,0,?,'success',?,?,?,?,?)""",
            (
                item_id,
                run_id,
                "qlib-cross-sectional-v1",
                json_dump({"externalRunId": validated["externalRunId"]}),
                json_dump(result),
                now,
                now,
                now,
            ),
        )
        connection.execute(
            """insert into qlib_research_imports
               (id,research_run_id,external_run_id,schema_version,run_kind,dataset_fingerprint,
                model_fingerprint,manifest_sha256,manifest_json,object_keys_json,created_at,
                data_release_id,root_artifact_ids_json)
               values (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                import_id,
                run_id,
                validated["externalRunId"],
                SCHEMA_VERSION,
                validated["runKind"],
                validated["dataReleaseId"],
                validated["modelReleaseId"],
                manifest_sha,
                manifest_json,
                json_dump(object_keys),
                now,
                validated["dataReleaseId"],
                json_dump(validated["rootArtifactIds"]),
            ),
        )
        artifact_registry.register_qlib_artifacts(connection, artifacts)
        if latest:
            artifact, targets, targets_sha, gross = latest
            snapshot_id = str(uuid.uuid4())
            connection.execute(
                """insert into qlib_signal_snapshots
                   (id,import_id,research_run_id,model_fingerprint,dataset_fingerprint,signal_date,
                    trade_date,targets_sha256,target_count,gross_exposure,targets_json,target_artifact_id,created_at)
                   values (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    snapshot_id,
                    import_id,
                    run_id,
                    validated["modelReleaseId"],
                    validated["dataReleaseId"],
                    artifact["signalDate"],
                    artifact["tradeDate"],
                    targets_sha,
                    len(targets),
                    gross,
                    json_dump(targets),
                    artifact["artifactId"],
                    now,
                ),
            )
    return {
        "researchRunId": run_id,
        "importId": import_id,
        "signalSnapshotId": snapshot_id,
        "replayed": False,
        "schemaVersion": SCHEMA_VERSION,
        "warnings": [],
    }
