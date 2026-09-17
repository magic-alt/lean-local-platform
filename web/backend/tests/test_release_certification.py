from __future__ import annotations

import json
from pathlib import Path

from app.services.certification_status import certification_status
from scripts import build_fault_matrix, release_certification


GIT_SHA = "a" * 40
MIGRATION_SHA = "b" * 64
OPENAPI_SHA = "c" * 64
FRONTEND_SHA = "d" * 64
DATA_MANIFEST_SHA = "e" * 64


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _policy(tmp_path: Path) -> Path:
    (tmp_path / "lock.txt").write_text("locked\n", encoding="utf-8")
    return _write(
        tmp_path / "policy.json",
        {
            "schemaVersion": 1,
            "policyId": "test-policy",
            "minimumPaperObservationCalendarDays": 21,
            "minimumExternalWebhookObservationHours": 24,
            "sourceLocks": ["lock.txt"],
            "profiles": {
                "backtest": {
                    "requiredEvidence": [
                        "releaseConvergence",
                        "localDataCertification",
                        "restoreDrill",
                        "faultMatrix",
                        "supplyChain",
                    ]
                },
                "paper": {
                    "requiredEvidence": [
                        "releaseConvergence",
                        "localDataCertification",
                        "restoreDrill",
                        "faultMatrix",
                        "supplyChain",
                        "paperSoak",
                        "externalWebhook",
                    ]
                },
            },
            "runtimes": {
                "linux-docker": {"requiresWindowsCertificate": False},
                "windows-native": {"requiresWindowsCertificate": True},
            },
            "requiredFaultScenarios": [
                "database_short_disconnect",
                "duplicate_delivery",
            ],
        },
    )


def _evidence(tmp_path: Path) -> dict[str, Path]:
    convergence = {
        "schemaVersion": 2,
        "passed": True,
        "managedStack": True,
        "health": {
            "database": {"engine": "postgresql", "status": "ready"},
            "broker": {"engine": "rabbitmq", "status": "ready"},
            "release": {
                "releaseId": "release-test",
                "gitSha": GIT_SHA,
                "schema": {
                    "aligned": True,
                    "latestAppliedMigration": "pg_0042",
                    "latestAppliedMigrationChecksum": MIGRATION_SHA,
                },
                "openApiSha256": OPENAPI_SHA,
                "frontendAssetsSha256": FRONTEND_SHA,
            },
        },
    }
    local_data = {
        "schemaVersion": 2,
        "passed": True,
        "gitSha": GIT_SHA,
        "dataRelease": {
            "passed": True,
            "dataReleaseId": "ds_test",
            "manifestSha256": DATA_MANIFEST_SHA,
        },
        "leanSmoke": {"passed": True},
    }
    restore = {
        "schemaVersion": 3,
        "passed": True,
        "status": "RESTORE_DRILL_PASS",
        "databaseEngine": "postgresql",
        "checksumMatch": True,
        "rowCountDiff": 0,
        "gitSha": GIT_SHA,
        "releaseId": "release-test",
        "dataReleaseId": "ds_test",
        "dataReleaseManifestSha256": DATA_MANIFEST_SHA,
        "projectionRebuild": {"mode": "apply", "passed": True},
    }
    fault_matrix = {
        "schemaVersion": 1,
        "status": "passed",
        "passed": True,
        "gitSha": GIT_SHA,
        "releaseGitSha": GIT_SHA,
        "releaseId": "release-test",
        "scenarios": {
            "database_short_disconnect": {
                "passed": True,
                "gitSha": GIT_SHA,
                "releaseGitSha": GIT_SHA,
                "releaseId": "release-test",
                "trace": {"service": "postgres"},
                "invariants": {"stable": True},
            },
            "duplicate_delivery": {
                "passed": True,
                "gitSha": GIT_SHA,
                "releaseGitSha": GIT_SHA,
                "releaseId": "release-test",
                "trace": {"deliveryCount": 2},
                "invariants": {"logicalExecutionCount": 1},
            },
        },
    }
    supply_chain = {"schemaVersion": 1, "status": "passed", "failures": []}
    paper_soak = {
        "schemaVersion": 1,
        "passed": True,
        "evidenceMode": "production_shape_observation",
        "startedAt": "2026-08-01T00:00:00+00:00",
        "completedAt": "2026-08-23T00:00:00+00:00",
        "gitSha": GIT_SHA,
        "releaseId": "release-test",
        "dataReleaseId": "ds_test",
        "ledgerProjection": {"passed": True},
        "interruptionRecovery": {"passed": True},
    }
    external_webhook = {
        "schemaVersion": 1,
        "passed": True,
        "status": "EXTERNAL_WEBHOOK_PASS",
        "thirdPartyCertified": True,
        "observedWindowHours": 24,
        "hasPersistedSuccess": True,
    }
    return {
        "releaseConvergence": _write(tmp_path / "convergence.json", convergence),
        "localDataCertification": _write(tmp_path / "local-data.json", local_data),
        "restoreDrill": _write(tmp_path / "restore.json", restore),
        "faultMatrix": _write(tmp_path / "fault.json", fault_matrix),
        "supplyChain": _write(tmp_path / "supply.json", supply_chain),
        "paperSoak": _write(tmp_path / "soak.json", paper_soak),
        "externalWebhook": _write(tmp_path / "webhook.json", external_webhook),
    }


