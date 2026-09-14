from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.qlib_import_v2 import validate_payload


DATA_RELEASE_ID = "ds_" + "a" * 64
UNIVERSE_RELEASE_ID = "universe-1"
SOURCE_MANIFEST_SHA256 = "d" * 64


def _artifact(
    artifact_id: str,
    artifact_type: str,
    *,
    parents: list[str] | None = None,
    source_manifest_sha256: str | None = None,
):
    model_id = "model-1"
    metadata = {}
    if source_manifest_sha256 is not None:
        metadata["sourceManifestSha256"] = source_manifest_sha256
    return {
        "schemaVersion": "2.0",
        "artifactId": artifact_id,
        "artifactType": artifact_type,
        "promotionStatus": "RESEARCH_PROMOTED",
        "dataReleaseId": DATA_RELEASE_ID,
        "universeReleaseId": UNIVERSE_RELEASE_ID,
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
        "payloadRef": {
            "objectKey": f"qlib/run/{artifact_id}.json",
            "sha256": "c" * 64,
            "mediaType": "application/json",
            "rows": 1,
        },
        "metadata": metadata,
    }


def _payload(*, with_source_manifest: bool = False):
    source_sha = SOURCE_MANIFEST_SHA256 if with_source_manifest else None
    model = _artifact("model-1", "MODEL_RELEASE", source_manifest_sha256=source_sha)
    target = _artifact(
        "target-1",
        "TARGET_PORTFOLIO",
        parents=["model-1"],
        source_manifest_sha256=source_sha,
    )
    artifacts = [model, target]
    roots = ["target-1"]
    if with_source_manifest:
        validation = _artifact(
            "validation-1",
            "VALIDATION_RESULT",
            parents=["target-1"],
            source_manifest_sha256=source_sha,
        )
        artifacts.append(validation)
        roots = ["validation-1"]
    return {
        "schemaVersion": "2.0",
        "importType": "QLIB_RESEARCH_BUNDLE",
        "externalRunId": "run-v2",
        "runKind": "walk_forward",
        "rootArtifactIds": roots,
        "artifacts": artifacts,
    }


def _register_data_release(connection, tmp_path: Path, *, universe_release_id: str = UNIVERSE_RELEASE_ID):
    connection.execute(
        """insert into data_releases
           (id,schema_version,profile,asset_class,market,universe,benchmark,coverage_start,coverage_end,
            as_of_time,identity_sha256,manifest_sha256,manifest_path,status,created_at)
           values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            DATA_RELEASE_ID,
            "2.0",
            "research",
            "equity",
            "china",
            "CSI300",
            "000300",
            "2020-01-01",
            "2020-12-31",
            "2026-08-14T00:00:00+08:00",
            "1" * 64,
            "2" * 64,
            str(tmp_path / "manifest.json"),
            "active",
            "2026-08-14T00:00:00+08:00",
        ),
    )
    component = {
        "role": "pit_universe",
        "componentReleaseId": universe_release_id,
        "datasetKey": "pit_universe",
        "schemaVersion": "1",
        "coverage": {"start": "2020-01-01", "end": "2020-12-31"},
        "files": [{"path": "pit_universe.parquet", "sha256": "3" * 64, "rowCount": 1}],
    }
    connection.execute(
        """insert into data_release_components
           (data_release_id,role,component_release_id,dataset_key,schema_version,
            coverage_start,coverage_end,file_count,row_count,component_sha256,component_json)
           values (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            DATA_RELEASE_ID,
            "pit_universe",
            universe_release_id,
            "pit_universe",
            "1",
            "2020-01-01",
            "2020-12-31",
            1,
            1,
            "4" * 64,
            json.dumps(component),
        ),
    )


