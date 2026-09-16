from __future__ import annotations

from pathlib import Path

from app.main import app
from app.services.integrated_workflow import derive_workflow_snapshot, recovery_decision


ROOT = Path(__file__).resolve().parents[3]


def _preview(*, validation: bool = False) -> dict:
    return {
        "id": "import-1",
        "researchRunId": "research-1",
        "schemaVersion": "2.0",
        "manifestSha256": "a" * 64,
        "dataReleaseId": "ds_" + "b" * 64,
        "latestSignal": {
            "targetArtifactId": "target-1",
            "targetsSha256": "c" * 64,
        },
        "leanValidation": (
            {
                "id": "validation-1",
                "status": "LEAN_VALIDATED",
                "leanBacktestRunId": "backtest-1",
            }
            if validation
            else None
        ),
    }


def _context(status: str, *, deployment_id: str | None = None) -> dict:
    return {
        "artifact": {
            "artifact_id": "target-1",
            "artifact_type": "TARGET_PORTFOLIO",
            "owner": "qlib",
            "promotion_status": status,
            "data_release_id": "ds_" + "b" * 64,
        },
        "paperPromotion": (
            {
                "to_status": "PAPER",
                "evidence": {"paperDeploymentId": deployment_id},
            }
            if deployment_id
            else None
        ),
    }


def _snapshot(preview: dict, context: dict) -> dict:
    return derive_workflow_snapshot(
        preview=preview,
        target_context=context,
        certification={"status": "NOT_CERTIFIED", "certified": False},
        authorization={
            "backtest": {"allowed": True},
            "paper": {"allowed": True},
            "liveTrading": {"allowed": False},
        },
    )


def test_integrated_workflow_derives_existing_owner_stages_without_shadow_state():
    promoted = _snapshot(_preview(), _context("RESEARCH_PROMOTED"))
    assert promoted["stage"] == "LEAN_VALIDATION_REQUIRED"
    assert promoted["nextAction"] == "RUN_OR_ATTACH_LEAN_VALIDATION"
    assert promoted["blockedReasons"][0]["owner"] == "platform"

    validated = _snapshot(_preview(validation=True), _context("LEAN_VALIDATED"))
    assert validated["stage"] == "PAPER_APPROVAL_REQUIRED"
    assert validated["readiness"]["leanValidated"] is True
    assert validated["readiness"]["paperApproved"] is False

    paper = _snapshot(
        _preview(validation=True),
        _context("PAPER", deployment_id="deployment-1"),
    )
    assert paper["stage"] == "PAPER_ACTIVE"
    assert paper["identity"]["deploymentId"] == "deployment-1"
    assert paper["operations"]["directSqlMutationAllowed"] is False
    assert paper["authorization"]["liveTrading"]["allowed"] is False


def test_integrated_workflow_fails_closed_on_validation_promotion_drift():
    drifted = _snapshot(_preview(validation=True), _context("RESEARCH_PROMOTED"))
    assert drifted["stage"] == "REQUIRES_REVIEW"
    assert drifted["readiness"]["requiresReview"] is True
    assert drifted["blockedReasons"][0]["code"] == "validation_promotion_drift"


def test_recovery_contract_is_deterministic_across_kill_and_redelivery_windows():
    uncommitted = recovery_decision(
        db_committed=False,
        message_published=False,
        message_acked=False,
        runner_status="unknown",
        lease_current=False,
    )
    assert uncommitted["decision"] == "RETRY_TRANSACTION"
    assert uncommitted["newLogicalTaskAllowed"] is True

    outbox = recovery_decision(
        db_committed=True,
        message_published=False,
        message_acked=False,
        runner_status="unknown",
        lease_current=False,
    )
    assert outbox["decision"] == "RESUME_OUTBOX"
    assert outbox["reuseLogicalTaskIdentity"] is True
    assert outbox["newLogicalTaskAllowed"] is False

    redelivery = recovery_decision(
        db_committed=True,
        message_published=True,
        message_acked=False,
        runner_status="queued",
        lease_current=True,
    )
    assert redelivery["decision"] == "REDELIVER_SAME_LOGICAL_TASK"
    assert redelivery["reuseLogicalTaskIdentity"] is True
    assert redelivery["newLogicalTaskAllowed"] is False

    completed_before_ack = recovery_decision(
        db_committed=True,
        message_published=True,
        message_acked=False,
        runner_status="completed",
        lease_current=False,
    )
    assert completed_before_ack["decision"] == "RECONCILE_COMPLETED_RESULT"
    assert completed_before_ack["reuseLogicalTaskIdentity"] is True

    assert recovery_decision(
        db_committed=True,
        message_published=True,
        message_acked=True,
        runner_status="running",
        lease_current=False,
    )["decision"] == "REQUIRES_REVIEW"
    assert recovery_decision(
        db_committed=True,
        message_published=True,
        message_acked=True,
        runner_status="completed",
        lease_current=False,
    )["decision"] == "COMPLETE"


def test_integrated_workflow_openapi_surface_has_consistent_operations_and_resume_idempotency():
    schema = app.openapi()
    paths = schema["paths"]
    assert "get" in paths["/api/integrated-workflows/{import_id}/status"]
    assert "get" in paths["/api/integrated-workflows/{import_id}/plan"]
    assert "get" in paths["/api/integrated-workflows/{import_id}/explain"]
    assert "get" in paths["/api/integrated-workflows/compare"]
    resume = paths["/api/integrated-workflows/{import_id}/resume"]["post"]
    parameters = {item["name"]: item for item in resume["parameters"]}
    assert parameters["Idempotency-Key"]["required"] is True


def test_python_sdk_and_cli_are_thin_api_clients_not_canonical_writers():
    sources = [
        ROOT / "sdk" / "python" / "lean_local_platform" / "workflows.py",
        ROOT / "scripts" / "workflowctl.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in sources)
    lowered = text.lower()
    assert "sqlite" not in lowered
    assert "paper_ledger_entries" not in lowered
    assert "artifact_registry" not in lowered
    assert "qlib_lean_validations" not in lowered
    assert "/api/integrated-workflows/" in text