def _codes(bundle: dict) -> set[str]:
    return {str(item["code"]) for item in bundle.get("blockedReasons") or []}


def test_complete_paper_bundle_can_certify_but_never_enables_live(tmp_path, monkeypatch):
    policy = _policy(tmp_path)
    evidence = _evidence(tmp_path)
    monkeypatch.setattr(release_certification, "_git_sha", lambda _root: GIT_SHA)

    bundle = release_certification.build_bundle(
        root=tmp_path,
        policy_path=policy,
        profile="paper",
        runtime="linux-docker",
        evidence_paths=evidence,
    )

    assert bundle["status"] == "CERTIFIED"
    assert bundle["certified"] is True
    assert bundle["liveActivationAllowed"] is False
    assert bundle["paperObservation"]["observedCalendarDays"] == 22.0


def test_accelerated_paper_replay_cannot_satisfy_real_soak_gate(tmp_path, monkeypatch):
    policy = _policy(tmp_path)
    evidence = _evidence(tmp_path)
    soak = json.loads(evidence["paperSoak"].read_text(encoding="utf-8"))
    soak["evidenceMode"] = "accelerated_replay"
    soak["completedAt"] = "2026-08-01T02:00:00+00:00"
    _write(evidence["paperSoak"], soak)
    monkeypatch.setattr(release_certification, "_git_sha", lambda _root: GIT_SHA)

    bundle = release_certification.build_bundle(
        root=tmp_path,
        policy_path=policy,
        profile="paper",
        runtime="linux-docker",
        evidence_paths=evidence,
    )

    assert bundle["certified"] is False
    assert {"paper_soak_mode_invalid", "paper_soak_too_short"} <= _codes(bundle)


def test_release_identity_drift_invalidates_certification_status(tmp_path):
    bundle = {
        "status": "CERTIFIED",
        "certified": True,
        "policyId": "test-policy",
        "profile": "paper",
        "runtime": "linux-docker",
        "release": {
            "releaseId": "release-test",
            "gitSha": GIT_SHA,
            "migrationRevision": "pg_0042",
            "migrationChecksum": MIGRATION_SHA,
            "openApiSha256": OPENAPI_SHA,
            "frontendAssetsSha256": FRONTEND_SHA,
        },
        "blockedReasons": [],
    }
    bundle_path = _write(tmp_path / "certification.json", bundle)
    current = {
        "releaseId": "release-test",
        "gitSha": "f" * 40,
        "schema": {
            "latestAppliedMigration": "pg_0042",
            "latestAppliedMigrationChecksum": MIGRATION_SHA,
        },
        "openApiSha256": OPENAPI_SHA,
        "frontendAssetsSha256": FRONTEND_SHA,
    }

    status = certification_status(current, bundle_path=bundle_path)

    assert status["certified"] is False
    assert status["status"] == "NOT_CERTIFIED"
    assert any(
        item["code"] == "certification_identity_mismatch"
        and item["detail"].startswith("gitSha:")
        for item in status["blockedReasons"]
    )
    assert status["liveActivationAllowed"] is False


