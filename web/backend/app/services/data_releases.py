from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Mapping

from ..db import db, json_dump, row_to_dict, utc_now


SCHEMA_VERSION = "2.0"
CORE_RESEARCH_COMPONENTS = frozenset(
    {
        "bars",
        "daily_basic",
        "adjustment_factors",
        "corporate_actions",
        "trade_status",
        "limit_prices",
        "st_status",
        "security_master",
        "trading_calendar",
        "pit_universe",
        "pit_fundamentals",
        "benchmark",
    }
)
REQUIRED_RESEARCH_COMPONENTS = CORE_RESEARCH_COMPONENTS
QLIB_RESEARCH_PROFILE = "ashare_qlib_research_v1"
QLIB_RESEARCH_PROFILE_V2 = "ashare_qlib_research_v2"
DATA_RELEASE_PROFILES = {
    "cn-equity-daily-research-v2": CORE_RESEARCH_COMPONENTS,
    QLIB_RESEARCH_PROFILE: CORE_RESEARCH_COMPONENTS | {"qlib_staging", "industry_classification_pit"},
    QLIB_RESEARCH_PROFILE_V2: CORE_RESEARCH_COMPONENTS | {"qlib_staging", "industry_classification_pit"},
}

PROFILE_COMPONENT_SCHEMAS = {
    QLIB_RESEARCH_PROFILE_V2: {
        "pit_fundamentals": "2",
        "industry_classification_pit": "1",
        "qlib_staging": "qlib-staging-v2",
    }
}
def required_components_for_profile(profile: str) -> frozenset[str]:
    if profile not in DATA_RELEASE_PROFILES:
        raise ValueError(f"Unknown DataRelease profile: {profile}")
    return frozenset(DATA_RELEASE_PROFILES[profile])


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inside(root: Path, raw: str | Path) -> Path:
    candidate = Path(raw).expanduser()
    candidate = candidate if candidate.is_absolute() else root / candidate
    if candidate.is_symlink():
        raise ValueError(f"DataRelease source must not be a symlink: {raw}")
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"DataRelease source escapes QUANT_DATA_ROOT: {raw}") from exc
    if not candidate.is_file():
        raise ValueError(f"DataRelease source file is missing: {raw}")
    return candidate


def _coverage(value: object, *, name: str) -> dict[str, str]:
    item = dict(value) if isinstance(value, Mapping) else {}
    start, end = str(item.get("start") or ""), str(item.get("end") or "")
    if not start or not end or end < start:
        raise ValueError(f"{name}.coverage must contain an ordered start/end window")
    return {"start": start, "end": end}


