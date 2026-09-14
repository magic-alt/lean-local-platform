from __future__ import annotations

import hashlib
import json

import pytest

from app.services import qlib_import_v2


DATA_RELEASE_ID = "ds_" + "a" * 64
UNIVERSE_RELEASE_ID = "universe-csi300-fixture-v2"
SOURCE_MANIFEST_SHA256 = "d" * 64


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _artifact(
    artifact_type: str,
    payload: object,
    *,
    parents: list[str],
    model_release_id: str | None,
    strategy_policy_id: str | None,
    dated: bool = False,
) -> dict:
    payload_sha = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    identity = {
        "artifactType": artifact_type,
        "promotionStatus": "RESEARCH_PROMOTED",
        "dataReleaseId": DATA_RELEASE_ID,
        "universeReleaseId": UNIVERSE_RELEASE_ID,
        "sourceManifestSha256": SOURCE_MANIFEST_SHA256,
        "payloadSha256": payload_sha,
        "parentArtifactIds": parents,
        "modelReleaseId": model_release_id,
        "strategyPolicyId": strategy_policy_id,
    }
    artifact_id = "art_" + hashlib.sha256(_canonical(identity).encode()).hexdigest()
    artifact = {
        "schemaVersion": "2.0",
        "artifactId": artifact_id,
        "artifactType": artifact_type,
        "promotionStatus": "RESEARCH_PROMOTED",
        "dataReleaseId": DATA_RELEASE_ID,
        "universeReleaseId": UNIVERSE_RELEASE_ID,
        "modelReleaseId": model_release_id,
        "strategyPolicyId": strategy_policy_id,
        "gitCommit": "fixture",
        "containerDigest": "sha256:" + "b" * 64,
        "asOfTime": "2026-08-14T00:00:00+08:00",
        "signalDate": "2026-08-13" if dated else None,
        "tradeDate": "2026-08-14" if dated else None,
        "timezone": "Asia/Shanghai",
        "currency": "CNY",
        "payloadSha256": payload_sha,
        "parentArtifactIds": parents,
        "payloadRef": {
            "objectKey": f"qlib/fixture/{artifact_id}.json",
            "sha256": payload_sha,
            "mediaType": "application/json",
            "rows": 1,
        },
        "metadata": {"sourceManifestSha256": SOURCE_MANIFEST_SHA256},
    }
    if artifact_type == "MODEL_RELEASE":
        artifact["modelReleaseId"] = artifact_id
    if artifact_type == "STRATEGY_POLICY":
        artifact["strategyPolicyId"] = artifact_id
    return artifact


def _bundle() -> dict:
    model = _artifact("MODEL_RELEASE", {"model": "fixture"}, parents=[], model_release_id=None, strategy_policy_id=None)
    policy = _artifact(
        "STRATEGY_POLICY",
        {"topk": 30},
        parents=[model["artifactId"]],
        model_release_id=model["artifactId"],
        strategy_policy_id=None,
    )
    signal = _artifact(
        "SIGNAL_SNAPSHOT",
        {"signals": [{"instrument": "SH600000", "score": 0.8}]},
        parents=[model["artifactId"], policy["artifactId"]],
        model_release_id=model["artifactId"],
        strategy_policy_id=policy["artifactId"],
        dated=True,
    )
    target = _artifact(
        "TARGET_PORTFOLIO",
        {"targets": [{"instrument": "SH600000", "targetWeight": 0.1, "score": 0.8}]},
        parents=[signal["artifactId"], policy["artifactId"]],
        model_release_id=model["artifactId"],
        strategy_policy_id=policy["artifactId"],
        dated=True,
    )
    validation = _artifact(
        "VALIDATION_RESULT",
        {"sourceManifestSha256": SOURCE_MANIFEST_SHA256},
        parents=[target["artifactId"]],
        model_release_id=model["artifactId"],
        strategy_policy_id=policy["artifactId"],
    )
    return {
        "schemaVersion": "2.0",
        "importType": "QLIB_RESEARCH_BUNDLE",
        "externalRunId": "consumer-semantics-fixture",
        "runKind": "walk_forward",
        "rootArtifactIds": [validation["artifactId"]],
        "artifacts": [model, policy, signal, target, validation],
    }


def test_lineage_bound_bundle_requires_frozen_content_addressed_graph():
    bundle = _bundle()
    result = qlib_import_v2.validate_payload(bundle)
    assert len(result["artifacts"]) == 5
    assert result["sourceManifestSha256"] == SOURCE_MANIFEST_SHA256

    tampered = _bundle()
    tampered["artifacts"][3]["parentArtifactIds"] = [tampered["artifacts"][0]["artifactId"]]
    with pytest.raises(ValueError, match="parent chain mismatch"):
        qlib_import_v2.validate_payload(tampered)

    tampered = _bundle()
    tampered["artifacts"][0]["artifactId"] = "art_" + "f" * 64
    with pytest.raises(ValueError):
        qlib_import_v2.validate_payload(tampered)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_consumer_rejects_nonfinite_target_values(invalid: float):
    with pytest.raises(ValueError, match="Invalid target weight"):
        qlib_import_v2._normalize_targets(
            {"targets": [{"instrument": "SH600000", "targetWeight": invalid, "score": 0.5}]}
        )
    with pytest.raises(ValueError, match="Invalid target score"):
        qlib_import_v2._normalize_targets(
            {"targets": [{"instrument": "SH600000", "targetWeight": 0.1, "score": invalid}]}
        )


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_consumer_rejects_nonfinite_signal_scores(invalid: float):
    with pytest.raises(ValueError, match="Invalid signal score"):
        qlib_import_v2._normalize_signals(
            {"signals": [{"instrument": "SH600000", "score": invalid}]}
        )


def test_consumer_rejects_duplicate_signal_instruments():
    with pytest.raises(ValueError, match="Duplicate Qlib signal instrument"):
        qlib_import_v2._normalize_signals(
            {
                "signals": [
                    {"instrument": "SH600000", "score": 0.8},
                    {"instrument": "sh600000", "score": 0.7},
                ]
            }
        )
