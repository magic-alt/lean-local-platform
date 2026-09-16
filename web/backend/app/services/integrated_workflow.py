from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Mapping

from ..db import db, row_to_dict
from . import research_interop
from .certification_status import authorization_status, certification_status
from .release_identity import runtime_release_identity


SCHEMA_VERSION = "1.0"
_WORKFLOW_NAMESPACE = uuid.UUID("e0f7b49f-fd75-4ddf-9014-7aaf76a6263e")


def _json(value: Any, fallback: Any) -> Any:
    if value in (None, ""):
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _blocked(code: str, detail: str, *, owner: str) -> dict[str, str]:
    return {"code": code, "detail": detail, "owner": owner}


def _stable_correlation(import_id: str) -> str:
    return str(uuid.uuid5(_WORKFLOW_NAMESPACE, f"qlib-import:{import_id}"))


def _contract_hash(*parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _target_context(target_artifact_id: str) -> dict[str, Any]:
    with db() as connection:
        artifact = connection.execute(
            """select artifact_id,artifact_type,owner,promotion_status,data_release_id,
                      universe_release_id,model_release_id,strategy_policy_id,payload_sha256
               from artifact_registry where artifact_id=?""",
            (target_artifact_id,),
        ).fetchone()
        promotion = connection.execute(
            """select from_status,to_status,reason,evidence_json,created_at
               from artifact_promotion_events
               where artifact_id=? and to_status='PAPER'
               order by created_at desc,id desc limit 1""",
            (target_artifact_id,),
        ).fetchone()
    item = row_to_dict(artifact)
    if not item:
        raise ValueError("integrated_workflow_target_artifact_missing")
    event = row_to_dict(promotion) or {}
    event["evidence"] = _json(event.pop("evidence_json", None), {})
    return {"artifact": item, "paperPromotion": event or None}


def _certification_view() -> dict[str, Any]:
    current = runtime_release_identity()
    status = certification_status(current)
    return {
        "status": status.get("status"),
        "certified": bool(status.get("certified")),
        "profile": status.get("profile"),
        "runtime": status.get("runtime"),
        "blockedReasons": list(status.get("blockedReasons") or []),
        "liveActivationAllowed": bool(status.get("liveActivationAllowed")),
    }


def _stage_for(
    preview: Mapping[str, Any],
    artifact: Mapping[str, Any] | None,
) -> tuple[str, list[dict[str, str]], str]:
    signal = preview.get("latestSignal") if isinstance(preview.get("latestSignal"), Mapping) else None
    validation = preview.get("leanValidation") if isinstance(preview.get("leanValidation"), Mapping) else None
    if not signal:
        return (
            "ARTIFACT_RECEIVED",
            [_blocked("target_portfolio_missing", "The imported bundle has no dispatchable TargetPortfolio.", owner="qlib-platform")],
            "WAIT_FOR_TARGET_PORTFOLIO",
        )
    if not artifact:
        return (
            "REQUIRES_REVIEW",
            [_blocked("target_registry_missing", "The TargetPortfolio identity is absent from the platform registry.", owner="platform")],
            "REVIEW_LINEAGE",
        )
    if artifact.get("artifact_type") != "TARGET_PORTFOLIO" or artifact.get("owner") != "qlib":
        return (
            "REQUIRES_REVIEW",
            [_blocked("target_identity_invalid", "The execution target is not a Qlib-owned TargetPortfolio.", owner="platform")],
            "REVIEW_LINEAGE",
        )

    promotion = str(artifact.get("promotion_status") or "")
    if promotion in {"CANDIDATE", "RESEARCH_REVIEW"}:
        return (
            "RESEARCH_REVIEW",
            [_blocked("research_promotion_required", "Qlib must explicitly promote the TargetPortfolio before LEAN validation.", owner="qlib-platform")],
            "WAIT_FOR_RESEARCH_PROMOTION",
        )
    if promotion == "RESEARCH_PROMOTED":
        if validation:
            return (
                "REQUIRES_REVIEW",
                [_blocked("validation_promotion_drift", "LEAN validation exists but the target did not advance to LEAN_VALIDATED.", owner="platform")],
                "REVIEW_VALIDATION_STATE",
            )
        return (
            "LEAN_VALIDATION_REQUIRED",
            [_blocked("lean_validation_required", "An authoritative, target-bound LEAN validation has not been recorded.", owner="platform")],
            "RUN_OR_ATTACH_LEAN_VALIDATION",
        )
    if promotion == "LEAN_VALIDATED":
        if not validation or str(validation.get("status") or "") != "LEAN_VALIDATED":
            return (
                "REQUIRES_REVIEW",
                [_blocked("validation_evidence_missing", "The target is LEAN_VALIDATED without matching validation evidence.", owner="platform")],
                "REVIEW_VALIDATION_STATE",
            )
        return (
            "PAPER_APPROVAL_REQUIRED",
            [_blocked("explicit_paper_approval_required", "Paper requires an explicit platform-owned approval/deployment action.", owner="platform")],
            "APPROVE_PAPER_EXPLICITLY",
        )
    if promotion == "PAPER":
        return "PAPER_ACTIVE", [], "OBSERVE_AND_RECONCILE"
    if promotion == "REJECTED":
        return (
            "REJECTED",
            [_blocked("research_artifact_rejected", "The Qlib TargetPortfolio is rejected and cannot enter execution validation.", owner="qlib-platform")],
            "NONE",
        )
    return (
        "REQUIRES_REVIEW",
        [_blocked("unknown_promotion_status", f"Unsupported promotion status: {promotion or 'missing'}", owner="platform")],
        "REVIEW_LINEAGE",
    )


def derive_workflow_snapshot(
    *,
    preview: Mapping[str, Any],
    target_context: Mapping[str, Any] | None,
    certification: Mapping[str, Any],
    authorization: Mapping[str, Any],
) -> dict[str, Any]:
    """Project canonical facts into one read-only cross-platform workflow contract.

    This function deliberately owns no state transition. Qlib artifacts, LEAN
    validation and Paper remain owned by their existing writers.
    """

    import_id = str(preview.get("id") or "")
    research_run_id = str(preview.get("researchRunId") or "")
    signal = preview.get("latestSignal") if isinstance(preview.get("latestSignal"), Mapping) else {}
    validation = preview.get("leanValidation") if isinstance(preview.get("leanValidation"), Mapping) else {}
    artifact = target_context.get("artifact") if isinstance(target_context, Mapping) else None
    paper_promotion = target_context.get("paperPromotion") if isinstance(target_context, Mapping) else None
    paper_evidence = paper_promotion.get("evidence") if isinstance(paper_promotion, Mapping) else {}

    stage, blockers, next_action = _stage_for(preview, artifact if isinstance(artifact, Mapping) else None)
    target_id = str(signal.get("targetArtifactId") or "") or None
    target_sha = str(signal.get("targetsSha256") or "") or None
    manifest_sha = str(preview.get("manifestSha256") or "") or None
    data_release_id = str(preview.get("dataReleaseId") or "") or None
    workflow_id = f"qlib-import:{import_id}"
    correlation_id = _stable_correlation(import_id)
    input_hash = _contract_hash(
        preview.get("schemaVersion"), manifest_sha, data_release_id, target_id, target_sha
    )
    deployment_id = (
        str(paper_evidence.get("paperDeploymentId") or "") or None
        if isinstance(paper_evidence, Mapping)
        else None
    )

    steps = [
        {"stage": "ARTIFACT_RECEIVED", "owner": "platform", "state": "complete"},
        {"stage": "INTEGRITY_VERIFIED", "owner": "platform", "state": "complete"},
        {
            "stage": "LEAN_VALIDATION",
            "owner": "platform",
            "state": "complete" if str((artifact or {}).get("promotion_status") or "") in {"LEAN_VALIDATED", "PAPER"} else "pending",
        },
        {
            "stage": "PAPER_APPROVAL",
            "owner": "platform",
            "state": "complete" if str((artifact or {}).get("promotion_status") or "") == "PAPER" else "pending",
        },
        {
            "stage": "RECONCILIATION",
            "owner": "platform",
            "state": "active" if stage == "PAPER_ACTIVE" else "pending",
        },
    ]

    return {
        "schemaVersion": SCHEMA_VERSION,
        "workflowId": workflow_id,
        "correlationId": correlation_id,
        "stage": stage,
        "nextAction": next_action,
        "blockedReasons": blockers,
        "identity": {
            "researchRunId": research_run_id or None,
            "dataReleaseId": data_release_id,
            "artifactId": target_id,
            "validationRunId": str(validation.get("id") or "") or None,
            "leanBacktestRunId": str(validation.get("leanBacktestRunId") or "") or None,
            "deploymentId": deployment_id,
            "cycleId": None,
            "inputHash": input_hash,
            "manifestSha256": manifest_sha,
            "targetsSha256": target_sha,
        },
        "readiness": {
            "integrityVerified": True,
            "leanValidated": str((artifact or {}).get("promotion_status") or "") in {"LEAN_VALIDATED", "PAPER"},
            "paperApproved": str((artifact or {}).get("promotion_status") or "") == "PAPER",
            "requiresReview": stage == "REQUIRES_REVIEW",
        },
        "certification": dict(certification),
        "authorization": dict(authorization),
        "steps": steps,
        "operations": {
            "plan": "read_only",
            "status": "read_only",
            "resume": "delegates_to_existing_owner",
            "explain": "read_only",
            "compare": "read_only",
            "mutationsRequireIdempotencyKey": True,
            "directSqlMutationAllowed": False,
        },
    }


def workflow_status(import_id: str) -> dict[str, Any]:
    preview = research_interop.get_import(import_id)
    signal = preview.get("latestSignal") if isinstance(preview.get("latestSignal"), Mapping) else {}
    target_id = str(signal.get("targetArtifactId") or "")
    context = _target_context(target_id) if target_id else None
    return derive_workflow_snapshot(
        preview=preview,
        target_context=context,
        certification=_certification_view(),
        authorization=authorization_status(),
    )


def workflow_plan(import_id: str) -> dict[str, Any]:
    status = workflow_status(import_id)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "workflowId": status["workflowId"],
        "correlationId": status["correlationId"],
        "inputHash": status["identity"]["inputHash"],
        "stage": status["stage"],
        "nextAction": status["nextAction"],
        "steps": status["steps"],
        "blockedReasons": status["blockedReasons"],
        "writeOwnerPolicy": {
            "artifactRegistry": "artifact_registry",
            "leanValidation": "qlib_promotion",
            "paperLedger": "paper_order_pipeline",
            "scheduler": "existing_platform_scheduler_only",
            "shadowSchedulerAllowed": False,
        },
    }