def _prepare_components(
    spec: Mapping[str, Any],
    root: Path,
    required_components: frozenset[str],
) -> list[dict[str, Any]]:
    raw_components = spec.get("components")
    if not isinstance(raw_components, list):
        raise ValueError("DataRelease components must be a list")
    roles = [
        str(item.get("role") or "")
        for item in raw_components
        if isinstance(item, Mapping)
    ]
    if len(roles) != len(set(roles)):
        raise ValueError("DataRelease component roles must be unique")
    missing = sorted(required_components - set(roles))
    if missing:
        raise ValueError(f"DataRelease is missing required components: {missing}")

    components: list[dict[str, Any]] = []
    for raw in raw_components:
        if not isinstance(raw, Mapping):
            raise ValueError("Each DataRelease component must be an object")
        role = str(raw.get("role") or "")
        release_id = str(raw.get("componentReleaseId") or "")
        dataset_key = str(raw.get("datasetKey") or "")
        schema_version = str(raw.get("schemaVersion") or "")
        if not role or not release_id or not dataset_key or not schema_version:
            raise ValueError(
                f"DataRelease component identity is incomplete: {role or '<unknown>'}"
            )
        coverage = _coverage(raw.get("coverage"), name=role)
        raw_files = raw.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise ValueError(f"DataRelease component has no files: {role}")
        files: list[dict[str, Any]] = []
        for index, raw_file in enumerate(raw_files):
            if not isinstance(raw_file, Mapping):
                raise ValueError(f"Invalid DataRelease file in {role}")
            source = _inside(root, str(raw_file.get("path") or ""))
            digest = _sha256_file(source)
            expected = str(raw_file.get("sha256") or "").lower()
            if expected and expected != digest:
                raise ValueError(
                    f"DataRelease source checksum mismatch: {raw_file.get('path')}"
                )
            suffix = source.suffix.lower() or ".bin"
            # Keep frozen paths short enough for Windows checkout and pytest roots.
            # The full digest remains authoritative in the manifest/checksums file.
            relative = Path("components") / role / f"{index:05d}{suffix}"
            files.append(
                {
                    "sourcePath": str(source),
                    "path": relative.as_posix(),
                    "sha256": digest,
                    "sizeBytes": source.stat().st_size,
                    "rowCount": int(raw_file.get("rowCount") or 0),
                }
            )
        identity_files = [
            {key: value for key, value in item.items() if key != "sourcePath"}
            for item in files
        ]
        identity = {
            "role": role,
            "componentReleaseId": release_id,
            "datasetKey": dataset_key,
            "schemaVersion": schema_version,
            "coverage": coverage,
            "files": identity_files,
        }
        components.append(
            {
                **identity,
                "componentSha256": hashlib.sha256(
                    _canonical_bytes(identity)
                ).hexdigest(),
                "_files": files,
            }
        )
    return sorted(components, key=lambda item: item["role"])


