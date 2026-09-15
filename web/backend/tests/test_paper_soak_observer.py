from __future__ import annotations

from argparse import Namespace
from datetime import datetime, timedelta, timezone
import json

from scripts import paper_soak_observer


def _sample(at: datetime, previous: str | None) -> dict:
    body = {
        "observedAt": at.isoformat(),
        "localDate": at.astimezone(paper_soak_observer.SHANGHAI).date().isoformat(),
        "releaseId": "release-test",
        "gitSha": "a" * 40,
        "healthStatus": "ok",
        "database": {"engine": "postgresql", "status": "ready"},
        "broker": {"engine": "rabbitmq", "status": "ready"},
        "cycleCounts": {"total": 1, "active": 0, "completed": 1, "failed": 0},
        "projectionVerification": [{"accountId": "paper-1", "passed": True}],
        "projectionPassed": True,
        "previousSampleSha256": previous,
    }
    return {**body, "sampleSha256": paper_soak_observer._canonical_digest(body)}


def _state(start: datetime, sample_days: list[int]) -> dict:
    samples = []
    previous = None
    for day in sample_days:
        item = _sample(start + timedelta(days=day), previous)
        samples.append(item)
        previous = item["sampleSha256"]
    return {
        "schemaVersion": 1,
        "evidenceMode": "production_shape_observation",
        "startedAt": start.isoformat(),
        "releaseId": "release-test",
        "gitSha": "a" * 40,
        "dataReleaseId": "ds_test",
        "dataReleaseManifestSha256": "b" * 64,
        "accountIds": ["paper-1"],
        "samples": samples,
    }


def _fault_matrix(path):
    path.write_text(
        json.dumps(
            {
                "passed": True,
                "scenarios": {
                    name: {"passed": True}
                    for name in (
                        "database_short_disconnect",
                        "rabbitmq_outage",
                        "worker_crash",
                    )
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_finalize_requires_actual_elapsed_days_and_distinct_observation_dates(tmp_path):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    state_path = tmp_path / "state.json"
    evidence_path = tmp_path / "evidence.json"
    fault_path = _fault_matrix(tmp_path / "fault.json")

    state_path.write_text(json.dumps(_state(start, list(range(1, 22)))), encoding="utf-8")
    result = paper_soak_observer.finalize(
        Namespace(
            state=state_path,
            evidence=evidence_path,
            fault_matrix=fault_path,
            minimum_days=21,
        )
    )

    assert result["passed"] is True
    assert result["evidenceMode"] == "production_shape_observation"
    assert result["observedElapsedDays"] == 21.0
    assert result["observedCalendarDays"] == 21
    assert result["hashChainValid"] is True


def test_same_day_accelerated_samples_do_not_satisfy_soak(tmp_path):
    start = datetime(2026, 8, 1, tzinfo=timezone.utc)
    state_path = tmp_path / "state.json"
    evidence_path = tmp_path / "evidence.json"
    fault_path = _fault_matrix(tmp_path / "fault.json")

    samples = []
    previous = None
    for minute in range(21):
        item = _sample(start + timedelta(minutes=minute), previous)
        samples.append(item)
        previous = item["sampleSha256"]
    state = _state(start, [])
    state["samples"] = samples
    state_path.write_text(json.dumps(state), encoding="utf-8")

    result = paper_soak_observer.finalize(
        Namespace(
            state=state_path,
            evidence=evidence_path,
            fault_matrix=fault_path,
            minimum_days=21,
        )
    )

    assert result["passed"] is False
    assert result["observedElapsedDays"] < 1
    assert result["observedCalendarDays"] == 1