def workflow_explain(import_id: str) -> dict[str, Any]:
    status = workflow_status(import_id)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "workflowId": status["workflowId"],
        "stage": status["stage"],
        "nextAction": status["nextAction"],
        "blockedReasons": status["blockedReasons"],
        "readiness": status["readiness"],
        "certification": status["certification"],
        "authorization": status["authorization"],
        "identity": status["identity"],
    }


def workflow_compare(left_import_id: str, right_import_id: str) -> dict[str, Any]:
    left = workflow_status(left_import_id)
    right = workflow_status(right_import_id)
    fields = ("dataReleaseId", "artifactId", "manifestSha256", "targetsSha256")
    identity_diff = {
        field: {"left": left["identity"].get(field), "right": right["identity"].get(field)}
        for field in fields
        if left["identity"].get(field) != right["identity"].get(field)
    }
    return {
        "schemaVersion": SCHEMA_VERSION,
        "left": {"workflowId": left["workflowId"], "stage": left["stage"], "identity": left["identity"]},
        "right": {"workflowId": right["workflowId"], "stage": right["stage"], "identity": right["identity"]},
        "sameDataRelease": left["identity"].get("dataReleaseId") == right["identity"].get("dataReleaseId"),
        "sameTarget": left["identity"].get("targetsSha256") == right["identity"].get("targetsSha256"),
        "identityDiff": identity_diff,
    }