def _copy_frozen(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _verify_frozen(release_root: Path, manifest: Mapping[str, Any]) -> None:
    resolved_root = release_root.resolve()
    for component in manifest.get("components") or []:
        for item in component.get("files") or []:
            frozen = (resolved_root / str(item.get("path") or "")).resolve()
            try:
                frozen.relative_to(resolved_root)
            except ValueError as exc:
                raise ValueError(
                    "DataRelease manifest path escapes its release root"
                ) from exc
            if frozen.is_symlink() or not frozen.is_file():
                raise ValueError(
                    f"Frozen DataRelease file is missing or linked: {item.get('path')}"
                )
            if _sha256_file(frozen) != str(item.get("sha256") or ""):
                raise ValueError(
                    f"Frozen DataRelease checksum mismatch: {item.get('path')}"
                )


def _persist(manifest: Mapping[str, Any], manifest_path: Path, *, root: Path) -> None:
    release_id = str(manifest["dataReleaseId"])
    with db() as connection:
        existing = connection.execute(
            "select * from data_releases where id=?", (release_id,)
        ).fetchone()
        if existing:
            if str(existing["manifest_sha256"]) != str(manifest["manifestSha256"]):
                raise ValueError(
                    "DataRelease ID already exists with a different manifest"
                )
            return
        coverage = manifest["coverage"]
        connection.execute(
            """insert into data_releases
               (id,schema_version,profile,asset_class,market,universe,benchmark,coverage_start,
                coverage_end,as_of_time,identity_sha256,manifest_sha256,manifest_path,status,created_at)
               values (?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?)""",
            (
                release_id,
                manifest["schemaVersion"],
                manifest["profile"],
                manifest["assetClass"],
                manifest["market"],
                manifest["universe"],
                manifest["benchmark"],
                coverage["start"],
                coverage["end"],
                manifest["asOfTime"],
                manifest["identitySha256"],
                manifest["manifestSha256"],
                manifest_path.resolve().relative_to(root).as_posix(),
                utc_now(),
            ),
        )
        for component in manifest["components"]:
            connection.execute(
                """insert into data_release_components
                   (data_release_id,role,component_release_id,dataset_key,schema_version,
                    coverage_start,coverage_end,file_count,row_count,component_sha256,component_json)
                   values (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    release_id,
                    component["role"],
                    component["componentReleaseId"],
                    component["datasetKey"],
                    component["schemaVersion"],
                    component["coverage"]["start"],
                    component["coverage"]["end"],
                    len(component["files"]),
                    sum(int(item.get("rowCount") or 0) for item in component["files"]),
                    component["componentSha256"],
                    json_dump(component),
                ),
            )


def publish_data_release(
    spec: Mapping[str, Any], data_root: str | Path, *, persist: bool = True
) -> dict[str, Any]:
    """Freeze a complete research dataset into an immutable shared-filesystem release."""

    root = Path(data_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    coverage = _coverage(spec.get("coverage"), name="release")
    profile = str(spec.get("profile") or "")
    required = {
        "profile": profile,
        "assetClass": str(spec.get("assetClass") or ""),
        "market": str(spec.get("market") or ""),
        "universe": str(spec.get("universe") or ""),
        "benchmark": str(spec.get("benchmark") or ""),
        "asOfTime": str(spec.get("asOfTime") or ""),
    }
    if any(not value for value in required.values()):
        raise ValueError(
            "DataRelease profile, scope, benchmark and asOfTime are required"
        )
    required_components = required_components_for_profile(profile)
    components = _prepare_components(spec, root, required_components)
    expected_schemas = PROFILE_COMPONENT_SCHEMAS.get(profile, {})
    schema_drift = {
        str(component["role"]): {
            "expected": expected_schemas[str(component["role"])],
            "actual": str(component["schemaVersion"]),
        }
        for component in components
        if str(component["role"]) in expected_schemas
        and str(component["schemaVersion"]) != expected_schemas[str(component["role"]) ]
    }
    if schema_drift:
        raise ValueError(f"DataRelease profile component schema mismatch: {schema_drift}")
    public_components = [
        {key: value for key, value in item.items() if key != "_files"}
        for item in components
    ]
    identity = {
        "schemaVersion": SCHEMA_VERSION,
        **required,
        "coverage": coverage,
        "requiredComponents": sorted(required_components),
        "components": public_components,
        "policies": dict(spec.get("policies") or {}),
        "lineage": dict(spec.get("lineage") or {}),
    }
    identity_sha = hashlib.sha256(_canonical_bytes(identity)).hexdigest()
    release_id = f"ds_{identity_sha}"
    releases = root / "releases"
    target = releases / release_id
    if target.exists():
        existing = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        if existing.get("identitySha256") != identity_sha:
            raise ValueError("Existing DataRelease directory has a different identity")
        _verify_frozen(target, existing)
        if persist:
            _persist(existing, target / "manifest.json", root=root)
        return existing

    staging = releases / ".staging" / uuid.uuid4().hex[:12]
    try:
        for component in components:
            for item in component["_files"]:
                destination = staging / item["path"]
                _copy_frozen(Path(item["sourcePath"]), destination)
                if _sha256_file(destination) != item["sha256"]:
                    raise ValueError(
                        f"Frozen DataRelease checksum mismatch: {item['path']}"
                    )
        manifest: dict[str, Any] = {
            **identity,
            "dataReleaseId": release_id,
            "identitySha256": identity_sha,
            "publishedAt": utc_now(),
        }
        manifest["manifestSha256"] = hashlib.sha256(
            _canonical_bytes(manifest)
        ).hexdigest()
        checksums = {
            "schemaVersion": SCHEMA_VERSION,
            "dataReleaseId": release_id,
            "manifestSha256": manifest["manifestSha256"],
            "files": {
                item["path"]: item["sha256"]
                for component in public_components
                for item in component["files"]
            },
        }
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        (staging / "checksums.json").write_text(
            json.dumps(checksums, ensure_ascii=False, sort_keys=True, indent=2),
            encoding="utf-8",
        )
        (staging / "lineage.json").write_text(
            json.dumps(
                manifest["lineage"], ensure_ascii=False, sort_keys=True, indent=2
            ),
            encoding="utf-8",
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if persist:
        _persist(manifest, target / "manifest.json", root=root)
    return manifest


def get_data_release(release_id: str) -> dict[str, Any] | None:
    with db() as connection:
        row = connection.execute(
            "select * from data_releases where id=?", (release_id,)
        ).fetchone()
    return row_to_dict(row)


