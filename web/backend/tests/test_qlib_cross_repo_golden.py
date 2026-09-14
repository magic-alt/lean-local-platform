from __future__ import annotations

import hashlib
import json
from pathlib import Path


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "qlib_artifact_v2" / "golden_v2"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _register_data_release(connection, tmp_path: Path, *, release_id: str, universe_release_id: str):
    connection.execute(
        """insert into data_releases
           (id,schema_version,profile,asset_class,market,universe,benchmark,coverage_start,coverage_end,
            as_of_time,identity_sha256,manifest_sha256,manifest_path,status,created_at)
           values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            release_id,
            "2.0",
            "research",
            "equity",
            "china",
            "CSI300",
            "000300",
            "2020-01-01",
            "2026-08-13",
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
        "coverage": {"start": "2020-01-01", "end": "2026-08-13"},
        "files": [
            {
                "path": "pit_universe.parquet",
                "sha256": "3" * 64,
                "rowCount": 1,
            }
        ],
    }
    connection.execute(
        """insert into data_release_components
           (data_release_id,role,component_release_id,dataset_key,schema_version,
            coverage_start,coverage_end,file_count,row_count,component_sha256,component_json)
           values (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            release_id,
            "pit_universe",
            universe_release_id,
            "pit_universe",
            "1",
            "2020-01-01",
            "2026-08-13",
            1,
            1,
            "4" * 64,
            json.dumps(component),
        ),
    )


def _fixture():
    lock = json.loads((FIXTURE_ROOT / "fixture.lock.json").read_text(encoding="utf-8"))
    bundle_path = FIXTURE_ROOT / lock["bundlePath"]
    assert _sha256(bundle_path) == lock["bundleSha256"]
    for relative, expected in lock["files"].items():
        assert _sha256(FIXTURE_ROOT / relative) == expected
    return lock, json.loads(bundle_path.read_text(encoding="utf-8"))


def _install_payload_paths(bundle: dict, monkeypatch):
    from app.services import qlib_import_v2

    paths = {}
    for artifact in bundle["artifacts"]:
        object_key = artifact["payloadRef"]["objectKey"]
        path = FIXTURE_ROOT / "payloads" / f"{artifact['artifactId']}.json"
        paths[object_key] = path
    monkeypatch.setattr(qlib_import_v2.object_store, "get_item_path", paths.__getitem__)


def test_qllib_producer_golden_bundle_imports_once_and_validation_is_idempotent(
    tmp_path,
    monkeypatch,
):
    from fastapi.testclient import TestClient

    from app import db as db_module
    from app.main import app
    from app.services import qlib_promotion

    lock, bundle = _fixture()
    assert lock["producerRepository"] == "magic-alt/qlib-platform"
    assert lock["producerBaselineCommit"] == "2c896093c34289e91860807cce88a61ec41473ec"

    _install_payload_paths(bundle, monkeypatch)

    with TestClient(app) as client:
        with db_module.db() as connection:
            _register_data_release(
                connection,
                tmp_path,
                release_id=lock["dataReleaseId"],
                universe_release_id=lock["universeReleaseId"],
            )

        first = client.post("/api/research/imports/qlib", json=bundle)
        second = client.post("/api/research/imports/qlib", json=bundle)

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        first_import = first.json()
        second_import = second.json()
        assert first_import["replayed"] is False
        assert second_import["replayed"] is True
        assert second_import["researchRunId"] == first_import["researchRunId"]
        assert second_import["importId"] == first_import["importId"]
        assert second_import["signalSnapshotId"] == first_import["signalSnapshotId"]

        with db_module.db() as connection:
            snapshot = connection.execute(
                "select * from qlib_signal_snapshots where id=?",
                (first_import["signalSnapshotId"],),
            ).fetchone()

        target_id = str(snapshot["target_artifact_id"])
        targets_sha256 = str(snapshot["targets_sha256"])
        fake_backtest = {
            "id": "golden-backtest-1",
            "status": "success",
            "data_release_id": lock["dataReleaseId"],
            "parameters": {
                "qlibTargetPortfolioArtifactId": target_id,
                "qlibTargetsSha256": targets_sha256,
            },
            "validation": {"passed": True},
            "fingerprint": {
                "gitCommit": "lean-golden-fixture",
                "executionBackend": "native",
                "runtimeIdentity": {
                    "artifactSha256": "f" * 64,
                    "runtimeId": "lean-native-golden",
                },
            },
            "execution_backend": "native",
        }
        monkeypatch.setattr(
            qlib_promotion,
            "get_backtest",
            lambda run_id: fake_backtest if run_id == "golden-backtest-1" else None,
        )

        validation_url = (
            f"/api/research/runs/{first_import['researchRunId']}/lean-validation"
        )
        first_validation = client.post(
            validation_url,
            json={"leanBacktestRunId": "golden-backtest-1"},
        )
        second_validation = client.post(
            validation_url,
            json={"leanBacktestRunId": "golden-backtest-1"},
        )

        assert first_validation.status_code == 200, first_validation.text
        assert second_validation.status_code == 200, second_validation.text
        first_validation_body = first_validation.json()
        second_validation_body = second_validation.json()
        assert first_validation_body["replayed"] is False
        assert second_validation_body["replayed"] is True
        assert (
            second_validation_body["validationId"]
            == first_validation_body["validationId"]
        )

    with db_module.db() as connection:
        counts = {
            table: connection.execute(f"select count(*) from {table}").fetchone()[0]
            for table in (
                "research_runs",
                "qlib_research_imports",
                "qlib_signal_snapshots",
                "qlib_lean_validations",
                "artifact_registry",
                "artifact_lineage_edges",
                "artifact_promotion_events",
            )
        }
        target = connection.execute(
            "select promotion_status from artifact_registry where artifact_id=?",
            (target_id,),
        ).fetchone()

    assert counts == {
        "research_runs": 1,
        "qlib_research_imports": 1,
        "qlib_signal_snapshots": 1,
        "qlib_lean_validations": 1,
        "artifact_registry": 6,
        "artifact_lineage_edges": 7,
        "artifact_promotion_events": 7,
    }
    assert target["promotion_status"] == "LEAN_VALIDATED"