def workflow_resume(import_id: str, *, idempotency_key: str) -> dict[str, Any]:
    status = workflow_status(import_id)
    stage = str(status["stage"])
    action = str(status["nextAction"])
    explicit = stage == "PAPER_APPROVAL_REQUIRED"
    requires_review = stage in {"REQUIRES_REVIEW", "REJECTED"}
    owner = "qlib-platform" if stage in {"RESEARCH_REVIEW", "ARTIFACT_RECEIVED"} else "platform"
    return {
        "schemaVersion": SCHEMA_VERSION,
        "workflowId": status["workflowId"],
        "correlationId": status["correlationId"],
        "idempotencyKey": idempotency_key,
        "inputHash": status["identity"]["inputHash"],
        "stage": stage,
        "decision": action,
        "owner": owner,
        "dispatched": False,
        "requiresExplicitApproval": explicit,
        "requiresReview": requires_review,
        "reason": (
            "Resume is a command contract only; the existing domain owner must perform any state transition."
        ),
    }


def recovery_decision(
    *,
    db_committed: bool,
    message_published: bool,
    message_acked: bool,
    runner_status: str,
    lease_current: bool,
) -> dict[str, Any]:
    """Classify one crash/re-delivery checkpoint without creating side effects."""

    normalized = str(runner_status or "unknown").strip().lower()
    completed = normalized in {"succeeded", "success", "completed"}
    if not db_committed:
        decision = "RETRY_TRANSACTION"
    elif not message_published:
        decision = "RESUME_OUTBOX"
    elif not message_acked and completed:
        decision = "RECONCILE_COMPLETED_RESULT"
    elif not message_acked:
        decision = "REDELIVER_SAME_LOGICAL_TASK"
    elif completed:
        decision = "COMPLETE"
    elif normalized in {"failed", "cancelled", "canceled"}:
        decision = "TERMINAL"
    elif normalized in {"queued", "running"} and lease_current:
        decision = "WAIT_FOR_EXISTING_WORK"
    else:
        decision = "REQUIRES_REVIEW"
    return {
        "decision": decision,
        "newLogicalTaskAllowed": decision == "RETRY_TRANSACTION",
        "reuseLogicalTaskIdentity": decision in {
            "RESUME_OUTBOX",
            "RECONCILE_COMPLETED_RESULT",
            "REDELIVER_SAME_LOGICAL_TASK",
            "WAIT_FOR_EXISTING_WORK",
        },
        "requiresReview": decision == "REQUIRES_REVIEW",
    }
