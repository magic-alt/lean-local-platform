from __future__ import annotations

import json
from pathlib import Path

from app.services.etf_rotation_execution_certification import (
    SCHEMA_VERSION,
    build_execution_certification,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "etf_rotation_execution_certification.v1.json"
)


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _build(payload: dict) -> dict:
    return build_execution_certification(
        data_release_id=payload["dataReleaseId"],
        candidate=payload["candidate"],
        baseline=payload["baseline"],
        walk_forward=payload["walkForward"],
        paper=payload["paper"],
        admission=payload["admission"],
        resources=payload["resources"],
        gates=payload["gates"],
        deterministic_fingerprints=payload["deterministicFingerprints"],
    )


def test_execution_certification_happy_path_is_deterministic():
    payload = _fixture()
    first = _build(payload)
    second = _build(payload)
    assert first == second
    assert first["schemaVersion"] == SCHEMA_VERSION
    assert first["certified"] is True
    assert first["failureReasons"] == []
    assert first["artifactFingerprint"] == second["artifactFingerprint"]


def test_execution_certification_fails_on_data_release_drift():
    payload = _fixture()
    payload["candidate"]["dataReleaseId"] = "ds_other"
    report = _build(payload)
    assert report["certified"] is False
    assert "candidate_data_release_match" in report["failureReasons"]


def test_execution_certification_fails_on_walk_forward_boundary_leakage():
    payload = _fixture()
    payload["walkForward"]["windows"][0]["validation_start"] = "2020-12-15"
    report = _build(payload)
    assert report["certified"] is False
    check = next(
        item for item in report["checks"] if item["name"] == "walk_forward_complete"
    )
    assert "walk_forward_fold_1_window_order" in check["details"]["failureReasons"]


def test_execution_certification_fails_when_rejected_intent_has_fill():
    payload = _fixture()
    payload["paper"]["fills"].append(
        {"id": "fill-bad", "intent_id": "intent-reject"}
    )
    payload["paper"]["ledgerEntries"].extend(
        [
            {"id": "l4", "fill_id": "fill-bad"},
            {"id": "l5", "fill_id": "fill-bad"},
            {"id": "l6", "fill_id": "fill-bad"},
        ]
    )
    report = _build(payload)
    assert report["certified"] is False
    check = next(
        item
        for item in report["checks"]
        if item["name"] == "paper_execution_chain_complete"
    )
    assert (
        "paper_intent_intent-reject_rejection_has_fill"
        in check["details"]["failureReasons"]
    )


def test_execution_certification_fails_when_fill_has_no_complete_ledger():
    payload = _fixture()
    payload["paper"]["ledgerEntries"] = payload["paper"]["ledgerEntries"][:2]
    report = _build(payload)
    assert report["certified"] is False
    check = next(
        item
        for item in report["checks"]
        if item["name"] == "paper_execution_chain_complete"
    )
    assert "paper_fill_fill-1_ledger_incomplete" in check["details"]["failureReasons"]


def test_execution_certification_fails_without_worker_constraint_decision():
    payload = _fixture()
    payload["paper"]["constraintDecisions"] = [
        item
        for item in payload["paper"]["constraintDecisions"]
        if item["intent_id"] != "intent-buy"
    ]
    report = _build(payload)
    assert report["certified"] is False
    check = next(
        item
        for item in report["checks"]
        if item["name"] == "paper_execution_chain_complete"
    )
    assert (
        "paper_intent_intent-buy_constraint_decision_missing"
        in check["details"]["failureReasons"]
    )


def test_execution_certification_requires_idempotency_evidence():
    payload = _fixture()
    payload["paper"].pop("idempotency")
    report = _build(payload)
    assert report["certified"] is False
    check = next(
        item
        for item in report["checks"]
        if item["name"] == "paper_execution_chain_complete"
    )
    assert "ledger_idempotency_evidence_missing" in check["details"]["failureReasons"]


def test_execution_certification_requires_runtime_cpu_and_rss():
    payload = _fixture()
    payload["resources"]["before"]["memory"].pop("processRssBytes")
    payload["resources"]["after"]["memory"].pop("processRssBytes")
    payload["resources"]["before"]["cpu"] = {}
    payload["resources"]["after"]["cpu"] = {}
    report = _build(payload)
    assert report["certified"] is False
    check = next(
        item for item in report["checks"] if item["name"] == "resource_evidence_complete"
    )
    assert "resource_memory_evidence_incomplete" in check["details"]["failureReasons"]
    assert "resource_cpu_evidence_incomplete" in check["details"]["failureReasons"]


def test_execution_certification_requires_admission():
    payload = _fixture()
    payload["admission"]["stage"] = "baseline_registered"
    report = _build(payload)
    assert report["certified"] is False
    assert "admission_passed" in report["failureReasons"]


def test_execution_certification_requires_complete_cost_attribution():
    payload = _fixture()
    payload["candidate"]["costAttribution"]["slippage"] = None
    payload["candidate"]["costAttribution"]["complete"] = False
    report = _build(payload)
    assert report["certified"] is False
    assert "candidate_cost_attribution_complete" in report["failureReasons"]
