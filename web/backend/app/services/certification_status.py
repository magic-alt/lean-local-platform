from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
DEFAULT_BUNDLE = ROOT / "web" / "runtime" / "audit" / "release-certification.json"


def certification_bundle_path() -> Path:
    configured = os.environ.get("LEAN_CERTIFICATION_BUNDLE_PATH", "").strip()
    return Path(configured).expanduser().resolve() if configured else DEFAULT_BUNDLE


def _blocked(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def _identity_mismatches(bundle: dict[str, Any], current_release: dict[str, Any]) -> list[dict[str, str]]:
    certified_release = bundle.get("release") or {}
    schema = current_release.get("schema") or {}
    expected = {
        "releaseId": current_release.get("releaseId"),
        "gitSha": current_release.get("gitSha"),
        "migrationRevision": schema.get("latestAppliedMigration"),
        "migrationChecksum": schema.get("latestAppliedMigrationChecksum"),
        "openApiSha256": current_release.get("openApiSha256"),
        "frontendAssetsSha256": current_release.get("frontendAssetsSha256"),
    }
    mismatches: list[dict[str, str]] = []
    for field, current_value in expected.items():
        certified_value = certified_release.get(field)
        if not current_value or certified_value != current_value:
            mismatches.append(
                _blocked(
                    "certification_identity_mismatch",
                    f"{field}:current={current_value or 'missing'},certified={certified_value or 'missing'}",
                )
            )
    return mismatches


def certification_status(current_release: dict[str, Any], *, bundle_path: Path | None = None) -> dict[str, Any]:
    path = (bundle_path or certification_bundle_path()).expanduser().resolve()
    if not path.is_file():
        return {
            "status": "NOT_CERTIFIED",
            "certified": False,
            "liveActivationAllowed": False,
            "bundlePath": str(path),
            "profile": None,
            "runtime": None,
            "blockedReasons": [_blocked("certification_bundle_missing", str(path))],
            "currentRelease": current_release,
        }
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        return {
            "status": "NOT_CERTIFIED",
            "certified": False,
            "liveActivationAllowed": False,
            "bundlePath": str(path),
            "profile": None,
            "runtime": None,
            "blockedReasons": [
                _blocked("certification_bundle_invalid", type(exc).__name__)
            ],
            "currentRelease": current_release,
        }
    if not isinstance(loaded, dict):
        return {
            "status": "NOT_CERTIFIED",
            "certified": False,
            "liveActivationAllowed": False,
            "bundlePath": str(path),
            "profile": None,
            "runtime": None,
            "blockedReasons": [_blocked("certification_bundle_invalid", "root_not_object")],
            "currentRelease": current_release,
        }

    reasons = [
        item
        for item in (loaded.get("blockedReasons") or [])
        if isinstance(item, dict) and item.get("code")
    ]
    identity_mismatches = _identity_mismatches(loaded, current_release)
    reasons.extend(identity_mismatches)
    certified = bool(
        loaded.get("certified")
        and str(loaded.get("status") or "") == "CERTIFIED"
        and not reasons
    )
    return {
        "status": "CERTIFIED" if certified else "NOT_CERTIFIED",
        "certified": certified,
        "liveActivationAllowed": False,
        "bundlePath": str(path),
        "policyId": loaded.get("policyId"),
        "profile": loaded.get("profile"),
        "runtime": loaded.get("runtime"),
        "generatedAt": loaded.get("generatedAt"),
        "blockedReasons": reasons,
        "certifiedRelease": loaded.get("release") or {},
        "certifiedDataRelease": loaded.get("dataRelease") or {},
        "currentRelease": current_release,
    }


def authorization_status() -> dict[str, Any]:
    return {
        "backtest": {"allowed": True},
        "paper": {"allowed": True, "subjectToOperationalGates": True},
        "production": {
            "allowed": False,
            "reason": "production_activation_not_implemented",
        },
        "liveTrading": {
            "allowed": False,
            "reason": "live_broker_writes_disabled",
        },
        "p9": {
            "allowed": False,
            "reason": "p9_activation_disabled",
        },
    }
