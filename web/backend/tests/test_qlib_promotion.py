from __future__ import annotations

import pytest


def _target() -> dict[str, object]:
    return {
        "schemaVersion": "2.0",
        "artifactId": "target-1",
        "artifactType": "TARGET_PORTFOLIO",
        "promotionStatus": "RESEARCH_PROMOTED",
        "dataReleaseId": "ds_" + "a" * 64,
        "universeReleaseId": "universe-1",
        "modelReleaseId": "model-1",
        "strategyPolicyId": "policy-1",
        "gitCommit": "abc123",
        "containerDigest": "sha256:" + "b" * 64,
        "asOfTime": "2026-08-14T00:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "currency": "CNY",
        "payloadSha256": "c" * 64,
        "parentArtifactIds": [],
        "payloadRef": {"objectKey": "qlib/target.json", "sha256": "c" * 64, "mediaType": "application/json", "rows": 1},
        "metadata": {},
    }


def test_platform_target_promotion_requires_lean_before_paper():
    from app import db as db_module
    from app.services import artifact_registry

    db_module.init_db()
    with db_module.db() as connection:
        artifact_registry.register_qlib_artifacts(connection, [_target()])
        with pytest.raises(ValueError, match="LEAN_VALIDATED"):
            artifact_registry.promote_target_to_platform_stage(
                connection,
                artifact_id="target-1",
                target_status="PAPER",
                reason="test",
                evidence={},
            )
        artifact_registry.promote_target_to_platform_stage(
            connection,
            artifact_id="target-1",
            target_status="LEAN_VALIDATED",
            reason="test",
            evidence={"leanBacktestRunId": "backtest-1"},
        )
        artifact_registry.promote_target_to_platform_stage(
            connection,
            artifact_id="target-1",
            target_status="PAPER",
            reason="test",
            evidence={"paperDeploymentId": "paper-1"},
        )
        row = connection.execute("select promotion_status from artifact_registry where artifact_id='target-1'").fetchone()
    assert row["promotion_status"] == "PAPER"


def test_platform_cannot_publish_a_non_execution_stage_artifact():
    from app import db as db_module
    from app.services import artifact_registry

    db_module.init_db()
    with db_module.db() as connection:
        with pytest.raises(ValueError, match="platform-owned promotion status"):
            artifact_registry.register_platform_artifact(connection, {**_target(), "artifactId": "validation-1", "promotionStatus": "RESEARCH_PROMOTED"})