def _materialize_payloads(
    payload: dict,
    tmp_path: Path,
    monkeypatch,
    *,
    validation_source_sha256: str = SOURCE_MANIFEST_SHA256,
):
    from app.services import qlib_import_v2

    raw_by_type = {
        "MODEL_RELEASE": b'{"model":"release"}',
        "TARGET_PORTFOLIO": json.dumps(
            {"targets": [{"instrument": "SH600000", "targetWeight": 1.0, "score": 1.0}]},
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
        "VALIDATION_RESULT": json.dumps(
            {"metrics": {"icir": 0.51}, "sourceManifestSha256": validation_source_sha256},
            sort_keys=True,
            separators=(",", ":"),
        ).encode(),
    }
    files: dict[str, Path] = {}
    for artifact in payload["artifacts"]:
        raw = raw_by_type[artifact["artifactType"]]
        path = tmp_path / f"{artifact['artifactId']}.json"
        path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        artifact["payloadSha256"] = digest
        artifact["payloadRef"]["sha256"] = digest
        files[artifact["payloadRef"]["objectKey"]] = path
    monkeypatch.setattr(qlib_import_v2.object_store, "get_item_path", files.__getitem__)
    return files


def _assert_no_import_side_effects(connection):
    for table in (
        "research_runs",
        "qlib_research_imports",
        "qlib_signal_snapshots",
        "artifact_registry",
        "artifact_lineage_edges",
        "artifact_promotion_events",
    ):
        assert connection.execute(f"select count(*) from {table}").fetchone()[0] == 0, table


def test_validate_v2_bundle_builds_one_release_graph():
    result = validate_payload(_payload())
    assert result["modelReleaseId"] == "model-1"
    assert result["dataReleaseId"] == DATA_RELEASE_ID
    assert result["universeReleaseId"] == UNIVERSE_RELEASE_ID


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


def test_validate_v2_rejects_malformed_release_and_inconsistent_lineage():
    payload = _payload()
    for artifact in payload["artifacts"]:
        artifact["dataReleaseId"] = "ds_" + "G" * 64
    with pytest.raises(ValueError, match="expected ds_<64 lowercase hex>"):
        validate_payload(payload)

    payload = _payload()
    payload["artifacts"][1]["universeReleaseId"] = "universe-2"
    with pytest.raises(ValueError, match="one UniverseRelease"):
        validate_payload(payload)

    payload = _payload(with_source_manifest=True)
    payload["artifacts"][1]["metadata"]["sourceManifestSha256"] = "e" * 64
    with pytest.raises(ValueError, match="one sourceManifestSha256"):
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
    assert event_count == 2


def test_registry_preflight_rejects_cycles_without_writes():
    from app import db as db_module
    from app.services.artifact_registry import register_qlib_artifacts

    db_module.init_db()
    model = _artifact("model-1", "MODEL_RELEASE", parents=["target-1"])
    target = _artifact("target-1", "TARGET_PORTFOLIO", parents=["model-1"])
    with pytest.raises(ValueError, match="cycle"):
        with db_module.db() as connection:
            register_qlib_artifacts(connection, [model, target])
    with db_module.db() as connection:
        _assert_no_import_side_effects(connection)


def test_v2_import_persists_target_artifact_identity(tmp_path, monkeypatch):
    from app import db as db_module
    from app.services import qlib_import_v2

    db_module.init_db()
    with db_module.db() as connection:
        _register_data_release(connection, tmp_path)
    payload = _payload()
    _materialize_payloads(payload, tmp_path, monkeypatch)

    result = qlib_import_v2.import_run(payload)

    with db_module.db() as connection:
        snapshot = connection.execute(
            "select target_artifact_id from qlib_signal_snapshots where id=?", (result["signalSnapshotId"],)
        ).fetchone()
    assert snapshot["target_artifact_id"] == "target-1"


def test_v2_import_rejects_registered_universe_mismatch_before_writes(tmp_path, monkeypatch):
    from app import db as db_module
    from app.services import qlib_import_v2

    db_module.init_db()
    with db_module.db() as connection:
        _register_data_release(connection, tmp_path, universe_release_id="universe-registered")
    payload = _payload(with_source_manifest=True)
    _materialize_payloads(payload, tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="UniverseRelease mismatch"):
        qlib_import_v2.import_run(payload)

    with db_module.db() as connection:
        _assert_no_import_side_effects(connection)


def test_v2_import_rejects_source_manifest_binding_mismatch_before_writes(tmp_path, monkeypatch):
    from app import db as db_module
    from app.services import qlib_import_v2

    db_module.init_db()
    with db_module.db() as connection:
        _register_data_release(connection, tmp_path)
    payload = _payload(with_source_manifest=True)
    _materialize_payloads(payload, tmp_path, monkeypatch, validation_source_sha256="e" * 64)

    with pytest.raises(ValueError, match="sourceManifestSha256"):
        qlib_import_v2.import_run(payload)

    with db_module.db() as connection:
        _assert_no_import_side_effects(connection)


def test_v2_api_rejects_corrupt_bundle_before_registry_or_promotion_side_effects(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import db as db_module
    from app.main import app
    from app.services import qlib_import_v2

    with TestClient(app) as client:
        with db_module.db() as connection:
            _register_data_release(connection, tmp_path)
        payload = _payload(with_source_manifest=True)
        _materialize_payloads(payload, tmp_path, monkeypatch)
        target = next(item for item in payload["artifacts"] if item["artifactType"] == "TARGET_PORTFOLIO")
        target["payloadSha256"] = "f" * 64
        target["payloadRef"]["sha256"] = "f" * 64

        register_called = False
        original_register = qlib_import_v2.artifact_registry.register_qlib_artifacts

        def tracked_register(*args, **kwargs):
            nonlocal register_called
            register_called = True
            return original_register(*args, **kwargs)

        monkeypatch.setattr(qlib_import_v2.artifact_registry, "register_qlib_artifacts", tracked_register)
        response = client.post("/api/research/imports/qlib", json=payload)

    assert response.status_code == 409
    assert "checksum mismatch" in response.text
    assert register_called is False
    with db_module.db() as connection:
        _assert_no_import_side_effects(connection)
