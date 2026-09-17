from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.error

import pytest

from scripts import run_post_migration_certification_campaign as campaign


GIT_SHA = "a" * 40
MANIFEST_SHA = "b" * 64


def _config(tmp_path: Path) -> dict:
    return {
        "schemaVersion": 1,
        "campaignId": "campaign-test",
        "expectedGitSha": GIT_SHA,
        "expectedReleaseId": "release-test",
        "dataReleaseId": "data-release-test",
        "dataReleaseManifestSha256": MANIFEST_SHA,
        "paperAccountIds": ["paper-1"],
        "apiUrl": "http://127.0.0.1:8000",
        "campaignRoot": str(tmp_path / "campaign"),
        "deployment": {
            "runtime": "linux-docker",
            "profile": "full",
            "composeProject": "lean-platform",
        },
        "restore": {"targetPrefix": "lean_restore_issue61_test"},
        "observation": {
            "webhookHours": 24,
            "webhookPollSeconds": 300,
            "paperDays": 21,
            "paperSampleSeconds": 21600,
            "loopSeconds": 60,
        },
        "evidence": {
            "releaseConvergence": str(tmp_path / "release.json"),
            "localDataCertification": str(tmp_path / "data.json"),
            "supplyChain": str(tmp_path / "supply.json"),
            "scenarioEvidence": {},
        },
    }


def test_campaign_config_enforces_real_windows_and_forbids_secret_material(tmp_path):
    config = _config(tmp_path)
    assert campaign._validate_config(config) is config

    too_short = json.loads(json.dumps(config))
    too_short["observation"]["webhookHours"] = 23.99
    with pytest.raises(ValueError, match="at_least_24_hours"):
        campaign._validate_config(too_short)

    secret = json.loads(json.dumps(config))
    secret["webhookUrl"] = "https://example.test/private-token"
    with pytest.raises(ValueError, match="secret_material_forbidden"):
        campaign._validate_config(secret)

    wrong_runtime = json.loads(json.dumps(config))
    wrong_runtime["deployment"]["runtime"] = "windows-native"
    with pytest.raises(ValueError, match="requires_linux_docker"):
        campaign._validate_config(wrong_runtime)


def test_paper_finalize_requires_elapsed_time_and_distinct_dates(tmp_path):
    config = _config(tmp_path)
    paths = campaign._campaign_paths(config)
    paths["paperState"].parent.mkdir(parents=True, exist_ok=True)
    started = datetime(2026, 8, 1, tzinfo=timezone.utc)
    samples = [
        {
            "observedAt": (started + timedelta(days=day)).isoformat(),
            "localDate": (started + timedelta(days=day)).date().isoformat(),
        }
        for day in range(1, 22)
    ]
    paths["paperState"].write_text(
        json.dumps({"startedAt": started.isoformat(), "samples": samples}),
        encoding="utf-8",
    )
    assert campaign._paper_ready_to_finalize(config, paths) is True

    same_day = [
        {
            "observedAt": (started + timedelta(minutes=minute)).isoformat(),
            "localDate": started.date().isoformat(),
        }
        for minute in range(21)
    ]
    paths["paperState"].write_text(
        json.dumps({"startedAt": started.isoformat(), "samples": same_day}),
        encoding="utf-8",
    )
    assert campaign._paper_ready_to_finalize(config, paths) is False


def test_interrupted_mutating_step_requires_manual_new_campaign():
    state = {
        "steps": {
            "restoreDrill": {"status": "RUNNING"},
            "externalWebhook": {"status": "RUNNING", "pid": 123},
        },
        "events": [],
    }
    campaign._recover_interrupted(state)
    assert state["steps"]["restoreDrill"]["status"] == "INDETERMINATE"
    assert state["steps"]["externalWebhook"]["status"] == "RUNNING"


def test_unavailable_runtime_waits_without_starting_side_effects(tmp_path, monkeypatch):
    config = _config(tmp_path)
    config_path = tmp_path / "config.json"
    state_path = tmp_path / "state.json"
    campaign._write(config_path, config)
    state = campaign._new_state(config_path, config)

    monkeypatch.setattr(
        campaign,
        "_health",
        lambda _url: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    campaign._tick(config, state, state_path)

    persisted = campaign._load(state_path)
    assert persisted["status"] == "WAITING_PREREQUISITES"
    assert persisted["blockers"][0]["code"] == "api_health_unavailable"
    assert persisted["steps"] == {}


def test_campaign_lock_rejects_a_second_live_owner(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    lock_path = state_path.with_suffix(".json.lock")
    lock_path.write_text("123\n", encoding="utf-8")
    monkeypatch.setattr(campaign, "_process_running", lambda pid: pid == 123)

    with pytest.raises(RuntimeError, match="campaign_already_running:123"):
        campaign._acquire_lock(state_path)
