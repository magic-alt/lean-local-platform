from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from ..db import db, json_dump, row_to_dict, utc_now
from ..repositories.backtest_repository import get_backtest
from . import artifact_registry, object_store


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _target_context(research_run_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute(
            """
            select signal.*, imported.data_release_id, imported.model_fingerprint,
                   artifact.promotion_status, artifact.strategy_policy_id, artifact.universe_release_id
            from qlib_signal_snapshots signal
            join qlib_research_imports imported on imported.id=signal.import_id
            left join artifact_registry artifact on artifact.artifact_id=signal.target_artifact_id
            where signal.research_run_id=?
            order by signal.created_at desc limit 1
            """,
            (research_run_id,),
        ).fetchone()
    item = row_to_dict(row)
    if not item:
        raise KeyError(f"Qlib signal snapshot not found for research run: {research_run_id}")
    if not item.get("target_artifact_id"):
        raise ValueError("Qlib import predates Artifact Contract v2 target binding; re-import the v2 bundle")
    if not item.get("promotion_status"):
        raise ValueError("Qlib TargetPortfolio artifact is not registered")
    return item


def validation_draft(research_run_id: str, *, data_scope: dict[str, Any]) -> dict[str, Any]:
    target = _target_context(research_run_id)
    if target["promotion_status"] != "RESEARCH_PROMOTED":
        raise ValueError("Qlib TargetPortfolio must be RESEARCH_PROMOTED before LEAN validation")
    return {
        "sourceResearchRunId": research_run_id,
        "targetPortfolioArtifactId": target["target_artifact_id"],
        "dataReleaseId": target["data_release_id"],
        "modelReleaseId": target["model_fingerprint"],
        "targetsSha256": target["targets_sha256"],
        "dataScope": data_scope,
        "target": "backtest",
        "strategyRequired": True,
        "preflightRequired": True,
        "requiredBindings": {
            "dataReleaseId": target["data_release_id"],
            "qlibTargetPortfolioArtifactId": target["target_artifact_id"],
            "qlibTargetsSha256": target["targets_sha256"],
        },
        "note": "LEAN validation is fail-closed: its completed run must retain this DataRelease and TargetPortfolio hash.",
    }


def _assert_lean_backtest(target: dict[str, Any], lean_backtest_run_id: str) -> dict[str, Any]:
    backtest = get_backtest(lean_backtest_run_id)
    if not backtest:
        raise KeyError(f"LEAN backtest not found: {lean_backtest_run_id}")
    if str(backtest.get("status")) not in {"success", "succeeded"}:
        raise ValueError("LEAN validation requires a successful LEAN backtest")
    if str(backtest.get("data_release_id") or "") != str(target["data_release_id"]):
        raise ValueError("LEAN validation DataRelease does not match the Qlib TargetPortfolio")
    parameters = dict(backtest.get("parameters") or {})
    if str(parameters.get("qlibTargetPortfolioArtifactId") or "") != str(target["target_artifact_id"]):
        raise ValueError("LEAN backtest is not bound to the Qlib TargetPortfolio artifact")
    if str(parameters.get("qlibTargetsSha256") or "") != str(target["targets_sha256"]):
        raise ValueError("LEAN backtest target hash does not match the imported TargetPortfolio")
    if not bool((backtest.get("validation") or {}).get("passed")):
        raise ValueError("LEAN validation requires a passed execution-validation gate")
    return backtest


def record_lean_validation(research_run_id: str, *, lean_backtest_run_id: str) -> dict[str, Any]:
    target = _target_context(research_run_id)
    with db() as connection:
        existing = connection.execute(
            """select * from qlib_lean_validations
               where target_artifact_id=? and lean_backtest_run_id=?""",
            (target["target_artifact_id"], lean_backtest_run_id),
        ).fetchone()
    existing_item = row_to_dict(existing)
    if existing_item:
        return {"validationId": existing_item["id"], "replayed": True, "status": existing_item["status"]}
    if target["promotion_status"] != "RESEARCH_PROMOTED":
        raise ValueError("Qlib TargetPortfolio must be RESEARCH_PROMOTED before LEAN validation")
    backtest = _assert_lean_backtest(target, lean_backtest_run_id)
    validation_id = str(uuid.uuid4())
    validation_artifact_id = f"lean_validation_{validation_id}"
    evidence = {
        "schemaVersion": "2.0",
        "kind": "LEAN_VALIDATION_RESULT",
        "validationId": validation_id,
        "researchRunId": research_run_id,
        "leanBacktestRunId": lean_backtest_run_id,
        "targetPortfolioArtifactId": target["target_artifact_id"],
        "dataReleaseId": target["data_release_id"],
        "modelReleaseId": target["model_fingerprint"],
        "targetsSha256": target["targets_sha256"],
        "executionValidation": backtest.get("validation") or {},
        "backtestFingerprint": backtest.get("fingerprint") or {},
    }
    raw = _canonical_json(evidence).encode("utf-8")
    payload_sha256 = hashlib.sha256(raw).hexdigest()
    object_key = f"artifacts/platform/lean-validation/{validation_id}.json"
    object_store.put_item(object_key, raw)
    artifact = {
        "schemaVersion": "2.0",
        "artifactId": validation_artifact_id,
        "artifactType": "VALIDATION_RESULT",
        "promotionStatus": "LEAN_VALIDATED",
        "dataReleaseId": target["data_release_id"],
        "universeReleaseId": target.get("universe_release_id"),
        "modelReleaseId": target["model_fingerprint"],
        "strategyPolicyId": target.get("strategy_policy_id"),
        "gitCommit": str((backtest.get("fingerprint") or {}).get("gitCommit") or "platform-control-plane"),
        "containerDigest": str(backtest.get("docker_image") or "lean-container-unresolved"),
        "asOfTime": utc_now(),
        "timezone": "Asia/Shanghai",
        "currency": "CNY",
        "payloadSha256": payload_sha256,
        "payloadRef": {"objectKey": object_key, "sha256": payload_sha256, "mediaType": "application/json", "rows": 1},
        "metadata": {"leanBacktestRunId": lean_backtest_run_id, "targetsSha256": target["targets_sha256"]},
    }
    with db() as connection:
        artifact_registry.register_platform_artifact(connection, artifact)
        connection.execute(
            """insert into artifact_lineage_edges (parent_artifact_id,child_artifact_id,created_at)
               values (?,?,?) on conflict(parent_artifact_id,child_artifact_id) do nothing""",
            (target["target_artifact_id"], validation_artifact_id, utc_now()),
        )
        artifact_registry.promote_target_to_platform_stage(
            connection,
            artifact_id=str(target["target_artifact_id"]),
            target_status="LEAN_VALIDATED",
            reason="authoritative_lean_validation",
            evidence={"validationArtifactId": validation_artifact_id, "leanBacktestRunId": lean_backtest_run_id},
        )
        connection.execute(
            """insert into qlib_lean_validations
               (id,research_run_id,signal_snapshot_id,target_artifact_id,validation_artifact_id,data_release_id,
                model_release_id,lean_backtest_run_id,targets_sha256,status,evidence_json,created_at)
               values (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                validation_id, research_run_id, target["id"], target["target_artifact_id"], validation_artifact_id,
                target["data_release_id"], target["model_fingerprint"], lean_backtest_run_id,
                target["targets_sha256"], "LEAN_VALIDATED", json_dump(evidence), utc_now(),
            ),
        )
    return {"validationId": validation_id, "validationArtifactId": validation_artifact_id, "replayed": False, "status": "LEAN_VALIDATED"}


def assert_paper_eligible(
    lean_backtest_run_id: str, *, parameters: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    if parameters is None:
        backtest = get_backtest(lean_backtest_run_id)
        if not backtest:
            raise KeyError(f"LEAN backtest not found: {lean_backtest_run_id}")
        parameters = dict(backtest.get("parameters") or {})
    target_id = str(parameters.get("qlibTargetPortfolioArtifactId") or "")
    if not target_id:
        return None
    with db() as connection:
        validation = connection.execute(
            """select * from qlib_lean_validations
               where target_artifact_id=? and lean_backtest_run_id=? and status='LEAN_VALIDATED'""",
            (target_id, lean_backtest_run_id),
        ).fetchone()
        artifact = connection.execute(
            "select promotion_status from artifact_registry where artifact_id=?", (target_id,)
        ).fetchone()
    if not validation or not artifact or artifact["promotion_status"] not in {"LEAN_VALIDATED", "PAPER"}:
        raise ValueError("Qlib TargetPortfolio must pass recorded LEAN validation before Paper deployment")
    return row_to_dict(validation)


def mark_paper_started(
    lean_backtest_run_id: str, *, deployment_id: str, parameters: dict[str, Any] | None = None
) -> None:
    validation = assert_paper_eligible(lean_backtest_run_id, parameters=parameters)
    if not validation:
        return
    with db() as connection:
        artifact_registry.promote_target_to_platform_stage(
            connection,
            artifact_id=str(validation["target_artifact_id"]),
            target_status="PAPER",
            reason="paper_deployment_created",
            evidence={"paperDeploymentId": deployment_id, "leanBacktestRunId": lean_backtest_run_id},
        )
