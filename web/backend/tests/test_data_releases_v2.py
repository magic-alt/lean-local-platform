from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.services.data_releases import (
    QLIB_RESEARCH_PROFILE,
    QLIB_RESEARCH_PROFILE_V2,
    REQUIRED_RESEARCH_COMPONENTS,
    publish_data_release,
    required_components_for_profile,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _spec(root: Path) -> dict[str, object]:
    components = []
    for role in sorted(REQUIRED_RESEARCH_COMPONENTS):
        path = root / "canonical" / f"{role}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"role": role}), encoding="utf-8")
        components.append(
            {
                "role": role,
                "componentReleaseId": f"component:{role}:1",
                "datasetKey": role,
                "schemaVersion": "1",
                "coverage": {"start": "2020-01-01", "end": "2026-08-13"},
                "files": [
                    {
                        "path": path.relative_to(root).as_posix(),
                        "sha256": _sha(path),
                        "rowCount": 1,
                    }
                ],
            }
        )
    return {
        "profile": "cn-equity-daily-research-v2",
        "assetClass": "equity",
        "market": "china",
        "universe": "CSI300",
        "benchmark": "SH000300",
        "coverage": {"start": "2020-01-01", "end": "2026-08-13"},
        "asOfTime": "2026-08-14T00:00:00+08:00",
        "policies": {"adjustment": "raw+factor", "pit": "announce_date"},
        "lineage": {"parentIngestionBatches": ["batch-1"]},
        "components": components,
    }


def test_publish_complete_release_is_deterministic_and_immutable(tmp_path: Path):
    spec = _spec(tmp_path)
    first = publish_data_release(spec, tmp_path, persist=False)
    second = publish_data_release(spec, tmp_path, persist=False)
    assert first["dataReleaseId"] == second["dataReleaseId"]
    release_root = tmp_path / "releases" / first["dataReleaseId"]
    frozen = release_root / first["components"][0]["files"][0]["path"]
    before = frozen.read_bytes()
    source = tmp_path / "canonical" / f"{first['components'][0]['role']}.json"
    source.write_text("changed", encoding="utf-8")
    assert frozen.read_bytes() == before
    assert json.loads((release_root / "manifest.json").read_text(encoding="utf-8"))[
        "manifestSha256"
    ]


def test_publish_detects_corrupt_frozen_release(tmp_path: Path):
    spec = _spec(tmp_path)
    manifest = publish_data_release(spec, tmp_path, persist=False)
    release_root = tmp_path / "releases" / manifest["dataReleaseId"]
    frozen = release_root / manifest["components"][0]["files"][0]["path"]
    frozen.write_text("corrupt", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen DataRelease checksum mismatch"):
        publish_data_release(spec, tmp_path, persist=False)


def test_publish_rejects_missing_component_and_checksum_mismatch(tmp_path: Path):
    spec = _spec(tmp_path)
    spec["components"] = list(spec["components"])[1:]
    with pytest.raises(ValueError, match="missing required components"):
        publish_data_release(spec, tmp_path, persist=False)

    spec = _spec(tmp_path)
    spec["components"][0]["files"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum mismatch"):
        publish_data_release(spec, tmp_path, persist=False)


def test_publish_rejects_source_outside_shared_root(tmp_path: Path):
    spec = _spec(tmp_path)
    spec["components"][0]["files"][0]["path"] = "../outside.parquet"
    with pytest.raises(ValueError, match="escapes QUANT_DATA_ROOT"):
        publish_data_release(spec, tmp_path, persist=False)


def test_qlib_profile_requires_staging_and_pit_industry(tmp_path: Path):
    spec = _spec(tmp_path)
    spec["profile"] = QLIB_RESEARCH_PROFILE
    with pytest.raises(ValueError, match="industry_classification_pit"):
        publish_data_release(spec, tmp_path, persist=False)
    for role in sorted(
        required_components_for_profile(QLIB_RESEARCH_PROFILE)
        - REQUIRED_RESEARCH_COMPONENTS
    ):
        path = tmp_path / "canonical" / f"{role}.json"
        path.write_text(json.dumps({"role": role}), encoding="utf-8")
        spec["components"].append(
            {
                "role": role,
                "componentReleaseId": f"component:{role}:1",
                "datasetKey": role,
                "schemaVersion": "1",
                "coverage": spec["coverage"],
                "files": [
                    {
                        "path": path.relative_to(tmp_path).as_posix(),
                        "sha256": _sha(path),
                        "rowCount": 1,
                    }
                ],
            }
        )
    assert (
        publish_data_release(spec, tmp_path, persist=False)["profile"]
        == QLIB_RESEARCH_PROFILE
    )


def test_phase2_qlib_profile_requires_staging_and_pit_industry(tmp_path: Path):
    spec = _spec(tmp_path)
    spec["profile"] = QLIB_RESEARCH_PROFILE_V2
    with pytest.raises(ValueError, match="industry_classification_pit"):
        publish_data_release(spec, tmp_path, persist=False)

    for role, schema_version in {
        "qlib_staging": "qlib-staging-v2",
        "industry_classification_pit": "1",
    }.items():
        path = tmp_path / "canonical" / f"{role}.json"
        path.write_text(json.dumps({"role": role}), encoding="utf-8")
        spec["components"].append(
            {
                "role": role,
                "componentReleaseId": f"component:{role}:1",
                "datasetKey": role,
                "schemaVersion": schema_version,
                "coverage": spec["coverage"],
                "files": [{"path": path.relative_to(tmp_path).as_posix(), "sha256": _sha(path)}],
            }
        )
    pit = next(item for item in spec["components"] if item["role"] == "pit_fundamentals")
    pit["schemaVersion"] = "2"
    assert publish_data_release(spec, tmp_path, persist=False)["profile"] == QLIB_RESEARCH_PROFILE_V2


def test_phase2_profile_rejects_legacy_pit_component_schema(tmp_path: Path):
    spec = _spec(tmp_path)
    spec["profile"] = QLIB_RESEARCH_PROFILE_V2
    for role in ("qlib_staging", "industry_classification_pit"):
        path = tmp_path / "canonical" / f"{role}.json"
        path.write_text(json.dumps({"role": role}), encoding="utf-8")
        spec["components"].append(
            {
                "role": role,
                "componentReleaseId": f"component:{role}:1",
                "datasetKey": role,
                "schemaVersion": "1",
                "coverage": spec["coverage"],
                "files": [{"path": path.relative_to(tmp_path).as_posix(), "sha256": _sha(path)}],
            }
        )
    with pytest.raises(ValueError, match="component schema mismatch"):
        publish_data_release(spec, tmp_path, persist=False)