def test_fault_matrix_fails_closed_until_every_required_scenario_has_evidence(tmp_path):
    policy = _write(
        tmp_path / "fault-policy.json",
        {
            "policyId": "fault-test",
            "requiredFaultScenarios": [
                "database_short_disconnect",
                "duplicate_delivery",
            ],
        },
    )
    service = _write(
        tmp_path / "service.json",
        {
            "status": "passed",
            "passed": True,
            "gitSha": GIT_SHA,
            "releaseGitSha": GIT_SHA,
            "releaseId": "release-test",
            "scenarios": {
                "database_short_disconnect": {
                    "passed": True,
                    "trace": {"service": "postgres"},
                    "invariants": {"stable": True},
                }
            },
        },
    )

    blocked = build_fault_matrix.build_matrix(
        policy_path=policy,
        service_restart_path=service,
        scenario_paths=[],
    )
    assert blocked["passed"] is False
    assert blocked["missingScenarios"] == ["duplicate_delivery"]

    duplicate = _write(
        tmp_path / "duplicate.json",
        {
            "passed": True,
            "gitSha": GIT_SHA,
            "releaseId": "release-test",
            "trace": {"deliveries": 2},
            "invariants": {"logicalExecutions": 1},
        },
    )
    passed = build_fault_matrix.build_matrix(
        policy_path=policy,
        service_restart_path=service,
        scenario_paths=[("duplicate_delivery", duplicate)],
    )
    assert passed["passed"] is True
    assert passed["schemaVersion"] == 2
    assert passed["releaseId"] == "release-test"
    assert passed["releaseGitSha"] == GIT_SHA


def test_fault_matrix_rejects_cross_release_and_duplicate_scenario_evidence(tmp_path):
    policy = _write(
        tmp_path / "fault-policy.json",
        {
            "policyId": "fault-test",
            "requiredFaultScenarios": [
                "database_short_disconnect",
                "duplicate_delivery",
            ],
        },
    )
    service = _write(
        tmp_path / "service.json",
        {
            "status": "passed",
            "passed": True,
            "gitSha": GIT_SHA,
            "releaseGitSha": GIT_SHA,
            "releaseId": "release-test",
            "scenarios": {
                "database_short_disconnect": {
                    "passed": True,
                    "trace": {"service": "postgres"},
                    "invariants": {"stable": True},
                }
            },
        },
    )
    stale = _write(
        tmp_path / "stale.json",
        {
            "passed": True,
            "gitSha": "f" * 40,
            "releaseId": "stale-release",
            "trace": {"deliveries": 2},
            "invariants": {"logicalExecutions": 1},
        },
    )
    duplicate = _write(
        tmp_path / "duplicate-service.json",
        {
            "passed": True,
            "gitSha": GIT_SHA,
            "releaseId": "release-test",
            "trace": {"service": "postgres"},
            "invariants": {"stable": True},
        },
    )

    matrix = build_fault_matrix.build_matrix(
        policy_path=policy,
        service_restart_path=service,
        scenario_paths=[
            ("duplicate_delivery", stale),
            ("database_short_disconnect", duplicate),
        ],
    )

    assert matrix["passed"] is False
    assert matrix["duplicateScenarios"] == ["database_short_disconnect"]
    assert any(item["code"] == "identity_mismatch" for item in matrix["identityErrors"])
    assert matrix["scenarios"]["database_short_disconnect"]["source"] == str(service)


def test_release_bundle_rejects_unbound_fault_scenario_identity(tmp_path, monkeypatch):
    policy = _policy(tmp_path)
    evidence = _evidence(tmp_path)
    matrix = json.loads(evidence["faultMatrix"].read_text(encoding="utf-8"))
    matrix["scenarios"]["duplicate_delivery"].pop("releaseId")
    matrix["scenarios"]["duplicate_delivery"]["gitSha"] = "f" * 40
    _write(evidence["faultMatrix"], matrix)
    monkeypatch.setattr(release_certification, "_git_sha", lambda _root: GIT_SHA)

    bundle = release_certification.build_bundle(
        root=tmp_path,
        policy_path=policy,
        profile="backtest",
        runtime="linux-docker",
        evidence_paths=evidence,
    )

    assert bundle["certified"] is False
    assert "fault_scenario_identity_mismatch" in _codes(bundle)
