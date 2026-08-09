import pytest

from app.services.research_runs import _validate_qlib_payload


def payload():
    return {
        "schemaVersion": "1.0",
        "externalRunId": "run-1",
        "runKind": "walk_forward",
        "dataset": {"fingerprint": "dataset-1", "universe": "CSI300"},
        "model": {"fingerprint": "model-1"},
        "folds": [],
        "execution": {"dealPrice": "open", "signalLagDays": 1},
        "metrics": {"returnTotal": 0.1},
        "artifacts": [],
        "latestTargets": {
            "signalDate": "2026-08-04",
            "tradeDate": "2026-08-05",
            "targets": [
                {"instrument": "SH600000", "targetWeight": 0.5, "score": 1.0},
                {"instrument": "SZ000001", "targetWeight": 0.5, "score": 0.5},
            ],
        },
    }


def test_validate_qlib_payload_is_canonical_and_bounded():
    result = _validate_qlib_payload(payload())
    assert result["grossExposure"] == 1.0
    assert len(result["targetsSha256"]) == 64
    assert result["targets"][0]["instrument"] == "SH600000"


def test_validate_qlib_payload_rejects_same_day_execution():
    item = payload()
    item["latestTargets"]["tradeDate"] = item["latestTargets"]["signalDate"]
    with pytest.raises(ValueError, match="must be after"):
        _validate_qlib_payload(item)
