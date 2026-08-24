from __future__ import annotations

import json


def _write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_windows_certificate_is_bound_to_evidence_host_and_locks(tmp_path, monkeypatch):
    from app.services import windows_certification as certification

    policy = tmp_path / "policy.json"
    requirements = tmp_path / "requirements.lock"
    runtime_lock = tmp_path / "lean-native.lock.json"
    certificate = tmp_path / "certificate.json"
    evidence = tmp_path / "evidence.json"
    requirements.write_text("locked", encoding="utf-8")
    runtime_lock.write_text("runtime", encoding="utf-8")
    _write_json(
        policy,
        {
            "schemaVersion": 1,
            "minimumSoakSeconds": 100,
            "maximumCertificateAgeDays": 90,
            "requiredVersionPrefixes": {"postgresql": "17.", "rabbitmq": "4.3.5"},
            "requiredScenarios": ["worker_kill_redelivery", "paper_cycle_idempotency"],
        },
    )
    _write_json(
        evidence,
        {
            "schemaVersion": 1,
            "passed": True,
            "soakSeconds": 100,
            "versions": {"postgresql": "17.11", "rabbitmq": "4.3.5"},
            "scenarios": {"worker_kill_redelivery": True, "paper_cycle_idempotency": True},
        },
    )
    monkeypatch.setattr(certification, "PLATFORM_DIR", tmp_path)
    monkeypatch.setattr(certification, "POLICY_PATH", policy)
    monkeypatch.setattr(certification, "BOUND_FILES", (requirements, runtime_lock, policy))
    monkeypatch.setenv("COMPUTERNAME", "certified-host")

    issued = certification.issue_windows_certificate(evidence, certificate)
    verified = certification.verify_windows_certificate(certificate)

    assert issued["status"] == "WINDOWS_CELERY_CERTIFIED"
    assert verified["ready"] is True

    requirements.write_text("drifted", encoding="utf-8")
    drifted = certification.verify_windows_certificate(certificate)
    assert drifted["ready"] is False
    assert "binding_requirements.lock" in drifted["errors"]


def test_windows_certificate_rejects_missing_fault_scenario(tmp_path, monkeypatch):
    from app.services import windows_certification as certification

    policy = tmp_path / "policy.json"
    evidence = tmp_path / "evidence.json"
    _write_json(
        policy,
        {
            "schemaVersion": 1,
            "minimumSoakSeconds": 10,
            "maximumCertificateAgeDays": 90,
            "requiredVersionPrefixes": {},
            "requiredScenarios": ["broker_restart_recovery"],
        },
    )
    _write_json(
        evidence,
        {
            "schemaVersion": 1,
            "passed": True,
            "soakSeconds": 10,
            "versions": {},
            "scenarios": {},
        },
    )
    monkeypatch.setattr(certification, "POLICY_PATH", policy)

    try:
        certification.issue_windows_certificate(evidence, tmp_path / "certificate.json")
    except RuntimeError as exc:
        assert "scenario_broker_restart_recovery" in str(exc)
    else:
        raise AssertionError("missing fault evidence must fail closed")
