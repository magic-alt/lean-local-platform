from __future__ import annotations

from pathlib import Path

import pytest

from app.services.data_releases import (
    US_ETF_CERTIFICATION_COMPONENTS,
    US_ETF_CERTIFICATION_PROFILE,
    publish_data_release,
    required_components_for_profile,
)


def _spec(root: Path) -> dict:
    components = []
    for role in sorted(US_ETF_CERTIFICATION_COMPONENTS):
        path = root / "source" / f"{role}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'{{"role":"{role}"}}\n', encoding="utf-8")
        components.append(
            {
                "role": role,
                "componentReleaseId": (
                    "legacy-us-etf-bars-release-v1"
                    if role == "bars"
                    else f"us-etf-{role}-v1"
                ),
                "datasetKey": f"us-etf/{role}",
                "schemaVersion": "1",
                "coverage": {"start": "2020-01-02", "end": "2024-12-31"},
                "files": [{"path": str(path.relative_to(root)), "rowCount": 1}],
            }
        )
    return {
        "profile": US_ETF_CERTIFICATION_PROFILE,
        "assetClass": "equity",
        "market": "usa",
        "universe": "SPY,QQQ,IWM,IEF,GLD",
        "benchmark": "SPY",
        "coverage": {"start": "2020-01-02", "end": "2024-12-31"},
        "asOfTime": "2025-01-02T00:00:00Z",
        "components": components,
        "policies": {
            "normalization": "adjusted",
            "purpose": "etf_execution_certification",
        },
        "lineage": {"owner": "lean-local-platform"},
    }


def test_us_etf_certification_profile_has_execution_components():
    assert required_components_for_profile(US_ETF_CERTIFICATION_PROFILE) == frozenset(
        {
            "bars",
            "adjustment_factors",
            "corporate_actions",
            "security_master",
            "trading_calendar",
            "benchmark",
        }
    )


def test_us_etf_certification_release_publishes_deterministically(tmp_path):
    spec = _spec(tmp_path)
    first = publish_data_release(spec, tmp_path, persist=False)
    second = publish_data_release(spec, tmp_path, persist=False)
    assert first["dataReleaseId"] == second["dataReleaseId"]
    assert first["identitySha256"] == second["identitySha256"]
    assert first["profile"] == US_ETF_CERTIFICATION_PROFILE
    assert first["market"] == "usa"
    assert first["assetClass"] == "equity"
    assert first["requiredComponents"] == sorted(US_ETF_CERTIFICATION_COMPONENTS)
    assert (tmp_path / "releases" / first["dataReleaseId"] / "manifest.json").is_file()


def test_us_etf_certification_release_rejects_missing_adjustment_evidence(tmp_path):
    spec = _spec(tmp_path)
    spec["components"] = [
        item for item in spec["components"] if item["role"] != "adjustment_factors"
    ]
    with pytest.raises(ValueError, match="adjustment_factors"):
        publish_data_release(spec, tmp_path, persist=False)


def test_us_etf_certification_release_rejects_scope_drift(tmp_path):
    spec = _spec(tmp_path)
    spec["market"] = "china"
    with pytest.raises(ValueError, match="profile scope mismatch"):
        publish_data_release(spec, tmp_path, persist=False)
