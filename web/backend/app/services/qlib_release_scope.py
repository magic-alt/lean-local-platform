from __future__ import annotations

from typing import Any, Mapping

from ..core.errors import LeanWebError
from ..db import db
from .data_releases import get_data_release


class QlibReleaseScopeError(LeanWebError, ValueError):
    status_code = 409
    error_code = "QLIB_RELEASE_SCOPE_MISMATCH"
    category = "state"


def _target_artifact(artifact_id: str) -> dict[str, Any]:
    with db() as connection:
        row = connection.execute(
            """select artifact_id,artifact_type,owner,promotion_status,data_release_id
               from artifact_registry where artifact_id=?""",
            (artifact_id,),
        ).fetchone()
    if not row:
        raise QlibReleaseScopeError(f"Qlib target artifact is not registered: {artifact_id}")
    artifact = {
        key: row[key]
        for key in (
            "artifact_id",
            "artifact_type",
            "owner",
            "promotion_status",
            "data_release_id",
        )
    }
    if artifact["artifact_type"] != "TARGET_PORTFOLIO" or artifact["owner"] != "qlib":
        raise QlibReleaseScopeError(
            "Qlib validation requires a registered Qlib TARGET_PORTFOLIO artifact"
        )
    if artifact["promotion_status"] != "RESEARCH_PROMOTED":
        raise QlibReleaseScopeError(
            "Qlib validation requires a RESEARCH_PROMOTED TARGET_PORTFOLIO artifact"
        )
    return artifact


def assert_qlib_release_scope(parameters: Mapping[str, Any]) -> dict[str, Any] | None:
    """Fail closed when a Qlib-bound backtest escapes its frozen DataRelease scope."""

    target_artifact_id = str(parameters.get("qlibTargetPortfolioArtifactId") or "").strip()
    if not target_artifact_id:
        return None

    release_id = str(parameters.get("dataReleaseId") or "").strip()
    if not release_id:
        raise QlibReleaseScopeError("Qlib validation requires a bound DataRelease")
    release = get_data_release(release_id)
    if not release:
        raise QlibReleaseScopeError(f"Qlib DataRelease is not registered: {release_id}")
    if str(release.get("status") or "") != "active":
        raise QlibReleaseScopeError(f"Qlib DataRelease is not active: {release_id}")

    artifact = _target_artifact(target_artifact_id)
    artifact_release_id = str(artifact.get("data_release_id") or "")
    if artifact_release_id != release_id:
        raise QlibReleaseScopeError(
            "Qlib target artifact/DataRelease mismatch: "
            f"artifact={artifact_release_id or 'missing'}, requested={release_id}"
        )

    asset_class = str(parameters.get("assetClass") or "").lower()
    market = str(parameters.get("market") or parameters.get("venue") or "").lower()
    release_asset = str(release.get("asset_class") or "").lower()
    release_market = str(release.get("market") or "").lower()
    if asset_class != release_asset:
        raise QlibReleaseScopeError(
            f"Qlib DataRelease asset class mismatch: release={release_asset}, requested={asset_class or 'missing'}"
        )
    if market != release_market:
        raise QlibReleaseScopeError(
            f"Qlib DataRelease market mismatch: release={release_market}, requested={market or 'missing'}"
        )

    start = str(parameters.get("start") or "")
    end = str(parameters.get("end") or "")
    coverage_start = str(release.get("coverage_start") or "")
    coverage_end = str(release.get("coverage_end") or "")
    if not start or not end:
        raise QlibReleaseScopeError("Qlib validation requires an explicit backtest date window")
    if coverage_start and start < coverage_start:
        raise QlibReleaseScopeError(
            f"Qlib backtest starts before DataRelease coverage: requested={start}, coverage_start={coverage_start}"
        )
    if coverage_end and end > coverage_end:
        raise QlibReleaseScopeError(
            f"Qlib backtest ends after DataRelease coverage: requested={end}, coverage_end={coverage_end}"
        )
    return release
