from __future__ import annotations

import pytest

from app.services.qlib_import_v2 import validate_payload


def _artifact(artifact_id: str, artifact_type: str, *, parents: list[str] | None = None):
    model_id = "model-1"
    return {
        "schemaVersion": "2.0",
        "artifactId": artifact_id,
        "artifactType": artifact_type,
        "promotionStatus": "RESEARCH_PROMOTED",
        "dataReleaseId": "ds_" + "a" * 64,
        "universeReleaseId": "universe-1",
        "modelReleaseId": artifact_id if artifact_type == "MODEL_RELEASE" else model_id,
        "strategyPolicyId": "policy-1",
        "gitCommit": "abc123",
        "containerDigest": "sha256:" + "b" * 64,
        "asOfTime": "2026-08-14T00:00:00+08:00",
        "signalDate": "2026-08-13" if artifact_type == "TARGET_PORTFOLIO" else None,
        "tradeDate": "2026-08-14" if artifact_type == "TARGET_PORTFOLIO" else None,
        "timezone": "Asia/Shanghai",
        "currency": "CNY",
        "payloadSha256": "c" * 64,
        "parentArtifactIds": parents or [],
        "payloadRef": {"objectKey": f"qlib/run/{artifact_id}.json", "sha256": "c" * 64, "mediaType": "application/json", "rows": 1},
        "metadata": {},
    }


def _payload():
    model = _artifact("model-1", "MODEL_RELEASE")
    target = _artifact("target-1", "TARGET_PORTFOLIO", parents=["model-1"])
    return {
        "schemaVersion": "2.0",
        "importType": "QLIB_RESEARCH_BUNDLE",
        "externalRunId": "run-v2",
        "runKind": "walk_forward",
        "rootArtifactIds": ["target-1"],
        "artifacts": [model, target],
    }


def test_validate_v2_bundle_builds_one_release_graph():
    result = validate_payload(_payload())
    assert result["modelReleaseId"] == "model-1"
    assert result["dataReleaseId"] == "ds_" + "a" * 64


def test_validate_v2_rejects_execution_artifacts_and_platform_statuses():
    payload = _payload()
    payload["artifacts"][1]["artifactType"] = "ORDER_INTENT"
    with pytest.raises(ValueError, match="cannot publish artifact type"):
        validate_payload(payload)
    payload = _payload()
    payload["artifacts"][1]["promotionStatus"] = "PRODUCTION"
    with pytest.raises(ValueError, match="cannot publish promotion status"):
        validate_payload(payload)


def test_validate_v2_rejects_unknown_parent_and_same_day_trade():
    payload = _payload()
    payload["artifacts"][1]["parentArtifactIds"] = ["missing"]
    with pytest.raises(ValueError, match="parents must be included"):
        validate_payload(payload)
    payload = _payload()
    payload["artifacts"][1]["tradeDate"] = payload["artifacts"][1]["signalDate"]
    with pytest.raises(ValueError, match="must be after"):
        validate_payload(payload)


def test_register_v2_artifact_graph_is_idempotent():
    from app import db as db_module
    from app.services.artifact_registry import register_qlib_artifacts

    db_module.init_db()
    artifacts = [
        _artifact("model-1", "MODEL_RELEASE"),
        _artifact("target-1", "TARGET_PORTFOLIO", parents=["model-1"]),
    ]
    with db_module.db() as connection:
        register_qlib_artifacts(connection, artifacts)
        register_qlib_artifacts(connection, artifacts)
    with db_module.db() as connection:
        artifact_count = connection.execute("select count(*) from artifact_registry").fetchone()[0]
        edge_count = connection.execute("select count(*) from artifact_lineage_edges").fetchone()[0]
        event_count = connection.execute("select count(*) from artifact_promotion_events").fetchone()[0]

    assert artifact_count == 2
    assert edge_count == 1
